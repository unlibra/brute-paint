"""Run a drawing script and write the views the drawer looks at between attempts.

A drawing script defines ``draw(c: Canvas) -> None`` and may set ``SEED: int``.
Everything is written to ``out/`` next to the script:

- sheet.png      400px, circle crop, 48px actual size and 48px at 2x, side by side
- form.png       400px in grayscale and mirrored, for checking shapes and values
- final_400.png  the icon itself
- iter/NNN.png   a copy of every sheet, never overwritten
- ref_sheet.png  only when character.md sits next to the script
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from brute_paint.canvas import Canvas

TOOL_ROOT = Path(__file__).resolve().parents[2]
MAX_SHEET_WIDTH = 1568
MAX_REFS = 5
GAP = 16
BG = (230, 234, 238)
_FONTS = ("meiryo.ttc", "YuGothM.ttc", "msgothic.ttc")


class RenderError(Exception):
    """A problem the user can fix; reported without a traceback."""


@dataclass(frozen=True)
class Result:
    out_dir: Path
    written: list[Path]


def ensure_outside_tool(paths: list[Path], root: Path = TOOL_ROOT) -> None:
    """Characters and their outputs never go into the public tool repository."""
    for p in paths:
        if p.resolve().is_relative_to(root.resolve()):
            raise RenderError(f"公開リポジトリの中には書けません: {p}")


def _load_script(script: Path):
    spec = importlib.util.spec_from_file_location(f"brute_paint_script_{abs(hash(script))}", script)
    if spec is None or spec.loader is None:
        raise RenderError(f"スクリプトを読めません: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(script.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(script.parent))
    draw = getattr(module, "draw", None)
    if not callable(draw):
        raise RenderError(f"draw(c) がありません: {script}")
    seed = getattr(module, "SEED", 0)
    if not isinstance(seed, int):
        raise RenderError(f"SEED は整数にしてください: {seed!r}")
    return draw, seed


def _font(size: int) -> ImageFont.ImageFont:
    for name in _FONTS:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def _sheet(icon: Image.Image) -> Image.Image:
    big = icon.resize((400, 400), Image.LANCZOS)
    small = icon.resize((48, 48), Image.LANCZOS)
    mask = Image.new("L", (400, 400), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, 399, 399), fill=255)
    circle = Image.new("RGB", (400, 400), BG)
    circle.paste(big, (0, 0), mask)
    width = 400 + GAP + 400 + GAP + 48 + GAP + 96
    sheet = Image.new("RGB", (width, 400), BG)
    x = 0
    for part in (big, circle, small, small.resize((96, 96), Image.NEAREST)):
        sheet.paste(part, (x, 0))
        x += part.width + GAP
    return sheet


def _form(icon: Image.Image) -> Image.Image:
    big = icon.resize((400, 400), Image.LANCZOS)
    form = Image.new("RGB", (400 + GAP + 400, 400), BG)
    form.paste(big.convert("L").convert("RGB"), (0, 0))
    form.paste(big.transpose(Image.FLIP_LEFT_RIGHT), (400 + GAP, 0))
    return form


def _next_iter(iter_dir: Path) -> Path:
    numbers = [int(p.stem) for p in iter_dir.glob("*.png") if re.fullmatch(r"\d+", p.stem)]
    return iter_dir / f"{max(numbers, default=0) + 1:03d}.png"


def _sections(markdown: str) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current = None
    for line in markdown.splitlines():
        heading = re.match(r"#+\s+(.+?)\s*$", line)
        if heading:
            current = heading.group(1)
            sections[current] = []
        elif current is not None and line.strip():
            sections[current].append(line.strip())
    return sections


def _bullet(line: str) -> str | None:
    m = re.match(r"[-*]\s+`?([^`]+?)`?\s*$", line)
    return m.group(1) if m else None


def _cached_ref(path: Path, cache_dir: Path) -> Image.Image:
    key = hashlib.sha1(f"{path.resolve()}|{path.stat().st_mtime_ns}".encode()).hexdigest()[:16]
    cached = cache_dir / f"{key}.png"
    if cached.exists():
        return Image.open(cached).convert("RGB")
    img = Image.open(path).convert("RGB")
    img.thumbnail((400, 400), Image.LANCZOS)
    cache_dir.mkdir(parents=True, exist_ok=True)
    img.save(cached)
    return img


def _wrap(text: str, font: ImageFont.ImageFont, width: int) -> list[str]:
    lines, line = [], ""
    for ch in text:
        if font.getlength(line + ch) > width:
            lines.append(line)
            line = ch
        else:
            line += ch
    return lines + ([line] if line else [])


def _ref_sheet(icon: Image.Image, character: Path, cache_dir: Path) -> Image.Image:
    sections = _sections(character.read_text(encoding="utf-8"))
    ref_paths = [p for p in (_bullet(line) for line in sections.get("参考画像", [])) if p][:MAX_REFS]
    refs = []
    for rel in ref_paths:
        path = (character.parent / rel)
        if not path.is_file():
            raise RenderError(f"参考画像が見つかりません: {rel}（{character} から）")
        refs.append(_cached_ref(path, cache_dir))
    thumb_w = (MAX_SHEET_WIDTH - 400 - GAP * (len(refs) + 1)) // max(len(refs), 1)
    thumb_w = min(thumb_w, 400)
    thumbs = []
    for ref in refs:
        t = ref.copy()
        t.thumbnail((thumb_w, 400), Image.LANCZOS)
        thumbs.append(t)
    font = _font(18)
    keep = [line.lstrip("-* ").strip() for line in sections.get("変えない特徴", [])]
    text_lines = []
    for item in keep:
        text_lines += _wrap(f"・{item}", font, MAX_SHEET_WIDTH - 2 * GAP)
    text_h = (len(text_lines) + 1) * 26 + GAP if text_lines else 0
    width = min(400 + sum(t.width + GAP for t in thumbs), MAX_SHEET_WIDTH)
    sheet = Image.new("RGB", (max(width, 400), 400 + text_h), BG)
    sheet.paste(icon.resize((400, 400), Image.LANCZOS), (0, 0))
    x = 400 + GAP
    for t in thumbs:
        sheet.paste(t, (x, 0))
        x += t.width + GAP
    if text_lines:
        d = ImageDraw.Draw(sheet)
        y = 400 + GAP
        d.text((GAP, y), "変えない特徴", font=font, fill=(40, 40, 40))
        for line in text_lines:
            y += 26
            d.text((GAP, y), line, font=font, fill=(40, 40, 40))
    return sheet


def render(script: Path, out_dir: Path | None = None) -> Result:
    script = Path(script)
    out = Path(out_dir) if out_dir is not None else script.parent / "out"
    ensure_outside_tool([script, out])
    if not script.is_file():
        raise RenderError(f"スクリプトがありません: {script}")
    draw, seed = _load_script(script)
    canvas = Canvas(seed)
    draw(canvas)
    icon = Image.fromarray(canvas.composite(), "RGBA").convert("RGB")

    out.mkdir(parents=True, exist_ok=True)
    written = []
    sheet_path = out / "sheet.png"
    _sheet(icon).save(sheet_path)
    written.append(sheet_path)
    _form(icon).save(out / "form.png")
    written.append(out / "form.png")
    final = out / "final_400.png"
    icon.resize((400, 400), Image.LANCZOS).save(final)
    written.append(final)
    iter_dir = out / "iter"
    iter_dir.mkdir(exist_ok=True)
    iter_path = _next_iter(iter_dir)
    shutil.copyfile(sheet_path, iter_path)
    written.append(iter_path)

    character = script.parent / "character.md"
    if character.is_file():
        ref_path = out / "ref_sheet.png"
        _ref_sheet(icon, character, out / "ref_cache").save(ref_path)
        written.append(ref_path)
    return Result(out, written)
