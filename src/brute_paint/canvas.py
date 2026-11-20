"""Canvas and layers.

The canvas is an 800px square worked on at 2x of the largest display size (400px).
Layers are composited bottom to top. A layer can be clipped to a layer below it,
the way painting software clips a shadow layer to its base colour layer.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import skia

SIZE = 800

Blend = Literal["normal", "multiply", "screen"]
_BLEND_MODES = {
    "normal": skia.BlendMode.kSrcOver,
    "multiply": skia.BlendMode.kMultiply,
    "screen": skia.BlendMode.kScreen,
}
_HEX = re.compile(r"#[0-9a-fA-F]{6}")

Point = tuple[float, float]


def rgb(hex_color: str, alpha: int = 255) -> int:
    """'#rrggbb' (and an optional alpha 0-255) to a colour value."""
    if not _HEX.fullmatch(hex_color):
        raise ValueError(f"色は #rrggbb の形で書いてください: {hex_color!r}")
    if not 0 <= alpha <= 255:
        raise ValueError(f"alpha は 0〜255 です: {alpha}")
    h = hex_color[1:]
    return skia.ColorSetARGB(alpha, int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


@dataclass(frozen=True)
class Gradient:
    shader: skia.Shader


def _smooth(points: np.ndarray, samples: int = 12) -> np.ndarray:
    """Catmull-Rom through the given points (ends included)."""
    p = np.concatenate([points[:1], points, points[-1:]])
    out = []
    for i in range(1, len(p) - 2):
        p0, p1, p2, p3 = p[i - 1], p[i], p[i + 1], p[i + 2]
        for t in np.linspace(0, 1, samples, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(
                0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)
            )
    out.append(p[-2])
    return np.array(out, dtype=float)


def _polygon(points: np.ndarray) -> skia.Path:
    path = skia.Path()
    path.moveTo(*points[0])
    for x, y in points[1:]:
        path.lineTo(float(x), float(y))
    path.close()
    return path


def _as_points(points: Sequence[Point], minimum: int, what: str) -> np.ndarray:
    arr = np.asarray(points, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < minimum:
        raise ValueError(f"{what}には点が{minimum}つ以上要ります")
    return arr


class Layer:
    def __init__(self, canvas: Canvas, name: str, blend: Blend, opacity: float, clip: Layer | None):
        self.canvas = canvas
        self.name = name
        self.blend = blend
        self.opacity = opacity
        self.clip = clip
        self._surface = skia.Surface(SIZE, SIZE)
        self._surface.getCanvas().clear(skia.ColorTRANSPARENT)

    def _paint(self, color: int | None, gradient: Gradient | None, blur: float) -> skia.Paint:
        if (color is None) == (gradient is None):
            raise ValueError("color と gradient のどちらか一方を指定してください")
        paint = skia.Paint(AntiAlias=True)
        if gradient is not None:
            paint.setShader(gradient.shader)
        else:
            paint.setColor(color)
        if blur < 0:
            raise ValueError(f"blur は 0 以上です: {blur}")
        if blur:
            paint.setMaskFilter(skia.MaskFilter.MakeBlur(skia.kNormal_BlurStyle, blur))
        return paint

    def fill(self, points: Sequence[Point], color: int | None = None, *, gradient: Gradient | None = None,
             blur: float = 0) -> None:
        """Fill the smooth closed shape through the points."""
        arr = _as_points(points, 3, "fill")
        smooth = _smooth(np.concatenate([arr, arr[:1]]))
        self._surface.getCanvas().drawPath(_polygon(smooth), self._paint(color, gradient, blur))

    def ellipse(self, cx: float, cy: float, rx: float, ry: float, color: int | None = None, *,
                gradient: Gradient | None = None, blur: float = 0) -> None:
        if rx <= 0 or ry <= 0:
            raise ValueError("rx と ry は 0 より大きくしてください")
        self._surface.getCanvas().drawOval(skia.Rect(cx - rx, cy - ry, cx + rx, cy + ry),
                                           self._paint(color, gradient, blur))

    def stroke(self, points: Sequence[Point], width: float, color: int, *,
               taper: tuple[float, float] = (0.25, 0.35), press: Sequence[float] | None = None,
               jitter: float = 0.0) -> None:
        """A line drawn like a pen: thin at the ink-in, thin at the ink-out.

        taper: the fraction of the line spent thickening at the start and thinning at the end.
        press: pen pressure along the line (multiplies the width), spread evenly from start to end.
        jitter: hand wobble in px. It comes from the canvas seed, so the same script draws the same line.
        """
        arr = _as_points(points, 2, "stroke")
        if width <= 0:
            raise ValueError(f"width は 0 より大きくしてください: {width}")
        t_in, t_out = taper
        if not (0 <= t_in <= 1 and 0 <= t_out <= 1):
            raise ValueError(f"taper は 0〜1 の組です: {taper}")
        if jitter < 0:
            raise ValueError(f"jitter は 0 以上です: {jitter}")
        if jitter:
            arr = arr + self.canvas.rng.normal(0, jitter, arr.shape)
        line = _smooth(arr)
        n = len(line)
        tangent = np.gradient(line, axis=0)
        normal = np.stack([-tangent[:, 1], tangent[:, 0]], axis=1)
        normal /= np.linalg.norm(normal, axis=1, keepdims=True) + 1e-9
        t = np.linspace(0, 1, n)
        w = np.ones(n)
        if t_in:
            w = np.minimum(w, np.clip(t / t_in, 0, 1) ** 0.7)
        if t_out:
            w = np.minimum(w, np.clip((1 - t) / t_out, 0, 1) ** 0.7)
        if press is not None:
            if len(press) == 0:
                raise ValueError("press は空にできません")
            w = w * np.interp(t, np.linspace(0, 1, len(press)), np.asarray(press, dtype=float))
        half = np.maximum(w * width / 2, 0.15)[:, None]
        outline = np.concatenate([line + normal * half, (line - normal * half)[::-1]])
        self._surface.getCanvas().drawPath(_polygon(outline), skia.Paint(Color=color, AntiAlias=True))

    def image(self) -> skia.Image:
        return self._surface.makeImageSnapshot()


class Canvas:
    def __init__(self, seed: int = 0):
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.layers: list[Layer] = []

    def layer(self, name: str, blend: Blend = "normal", opacity: float = 1.0, clip: Layer | None = None) -> Layer:
        """Add a layer on top. clip: a layer below this one; this layer only shows where that one has paint."""
        if blend not in _BLEND_MODES:
            raise ValueError(f"blend は {', '.join(_BLEND_MODES)} のどれかです: {blend!r}")
        if not 0 <= opacity <= 1:
            raise ValueError(f"opacity は 0〜1 です: {opacity}")
        if any(existing.name == name for existing in self.layers):
            raise ValueError(f"同じ名前のレイヤーがあります: {name!r}")
        if clip is not None and not any(existing is clip for existing in self.layers):
            raise ValueError("clip には、このキャンバスにある下のレイヤーを渡してください")
        layer = Layer(self, name, blend, opacity, clip)
        self.layers.append(layer)
        return layer

    def linear(self, start: Point, end: Point, colors: Sequence[int]) -> Gradient:
        if len(colors) < 2:
            raise ValueError("グラデーションには色が2つ以上要ります")
        return Gradient(skia.GradientShader.MakeLinear([skia.Point(*start), skia.Point(*end)], list(colors)))

    def radial(self, center: Point, radius: float, colors: Sequence[int]) -> Gradient:
        if len(colors) < 2:
            raise ValueError("グラデーションには色が2つ以上要ります")
        if radius <= 0:
            raise ValueError("radius は 0 より大きくしてください")
        return Gradient(skia.GradientShader.MakeRadial(skia.Point(*center), radius, list(colors)))

    def composite(self, background: int = skia.ColorWHITE) -> np.ndarray:
        """All layers merged, as an 800x800x4 RGBA uint8 array."""
        out = skia.Surface(SIZE, SIZE)
        oc = out.getCanvas()
        oc.clear(background)
        for layer in self.layers:
            img = layer.image()
            if layer.clip is not None:
                tmp = skia.Surface(SIZE, SIZE)
                tc = tmp.getCanvas()
                tc.clear(skia.ColorTRANSPARENT)
                tc.drawImage(img, 0, 0)
                tc.drawImage(layer.clip.image(), 0, 0, skia.SamplingOptions(),
                             skia.Paint(BlendMode=skia.BlendMode.kDstIn))
                img = tmp.makeImageSnapshot()
            oc.drawImage(img, 0, 0, skia.SamplingOptions(),
                         skia.Paint(BlendMode=_BLEND_MODES[layer.blend], Alphaf=layer.opacity))
        return out.makeImageSnapshot().toarray(colorType=skia.kRGBA_8888_ColorType)
