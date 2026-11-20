"""brute-paint render SCRIPT [--out DIR] / brute-paint color IMAGE --box x0,y0,x1,y1"""

from __future__ import annotations

import argparse
import sys
import time
import traceback
from pathlib import Path

from brute_paint.color import median_color, parse_box
from brute_paint.render import RenderError, render


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="brute-paint")
    sub = parser.add_subparsers(dest="command", required=True)
    p_render = sub.add_parser("render", help="draw(c) を実行して確認用の画像を書く")
    p_render.add_argument("script", type=Path)
    p_render.add_argument("--out", type=Path, default=None, help="出力先（既定はスクリプトの隣の out/）")
    p_color = sub.add_parser("color", help="画像の範囲の代表色を #rrggbb で出す")
    p_color.add_argument("image", type=Path)
    p_color.add_argument("--box", required=True, help="x0,y0,x1,y1（画素の座標。x1, y1 は含まない）")
    args = parser.parse_args(argv)

    if args.command == "render":
        start = time.perf_counter()
        try:
            result = render(args.script, args.out)
        except RenderError as e:
            print(f"エラー: {e}", file=sys.stderr)
            return 1
        except Exception:  # noqa: BLE001 - the drawing script can raise anything; show its traceback
            # An error inside the drawing script: show where, so the drawer can fix that line.
            traceback.print_exc()
            return 1
        for path in result.written:
            print(path)
        print(f"{time.perf_counter() - start:.1f}s")
        return 0

    try:
        print(median_color(args.image, parse_box(args.box)))
    except (ValueError, FileNotFoundError) as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
