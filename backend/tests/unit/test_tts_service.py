from pathlib import Path

import pytest

from src.services import tts_service as tts


def test_resolve_voice_matches_the_language():
    assert tts.resolve_voice("Spanish") == "es-ES-ElviraNeural"
    assert tts.resolve_voice("Spanish", "male") == "es-ES-AlvaroNeural"


def test_resolve_voice_is_case_insensitive():
    assert tts.resolve_voice("SPANISH") == tts.resolve_voice("spanish")


def test_resolve_voice_falls_back_to_english_for_an_unmapped_language():
    # Better to narrate in English than to fail the whole generation.
    assert tts.resolve_voice("Klingon") == "en-US-AriaNeural"


def test_resolve_voice_falls_back_to_female_for_an_unknown_gender():
    assert tts.resolve_voice("English", "robot") == "en-US-AriaNeural"


@pytest.mark.asyncio
async def test_narrate_rejects_empty_text(tmp_path: Path):
    with pytest.raises(tts.NarrationError, match="Nothing to narrate"):
        await tts.narrate("   ", tmp_path / "out.mp3", "en-US-AriaNeural")


def test_total_duration_sums_measured_values():
    results = [{"duration": 1.5}, {"duration": 2.25}, {"duration": None}]

    assert tts.total_narrated_duration(results) == 3.75


def test_retiming_replaces_the_estimate_with_what_was_measured():
    scenes = [
        {"order": 1, "narration": "one", "duration_seconds": 5.0},
        {"order": 2, "narration": "two", "duration_seconds": 5.0},
    ]
    results = [
        {"order": 1, "duration": 1.96},
        {"order": 2, "duration": 2.06},
    ]

    retimed = tts.retimed_scenes(scenes, results)

    # The script guesses from word count and runs long; the voice is the truth.
    assert [scene["duration_seconds"] for scene in retimed] == [1.96, 2.06]


def test_retiming_keeps_the_estimate_when_narration_failed():
    scenes = [{"order": 1, "narration": "", "duration_seconds": 3.0}]
    results = [{"order": 1, "duration": 0.0}]

    # Dropping to zero would silently remove the scene from the timeline.
    assert tts.retimed_scenes(scenes, results)[0]["duration_seconds"] == 3.0


def test_retiming_leaves_scenes_it_has_no_result_for():
    scenes = [{"order": 7, "narration": "x", "duration_seconds": 4.0}]

    assert tts.retimed_scenes(scenes, [])[0]["duration_seconds"] == 4.0


def test_retiming_does_not_mutate_the_input():
    scenes = [{"order": 1, "narration": "one", "duration_seconds": 5.0}]
    tts.retimed_scenes(scenes, [{"order": 1, "duration": 2.0}])

    assert scenes[0]["duration_seconds"] == 5.0


@pytest.mark.asyncio
async def test_a_scene_without_narration_is_reported_not_dropped(tmp_path: Path):
    scenes = [
        {"order": 1, "narration": "", "duration_seconds": 3.0},
        {"order": 2, "narration": "   ", "duration_seconds": 2.0},
    ]

    results = await tts.narrate_scenes(scenes, tmp_path)

    assert [result["order"] for result in results] == [1, 2]
    assert all(result["error"] for result in results)
    assert all(result["audio_path"] is None for result in results)
