"""機種ヘッダー画像を、全機種共通サイズに加工してassets/へ書き出す。

新しい機種のヘッダー画像を追加するときは、毎回このスクリプトを通すこと。
機種ごとに元画像の解像度・縦横比がバラバラでも、この加工を通せばカードの
高さが揃う(picker.pyはst.image(..., use_container_width=True)で幅を
コンテナ幅に合わせるだけなので、縦横比が機種ごとに違うとカードの高さが
バラつく)。

使い方:
    python scripts/process_header_image.py <元画像のパス> <machine_id>

<machine_id>は対象profileの`id`と一致させること(例: monkey_turn_v)。
出力は assets/<machine_id>.jpg に保存され、この相対パスをそのまま
profiles/<machine_id>.yamlのheader_imageに設定する。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

# 全機種共通のヘッダー画像サイズ(2:1)。カード幅に合わせて表示されるため、
# 極端に高さのある画像だと機種選択画面が縦に間延びする。将来サイズを変える
# 場合はこの定数だけ変更し、既存画像も本スクリプトで再生成すること。
TARGET_WIDTH = 800
TARGET_HEIGHT = 400
JPEG_QUALITY = 85

ASSETS_DIR = Path(__file__).parent.parent / "assets"


def process(src_path: Path, machine_id: str) -> Path:
    im = Image.open(src_path).convert("RGB")

    # アスペクト比をTARGET_WIDTH:TARGET_HEIGHTに合わせて中央クロップしてから
    # リサイズする(cover方式。引き伸ばしで歪ませない)。
    target_ratio = TARGET_WIDTH / TARGET_HEIGHT
    src_ratio = im.width / im.height

    if src_ratio > target_ratio:
        # 元画像の方が横長 → 左右を切る
        new_width = round(im.height * target_ratio)
        left = (im.width - new_width) // 2
        im = im.crop((left, 0, left + new_width, im.height))
    elif src_ratio < target_ratio:
        # 元画像の方が縦長 → 上下を切る
        new_height = round(im.width / target_ratio)
        top = (im.height - new_height) // 2
        im = im.crop((0, top, im.width, top + new_height))

    im = im.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)

    ASSETS_DIR.mkdir(exist_ok=True)
    out_path = ASSETS_DIR / f"{machine_id}.jpg"
    im.save(out_path, "JPEG", quality=JPEG_QUALITY)
    return out_path


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        raise SystemExit(1)
    src_path = Path(sys.argv[1])
    machine_id = sys.argv[2]
    out_path = process(src_path, machine_id)
    print(f"{src_path} -> {out_path} ({TARGET_WIDTH}x{TARGET_HEIGHT})")


if __name__ == "__main__":
    main()
