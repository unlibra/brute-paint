from pathlib import Path

import pytest
from PIL import Image

from brute_paint.cli import main
from brute_paint.render import BG, MAX_SHEET_WIDTH, TOOL_ROOT, RenderError, render

SCRIPT = """
from brute_paint import rgb
SEED = 3

def draw(c):
    base = c.layer("下塗り")
    base.ellipse(400, 400, 250, 250, rgb("#88aadd"))
    c.layer("影", blend="multiply", clip=base).ellipse(480, 480, 200, 200, rgb("#bbbbbb"))
    c.layer("線画").stroke([(150, 400), (400, 160), (650, 400)], 6, rgb("#333344"), jitter=2)
"""

CHARACTER = """# テスト

## 変えない特徴

- 青い丸
- 線は濃い紺色

## デフォルメしてよい点

- 大きさ

## 参考画像

- refs/a.png
- `refs/b.png`
"""


@pytest.fixture
def work(tmp_path: Path) -> Path:
    (tmp_path / "draw.py").write_text(SCRIPT, encoding="utf-8")
    return tmp_path


def _add_character(work: Path, refs=("a.png", "b.png"), text=CHARACTER):
    (work / "refs").mkdir()
    for i, name in enumerate(refs):
        Image.new("RGB", (1200, 900), (40 * i, 100, 200)).save(work / "refs" / name)
    (work / "character.md").write_text(text, encoding="utf-8")


def test_render_writes_the_views(work):
    result = render(work / "draw.py")
    out = work / "out"
    assert result.out_dir == out
    for name in ("sheet.png", "form.png", "final_400.png", "iter/001.png"):
        assert (out / name).is_file(), name
    assert Image.open(out / "final_400.png").size == (400, 400)
    assert not (out / "ref_sheet.png").exists()


def test_sheet_fits_the_width_the_model_sees_unscaled(work):
    _add_character(work, refs=tuple(f"{i}.png" for i in range(5)),
                   text=CHARACTER.replace("- refs/a.png\n- `refs/b.png`", "\n".join(f"- refs/{i}.png" for i in range(5))))
    render(work / "draw.py")
    assert Image.open(work / "out" / "sheet.png").width <= MAX_SHEET_WIDTH
    assert Image.open(work / "out" / "ref_sheet.png").width <= MAX_SHEET_WIDTH


def test_iterations_count_up_and_never_overwrite(work):
    for _ in range(3):
        render(work / "draw.py")
    iter_dir = work / "out" / "iter"
    assert sorted(p.name for p in iter_dir.iterdir()) == ["001.png", "002.png", "003.png"]
    (iter_dir / "002.png").unlink()
    render(work / "draw.py")
    assert sorted(p.name for p in iter_dir.iterdir()) == ["001.png", "003.png", "004.png"]


def test_ref_sheet_written_when_character_md_exists(work):
    _add_character(work)
    render(work / "draw.py")
    ref = Image.open(work / "out" / "ref_sheet.png")
    assert ref.height > 400  # the "do not change" text sits under the images
    assert len(list((work / "out" / "ref_cache").iterdir())) == 2


@pytest.mark.parametrize("refs", [(), ("a.png",)])
def test_long_features_are_not_cut_at_the_right_edge(work, refs):
    long_item = "前髪はぱっつんで、目にかかる長さ。毛先に向かってピンクが強くなる。" * 3
    text = CHARACTER.replace("- 青い丸", f"- {long_item}")
    text = text.replace("- refs/a.png\n- `refs/b.png`", "\n".join(f"- refs/{n}" for n in refs))
    _add_character(work, refs=refs, text=text)
    render(work / "draw.py")
    sheet = Image.open(work / "out" / "ref_sheet.png").convert("RGB")
    text_area = sheet.crop((sheet.width - 8, 400, sheet.width, sheet.height))
    assert all(px == BG for px in text_area.get_flattened_data())


def test_only_first_five_references_are_used(work):
    names = tuple(f"{i}.png" for i in range(10))
    _add_character(work, refs=names, text=CHARACTER.replace(
        "- refs/a.png\n- `refs/b.png`", "\n".join(f"- refs/{n}" for n in names)))
    render(work / "draw.py")
    assert len(list((work / "out" / "ref_cache").iterdir())) == 5


def test_missing_reference_fails_but_sheet_is_written(work):
    _add_character(work, refs=("a.png",))
    with pytest.raises(RenderError, match="refs/b.png"):
        render(work / "draw.py")
    assert (work / "out" / "sheet.png").is_file()


def test_script_without_draw_fails_and_writes_nothing(tmp_path):
    (tmp_path / "draw.py").write_text("SEED = 1\n", encoding="utf-8")
    with pytest.raises(RenderError, match="draw"):
        render(tmp_path / "draw.py")
    assert not (tmp_path / "out").exists()


def test_error_inside_draw_keeps_previous_outputs(work):
    render(work / "draw.py")
    before = (work / "out" / "sheet.png").read_bytes()
    (work / "draw.py").write_text("def draw(c):\n    c.layer('x', blend='overlay')\n", encoding="utf-8")
    with pytest.raises(ValueError):
        render(work / "draw.py")
    assert (work / "out" / "sheet.png").read_bytes() == before
    assert len(list((work / "out" / "iter").iterdir())) == 1


def test_script_inside_tool_repo_is_refused_without_writing():
    script = TOOL_ROOT / "examples" / "x.py"
    with pytest.raises(RenderError, match="公開リポジトリ"):
        render(script)
    assert not (TOOL_ROOT / "examples").exists()


def test_out_dir_inside_tool_repo_is_refused_without_writing(work):
    out = TOOL_ROOT / "tmp-out"
    with pytest.raises(RenderError, match="公開リポジトリ"):
        render(work / "draw.py", out)
    assert not out.exists()
    assert not (work / "out").exists()


def test_cli_render_reports_errors_with_exit_code(work, tmp_path, capsys):
    assert main(["render", str(work / "draw.py")]) == 0
    assert main(["render", str(TOOL_ROOT / "x.py")]) == 1
    assert "公開リポジトリ" in capsys.readouterr().err
    (work / "draw.py").write_text("def draw(c):\n    c.layer('x', opacity=2)\n", encoding="utf-8")
    assert main(["render", str(work / "draw.py")]) == 1
    assert "draw.py" in capsys.readouterr().err  # traceback points at the script line
