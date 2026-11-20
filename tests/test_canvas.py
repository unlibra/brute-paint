import numpy as np
import pytest

from brute_paint import SIZE, Canvas, rgb

SQUARE = [(100, 100), (700, 100), (700, 700), (100, 700)]


def px(img, x, y):
    return tuple(int(v) for v in img[y, x, :3])


def test_rgb_rejects_bad_hex():
    with pytest.raises(ValueError):
        rgb("red")
    with pytest.raises(ValueError):
        rgb("#12345")


def test_fill_paints_inside_and_not_outside():
    c = Canvas()
    c.layer("base").fill(SQUARE, rgb("#ff0000"))
    img = c.composite()
    assert img.shape == (SIZE, SIZE, 4)
    assert px(img, 400, 400) == (255, 0, 0)
    assert px(img, 10, 10) == (255, 255, 255)


def test_multiply_darkens_and_screen_lightens():
    c = Canvas()
    c.layer("base").fill(SQUARE, rgb("#808080"))
    c.layer("shadow", blend="multiply").ellipse(300, 400, 50, 50, rgb("#808080"))
    c.layer("light", blend="screen").ellipse(500, 400, 50, 50, rgb("#808080"))
    img = c.composite()
    assert px(img, 300, 400)[0] < 0x80 - 40  # 0x80 * 0x80 / 255 ≈ 64
    assert px(img, 500, 400)[0] > 0x80 + 40  # screen ≈ 192


def test_opacity_blends_with_below():
    c = Canvas()
    c.layer("top", opacity=0.5).fill(SQUARE, rgb("#000000"))
    assert 120 <= px(c.composite(), 400, 400)[0] <= 135


def test_clip_shows_only_where_base_has_paint():
    c = Canvas()
    base = c.layer("skin")
    base.ellipse(400, 400, 100, 100, rgb("#ffffff"))
    c.layer("shade", clip=base).fill([(0, 0), (800, 0), (800, 800), (0, 800)], rgb("#0000ff"))
    img = c.composite(background=rgb("#00ff00"))
    assert px(img, 400, 400) == (0, 0, 255)
    assert px(img, 50, 50) == (0, 255, 0)


def test_gradient_fill_is_opaque_and_changes_along_axis():
    c = Canvas()
    c.layer("hair").fill(SQUARE, gradient=c.linear((0, 100), (0, 700), [rgb("#000000"), rgb("#ffffff")]))
    img = c.composite(background=rgb("#ff0000"))
    top, bottom = px(img, 400, 150), px(img, 400, 650)
    assert top[0] == top[1] == top[2] and bottom[0] == bottom[1] == bottom[2]  # no red showing through
    assert top[0] < 80 and bottom[0] > 175


@pytest.mark.parametrize(
    "kwargs",
    [{"blend": "overlay"}, {"opacity": 1.5}, {"opacity": -0.1}],
)
def test_layer_rejects_bad_options(kwargs):
    with pytest.raises(ValueError):
        Canvas().layer("x", **kwargs)


def test_layer_rejects_duplicate_name():
    c = Canvas()
    c.layer("線画")
    with pytest.raises(ValueError):
        c.layer("線画")


def test_clip_must_be_a_layer_below_on_the_same_canvas():
    other = Canvas().layer("base")
    with pytest.raises(ValueError):
        Canvas().layer("shade", clip=other)


def test_fill_needs_three_points_and_one_paint():
    layer = Canvas().layer("x")
    with pytest.raises(ValueError):
        layer.fill([(0, 0), (10, 10)], rgb("#000000"))
    with pytest.raises(ValueError):
        layer.fill(SQUARE)
    c = Canvas()
    with pytest.raises(ValueError):
        c.layer("y").fill(SQUARE, rgb("#000000"), gradient=c.linear((0, 0), (1, 1), [0, 1]))


def test_stroke_needs_two_points():
    layer = Canvas().layer("x")
    with pytest.raises(ValueError):
        layer.stroke([(10, 10)], 4, rgb("#000000"))


def _stroke_width_at(img, x):
    column = img[:, x, 0]
    return int((column < 128).sum())


def test_two_point_stroke_draws_a_line_with_taper():
    c = Canvas()
    c.layer("line").stroke([(100, 400), (700, 400)], 20, rgb("#000000"), taper=(0.3, 0.3))
    img = c.composite()
    middle, near_start = _stroke_width_at(img, 400), _stroke_width_at(img, 120)
    assert 18 <= middle <= 22
    assert near_start < middle / 2


def test_zero_taper_keeps_width_constant():
    c = Canvas()
    c.layer("line").stroke([(100, 400), (700, 400)], 20, rgb("#000000"), taper=(0, 0))
    img = c.composite()
    assert abs(_stroke_width_at(img, 110) - _stroke_width_at(img, 400)) <= 1


def test_press_scales_width():
    c = Canvas()
    c.layer("line").stroke([(100, 400), (700, 400)], 20, rgb("#000000"), taper=(0, 0), press=[0.5, 0.5])
    assert 8 <= _stroke_width_at(c.composite(), 400) <= 12


def _jittery(seed, jitter):
    c = Canvas(seed)
    c.layer("line").stroke([(100, 300), (400, 500), (700, 300)], 6, rgb("#000000"), jitter=jitter)
    return c.composite()


def test_same_seed_draws_the_same_image():
    assert np.array_equal(_jittery(7, 4.0), _jittery(7, 4.0))


def test_different_seed_moves_the_jittered_line():
    assert not np.array_equal(_jittery(7, 4.0), _jittery(8, 4.0))


def test_zero_jitter_ignores_seed():
    assert np.array_equal(_jittery(7, 0), _jittery(8, 0))
