"""自作の機種バッジ画像(サムネイル)を作る。

メーカーのパネル画像・公式画像は著作権の心配があるため、このスクリプトで
「色+短い機種名+単純な図形」だけのバッジを作り、機種カードの目印にする。
キャラクター・ロゴ・公式の書体やキービジュアルのまねは一切しない。
ネットから画像も取ってこない(すべて円・線・多角形をプログラムで描く)。

使い方:
    python scripts/make_badge.py <machine_id>     # 1機種だけ作る
    python scripts/make_badge.py --all            # profiles/ の全機種を作る
    python scripts/make_badge.py --all --style mascot   # マスコット版(assets/badges_mascot/)を作る

出力: assets/badges/<machine_id>.jpg (800x400, 2:1。process_header_image.pyと同じサイズ)
できた画像を使うには、profiles/<machine_id>.yaml の header_image を
"assets/badges/<machine_id>.jpg" にする。

色・短い名前・モチーフを変えたいときは、下の BADGES 表を書きかえて再実行する。
表に無い機種は、正式名から自動で色を決めた汎用デザインになる。
"""
from __future__ import annotations

import colorsys
import hashlib
import math
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent.parent
PROFILES_DIR = ROOT / "profiles"
OUT_DIR = ROOT / "assets" / "badges"

WIDTH, HEIGHT = 800, 400
SS = 2  # なめらかに描くため2倍で描いてから縮小する
JPEG_QUALITY = 88

FONT_BOLD_CANDIDATES = [
    r"C:\Windows\Fonts\YuGothB.ttc",
    r"C:\Windows\Fonts\meiryob.ttc",
]
FONT_REGULAR_CANDIDATES = [
    r"C:\Windows\Fonts\YuGothM.ttc",
    r"C:\Windows\Fonts\meiryo.ttc",
]

# ---------------------------------------------------------------------------
# 機種ごとの設定表(ここを書きかえればデザインが変わる)
#   short : 大きく出す短い名前。"\n" を入れると2行になる
#   colors: 背景グラデーションの (上の色, 下の色)
#   accent: 図形・ラベルの色
#   motif : 下の MOTIFS にある図形の名前
# ---------------------------------------------------------------------------
BADGES: dict[str, dict] = {
    "monkey_turn_v": {
        "short": "モンキーターンV",
        "colors": ("#0b4f8a", "#062448"), "accent": "#7fd3ff", "motif": "boat",
    },
    "bakemonogatari": {
        "short": "化物語",
        "colors": ("#3a1f5c", "#120a24"), "accent": "#f3d36b", "motif": "moon",
    },
    "fire_force2": {
        "short": "炎炎ノ消防隊2",
        "colors": ("#b8320f", "#3d0b05"), "accent": "#ffb347", "motif": "flame",
    },
    "jormungand": {
        "short": "ヨルムンガンド",
        "colors": ("#3c4a2a", "#151c10"), "accent": "#c9d98a", "motif": "globe",
    },
    "kabaneri_kaimon_kessen": {
        "short": "カバネリ海門",
        "colors": ("#4a4f57", "#16181c"), "accent": "#e0a050", "motif": "train",
    },
    "kanojo_okarishimasu": {
        "short": "かのかり",
        "colors": ("#e06a8e", "#7a2a4a"), "accent": "#ffe0ea", "motif": "hearts",
    },
    "karakuri_circus2": {
        "short": "からくり\nサーカス2",
        "colors": ("#8a1c2c", "#2e0a10"), "accent": "#f2c14e", "motif": "circus",
    },
    "l_sengoku_musume5": {
        "short": "戦国乙女5",
        "colors": ("#c2416b", "#3b1030"), "accent": "#ffd1e0", "motif": "petals",
    },
    "lycoris_recoil": {
        "short": "リコリス\nリコイル",
        "colors": ("#c8243a", "#401018"), "accent": "#ffd6d6", "motif": "lily",
    },
    "sao2": {
        "short": "SAO2",
        "colors": ("#1d3f7a", "#0a1430"), "accent": "#8fe3ff", "motif": "hexgrid",
    },
    "sengoku_collection6": {
        "short": "戦コレ6",
        "colors": ("#6b1a1a", "#1e0606"), "accent": "#f0c05a", "motif": "swords",
    },
    "toaru_index2": {
        "short": "とある禁書目録2",
        "colors": ("#2a2a7a", "#0c0c2a"), "accent": "#c0b0ff", "motif": "magic_circle",
    },
    "tokyo_ghoul": {
        "short": "東京喰種",
        "colors": ("#2a2a2e", "#0a0a0c"), "accent": "#d62a3a", "motif": "skyline",
    },
    "world_dystar": {
        "short": "ワールド\nダイスター",
        "colors": ("#5a2a8a", "#1a0a33"), "accent": "#ffe27a", "motif": "stage",
    },
    "mahoako": {
        "short": "まほあこ",
        "colors": ("#b0478a", "#3a0f33"), "accent": "#ffd1f0", "motif": "petals",
    },
    "juoh": {
        "short": "獣王",
        "colors": ("#c27a1c", "#3d2306"), "accent": "#ffe08a", "motif": "generic",
    },
    "paripi_koumei": {
        "short": "パリピ孔明",
        "colors": ("#1c6b8a", "#081f2e"), "accent": "#7ff0ff", "motif": "stage",
    },
    "mhrsb": {
        "short": "モンハン\nサンブレイク",
        "colors": ("#2f5a3a", "#0e1c12"), "accent": "#e8b04a", "motif": "flame",
    },
    "tenseioujo": {
        "short": "転生王女",
        "colors": ("#3a5cb0", "#101a3d"), "accent": "#ffd98a", "motif": "magic_circle",
    },
    "aobuta": {
        "short": "青ブタ",
        "colors": ("#3a7bd5", "#0f2347"), "accent": "#cfe6ff", "motif": "moon",
    },
}

# 正式名の先頭にある種別。長い順に判定する
KIND_PREFIXES = ["Lパチスロ", "スマスロ", "パチスロ"]


# ---------------------------------------------------------------------------
# 小道具
# ---------------------------------------------------------------------------
def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgba(h: str, a: int) -> tuple[int, int, int, int]:
    return (*hex_rgb(h), a)


def load_font(candidates: list[str], size: int) -> ImageFont.FreeTypeFont:
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    raise SystemExit(f"日本語フォントが見つかりません: {candidates}")


def split_kind(name: str) -> tuple[str, str]:
    """正式名を(種別ラベル, 種別を除いた名前)に分ける。"""
    for prefix in KIND_PREFIXES:
        if name.startswith(prefix):
            return prefix, name[len(prefix):].strip()
    return "パチスロ", name


def auto_style(machine_id: str, name: str) -> dict:
    """表に無い機種用。名前から色相を決める(同じ名前なら毎回同じ色)。"""
    hue = int(hashlib.md5(name.encode("utf-8")).hexdigest()[:4], 16) / 0xFFFF

    def hsv_hex(h: float, s: float, v: float) -> str:
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))

    _, rest = split_kind(name)
    return {
        "short": rest or machine_id,
        "colors": (hsv_hex(hue, 0.65, 0.55), hsv_hex(hue, 0.75, 0.18)),
        "accent": hsv_hex(hue + 0.08, 0.35, 1.0),
        "motif": "generic",
    }


# ---------------------------------------------------------------------------
# モチーフ(すべて単純な図形。座標は2倍サイズのキャンバス基準)
# d: ImageDraw(RGBA重ね描き用), W/H: キャンバスサイズ, c: アクセント色
# ---------------------------------------------------------------------------
def m_boat(d, W, H, c):
    # 波線3本
    for k, (y0, a) in enumerate([(0.70, 110), (0.80, 80), (0.90, 60)]):
        pts = [(x, H * y0 + math.sin(x / W * math.pi * 6 + k) * H * 0.03) for x in range(0, W + 1, 8)]
        d.line(pts, fill=rgba(c, a), width=int(H * 0.018))
    # ボート風の三角(右下)
    bx, by = W * 0.80, H * 0.66
    d.polygon([(bx - W * 0.12, by), (bx + W * 0.10, by), (bx + W * 0.13, by - H * 0.05),
               (bx - W * 0.06, by - H * 0.07)], fill=rgba(c, 90))
    # 引き波
    d.line([(bx - W * 0.13, by + H * 0.01), (bx - W * 0.35, by + H * 0.04)], fill=rgba(c, 70), width=int(H * 0.012))


def _flame_shape(cx, base, w, h):
    pts = []
    for i in range(41):
        t = i / 40 * math.pi
        x = cx - math.cos(t) * w / 2
        y = base - math.sin(t) ** 0.6 * h * (0.35 + 0.65 * math.sin(t / 2) ** 2)
        pts.append((x, y))
    pts.append((cx + w * 0.05, base - h * 1.05))  # とがった先
    return pts


def m_flame(d, W, H, c):
    for cx, w, h, a in [(W * 0.12, W * 0.18, H * 0.75, 70), (W * 0.88, W * 0.22, H * 0.9, 80),
                        (W * 0.72, W * 0.12, H * 0.5, 60), (W * 0.30, W * 0.10, H * 0.4, 50)]:
        d.polygon(_flame_shape(cx, H * 1.02, w, h), fill=rgba(c, a))


def m_moon(d, W, H, c):
    r = H * 0.28
    cx, cy = W * 0.82, H * 0.30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgba(c, 110))
    # 欠けた部分(背景色に近い暗い円で隠す)
    d.ellipse([cx - r * 0.55, cy - r * 1.15, cx + r * 1.45, cy + r * 0.85], fill=(20, 10, 36, 255))
    # 縦線(都会の夜の格子)
    for i in range(9):
        x = W * (0.05 + i * 0.07)
        d.line([(x, H * 0.75), (x, H)], fill=rgba(c, 40), width=int(W * 0.004))


def m_globe(d, W, H, c):
    r = H * 0.42
    cx, cy = W * 0.84, H * 0.55
    w = int(H * 0.01)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=rgba(c, 90), width=w)
    for k in (0.35, 0.7):
        d.ellipse([cx - r * k, cy - r, cx + r * k, cy + r], outline=rgba(c, 70), width=w)
    for k in (-0.5, 0, 0.5):
        yy = cy + r * k
        half = math.sqrt(max(r * r - (r * k) ** 2, 0))
        d.line([(cx - half, yy), (cx + half, yy)], fill=rgba(c, 70), width=w)
    # 航路の点線
    for i in range(12):
        x = W * 0.05 + i * W * 0.05
        y = H * 0.85 - math.sin(i / 11 * math.pi) * H * 0.15
        d.ellipse([x - w * 1.2, y - w * 1.2, x + w * 1.2, y + w * 1.2], fill=rgba(c, 90))


def m_train(d, W, H, c):
    col = rgba(c, 85)
    base = H * 0.88
    x0 = W * 0.60
    # 車体・運転室・煙突
    d.rectangle([x0, base - H * 0.22, x0 + W * 0.28, base - H * 0.06], fill=col)
    d.rectangle([x0 + W * 0.20, base - H * 0.36, x0 + W * 0.30, base - H * 0.06], fill=col)
    d.rectangle([x0 + W * 0.04, base - H * 0.34, x0 + W * 0.08, base - H * 0.22], fill=col)
    # 車輪
    for wx in (0.05, 0.13, 0.24):
        r = H * 0.055
        cx = x0 + W * wx
        d.ellipse([cx - r, base - r * 1.2, cx + r, base + r * 0.8], fill=col)
    # 煙
    for i, (dx, dy, r) in enumerate([(0.05, 0.42, 0.05), (0.0, 0.52, 0.065), (-0.07, 0.60, 0.08)]):
        cx, cy, rr = x0 + W * dx, base - H * dy, H * r
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=rgba(c, 50 - i * 10))
    # レール
    d.line([(0, base + H * 0.04), (W, base + H * 0.04)], fill=rgba(c, 90), width=int(H * 0.012))


def _heart(cx, cy, s):
    pts = []
    for i in range(60):
        t = i / 60 * 2 * math.pi
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        pts.append((cx + x * s, cy - y * s))
    return pts


def m_hearts(d, W, H, c):
    for cx, cy, s, a in [(0.85, 0.30, 0.012, 90), (0.10, 0.78, 0.008, 70), (0.93, 0.80, 0.006, 60),
                         (0.18, 0.22, 0.005, 50), (0.70, 0.88, 0.004, 50)]:
        d.polygon(_heart(W * cx, H * cy, W * s), fill=rgba(c, a))


def m_circus(d, W, H, c):
    # テントの縞(上から放射状)
    apex = (W * 0.5, -H * 0.2)
    n = 14
    for i in range(n):
        if i % 2:
            continue
        x1, x2 = W * i / n * 1.4 - W * 0.2, W * (i + 1) / n * 1.4 - W * 0.2
        d.polygon([apex, (x1, H * 0.25), (x2, H * 0.25)], fill=rgba(c, 45))
    # 歯車(右下)
    cx, cy, r = W * 0.86, H * 0.80, H * 0.18
    teeth = 10
    pts = []
    for i in range(teeth * 2):
        ang = i / (teeth * 2) * 2 * math.pi
        rr = r if i % 2 == 0 else r * 0.8
        pts.append((cx + math.cos(ang) * rr, cy + math.sin(ang) * rr))
    d.polygon(pts, fill=rgba(c, 80))
    d.ellipse([cx - r * 0.35, cy - r * 0.35, cx + r * 0.35, cy + r * 0.35], fill=(40, 10, 16, 255))


def _petal(cx, cy, s, rot):
    pts = []
    for i in range(30):
        t = i / 30 * 2 * math.pi
        x = math.sin(t) * 0.5
        y = -math.cos(t) * (1 if math.cos(t) > 0 else 0.6)
        xr = x * math.cos(rot) - y * math.sin(rot)
        yr = x * math.sin(rot) + y * math.cos(rot)
        pts.append((cx + xr * s, cy + yr * s))
    return pts


def m_petals(d, W, H, c):
    # 刀の直線2本と花びら
    w = int(H * 0.014)
    d.line([(W * 0.60, H * 1.0), (W * 0.98, H * 0.05)], fill=rgba(c, 80), width=w)
    d.line([(W * 0.02, H * 0.95), (W * 0.30, H * 0.10)], fill=rgba(c, 60), width=w)
    for cx, cy, s, rot, a in [(0.80, 0.25, 0.05, 0.5, 90), (0.90, 0.70, 0.035, 1.8, 70), (0.12, 0.30, 0.03, 2.5, 60),
                              (0.20, 0.82, 0.04, 4.0, 70), (0.68, 0.85, 0.025, 1.0, 60)]:
        d.polygon(_petal(W * cx, H * cy, H * s * 2, rot), fill=rgba(c, a))


def m_lily(d, W, H, c):
    # 放射状の細い線(花の形を線だけで表す)
    for cx, cy, r, a in [(W * 0.86, H * 0.25, H * 0.30, 90), (W * 0.10, H * 0.85, H * 0.22, 70)]:
        for i in range(10):
            ang = -math.pi / 2 + (i - 4.5) * 0.28
            x2, y2 = cx + math.cos(ang) * r, cy + math.sin(ang) * r * 0.6 - r * 0.2
            d.line([(cx, cy + r * 0.4), (x2, y2)], fill=rgba(c, a), width=int(H * 0.008))
            d.ellipse([x2 - 4, y2 - 4, x2 + 4, y2 + 4], fill=rgba(c, a))


def m_hexgrid(d, W, H, c):
    r = H * 0.09
    for row in range(-1, 7):
        for col in range(-1, 12):
            cx = col * r * 1.75 + (r * 0.87 if row % 2 else 0)
            cy = row * r * 1.5
            # 右側ほど濃く
            a = int(20 + 60 * max(0.0, min(1.0, (cx / W - 0.3) / 0.7)))
            pts = [(cx + math.cos(math.pi / 3 * k + math.pi / 6) * r * 0.9,
                    cy + math.sin(math.pi / 3 * k + math.pi / 6) * r * 0.9) for k in range(6)]
            d.polygon(pts, outline=rgba(c, a), width=int(H * 0.006))


def m_swords(d, W, H, c):
    w = int(H * 0.016)
    # 交差する2本の直線(刀)
    d.line([(W * 0.62, H * 0.95), (W * 0.98, H * 0.05)], fill=rgba(c, 90), width=w)
    d.line([(W * 0.98, H * 0.95), (W * 0.62, H * 0.05)], fill=rgba(c, 90), width=w)
    # つば(短い横線)
    for (x, y) in [(W * 0.665, H * 0.83), (W * 0.935, H * 0.83)]:
        d.line([(x - W * 0.03, y), (x + W * 0.03, y)], fill=rgba(c, 90), width=w * 2)
    # 日輪
    r = H * 0.22
    d.ellipse([W * 0.08 - r, H * 0.25 - r, W * 0.08 + r, H * 0.25 + r], fill=rgba(c, 45))


def m_magic_circle(d, W, H, c):
    cx, cy = W * 0.84, H * 0.50
    w = int(H * 0.008)
    for r, a in [(H * 0.42, 80), (H * 0.36, 60), (H * 0.20, 70)]:
        d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=rgba(c, a), width=w)
    r = H * 0.36
    star = [(cx + math.cos(-math.pi / 2 + k * 4 * math.pi / 5) * r,
             cy + math.sin(-math.pi / 2 + k * 4 * math.pi / 5) * r) for k in range(6)]
    d.line(star, fill=rgba(c, 70), width=w)
    # 小さな稲妻(左)
    x, y = W * 0.08, H * 0.15
    d.polygon([(x, y), (x + W * 0.05, y), (x + W * 0.02, y + H * 0.18), (x + W * 0.06, y + H * 0.18),
               (x - W * 0.01, y + H * 0.45), (x + W * 0.01, y + H * 0.25), (x - W * 0.02, y + H * 0.25)],
              fill=rgba(c, 60))


def m_skyline(d, W, H, c):
    # ビルのシルエット
    x = 0.0
    heights = [0.35, 0.55, 0.28, 0.62, 0.40, 0.72, 0.30, 0.50, 0.45, 0.66, 0.33, 0.58]
    bw = W / len(heights)
    for h in heights:
        d.rectangle([x, H * (1 - h * 0.6), x + bw * 0.9, H], fill=(5, 5, 8, 200))
        x += bw
    # 赤い月
    r = H * 0.17
    cx, cy = W * 0.84, H * 0.24
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgba(c, 140))


def _star(cx, cy, r):
    return [(cx + math.cos(-math.pi / 2 + k * math.pi / 5) * (r if k % 2 == 0 else r * 0.42),
             cy + math.sin(-math.pi / 2 + k * math.pi / 5) * (r if k % 2 == 0 else r * 0.42)) for k in range(10)]


def m_stage(d, W, H, c):
    # スポットライト2本
    d.polygon([(W * 0.15, -H * 0.05), (W * 0.22, -H * 0.05), (W * 0.45, H), (W * 0.0, H)], fill=rgba(c, 30))
    d.polygon([(W * 0.80, -H * 0.05), (W * 0.87, -H * 0.05), (W * 1.0, H), (W * 0.55, H)], fill=rgba(c, 30))
    for cx, cy, r, a in [(0.88, 0.22, 0.10, 110), (0.10, 0.70, 0.06, 80), (0.72, 0.78, 0.045, 80),
                         (0.30, 0.15, 0.035, 70), (0.95, 0.60, 0.03, 60)]:
        d.polygon(_star(W * cx, H * cy, H * r * 1.6), fill=rgba(c, a))


def m_generic(d, W, H, c):
    for cx, cy, r, a in [(0.88, 0.20, 0.30, 50), (0.10, 0.90, 0.25, 40), (0.70, 0.95, 0.12, 40)]:
        d.ellipse([W * cx - H * r, H * cy - H * r, W * cx + H * r, H * cy + H * r], fill=rgba(c, a))


MOTIFS = {
    "boat": m_boat, "flame": m_flame, "moon": m_moon, "globe": m_globe, "train": m_train,
    "hearts": m_hearts, "circus": m_circus, "petals": m_petals, "lily": m_lily,
    "hexgrid": m_hexgrid, "swords": m_swords, "magic_circle": m_magic_circle,
    "skyline": m_skyline, "stage": m_stage, "generic": m_generic,
}


# ---------------------------------------------------------------------------
# 描画本体
# ---------------------------------------------------------------------------
def _gradient(W, H, top, bottom) -> Image.Image:
    t, b = hex_rgb(top), hex_rgb(bottom)
    im = Image.new("RGB", (W, H))
    px = ImageDraw.Draw(im)
    # 上→下のグラデーション
    for y in range(H):
        k = y / (H - 1)
        col = tuple(int(t[i] + (b[i] - t[i]) * k) for i in range(3))
        px.line([(0, y), (W, y)], fill=col)
    # 斜め方向の明暗を少し足す
    shade = Image.linear_gradient("L").rotate(-60, expand=False).resize((W, H))
    dark = Image.new("RGB", (W, H), (0, 0, 0))
    return Image.composite(im, dark, shade.point(lambda v: 150 + v * 105 // 255))


def _fit_font(draw, lines: list[str], max_w: int, max_h: int, start: int) -> tuple[ImageFont.FreeTypeFont, int]:
    size = start
    while size > 20:
        font = load_font(FONT_BOLD_CANDIDATES, size)
        widths = [draw.textbbox((0, 0), ln, font=font)[2] for ln in lines]
        line_h = int(size * 1.12)
        if max(widths) <= max_w and line_h * len(lines) <= max_h:
            return font, line_h
        size -= 4
    font = load_font(FONT_BOLD_CANDIDATES, size)
    return font, int(size * 1.12)


def make_badge(machine_id: str, name: str, style: dict) -> Path:
    W, H = WIDTH * SS, HEIGHT * SS
    top, bottom = style["colors"]
    accent = style["accent"]

    base = _gradient(W, H, top, bottom).convert("RGBA")

    # モチーフ(半透明で背景に)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    MOTIFS.get(style.get("motif", "generic"), m_generic)(ImageDraw.Draw(layer), W, H, accent)
    base = Image.alpha_composite(base, layer)

    # 下の帯(正式名を読みやすくする)
    band = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    band_top = int(H * 0.82)
    bd.rectangle([0, band_top, W, H], fill=(0, 0, 0, 120))
    base = Image.alpha_composite(base, band)

    kind, rest = split_kind(name)
    lines = style["short"].split("\n")

    # 大きな短い名前(影→本体)
    probe = ImageDraw.Draw(base)
    area_top, area_bottom = int(H * 0.17), band_top - int(H * 0.03)
    font, line_h = _fit_font(probe, lines, int(W * 0.90), area_bottom - area_top, start=int(H * 0.42))
    total_h = line_h * len(lines)
    y0 = area_top + (area_bottom - area_top - total_h) // 2

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text)
    stroke = max(4, font.size // 14)
    for i, ln in enumerate(lines):
        bbox = td.textbbox((0, 0), ln, font=font)
        x = (W - (bbox[2] - bbox[0])) // 2 - bbox[0]
        y = y0 + i * line_h - bbox[1] + (line_h - (bbox[3] - bbox[1])) // 2
        sd.text((x + stroke, y + stroke * 1.5), ln, font=font, fill=(0, 0, 0, 200),
                stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
        td.text((x, y), ln, font=font, fill=(255, 255, 255, 255),
                stroke_width=stroke, stroke_fill=(*hex_rgb(bottom), 255))
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(stroke * 1.5)))
    base = Image.alpha_composite(base, text)

    d = ImageDraw.Draw(base)

    # 種別ラベル(左上)
    lab_font = load_font(FONT_BOLD_CANDIDATES, int(H * 0.075))
    lb = d.textbbox((0, 0), kind, font=lab_font)
    pad_x, pad_y = int(H * 0.03), int(H * 0.015)
    lx, ly = int(W * 0.03), int(H * 0.05)
    d.rounded_rectangle([lx, ly, lx + (lb[2] - lb[0]) + pad_x * 2, ly + (lb[3] - lb[1]) + pad_y * 2],
                        radius=int(H * 0.03), fill=rgba(accent, 235))
    d.text((lx + pad_x - lb[0], ly + pad_y - lb[1]), kind, font=lab_font, fill=(*hex_rgb(bottom), 255))

    # 正式名(下の帯の中、小さめ。長ければ縮める)
    sub_size = int(H * 0.08)
    while sub_size > 16:
        sub_font = load_font(FONT_REGULAR_CANDIDATES, sub_size)
        sb = d.textbbox((0, 0), rest, font=sub_font)
        if sb[2] - sb[0] <= W * 0.94:
            break
        sub_size -= 2
    sx = (W - (sb[2] - sb[0])) // 2 - sb[0]
    sy = band_top + (H - band_top - (sb[3] - sb[1])) // 2 - sb[1]
    d.text((sx, sy), rest, font=sub_font, fill=(235, 235, 235, 255))

    out = base.convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / f"{machine_id}.jpg"
    out.save(out_path, "JPEG", quality=JPEG_QUALITY)
    return out_path


def load_profiles() -> dict[str, str]:
    """{machine_id: 正式名} を profiles/*.yaml から読む。"""
    result = {}
    for p in sorted(PROFILES_DIR.glob("*.yaml")):
        data = yaml.safe_load(p.read_text(encoding="utf-8"))
        result[data["id"]] = data.get("name", data["id"])
    return result


def build(machine_id: str, profiles: dict[str, str]) -> Path:
    if machine_id not in profiles:
        raise SystemExit(f"profiles/ に id={machine_id} の機種がありません")
    name = profiles[machine_id]
    style = BADGES.get(machine_id) or auto_style(machine_id, name)
    return make_badge(machine_id, name, style)


# ===========================================================================
# マスコット版(--style mascot)
#
# このアプリ専用のオリジナルマスコット「おもち」(丸いおもち形の小さな生きもの。
# クリーム色の体・点の目・小さな口・ピンクのほっぺ・小さな足)に、機種ごとの
# 一般的なテーマの小物(ヘルメット、刀、花束など)を持たせて見分けやすくする。
# 作品のキャラクターには似せない(デフォルメ・ちび化もしない)。小物は一般名詞
# レベルの形だけで、作品固有の道具・衣装・武器のデザインはまねない。
# 出力: assets/badges_mascot/<machine_id>.jpg
# ===========================================================================
MASCOT_OUT_DIR = ROOT / "assets" / "badges_mascot"

MOCHI_BODY = "#fff3dc"     # クリーム色(既存キャラの色と重ならないよう、紫・黄・ピンク一色は避ける)
MOCHI_LINE = "#5a3b2e"     # こげ茶のふち
MOCHI_CHEEK = "#ffb3bf"

# 機種ごとのマスコット設定
#   short  : マスコット版で大きく出す名前(文字の場所がせまいので2行にしやすい)
#   side   : マスコットを置く側("left" / "right")。文字は反対側
#   scale  : マスコットの大きさ(1.0が標準)
#   tilt   : 体の傾き(度。プラスで左回り)
#   look   : 目の向き("front" / "up" / "side")
#   props  : 持たせる・着せる小物(下の PROPS の名前)
MASCOTS: dict[str, dict] = {
    "monkey_turn_v": {"short": "モンキー\nターンV", "side": "right", "scale": 0.95, "tilt": -8,
                      "look": "side", "props": ["race_helmet", "boat"]},
    "fire_force2": {"short": "炎炎ノ\n消防隊2", "side": "left", "scale": 0.9, "tilt": 6,
                    "look": "side", "props": ["fire_helmet", "hose"]},
    "kabaneri_kaimon_kessen": {"short": "カバネリ\n海門", "side": "right", "scale": 0.9, "tilt": 0,
                               "look": "front", "props": ["steam", "conductor_cap"]},
    "l_sengoku_musume5": {"short": "戦国乙女5", "side": "left", "scale": 0.85, "tilt": -6,
                          "look": "front", "props": ["kabuto", "sword"]},
    "sengoku_collection6": {"short": "戦コレ6", "side": "right", "scale": 1.1, "tilt": 10,
                            "look": "side", "props": ["banner", "kabuto", "sword"]},
    "bakemonogatari": {"short": "化物語", "side": "right", "scale": 0.8, "tilt": 8,
                       "look": "up", "props": ["nightcap"]},
    "jormungand": {"short": "ヨルムン\nガンド", "side": "left", "scale": 0.85, "tilt": 0,
                   "look": "front", "props": ["fedora", "suitcase"]},
    "kanojo_okarishimasu": {"short": "かのかり", "side": "right", "scale": 0.95, "tilt": -6,
                            "look": "front", "props": ["bouquet"]},
    "karakuri_circus2": {"short": "からくり\nサーカス2", "side": "left", "scale": 0.85, "tilt": 8,
                         "look": "front", "props": ["tophat"]},
    "lycoris_recoil": {"short": "リコリス\nリコイル", "side": "right", "scale": 0.9, "tilt": 4,
                       "look": "front", "props": ["lily_head"]},
    "sao2": {"short": "SAO2", "side": "left", "scale": 0.95, "tilt": -4,
             "look": "front", "props": ["goggles", "sword"]},
    "toaru_index2": {"short": "とある\n禁書目録2", "side": "right", "scale": 0.85, "tilt": 0,
                     "look": "up", "props": ["magic_floor", "wizard_hat"]},
    "tokyo_ghoul": {"short": "東京喰種", "side": "left", "scale": 0.85, "tilt": 0,
                    "look": "up", "props": ["scarf"]},
    "world_dystar": {"short": "ワールド\nダイスター", "side": "right", "scale": 0.9, "tilt": -8,
                     "look": "front", "props": ["bow", "mic"]},
    "mahoako": {"short": "まほあこ", "side": "left", "scale": 0.9, "tilt": 6,
                "look": "front", "props": ["bow", "wand"]},
    "juoh": {"short": "獣王", "side": "right", "scale": 1.0, "tilt": -4,
             "look": "side", "props": ["crown"]},
    "paripi_koumei": {"short": "パリピ\n孔明", "side": "left", "scale": 0.9, "tilt": -6,
                      "look": "front", "props": ["feather_fan"]},
    "mhrsb": {"short": "モンハン\nサンブレイク", "side": "right", "scale": 0.95, "tilt": 8,
              "look": "side", "props": ["race_helmet", "sword"]},
    "tenseioujo": {"short": "転生王女", "side": "left", "scale": 0.9, "tilt": 0,
                   "look": "up", "props": ["crown", "wand"]},
    "aobuta": {"short": "青ブタ", "side": "right", "scale": 0.9, "tilt": -6,
               "look": "front", "props": ["bunny_ears"]},
}

# 体の後ろに描く小物(体より先に描く)
BACK_PROPS = {"steam", "banner", "magic_floor"}


def _mochi_points(ox, oy, a, b):
    pts = []
    for i in range(90):
        t = i / 90 * 2 * math.pi
        c, s = math.cos(t), math.sin(t)
        x = ox + a * math.copysign(abs(c) ** 0.85, c)
        y = oy - b * s if s >= 0 else oy + 0.72 * b * abs(s) ** 0.55
        pts.append((x, y))
    return pts


# --- 小物(座標は体の中心 ox,oy と横半径 a・縦半径 b 基準) ---
def p_race_helmet(d, ox, oy, a, b, c, lw):
    d.pieslice([ox - a * 0.97, oy - b * 1.1, ox + a * 0.97, oy + b * 0.75], 180, 360, fill=c, outline=MOCHI_LINE, width=lw)
    d.line([(ox - a * 0.9, oy - b * 0.25), (ox + a * 0.9, oy - b * 0.25)], fill="#ffffff", width=lw * 2)
    d.arc([ox - a * 0.6, oy - b * 1.0, ox + a * 0.6, oy - b * 0.2], 200, 340, fill="#ffffff", width=lw * 2)


def p_boat(d, ox, oy, a, b, c, lw):
    hull = [(ox - a * 1.6, oy + b * 0.45), (ox + a * 1.75, oy + b * 0.45),
            (ox + a * 1.3, oy + b * 1.0), (ox - a * 1.35, oy + b * 1.0)]
    d.polygon(hull, fill="#ffffff", outline=MOCHI_LINE, width=lw)
    d.line([(ox - a * 1.45, oy + b * 0.7), (ox + a * 1.55, oy + b * 0.7)], fill=c, width=lw * 3)


def p_fire_helmet(d, ox, oy, a, b, c, lw):
    d.ellipse([ox - a * 1.18, oy - b * 0.5, ox + a * 1.18, oy - b * 0.18], fill=c, outline=MOCHI_LINE, width=lw)
    d.pieslice([ox - a * 0.82, oy - b * 1.2, ox + a * 0.82, oy + b * 0.05], 180, 360, fill=c, outline=MOCHI_LINE, width=lw)
    d.polygon([(ox, oy - b * 0.95), (ox + a * 0.18, oy - b * 0.8), (ox + a * 0.12, oy - b * 0.5),
               (ox - a * 0.12, oy - b * 0.5), (ox - a * 0.18, oy - b * 0.8)], fill="#ffe08a", outline=MOCHI_LINE, width=lw)


def p_hose(d, ox, oy, a, b, c, lw):
    pts = [(ox + a * 0.7, oy + b * 0.45), (ox + a * 1.15, oy + b * 0.55), (ox + a * 1.45, oy + b * 0.2),
           (ox + a * 1.6, oy - b * 0.25)]
    d.line(pts, fill="#3a3a3a", width=lw * 5, joint="curve")
    d.polygon([(ox + a * 1.5, oy - b * 0.25), (ox + a * 1.72, oy - b * 0.25),
               (ox + a * 1.66, oy - b * 0.55), (ox + a * 1.56, oy - b * 0.55)], fill="#c0c0c0", outline=MOCHI_LINE, width=lw)
    for k, (dx, dy, r) in enumerate([(1.62, -0.75, 0.07), (1.75, -0.95, 0.09), (1.55, -1.05, 0.06), (1.85, -1.2, 0.08)]):
        d.ellipse([ox + a * dx - a * r, oy + b * dy - a * r, ox + a * dx + a * r, oy + b * dy + a * r], fill="#9fdcff")


def p_conductor_cap(d, ox, oy, a, b, c, lw):
    d.rounded_rectangle([ox - a * 0.6, oy - b * 1.3, ox + a * 0.6, oy - b * 0.82], radius=int(a * 0.12),
                        fill="#2b3550", outline=MOCHI_LINE, width=lw)
    d.ellipse([ox - a * 0.78, oy - b * 0.92, ox + a * 0.78, oy - b * 0.7], fill="#1c2236", outline=MOCHI_LINE, width=lw)
    d.ellipse([ox - a * 0.12, oy - b * 1.2, ox + a * 0.12, oy - b * 0.95], fill=c)


def p_steam(d, ox, oy, a, b, c, lw):
    for dx, dy, r in [(0.75, -1.35, 0.26), (1.05, -1.75, 0.34), (0.55, -1.95, 0.28), (1.45, -2.05, 0.38)]:
        d.ellipse([ox + a * dx - a * r, oy + b * dy - a * r, ox + a * dx + a * r, oy + b * dy + a * r], fill="#e8e8e8")


def p_kabuto(d, ox, oy, a, b, c, lw):
    d.polygon([(ox - a * 1.05, oy - b * 0.3), (ox - a * 0.75, oy - b * 0.6), (ox - a * 0.6, oy - b * 0.2)],
              fill="#3a3a48", outline=MOCHI_LINE, width=lw)
    d.polygon([(ox + a * 1.05, oy - b * 0.3), (ox + a * 0.75, oy - b * 0.6), (ox + a * 0.6, oy - b * 0.2)],
              fill="#3a3a48", outline=MOCHI_LINE, width=lw)
    d.pieslice([ox - a * 0.9, oy - b * 1.15, ox + a * 0.9, oy + b * 0.2], 180, 360, fill="#3a3a48", outline=MOCHI_LINE, width=lw)
    # 前立て(シンプルなV字)
    for sx in (-1, 1):
        d.line([(ox, oy - b * 0.95), (ox + sx * a * 0.5, oy - b * 1.65)], fill=c, width=lw * 3)


def p_sword(d, ox, oy, a, b, c, lw):
    d.line([(ox + a * 0.75, oy + b * 0.35), (ox + a * 1.7, oy - b * 1.35)], fill="#dfe6ee", width=lw * 3)
    d.line([(ox + a * 0.75, oy + b * 0.35), (ox + a * 0.55, oy + b * 0.7)], fill="#3a2a20", width=lw * 4)
    d.line([(ox + a * 0.6, oy + b * 0.25), (ox + a * 0.95, oy + b * 0.45)], fill=c, width=lw * 3)


def p_banner(d, ox, oy, a, b, c, lw):
    # 体の後ろから立てたのぼり旗(頭の左うしろ)
    x = ox - a * 0.55
    d.line([(x, oy), (x, oy - b * 2.1)], fill="#4a3020", width=lw * 2)
    d.rectangle([x - a * 0.5, oy - b * 2.05, x, oy - b * 0.9], fill=c, outline=MOCHI_LINE, width=lw)
    d.line([(x - a * 0.55, oy - b * 2.05), (x + a * 0.05, oy - b * 2.05)], fill="#4a3020", width=lw * 2)


def p_nightcap(d, ox, oy, a, b, c, lw):
    d.polygon([(ox - a * 0.7, oy - b * 0.78), (ox + a * 0.7, oy - b * 0.78), (ox + a * 1.15, oy - b * 1.35),
               (ox + a * 0.2, oy - b * 1.5)], fill="#4b5fb0", outline=MOCHI_LINE, width=lw)
    d.rounded_rectangle([ox - a * 0.78, oy - b * 0.95, ox + a * 0.78, oy - b * 0.7], radius=int(a * 0.1),
                        fill="#ffffff", outline=MOCHI_LINE, width=lw)
    r = a * 0.16
    d.ellipse([ox + a * 1.15 - r, oy - b * 1.35 - r, ox + a * 1.15 + r, oy - b * 1.35 + r], fill="#ffffff", outline=MOCHI_LINE, width=lw)


def p_fedora(d, ox, oy, a, b, c, lw):
    d.ellipse([ox - a * 0.98, oy - b * 1.0, ox + a * 0.98, oy - b * 0.75], fill="#6b5a40", outline=MOCHI_LINE, width=lw)
    d.rounded_rectangle([ox - a * 0.55, oy - b * 1.4, ox + a * 0.55, oy - b * 0.86], radius=int(a * 0.2),
                        fill="#6b5a40", outline=MOCHI_LINE, width=lw)
    d.rectangle([ox - a * 0.55, oy - b * 1.05, ox + a * 0.55, oy - b * 0.92], fill=c)


def p_suitcase(d, ox, oy, a, b, c, lw):
    x0, y0 = ox + a * 1.0, oy - b * 0.05
    d.arc([x0 + a * 0.22, y0 - b * 0.3, x0 + a * 0.62, y0 + b * 0.1], 180, 360, fill=MOCHI_LINE, width=lw * 2)
    d.rounded_rectangle([x0, y0, x0 + a * 0.85, y0 + b * 1.0], radius=int(a * 0.1), fill="#a0522d", outline=MOCHI_LINE, width=lw)
    for k in (0.25, 0.6):
        d.line([(x0 + a * 0.85 * k, y0), (x0 + a * 0.85 * k, y0 + b * 1.0)], fill=c, width=lw * 2)


def p_bouquet(d, ox, oy, a, b, c, lw):
    for dx, dy, col in [(1.05, -0.55, "#ff6f91"), (1.4, -0.45, "#ffd166"), (1.25, -0.8, "#ff9fb2"),
                        (0.9, -0.85, "#ffffff"), (1.55, -0.75, "#ff6f91")]:
        r = a * 0.2
        d.ellipse([ox + a * dx - r, oy + b * dy - r, ox + a * dx + r, oy + b * dy + r], fill=col, outline=MOCHI_LINE, width=lw)
    d.polygon([(ox + a * 0.75, oy - b * 0.4), (ox + a * 1.7, oy - b * 0.4), (ox + a * 0.95, oy + b * 0.55)],
              fill="#8fd18f", outline=MOCHI_LINE, width=lw)


def p_tophat(d, ox, oy, a, b, c, lw):
    d.ellipse([ox - a * 0.8, oy - b * 1.0, ox + a * 0.8, oy - b * 0.78], fill="#222222", outline=MOCHI_LINE, width=lw)
    d.rectangle([ox - a * 0.48, oy - b * 1.75, ox + a * 0.48, oy - b * 0.9], fill="#222222", outline=MOCHI_LINE, width=lw)
    d.rectangle([ox - a * 0.48, oy - b * 1.12, ox + a * 0.48, oy - b * 0.95], fill=c)


def p_lily_head(d, ox, oy, a, b, c, lw):
    cx, cy = ox + a * 0.45, oy - b * 0.92
    for i in range(9):
        ang = -math.pi / 2 + (i - 4) * 0.33
        x2, y2 = cx + math.cos(ang) * a * 0.7, cy + math.sin(ang) * b * 0.75
        mx, my = cx + math.cos(ang) * a * 0.35, cy + math.sin(ang) * b * 0.5
        d.line([(cx, cy), (mx, my), (x2, y2)], fill="#e0233a", width=lw * 2, joint="curve")
        r = a * 0.04
        d.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill="#e0233a")
    r = a * 0.1
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#c0182c", outline=MOCHI_LINE, width=lw)


def p_goggles(d, ox, oy, a, b, c, lw):
    y = oy - b * 0.62
    d.line([(ox - a * 0.95, y), (ox + a * 0.95, y)], fill="#333344", width=lw * 3)
    for sx in (-1, 1):
        d.rounded_rectangle([ox + sx * a * 0.08 - (a * 0.5 if sx < 0 else 0), y - b * 0.18,
                             ox + sx * a * 0.08 + (a * 0.5 if sx > 0 else 0), y + b * 0.18],
                            radius=int(a * 0.1), fill=c, outline=MOCHI_LINE, width=lw)


def p_wizard_hat(d, ox, oy, a, b, c, lw):
    d.polygon([(ox - a * 0.68, oy - b * 0.82), (ox + a * 0.68, oy - b * 0.82), (ox + a * 0.3, oy - b * 2.0)],
              fill="#3b3b8f", outline=MOCHI_LINE, width=lw)
    d.ellipse([ox - a * 0.95, oy - b * 0.98, ox + a * 0.95, oy - b * 0.72], fill="#3b3b8f", outline=MOCHI_LINE, width=lw)
    d.polygon(_star(ox + a * 0.1, oy - b * 1.3, a * 0.14), fill=c)


def p_magic_floor(d, ox, oy, a, b, c, lw):
    for k in (1.0, 0.72):
        d.ellipse([ox - a * 1.7 * k, oy + b * 0.75 - b * 0.4 * k, ox + a * 1.7 * k, oy + b * 0.75 + b * 0.4 * k],
                  outline=c, width=lw * 2)
    # 稲妻
    x, y = ox - a * 1.5, oy - b * 1.5
    d.polygon([(x, y), (x + a * 0.35, y), (x + a * 0.15, y + b * 0.55), (x + a * 0.4, y + b * 0.55),
               (x - a * 0.05, y + b * 1.35), (x + a * 0.05, y + b * 0.8), (x - a * 0.18, y + b * 0.8)], fill="#ffe27a")


def p_scarf(d, ox, oy, a, b, c, lw):
    d.rounded_rectangle([ox - a * 0.92, oy + b * 0.28, ox + a * 0.92, oy + b * 0.5], radius=int(a * 0.1),
                        fill=c, outline=MOCHI_LINE, width=lw)
    d.polygon([(ox + a * 0.35, oy + b * 0.45), (ox + a * 0.65, oy + b * 0.45), (ox + a * 0.75, oy + b * 0.95),
               (ox + a * 0.45, oy + b * 0.95)], fill=c, outline=MOCHI_LINE, width=lw)


def p_bow(d, ox, oy, a, b, c, lw):
    cx, cy = ox - a * 0.45, oy - b * 0.92
    d.polygon([(cx, cy), (cx - a * 0.35, cy - b * 0.25), (cx - a * 0.35, cy + b * 0.2)], fill="#ff6f91", outline=MOCHI_LINE, width=lw)
    d.polygon([(cx, cy), (cx + a * 0.35, cy - b * 0.25), (cx + a * 0.35, cy + b * 0.2)], fill="#ff6f91", outline=MOCHI_LINE, width=lw)
    r = a * 0.09
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#ff4d79", outline=MOCHI_LINE, width=lw)


def p_mic(d, ox, oy, a, b, c, lw):
    d.line([(ox + a * 0.75, oy + b * 0.35), (ox + a * 1.2, oy - b * 0.35)], fill="#333333", width=lw * 4)
    r = a * 0.2
    cx, cy = ox + a * 1.28, oy - b * 0.52
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill="#c8c8d0", outline=MOCHI_LINE, width=lw)
    d.line([(cx - r * 0.7, cy), (cx + r * 0.7, cy)], fill="#888888", width=lw)
    for sx, sy, rr in [(1.7, -1.1, 0.12), (1.9, -0.6, 0.08)]:
        d.polygon(_star(ox + a * sx, oy + b * sy, a * rr * 1.5), fill=c)


def p_wand(d, ox, oy, a, b, c, lw):
    # 先に星がついた細い杖(汎用の魔法の杖)
    d.line([(ox + a * 0.75, oy + b * 0.4), (ox + a * 1.45, oy - b * 0.95)], fill="#8b5a2b", width=lw * 3)
    d.polygon(_star(ox + a * 1.5, oy - b * 1.05, a * 0.26), fill=c, outline=MOCHI_LINE, width=lw)


def p_crown(d, ox, oy, a, b, c, lw):
    # ぎざぎざ3山の単純な王冠
    y0, y1 = oy - b * 0.78, oy - b * 1.35
    pts = [(ox - a * 0.55, y0), (ox - a * 0.6, y1), (ox - a * 0.3, oy - b * 1.05), (ox, y1 - b * 0.1),
           (ox + a * 0.3, oy - b * 1.05), (ox + a * 0.6, y1), (ox + a * 0.55, y0)]
    d.polygon(pts, fill="#f2c14e", outline=MOCHI_LINE, width=lw)
    r = a * 0.07
    for dx in (-0.6, 0.0, 0.6):
        yy = y1 - (b * 0.1 if dx == 0.0 else 0)
        d.ellipse([ox + a * dx - r, yy - r, ox + a * dx + r, yy + r], fill=c, outline=MOCHI_LINE, width=lw)


def p_feather_fan(d, ox, oy, a, b, c, lw):
    # 羽根うちわ(扇形+持ち手)
    hx, hy = ox + a * 0.85, oy + b * 0.35
    d.line([(hx, hy), (hx + a * 0.3, hy - b * 0.55)], fill="#6b4a2a", width=lw * 3)
    fx, fy = hx + a * 0.3, hy - b * 0.55
    d.pieslice([fx - a * 0.6, fy - b * 1.2, fx + a * 0.6, fy + b * 0.3], 200, 340, fill="#ffffff", outline=MOCHI_LINE, width=lw)
    for k in range(5):
        ang = math.radians(205 + k * 32.5)
        d.line([(fx, fy), (fx + math.cos(ang) * a * 0.55, fy + math.sin(ang) * b * 0.7)], fill=c, width=lw)


def p_bunny_ears(d, ox, oy, a, b, c, lw):
    # カチューシャのうさ耳(汎用の仮装小物)
    d.arc([ox - a * 0.8, oy - b * 1.05, ox + a * 0.8, oy - b * 0.45], 200, 340, fill="#333333", width=lw * 3)
    for sx, rot in ((-1, -12), (1, 12)):
        cx = ox + sx * a * 0.32
        d.ellipse([cx - a * 0.16, oy - b * 1.85, cx + a * 0.16, oy - b * 0.85], fill="#333333", outline=MOCHI_LINE, width=lw)
        d.ellipse([cx - a * 0.08, oy - b * 1.7, cx + a * 0.08, oy - b * 1.0], fill=c)


PROPS = {
    "wand": p_wand, "crown": p_crown, "feather_fan": p_feather_fan, "bunny_ears": p_bunny_ears,
    "race_helmet": p_race_helmet, "boat": p_boat, "fire_helmet": p_fire_helmet, "hose": p_hose,
    "conductor_cap": p_conductor_cap, "steam": p_steam, "kabuto": p_kabuto, "sword": p_sword,
    "banner": p_banner, "nightcap": p_nightcap, "fedora": p_fedora, "suitcase": p_suitcase,
    "bouquet": p_bouquet, "tophat": p_tophat, "lily_head": p_lily_head, "goggles": p_goggles,
    "wizard_hat": p_wizard_hat, "magic_floor": p_magic_floor, "scarf": p_scarf, "bow": p_bow, "mic": p_mic,
}


def draw_mochi(size: int, accent: str, props: list[str], look: str) -> Image.Image:
    """マスコット1体を透明背景の正方形画像として描く(右向き基準)。"""
    L = size
    layer = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    a = L * 0.2           # 体の横半径
    b = a * 0.8           # 体の縦半径
    ox, oy = L * 0.42, L * 0.56
    lw = max(2, int(a * 0.035))

    for p in props:
        if p in BACK_PROPS:
            PROPS[p](d, ox, oy, a, b, accent, lw)

    # 足
    for sx in (-1, 1):
        fx, fy = ox + sx * a * 0.45, oy + b * 0.68
        d.ellipse([fx - a * 0.2, fy - b * 0.12, fx + a * 0.2, fy + b * 0.12], fill=MOCHI_BODY, outline=MOCHI_LINE, width=lw)
    # 体
    d.polygon(_mochi_points(ox, oy, a, b), fill=MOCHI_BODY, outline=MOCHI_LINE, width=lw)
    # 顔
    ex_off = {"front": 0.0, "side": 0.12, "up": 0.0}[look]
    ey_off = {"front": 0.0, "side": 0.0, "up": -0.18}[look]
    er = a * 0.085
    for sx in (-1, 1):
        ex, ey = ox + sx * a * 0.33 + a * ex_off, oy - b * 0.05 + b * ey_off
        d.ellipse([ex - er, ey - er * 1.2, ex + er, ey + er * 1.2], fill="#2a1a14")
        hr = er * 0.35
        d.ellipse([ex - er * 0.35 - hr, ey - er * 0.5 - hr, ex - er * 0.35 + hr, ey - er * 0.5 + hr], fill="#ffffff")
        cx, cy = ox + sx * a * 0.6 + a * ex_off, oy + b * 0.18
        d.ellipse([cx - a * 0.13, cy - b * 0.07, cx + a * 0.13, cy + b * 0.07], fill=MOCHI_CHEEK)
    mx, my = ox + a * ex_off, oy + b * 0.2 + b * ey_off * 0.5
    d.arc([mx - a * 0.1, my - b * 0.1, mx + a * 0.1, my + b * 0.08], 20, 160, fill="#2a1a14", width=lw)

    for p in props:
        if p not in BACK_PROPS:
            PROPS[p](d, ox, oy, a, b, accent, lw)
    return layer


def make_mascot_badge(machine_id: str, name: str, style: dict, mcfg: dict) -> Path:
    W, H = WIDTH * SS, HEIGHT * SS
    top, bottom = style["colors"]
    accent = style["accent"]
    side = mcfg.get("side", "right")

    base = _gradient(W, H, top, bottom).convert("RGBA")

    # 背景の図形(マスコット側に寄るよう、マスコットが左なら左右反転)
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    MOTIFS.get(style.get("motif", "generic"), m_generic)(ImageDraw.Draw(layer), W, H, accent)
    if side == "left":
        layer = layer.transpose(Image.FLIP_LEFT_RIGHT)
    base = Image.alpha_composite(base, layer)

    # マスコット
    msize = int(H * 1.4 * mcfg.get("scale", 1.0))
    mochi = draw_mochi(msize, accent, mcfg.get("props", []), mcfg.get("look", "front"))
    if side == "left":
        mochi = mochi.transpose(Image.FLIP_LEFT_RIGHT)
    mochi = mochi.rotate(mcfg.get("tilt", 0), resample=Image.BICUBIC)
    # 影
    cx = int(W * (0.73 if side == "right" else 0.27))
    ground = int(H * 0.93)
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse([cx - msize * 0.28, ground - msize * 0.04, cx + msize * 0.28, ground + msize * 0.04],
                               fill=(0, 0, 0, 90))
    base = Image.alpha_composite(base, sh.filter(ImageFilter.GaussianBlur(10)))
    # 体の下端(足)が地面に来るよう配置
    px = cx - int(msize * (0.42 if side == "right" else 0.58))
    py = ground - int(msize * 0.56 + msize * 0.2 * 0.8 * 0.8)
    base.paste(mochi, (px, py), mochi)

    # 文字(マスコットと反対側)
    kind, rest = split_kind(name)
    lines = mcfg.get("short", style["short"]).split("\n")
    x0, x1 = (int(W * 0.04), int(W * 0.52)) if side == "right" else (int(W * 0.48), int(W * 0.96))
    probe = ImageDraw.Draw(base)
    area_top, area_bottom = int(H * 0.2), int(H * 0.8)
    font, line_h = _fit_font(probe, lines, x1 - x0, area_bottom - area_top, start=int(H * 0.3))
    total_h = line_h * len(lines)
    y0 = area_top + (area_bottom - area_top - total_h) // 2 - int(H * 0.03)

    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text)
    stroke = max(4, font.size // 12)
    for i, ln in enumerate(lines):
        bbox = td.textbbox((0, 0), ln, font=font)
        x = x0 + ((x1 - x0) - (bbox[2] - bbox[0])) // 2 - bbox[0]
        y = y0 + i * line_h - bbox[1] + (line_h - (bbox[3] - bbox[1])) // 2
        sd.text((x + stroke, y + stroke * 1.5), ln, font=font, fill=(0, 0, 0, 200),
                stroke_width=stroke, stroke_fill=(0, 0, 0, 200))
        td.text((x, y), ln, font=font, fill=(255, 255, 255, 255),
                stroke_width=stroke, stroke_fill=(*hex_rgb(bottom), 255))
    base = Image.alpha_composite(base, shadow.filter(ImageFilter.GaussianBlur(stroke * 1.5)))
    base = Image.alpha_composite(base, text)

    d = ImageDraw.Draw(base)
    # 種別ラベル(文字側の上)
    lab_font = load_font(FONT_BOLD_CANDIDATES, int(H * 0.07))
    lb = d.textbbox((0, 0), kind, font=lab_font)
    pad_x, pad_y = int(H * 0.03), int(H * 0.015)
    lw_ = (lb[2] - lb[0]) + pad_x * 2
    lx = x0 + ((x1 - x0) - lw_) // 2
    ly = int(H * 0.06)
    d.rounded_rectangle([lx, ly, lx + lw_, ly + (lb[3] - lb[1]) + pad_y * 2], radius=int(H * 0.03), fill=rgba(accent, 235))
    d.text((lx + pad_x - lb[0], ly + pad_y - lb[1]), kind, font=lab_font, fill=(*hex_rgb(bottom), 255))

    # 正式名(文字側の下、小さく)
    sub_size = int(H * 0.06)
    while sub_size > 16:
        sub_font = load_font(FONT_REGULAR_CANDIDATES, sub_size)
        sb = d.textbbox((0, 0), rest, font=sub_font, stroke_width=3)
        if sb[2] - sb[0] <= (x1 - x0):
            break
        sub_size -= 2
    sx = x0 + ((x1 - x0) - (sb[2] - sb[0])) // 2 - sb[0]
    sy = int(H * 0.86) - sb[1]
    d.text((sx, sy), rest, font=sub_font, fill=(240, 240, 240, 255), stroke_width=3, stroke_fill=(0, 0, 0, 200))

    out = base.convert("RGB").resize((WIDTH, HEIGHT), Image.LANCZOS)
    MASCOT_OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = MASCOT_OUT_DIR / f"{machine_id}.jpg"
    out.save(out_path, "JPEG", quality=JPEG_QUALITY)
    return out_path


def build_mascot(machine_id: str, profiles: dict[str, str]) -> Path:
    if machine_id not in profiles:
        raise SystemExit(f"profiles/ に id={machine_id} の機種がありません")
    name = profiles[machine_id]
    style = BADGES.get(machine_id) or auto_style(machine_id, name)
    mcfg = MASCOTS.get(machine_id) or {"short": style["short"], "side": "right", "props": []}
    return make_mascot_badge(machine_id, name, style, mcfg)


def main() -> None:
    args = sys.argv[1:]
    style = "text"
    if "--style" in args:
        i = args.index("--style")
        if i + 1 >= len(args) or args[i + 1] not in ("text", "mascot"):
            raise SystemExit("--style は text か mascot を指定してください")
        style = args[i + 1]
        del args[i:i + 2]
    if len(args) != 1:
        print(__doc__)
        raise SystemExit(1)
    profiles = load_profiles()
    targets = list(profiles) if args[0] == "--all" else [args[0]]
    builder = build_mascot if style == "mascot" else build
    for mid in targets:
        out = builder(mid, profiles)
        print(f"{mid} -> {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
