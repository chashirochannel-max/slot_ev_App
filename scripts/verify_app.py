"""機種プロファイル追加・更新後の動作確認(自動メンテ docs/AUTO_UPDATE.md の検証手順)。

やること:
  1. profiles/*.yaml を全部アプリの読み込み関数(load_all_profiles)で読む
  2. Streamlit AppTest で機種選択画面と全機種の画面を動かし、例外0件を確認
     (ゲーム数入力に300を入れて判定まで動かす)
  3. profiles/ と scripts/make_badge.py に制御文字が混ざっていないか確認
  4. --sheet ID ... を付けると、指定した機種のサムネイルを並べた一覧画像を
     reports/thumbs_YYYY-MM-DD.jpg に作る

Google Sheetsへの実戦ログ書き込みは必ず無効化する:
  - AppTest にダミーの secrets を渡す(=本物の .streamlit/secrets.toml を使わせない)
  - さらに services.sheets_log._get_worksheet を「必ず失敗する関数」に差しかえる
  → append_log は SheetsLogError になり、画面に案内が出るだけで外部には何も送られない

使い方:
    python scripts/verify_app.py
    python scripts/verify_app.py --sheet new_id1 new_id2

終了コード: 0=問題なし / 1=問題あり
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import services.sheets_log as sheets_log  # noqa: E402
from engine.profile_loader import load_all_profiles  # noqa: E402

CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
DUMMY_SECRETS = {"app_password": "verify-only-dummy"}  # 本物の秘密情報ではない
sheets_calls = 0


def _blocked_worksheet():
    global sheets_calls
    sheets_calls += 1
    raise RuntimeError("verify_app.py: Google Sheetsへの書き込みは検証中は無効")


def check_control_chars() -> list[str]:
    bad = []
    targets = sorted((ROOT / "profiles").glob("*.yaml")) + [ROOT / "scripts" / "make_badge.py"]
    for path in targets:
        for no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if CONTROL_RE.search(line):
                bad.append(f"{path.relative_to(ROOT).as_posix()}:{no}")
    return bad


def run_apptest(profile_ids: list[str]) -> list[str]:
    from streamlit.testing.v1 import AppTest

    problems = []

    def new_app(selected: str | None):
        at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=90)
        at.secrets.update(DUMMY_SECRETS)
        at.session_state["authenticated"] = True
        if selected:
            at.session_state["selected_profile_id"] = selected
        return at

    at = new_app(None)
    at.run()
    if at.exception:
        problems += [f"機種選択画面: {e.message}" for e in at.exception]
    print(f"機種選択画面: 例外{len(at.exception)}件 / ボタン{len(at.button)}個")

    for pid in profile_ids:
        at = new_app(pid)
        at.run()
        n1 = len(at.exception)
        if at.number_input and not at.exception:
            at.number_input[0].set_value(300).run()
        judge = [b for b in at.button if b.label == "判定する"]
        if judge and not at.exception:
            judge[0].click().run()  # 判定→実戦ログ記録(遮断済み)まで通す
        n2 = len(at.exception)
        metrics = [(m.label, m.value) for m in at.metric][:2]
        print(f"{pid}: 例外 {n1}/{n2}件  判定ボタン{'あり' if judge else 'なし'}  {metrics}")
        problems += [f"{pid}: {e.message}" for e in at.exception]
    return problems


def make_contact_sheet(ids: list[str]) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    thumbs = []
    for mid in ids:
        p = ROOT / "assets" / "badges_mascot" / f"{mid}.jpg"
        if not p.exists():
            raise SystemExit(f"サムネイルがありません: {p}")
        thumbs.append((mid, Image.open(p).convert("RGB").resize((400, 200))))
    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * 410 + 10, rows * 235 + 10), "white")
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\meiryo.ttc", 16)
    except OSError:
        font = ImageFont.load_default()
    for i, (mid, img) in enumerate(thumbs):
        x, y = 10 + (i % cols) * 410, 10 + (i // cols) * 235
        sheet.paste(img, (x, y))
        draw.text((x, y + 203), mid, fill="black", font=font)
    today = datetime.now(timezone(timedelta(hours=9))).strftime("%Y-%m-%d")
    out = ROOT / "reports" / f"thumbs_{today}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, "JPEG", quality=88)
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--sheet", nargs="+", metavar="ID", help="一覧画像に並べる機種ID")
    args = parser.parse_args()

    sheets_log._get_worksheet = _blocked_worksheet  # Sheets書き込みを無効化

    problems: list[str] = []
    profiles = load_all_profiles(ROOT / "profiles")
    ids = [p.id for p in profiles]
    print(f"プロファイル読み込み: {len(profiles)}機種 OK")
    if len(set(ids)) != len(ids):
        problems.append("機種IDが重複しています")
    for p in profiles:
        if p.header_image and not (ROOT / p.header_image).exists():
            problems.append(f"{p.id}: header_image が見つかりません ({p.header_image})")

    bad = check_control_chars()
    print(f"制御文字: {len(bad)}件")
    problems += [f"制御文字: {b}" for b in bad]

    problems += run_apptest(ids)
    print(f"Sheetsへの接続試行(すべて遮断済み): {sheets_calls}回")

    if args.sheet:
        print(f"サムネイル一覧: {make_contact_sheet(args.sheet).relative_to(ROOT).as_posix()}")

    if problems:
        print("NG:")
        for p in problems:
            print(f"  - {p}")
        return 1
    print("OK: 問題なし")
    return 0


if __name__ == "__main__":
    sys.exit(main())
