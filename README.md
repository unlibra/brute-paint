# brute-paint

Drawing illustrations purely with code and brute-force LLM loops—no diffusion models involved.

An LLM writes a drawing script, renders it, looks at the result and fixes the script, again and again. Every line and every fill comes from code. No image generation model touches the pixels, and reference images are only looked at, never traced.

The target is an SNS profile icon, shown anywhere from 48px to 400px.

## How it draws like a person

- Layers: base colours, multiply shadows and screen highlights clipped to them, line art on top.
- Lines have ink-in and ink-out, pen pressure and a little hand wobble, and are never pure black.
- Effort goes into the face. Hair, clothes and background get less. See [docs/drawing-guide.md](docs/drawing-guide.md) (Japanese).

## Use

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

Keep your drawing scripts outside this repository. `render` refuses to write inside it.

```python
# my-icon/draw.py
from brute_paint import rgb

SEED = 1

def draw(c):
    skin = c.layer("skin")
    skin.ellipse(400, 420, 230, 260, rgb("#fbe9e1"))
    shade = c.layer("skin shadow", blend="multiply", clip=skin)
    shade.ellipse(400, 250, 300, 120, rgb("#f3cfc8"))
    c.layer("line").stroke([(180, 420), (260, 620), (400, 690)], 5, rgb("#4a2a2e"), taper=(0.3, 0.1))
```

```
uv run --project path/to/brute-paint brute-paint render my-icon/draw.py
```

This writes to `my-icon/out/`:

| File | What it is |
|---|---|
| `sheet.png` | 400px, circle crop, 48px actual size and 2x |
| `form.png` | grayscale and mirrored, for checking shapes and values |
| `final_400.png` | the icon |
| `iter/001.png`, ... | every sheet, kept for comparison |
| `ref_sheet.png` | the icon next to references, when `character.md` is beside the script |

`character.md` has three headings: `変えない特徴` (features that must not change), `デフォルメしてよい点` (what may be stylised) and `参考画像` (a bullet list of image paths relative to the file; the first five are used).

To turn a reference colour into a number:

```
uv run --project path/to/brute-paint brute-paint color reference.jpg --box 120,60,200,120
```

## License

MIT
