from src.camera_inset_layout import (
    MAX_CAMERA_RATIO,
    build_inset_filtergraph,
    inset_box,
    is_cornered,
    nearest_corner,
    resolve_inset,
    usable,
)

FRAME_W, FRAME_H = 1920, 1080


def test_nearest_corner_reads_the_subject_position():
    assert nearest_corner((100, 100, 200, 150), FRAME_W, FRAME_H) == ("left", "top")
    assert nearest_corner((1600, 900, 200, 150), FRAME_W, FRAME_H) == ("right", "bottom")


def test_a_small_off_centre_subject_is_an_inset():
    # Bottom-right webcam: small, hard against two edges.
    assert is_cornered((1620, 880, 260, 180), FRAME_W, FRAME_H) is True


def test_a_centred_talking_head_is_not_an_inset():
    # Centred horizontally, so no matter how near the top it sits it is the
    # shot rather than a composited camera.
    assert is_cornered((860, 60, 200, 150), FRAME_W, FRAME_H) is False


def test_a_subject_filling_the_frame_is_not_an_inset():
    assert is_cornered((1500, 100, 400, 900), FRAME_W, FRAME_H) is False


def test_inset_box_pins_to_the_bottom_right_corner():
    box = inset_box((1620, 880, 260, 180), FRAME_W, FRAME_H)
    x, y, w, h = box

    # Grown box still reaches both edges it was anchored to.
    assert x + w == FRAME_W
    assert y + h == FRAME_H


def test_inset_box_pins_to_the_top_left_corner():
    x, y, _, _ = inset_box((20, 30, 260, 180), FRAME_W, FRAME_H)

    assert (x, y) == (0, 0)


def test_inset_height_comes_from_the_aspect_not_the_detection():
    # A wide, short detection (a torso) must still produce a box tall enough to
    # contain the head: 16:9 off the grown width, not 1.45x the detection.
    _, _, w, h = inset_box((1620, 940, 260, 86), FRAME_W, FRAME_H)

    assert h >= round(w / (16 / 9)) - 1
    assert h > 86 * 1.45


def test_inset_box_stays_inside_the_frame():
    for detection in [(0, 0, 300, 200), (1800, 1000, 300, 200), (960, 540, 100, 80)]:
        x, y, w, h = inset_box(detection, FRAME_W, FRAME_H)
        assert x >= 0 and y >= 0
        assert x + w <= FRAME_W
        assert y + h <= FRAME_H


def test_usable_rejects_boxes_outside_the_size_guard_rails():
    assert usable((0, 0, 300, 60), FRAME_H) is False   # 5.5% of height
    assert usable((0, 0, 300, 250), FRAME_H) is True   # 23%
    assert usable((0, 0, 300, 500), FRAME_H) is False  # 46%


def test_filtergraph_keeps_the_screen_at_full_width():
    graph = build_inset_filtergraph(FRAME_W, FRAME_H, (1500, 800, 400, 225))

    # The screen branch scales only; cropping it would lose the HUD or the
    # edges of the desktop, which is what this layout exists to preserve.
    assert "[sc]scale=1080:" in graph
    assert "[sc]crop" not in graph
    assert "vstack=inputs=2" in graph
    assert graph.endswith("[v]")


def test_camera_band_is_capped():
    # A very tall inset would otherwise take most of the frame.
    graph = build_inset_filtergraph(FRAME_W, FRAME_H, (1500, 400, 300, 600))
    camera_height = int(graph.split("[camera]")[0].rsplit("scale=1080:", 1)[1].split(":")[0])

    assert camera_height <= int(1920 * MAX_CAMERA_RATIO)


def test_filtergraph_dimensions_are_even():
    graph = build_inset_filtergraph(FRAME_W, FRAME_H, (1501, 801, 401, 227))
    crop = graph.split("crop=")[1].split(",")[0]
    values = [int(part) for part in crop.split(":")]

    assert all(value % 2 == 0 for value in values)


def test_filtergraph_appends_subtitles_last():
    graph = build_inset_filtergraph(
        FRAME_W, FRAME_H, (1500, 800, 400, 225), subtitles_filter="subtitles=x.ass"
    )

    assert graph.endswith(",subtitles=x.ass[v]")


def test_resolve_picks_the_corner_subject_over_a_centred_one():
    boxes = [
        (860, 400, 220, 200),   # centred: the content, not the camera
        (1620, 880, 260, 180),  # bottom-right webcam
    ]
    resolved = resolve_inset(boxes, FRAME_W, FRAME_H)

    assert resolved is not None
    assert resolved[0] + resolved[2] == FRAME_W


def test_resolve_returns_none_without_a_corner_subject():
    assert resolve_inset([(860, 400, 220, 200)], FRAME_W, FRAME_H) is None
    assert resolve_inset([], FRAME_W, FRAME_H) is None


def test_resolve_rejects_an_inset_that_is_too_large():
    # A big corner subject grows past the ceiling and is refused rather than
    # producing a camera band that swallows the screen.
    assert resolve_inset([(1500, 700, 400, 370)], FRAME_W, FRAME_H) is None
