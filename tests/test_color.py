import pytest
from PIL import Image

from brute_paint.cli import main
from brute_paint.color import median_color, parse_box


@pytest.fixture
def image(tmp_path):
    img = Image.new("RGB", (100, 80), (176, 122, 98))
    img.paste((255, 255, 255), (0, 0, 10, 80))  # a white strip the median should ignore
    path = tmp_path / "ref.png"
    img.save(path)
    return path


def test_median_color_of_a_flat_area(image):
    assert median_color(image, (20, 10, 60, 50)) == "#b07a62"


def test_median_ignores_a_minority_of_other_pixels(image):
    assert median_color(image, (0, 0, 100, 80)) == "#b07a62"


@pytest.mark.parametrize("box", [(50, 10, 50, 20), (60, 10, 50, 20), (0, 0, 101, 80), (-1, 0, 10, 10)])
def test_bad_boxes_fail(image, box):
    with pytest.raises(ValueError):
        median_color(image, box)


@pytest.mark.parametrize("text", ["1,2,3", "a,b,c,d", ""])
def test_parse_box_rejects_bad_text(text):
    with pytest.raises(ValueError):
        parse_box(text)


def test_cli_prints_hex(image, capsys):
    assert main(["color", str(image), "--box", "20,10,60,50"]) == 0
    assert capsys.readouterr().out.strip() == "#b07a62"
    assert main(["color", str(image), "--box", "0,0,500,500"]) == 1
