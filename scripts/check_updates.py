"""slot-toolbox.com の天井期待値ページの「新規追加」と「既存機種の出典更新」を検出する。

AIを使わない決定的なスクリプト。毎週月曜の自動メンテ(docs/AUTO_UPDATE.md)の入口。

やること:
  1. slot-toolbox.com のサイトマップ(sitemap_index.xml → post-sitemap*.xml)だけを取得し、
     URLが「-tenjo/」で終わるページとその lastmod(最終更新日時)を集める。
  2. profiles/*.yaml の本文(ヘッダーコメント含む)に書かれた slot-toolbox.com のURLを
     「その機種の出典」として集める。
  3. data/update_state.json(前回チェック時の記録)と比べて、
       - まだ見たことのない天井ページ(=新機種の候補)
       - 出典ページの lastmod が前回から変わったもの
     を見つける。新機種候補のページだけは <title> を取るために本体HTMLを取得する(2秒間隔)。
  4. 1geki.jp の新台カレンダー(今月・来月)からスロットの機種名と導入日を拾い、参考に載せる。
  5. reports/update_YYYY-MM-DD.md にレポートを書き、1行の要約を表示する。

終了コード: 0=変化なし / 10=何か見つかった / 1=エラー(状態ファイルは書きかえない)

使い方:
    python scripts/check_updates.py                 # 検出してレポートを書く(状態は保存しない)
    python scripts/check_updates.py --dry-run       # 同上(明示)
    python scripts/check_updates.py --update-state  # 検出後、状態ファイルを保存する
    python scripts/check_updates.py --update-state --defer magia-record-tenjo
        # 今回は見送る候補(1回4機種の上限超え等)は --defer で「未確認」のまま残す(複数可)

状態ファイルが無い初回の --update-state は「基準作り」だけを行う:
  lastmod が21日より前の天井ページは「見たことがある」扱いで保存し、
  21日以内のものは未確認のまま残す(=次回以降も新機種候補として出る)。
"""
from __future__ import annotations

import argparse
import difflib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = ROOT / "profiles"
STATE_PATH = ROOT / "data" / "update_state.json"
REPORTS_DIR = ROOT / "reports"

SITEMAP_INDEX = "https://slot-toolbox.com/sitemap_index.xml"
CALENDAR_URL = "https://1geki.jp/newmachinecalender/{yyyymm}/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) slot-evassist-update-check/1.0"
REQUEST_DELAY_SEC = 2.0
TIMEOUT_SEC = 30
RETRIES = 2
INITIAL_RECENT_DAYS = 21
MAX_TITLE_FETCH = 12  # 新機種候補のタイトル取得は最大この件数まで(礼儀として抑える)

JST = timezone(timedelta(hours=9))
SM_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
TOOLBOX_URL_RE = re.compile(r"https://slot-toolbox\.com/[A-Za-z0-9\-_/]+")
TENJO_RE = re.compile(r"^https://slot-toolbox\.com/([a-z0-9\-]+)-tenjo/$")

# 出典URLには書かれていないが、すでにプロファイルがある機種のスラッグ(URLの名前部分)。
# ここに載っている天井ページは「新機種候補」ではなく「既存機種(別サイト出典)」として扱う。
# 例: https://slot-toolbox.com/kanokari-tenjo/ → スラッグ "kanokari"
SLUG_ALIASES: dict[str, str] = {
    "kanokari": "kanojo_okarishimasu",
    "monkey-turn5": "monkey_turn_v",
    "lycoris-recoil": "lycoris_recoil",
    "sao2": "sao2",
    "jormungand": "jormungand",
    "fire-force2": "fire_force2",
    "enen2": "fire_force2",
}


class FetchError(Exception):
    pass


# ---------------------------------------------------------------------------
# 通信
# ---------------------------------------------------------------------------
_last_request_at = 0.0


def fetch(url: str) -> str:
    """URLを取得して文字列で返す。リクエスト間は REQUEST_DELAY_SEC 秒あける。"""
    global _last_request_at
    last_exc: Exception | None = None
    for attempt in range(RETRIES + 1):
        wait = REQUEST_DELAY_SEC - (time.monotonic() - _last_request_at)
        if wait > 0:
            time.sleep(wait)
        _last_request_at = time.monotonic()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "ja"})
            with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
                charset = resp.headers.get_content_charset() or "utf-8"
                return resp.read().decode(charset, errors="replace")
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_exc = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code in (403, 404, 410):
                break  # 再試行しても変わらない
            time.sleep(REQUEST_DELAY_SEC * (attempt + 1))
    raise FetchError(f"{url}: {last_exc}")


# ---------------------------------------------------------------------------
# slot-toolbox サイトマップ
# ---------------------------------------------------------------------------
def parse_lastmod(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_post_sitemap_entries() -> dict[str, str]:
    """投稿サイトマップの {URL: lastmod文字列} を返す(全投稿)。"""
    index_xml = fetch(SITEMAP_INDEX)
    root = ET.fromstring(index_xml.encode("utf-8"))
    child_urls = [
        loc.text.strip()
        for loc in root.findall("sm:sitemap/sm:loc", SM_NS)
        if loc.text and re.search(r"/post-sitemap\d*\.xml$", loc.text.strip())
    ]
    if not child_urls:
        raise FetchError("sitemap_index.xml に post-sitemap が見つかりません(サイト構成が変わった可能性)")
    entries: dict[str, str] = {}
    for child in child_urls:
        sm_root = ET.fromstring(fetch(child).encode("utf-8"))
        for url_el in sm_root.findall("sm:url", SM_NS):
            loc = url_el.findtext("sm:loc", default="", namespaces=SM_NS).strip()
            lastmod = url_el.findtext("sm:lastmod", default="", namespaces=SM_NS).strip()
            if loc:
                entries[normalize_url(loc)] = lastmod
    if not entries:
        raise FetchError("post-sitemap からURLが1件も取れません")
    return entries


def normalize_url(url: str) -> str:
    url = url.strip().rstrip(".,、。)")
    if not url.endswith("/"):
        url += "/"
    return url


def fetch_title(url: str) -> str:
    try:
        page = fetch(url)
    except FetchError as exc:
        return f"(タイトル取得失敗: {exc})"
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    return html.unescape(m.group(1)).strip() if m else "(タイトルなし)"


# ---------------------------------------------------------------------------
# プロファイル
# ---------------------------------------------------------------------------
def load_profile_sources() -> tuple[dict[str, list[str]], dict[str, str]]:
    """({出典URL: [profile_id, ...]}, {profile_id: 機種名}) を返す。"""
    sources: dict[str, list[str]] = {}
    names: dict[str, str] = {}
    for path in sorted(PROFILES_DIR.glob("*.yaml")):
        text = path.read_text(encoding="utf-8")
        data = yaml.safe_load(text) or {}
        pid = str(data.get("id") or path.stem)
        names[pid] = str(data.get("name") or pid)
        for raw in TOOLBOX_URL_RE.findall(text):
            url = normalize_url(raw)
            ids = sources.setdefault(url, [])
            if pid not in ids:
                ids.append(pid)
    return sources, names


def existing_profile_for_slug(slug: str, sources: dict[str, list[str]], names: dict[str, str]) -> str | None:
    url = f"https://slot-toolbox.com/{slug}-tenjo/"
    if url in sources:
        return ",".join(sources[url])
    if slug in SLUG_ALIASES and SLUG_ALIASES[slug] in names:
        return SLUG_ALIASES[slug]
    as_id = slug.replace("-", "_")
    if as_id in names:
        return as_id
    return None


# ---------------------------------------------------------------------------
# 1geki 新台カレンダー
# ---------------------------------------------------------------------------
def parse_calendar(page: str) -> list[dict[str, str]]:
    """スロット機種だけを [{date, name, maker, types, url}] で返す。"""
    machines: list[dict[str, str]] = []
    blocks = re.split(r'<h3 class="introduction_date">', page)[1:]
    for block in blocks:
        dm = re.search(r'<span class="date_ymdw">\s*([^<]+?)\s*</span>', block)
        date = dm.group(1) if dm else "?"
        for item in re.findall(r'<li class="slot-item">(.*?)</li>', block, re.S):
            nm = re.search(r'<h4 class="slot">\s*(.*?)\s*</h4>', item, re.S)
            if not nm:
                continue
            mk = re.search(r'<p class="maker_item">\s*(.*?)\s*</p>', item, re.S)
            href = re.search(r'href="([^"]+)"', item)
            types = [html.unescape(t).strip() for t in re.findall(r'<span class="type">\s*(.*?)\s*</span>', item, re.S)]
            machines.append({
                "date": html.unescape(date),
                "name": html.unescape(re.sub(r"\s+", " ", nm.group(1))).strip(),
                "maker": html.unescape(mk.group(1)).strip() if mk else "",
                "types": " / ".join(types),
                "url": href.group(1) if href else "",
            })
    return machines


def fetch_calendars(today: datetime) -> tuple[list[dict[str, str]], list[str]]:
    months = [today.strftime("%Y%m")]
    nxt = (today.replace(day=1) + timedelta(days=32)).strftime("%Y%m")
    months.append(nxt)
    machines: list[dict[str, str]] = []
    errors: list[str] = []
    for ym in months:
        try:
            machines.extend(parse_calendar(fetch(CALENDAR_URL.format(yyyymm=ym))))
        except FetchError as exc:
            errors.append(str(exc))
    return machines, errors


def _norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = re.sub(r"【.*?】|\(.*?\)|（.*?）", "", s)
    for w in ("スマスロ", "パチスロ", "天井期待値", "天井", "期待値", "狙い目", "ヤメ時", "やめどき",
              "slot-toolbox", "slot toolbox", "スロット"):
        s = s.replace(w, "")
    s = re.sub(r"^l\s*", "", s)
    return re.sub(r"[\s・:：\-|｜!！?？、。,.『』「」]", "", s)


def best_calendar_match(title: str, calendar: list[dict[str, str]]) -> tuple[dict[str, str] | None, float]:
    """名前のゆるい一致(目安)。続編・派生機の取り違えを避けるため、長さが大きく違うものは一致扱いしない。"""
    key = _norm_name(re.split(r"\s[-|｜]\s|[|｜]", title)[0])
    best, best_ratio = None, 0.0
    for m in calendar:
        cand = _norm_name(m["name"])
        if not cand or not key:
            continue
        ratio = difflib.SequenceMatcher(None, key, cand).ratio()
        shorter, longer = sorted((len(key), len(cand)))
        if (cand in key or key in cand) and shorter / longer >= 0.6:
            ratio = max(ratio, 0.9)
        if ratio > best_ratio:
            best, best_ratio = m, ratio
    return (best, best_ratio) if best_ratio >= 0.6 else (None, best_ratio)


# ---------------------------------------------------------------------------
# 状態ファイル
# ---------------------------------------------------------------------------
def load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    with STATE_PATH.open(encoding="utf-8") as f:
        state = json.load(f)
    state.setdefault("seen_tenjo", {})
    state.setdefault("source_lastmod", {})
    return state


def save_state(state: dict) -> None:
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(STATE_PATH)  # 書きかけで壊れないよう、一時ファイルから置きかえる


# ---------------------------------------------------------------------------
# メイン
# ---------------------------------------------------------------------------
def _rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def md_escape(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def run(args: argparse.Namespace) -> int:
    now = datetime.now(JST)
    today = now.strftime("%Y-%m-%d")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"update_{today}.md"

    try:
        state = load_state()
    except (OSError, json.JSONDecodeError) as exc:
        report_path.write_text(f"# 更新チェック {today}\n\n**エラー**: 状態ファイルが読めません: {exc}\n", encoding="utf-8")
        print(f"ERROR: 状態ファイルが読めません: {exc}")
        return 1
    first_run = state is None

    try:
        entries = fetch_post_sitemap_entries()
    except (FetchError, ET.ParseError) as exc:
        report_path.write_text(
            f"# 更新チェック {today}\n\n**エラー**: slot-toolbox.com のサイトマップを取得できませんでした。"
            f"状態ファイルは変更していません。\n\n```\n{exc}\n```\n",
            encoding="utf-8",
        )
        print(f"ERROR: サイトマップ取得失敗(状態は未変更): {exc}")
        return 1

    tenjo = {u: lm for u, lm in entries.items() if TENJO_RE.match(u)}
    sources, names = load_profile_sources()
    defer = set()
    for d in args.defer or []:
        d = d.strip()
        if d.startswith("http"):
            defer.add(normalize_url(d))
        else:
            slug = d[:-len("-tenjo")] if d.endswith("-tenjo") else d
            defer.add(f"https://slot-toolbox.com/{slug}-tenjo/")

    # --- 新しい天井ページ ---------------------------------------------------
    cutoff = now - timedelta(days=INITIAL_RECENT_DAYS)
    new_candidates: list[dict] = []
    existing_unlisted: list[dict] = []
    baseline_seen: dict[str, str] = {}
    seen = {} if first_run else state["seen_tenjo"]
    for url, lm in sorted(tenjo.items(), key=lambda kv: kv[1], reverse=True):
        if url in seen:
            continue
        slug = TENJO_RE.match(url).group(1)
        if url in sources:
            # すでにどれかのプロファイルの出典になっている(更新は出典チェック側で見る)
            baseline_seen[url] = today
            continue
        owner = existing_profile_for_slug(slug, sources, names)
        lm_dt = parse_lastmod(lm)
        if first_run and lm_dt is not None and lm_dt < cutoff:
            baseline_seen[url] = today
            continue
        if owner:
            existing_unlisted.append({"url": url, "lastmod": lm, "profile": owner})
        else:
            new_candidates.append({"url": url, "lastmod": lm, "slug": slug})

    calendar, cal_errors = fetch_calendars(now)
    for i, c in enumerate(new_candidates):
        if i < MAX_TITLE_FETCH:
            c["title"] = fetch_title(c["url"])
        else:
            c["title"] = "(件数上限のため未取得)"
        match, ratio = best_calendar_match(c["title"], calendar)
        c["calendar"] = f'{match["date"]} {match["name"]}(一致度{ratio:.2f})' if match else "該当なし"

    # --- 既存機種の出典ページ更新 ---------------------------------------------
    source_updates: list[dict] = []
    newly_tracked: list[dict] = []
    missing_sources: list[dict] = []
    known_lastmod = {} if first_run else state["source_lastmod"]
    for url, pids in sorted(sources.items()):
        if url not in entries:
            missing_sources.append({"url": url, "profiles": ",".join(pids)})
            continue
        cur = entries[url]
        old = known_lastmod.get(url)
        if old is None:
            newly_tracked.append({"url": url, "profiles": ",".join(pids), "lastmod": cur})
        elif old != cur:
            source_updates.append({"url": url, "profiles": ",".join(pids), "old": old, "new": cur})

    # 初回は「基準作り」なので、既存機種の別ソース/新規追跡は報告対象にしない
    found = bool(new_candidates or source_updates or (missing_sources and not first_run)
                 or (existing_unlisted and not first_run))

    # --- レポート ---------------------------------------------------------------
    lines: list[str] = [f"# 更新チェック {today}", ""]
    lines.append(f"- 実行日時: {now.strftime('%Y-%m-%d %H:%M')} JST")
    lines.append(f"- モード: {'状態を保存' if args.update_state else 'ドライラン(状態は保存しない)'}"
                 f"{' / 初回(基準作り)' if first_run else ''}")
    lines.append(f"- サイトマップの天井ページ数: {len(tenjo)} / 追跡中の出典URL数: {len(sources)}")
    if first_run:
        lines.append(f"- 初回のため、lastmodが{INITIAL_RECENT_DAYS}日より前の天井ページ{len(baseline_seen)}件は"
                     "「確認済み」扱いにしました。")
    lines += ["", "## 新しい天井ページ", ""]
    if new_candidates:
        lines.append("| # | URL | ページタイトル | lastmod | 新台カレンダー照合 | 備考 |")
        lines.append("|---|---|---|---|---|---|")
        for i, c in enumerate(new_candidates, 1):
            note = "今回は見送り(--defer)" if c["url"] in defer else ""
            lines.append(f"| {i} | {c['url']} | {md_escape(c['title'])} | {c['lastmod']} | "
                         f"{md_escape(c['calendar'])} | {note} |")
        lines += ["", "※ lastmodは「最終更新日時」で公開日ではありません。サイト全体の一括更新でも変わります。",
                  "※ パチンコ・沖スロ/ノーマル(A)タイプ・既存機種は対象外。1回の実行で新規作成は最大4機種まで。"]
    else:
        lines.append("なし")
    if existing_unlisted:
        lines += ["", "### 参考: 既存プロファイルがある機種の天井ページ(出典は別サイト)", ""]
        lines.append("| URL | 該当プロファイル | lastmod |")
        lines.append("|---|---|---|")
        for e in existing_unlisted:
            lines.append(f"| {e['url']} | {e['profile']} | {e['lastmod']} |")

    lines += ["", "## 既存機種の出典ページ更新", ""]
    if source_updates:
        lines.append("| プロファイル | URL | 前回lastmod → 今回lastmod |")
        lines.append("|---|---|---|")
        for u in source_updates:
            lines.append(f"| {u['profiles']} | {u['url']} | {u['old']} → {u['new']} |")
    else:
        lines.append("なし")
    if newly_tracked:
        lines += ["", f"### 今回から追跡を始めた出典URL({len(newly_tracked)}件・基準lastmodを記録)", ""]
        for n in newly_tracked:
            lines.append(f"- {n['profiles']}: {n['url']} (lastmod {n['lastmod']})")
    if missing_sources:
        lines += ["", "### 注意: プロファイルに書かれているがサイトマップに無いURL", "",
                  "(削除・URL変更、または設定判別ページ等の固定ページの可能性。中身を確認すること)", ""]
        for m in missing_sources:
            lines.append(f"- {m['profiles']}: {m['url']}")

    lines += ["", "## 新台カレンダー(1geki.jp・スロットのみ・今月と来月)", ""]
    if calendar:
        profile_list = [{"name": n} for n in names.values()]
        lines.append("| 導入日 | 機種名 | メーカー | タイプ | アプリ収録(名前照合・目安) |")
        lines.append("|---|---|---|---|---|")
        for m in calendar:
            hit, _ = best_calendar_match(m["name"], profile_list)
            have = f"あり({hit['name']})" if hit else "-"
            lines.append(f"| {m['date']} | {md_escape(m['name'])} | {md_escape(m['maker'])} | "
                         f"{md_escape(m['types'])} | {md_escape(have)} |")
    else:
        lines.append("取得できませんでした")
    for e in cal_errors:
        lines.append(f"- 取得エラー: {e}")

    saved = False
    if args.update_state:
        new_state = {
            "version": 1,
            "note": "scripts/check_updates.py が管理。個人情報は含まない。",
            "updated_at": now.isoformat(timespec="seconds"),
            "seen_tenjo": dict(seen),
            "source_lastmod": dict(known_lastmod),
        }
        new_state["seen_tenjo"].update(baseline_seen)
        if not first_run:
            for c in new_candidates:
                if c["url"] not in defer:
                    new_state["seen_tenjo"][c["url"]] = today
            for e in existing_unlisted:
                new_state["seen_tenjo"][e["url"]] = today
        else:
            # 初回: 既存機種の天井ページは確認済み、21日以内の新機種候補は未確認のまま残す
            for e in existing_unlisted:
                new_state["seen_tenjo"][e["url"]] = today
        for url in sources:
            if url in entries:
                new_state["source_lastmod"][url] = entries[url]
        save_state(new_state)
        saved = True
        lines += ["", f"状態ファイルを保存しました: {_rel(STATE_PATH)}"]
        if first_run and new_candidates:
            lines.append(f"(初回のため新機種候補{len(new_candidates)}件は未確認のまま残しています。次回も表示されます)")

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    summary = (f"新天井ページ{len(new_candidates)}件 / 出典更新{len(source_updates)}件 / "
               f"出典URL不明{len(missing_sources)}件 / 新台カレンダー{len(calendar)}機種"
               f"{' / 状態保存済み' if saved else ''} -> {_rel(report_path)}")
    print(("FOUND: " if found else "変更なし: ") + summary)
    return 10 if found else 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="状態ファイルを保存しない(既定)")
    mode.add_argument("--update-state", action="store_true", help="状態ファイルを保存する")
    parser.add_argument("--defer", action="append", metavar="URL_OR_SLUG",
                        help="今回は見送る新機種候補(未確認のまま残す)。複数指定可")
    args = parser.parse_args()
    try:
        return run(args)
    except Exception as exc:  # 想定外でも状態ファイルは書いていない(保存は最後の1回だけ)
        print(f"ERROR: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
