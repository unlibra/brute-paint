"""Read a colour off a reference image as text. The image itself never reaches the canvas."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image


def parse_box(text: str) -> tuple[int, int, int, int]:
    parts = text.split(",")
    if len(parts) != 4:
        raise ValueError(f"--box は x0,y0,x1,y1 の形です: {text!r}")
    try:
        x0, y0, x1, y1 = (int(p) for p in parts)
    except ValueError:
        raise ValueError(f"--box は整数で書いてください: {text!r}") from None
    return x0, y0, x1, y1


def median_color(image: Path, box: tuple[int, int, int, int]) -> str:
    """Median colour of the box (x0, y0 inclusive; x1, y1 exclusive) as '#rrggbb'."""
    x0, y0, x1, y1 = box
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"範囲は x0 < x1、y0 < y1 にしてください: {box}")
    with Image.open(image) as img:
        width, height = img.size
        if x0 < 0 or y0 < 0 or x1 > width or y1 > height:
            raise ValueError(f"範囲が画像（{width}x{height}）の外に出ています: {box}")
        pixels = np.asarray(img.convert("RGB").crop((x0, y0, x1, y1))).reshape(-1, 3)
    r, g, b = (int(v) for v in np.median(pixels, axis=0).round())
    return f"#{r:02x}{g:02x}{b:02x}"
