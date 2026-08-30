import pytest

from src.screencast_layout import (
    build_screencast_filtergraph,
    content_bands,
    default_face_center,
    is_suitable,
    resolve_face_center,
    speaker_crop,
)


def test_content_band_keeps_the_full_source_width():
    # A 16:9 source scaled to 1080 wide is 607.5px tall, rounding to an even
    # 608; the rest of the 1920 frame goes to the presenter.
    content_h, speaker_h = content_bands(1920, 1080, 1080, 1920)

    assert content_h == 608
    assert speaker_h == 1312
    assert content_h + speaker_h == 1920


def test_bands_are_even_for_h264():
    for source_h in (1080, 1079, 800, 721):
        content_h, speaker_h = content_bands(1920, source_h, 1080, 1920)
        assert content_h % 2 == 0
        assert speaker_h % 2 == 0


def test_content_band_never_swallows_the_whole_frame():
    # An extremely tall source would compute a content band past the output
    # height; it is clamped so the speaker band still exists.
    content_h, speaker_h = content_bands(100, 10000, 1080, 1920)

    assert content_h == 1918
    assert speaker_h == 2


def test_content_bands_rejects_degenerate_sources():
    with pytest.raises(ValueError):
        content_bands(0, 1080, 1080, 1920)


def test_speaker_crop_frames_on_the_face_with_headroom():
    _, speaker_h = content_bands(1920, 1080, 1080, 1920)
    crop_w, crop_h, x, y = speaker_crop(1920, 1080, 1080, speaker_h, (960.0, 540.0))

    # The crop is centred horizontally on the face...
    assert x <= 960 <= x + crop_w
    # ...and anchored above centre, so the face sits high with body below.
    assert y < 540 - crop_h / 2 + crop_h * 0.5
    assert crop_w % 2 == 0 and crop_h % 2 == 0


def test_speaker_crop_stays_inside_the_frame_for_a_corner_face():
    _, speaker_h = content_bands(1920, 1080, 1080, 1920)
    crop_w, crop_h, x, y = speaker_crop(1920, 1080, 1080, speaker_h, (1900.0, 1040.0))

    assert x >= 0 and y >= 0
    assert x + crop_w <= 1920
    assert y + crop_h <= 1080


def test_filtergraph_scales_the_whole_frame_for_the_content_band():
    graph = build_screencast_filtergraph(1920, 1080, (960.0, 540.0))

    # The content branch scales, never crops: that is the guarantee.
    assert "[ca]scale=1080:608" in graph
    assert "[ca]crop" not in graph
    assert "vstack=inputs=2" in graph
    assert graph.endswith("[v]")


def test_filtergraph_appends_subtitles_after_the_stack():
    graph = build_screencast_filtergraph(
        1920, 1080, (960.0, 540.0), subtitles_filter="subtitles=x.ass"
    )

    assert "vstack=inputs=2,setsar=1,subtitles=x.ass[v]" in graph


def test_unsuitable_for_a_nearly_vertical_source():
    # Nothing to preserve horizontally, so the normal crop is no worse.
    assert is_suitable(1080, 1080) is False
    assert is_suitable(1080, 1920) is False


def test_suitable_for_a_landscape_screen_recording():
    assert is_suitable(1920, 1080) is True
    assert is_suitable(1280, 720) is True


def test_the_aspect_threshold_always_leaves_a_usable_speaker_band():
    # The single aspect test is enough: at the 1.2 threshold the content band
    # is at most 900px, so the presenter always gets over 1000px of the frame.
    _, speaker_h = content_bands(1200, 1000, 1080, 1920)

    assert speaker_h > 1000


def test_face_center_uses_the_median_to_resist_outliers():
    # A stray detection on a face inside the shared content must not drag the
    # framing away from the presenter.
    centers = [(500.0, 900.0), (505.0, 905.0), (510.0, 910.0), (50.0, 100.0)]

    assert resolve_face_center(centers, 1920, 1080) == (505.0, 905.0)


def test_face_center_falls_back_when_nothing_is_detected():
    assert resolve_face_center([], 1920, 1080) == default_face_center(1920, 1080)
    assert default_face_center(1920, 1080) == (960.0, pytest.approx(669.6))
