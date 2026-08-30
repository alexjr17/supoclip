import pytest

from src.services.edl_service import (
    SNAP_WINDOW_SECONDS,
    EdlError,
    snap_to_words,
    validate_segments,
)


WORDS = [
    {"text": "hello", "start": 1.00, "end": 1.40},
    {"text": "there", "start": 1.45, "end": 1.90},
    {"text": "friend", "start": 2.00, "end": 2.60},
]


def test_snap_moves_cut_onto_a_nearby_word_boundary():
    # 1.02 sits just inside "hello"; snapping back to 1.00 keeps the whole word.
    assert snap_to_words(1.02, WORDS) == 1.00


def test_snap_leaves_cuts_that_are_far_from_any_word():
    # 5.0 is well outside the snap window, so the user's exact cut is honoured.
    assert snap_to_words(5.0, WORDS) == 5.0


def test_snap_respects_the_window_boundary():
    # Measured from the last boundary (2.60) so no other word is closer.
    just_outside = 2.60 + SNAP_WINDOW_SECONDS + 0.01
    assert snap_to_words(just_outside, WORDS) == pytest.approx(just_outside)

    just_inside = 2.60 + SNAP_WINDOW_SECONDS - 0.01
    assert snap_to_words(just_inside, WORDS) == pytest.approx(2.60)


def test_snap_prefers_word_starts_for_a_segment_opening():
    # With prefer="start" only word starts are candidates, so a time closer to
    # the *end* of "hello" (1.40) still snaps forward to "there" (1.45).
    assert snap_to_words(1.42, WORDS, prefer="start") == 1.45


def test_snap_prefers_word_ends_for_a_segment_closing():
    assert snap_to_words(1.42, WORDS, prefer="end") == 1.40


def test_snap_is_a_no_op_without_a_transcript():
    assert snap_to_words(3.3, []) == 3.3


def test_validate_segments_normalises_and_keeps_order():
    segments = [{"start": 10.0, "end": 12.0}, {"start": 4.0, "end": 6.0}]

    # Order is deliberately preserved: reordering segments is a valid edit, so
    # the render must follow the list rather than the timeline.
    assert validate_segments(segments) == [(10.0, 12.0), (4.0, 6.0)]


def test_validate_segments_rejects_an_empty_edl():
    with pytest.raises(EdlError):
        validate_segments([])


def test_validate_segments_rejects_a_zero_length_segment():
    with pytest.raises(EdlError):
        validate_segments([{"start": 5.0, "end": 5.0}])


def test_validate_segments_rejects_a_negative_start():
    with pytest.raises(EdlError):
        validate_segments([{"start": -1.0, "end": 4.0}])


def test_validate_segments_rejects_a_segment_past_the_source():
    with pytest.raises(EdlError):
        validate_segments([{"start": 1.0, "end": 90.0}], source_duration=30.0)


def test_validate_segments_allows_extending_within_the_source():
    # The point of the EDL: a segment may grow beyond what the clip currently
    # covers, as long as the master video actually has that material.
    assert validate_segments([{"start": 1.0, "end": 29.0}], source_duration=30.0) == [
        (1.0, 29.0)
    ]


def test_validate_segments_reports_a_missing_field():
    with pytest.raises(EdlError, match="numeric start/end"):
        validate_segments([{"start": 1.0}])
