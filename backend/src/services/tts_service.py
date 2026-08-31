"""
Narration for AI-generated scripts.

The script step guesses each scene's duration from its word count at roughly
2.5 words per second. That is fine for drafting and wrong for assembly: the
narration is the spine of a generated video, so the scene lasts exactly as long
as the voice takes, not as long as the model estimated.

This synthesises the narration and reports the *measured* duration back, plus
word-level timings taken from the synthesiser itself. Those timings are what
lets captions land on the word rather than being spread evenly.

Uses edge-tts, which speaks through Microsoft Edge's online voices: no API key,
no model files to download, and 300+ voices across languages.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# edge-tts reports offsets in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000

# Synthesis is a network round trip per scene. Bounded so a 20-scene script does
# not open twenty sockets at once.
MAX_CONCURRENT_SYNTHESIS = 4

DEFAULT_VOICES: Dict[str, Dict[str, str]] = {
    "english": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
    "spanish": {"female": "es-ES-ElviraNeural", "male": "es-ES-AlvaroNeural"},
    "portuguese": {"female": "pt-BR-FranciscaNeural", "male": "pt-BR-AntonioNeural"},
    "french": {"female": "fr-FR-DeniseNeural", "male": "fr-FR-HenriNeural"},
    "german": {"female": "de-DE-KatjaNeural", "male": "de-DE-ConradNeural"},
    "italian": {"female": "it-IT-ElsaNeural", "male": "it-IT-DiegoNeural"},
}


class NarrationError(RuntimeError):
    """Raised when narration cannot be synthesised."""


def resolve_voice(language: str, gender: str = "female") -> str:
    """Pick a voice for a language, falling back to English."""
    voices = DEFAULT_VOICES.get(language.strip().lower())
    if not voices:
        logger.info("No voice mapped for %r; narrating in English", language)
        voices = DEFAULT_VOICES["english"]
    return voices.get(gender.strip().lower(), voices["female"])


async def list_voices_for_language(language: str) -> List[Dict[str, str]]:
    """Available voices whose locale matches the language, for the picker."""
    import edge_tts

    prefix = {
        "english": "en",
        "spanish": "es",
        "portuguese": "pt",
        "french": "fr",
        "german": "de",
        "italian": "it",
    }.get(language.strip().lower())

    voices = await edge_tts.list_voices()
    if prefix:
        voices = [voice for voice in voices if voice["Locale"].startswith(prefix)]

    return [
        {
            "name": voice["ShortName"],
            "locale": voice["Locale"],
            "gender": voice["Gender"],
        }
        for voice in sorted(voices, key=lambda item: item["ShortName"])
    ]


async def narrate(
    text: str,
    output_path: Path,
    voice: str,
    rate: str = "+0%",
) -> Dict[str, Any]:
    """
    Speak `text` into `output_path` and report what was actually produced.

    Word timings come from the synthesiser's own boundary events, so they are
    measured rather than inferred. `boundary="WordBoundary"` is required —
    the default only reports sentences.
    """
    # Validated before the import so a caller passing empty text gets a clear
    # error even where the synthesiser is unavailable.
    if not text or not text.strip():
        raise NarrationError("Nothing to narrate")

    import edge_tts

    communicate = edge_tts.Communicate(
        text.strip(), voice, rate=rate, boundary="WordBoundary"
    )

    words: List[Dict[str, float]] = []
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with output_path.open("wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    start = chunk["offset"] / TICKS_PER_SECOND
                    words.append(
                        {
                            "text": chunk["text"],
                            "start": round(start, 3),
                            "end": round(
                                start + chunk["duration"] / TICKS_PER_SECOND, 3
                            ),
                        }
                    )
    except Exception as exc:
        output_path.unlink(missing_ok=True)
        raise NarrationError(f"Narration failed: {exc}") from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise NarrationError("Narration produced no audio")

    duration = words[-1]["end"] if words else 0.0

    return {
        "path": str(output_path),
        "voice": voice,
        "duration": duration,
        "words": words,
    }


async def narrate_scenes(
    scenes: Sequence[Dict[str, Any]],
    output_dir: Path,
    language: str = "English",
    gender: str = "female",
    voice: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Narrate every scene and return each one's measured duration.

    The measured duration replaces the script's estimate: a scene lasts as long
    as its narration takes, and the caller re-times the timeline from these
    values rather than from the model's word-count guess.
    """
    selected_voice = voice or resolve_voice(language, gender)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SYNTHESIS)

    async def run(index: int, scene: Dict[str, Any]) -> Dict[str, Any]:
        order = scene.get("order", index + 1)
        narration = (scene.get("narration") or "").strip()

        if not narration:
            return {
                "order": order,
                "narration": "",
                "audio_path": None,
                "duration": 0.0,
                "estimated_duration": scene.get("duration_seconds"),
                "words": [],
                "error": "Scene has no narration",
            }

        async with semaphore:
            try:
                result = await narrate(
                    narration,
                    output_dir / f"scene-{order:02d}.mp3",
                    selected_voice,
                )
            except NarrationError as exc:
                logger.warning("Scene %s narration failed: %s", order, exc)
                return {
                    "order": order,
                    "narration": narration,
                    "audio_path": None,
                    "duration": 0.0,
                    "estimated_duration": scene.get("duration_seconds"),
                    "words": [],
                    "error": str(exc),
                }

        return {
            "order": order,
            "narration": narration,
            "audio_path": result["path"],
            "duration": result["duration"],
            "estimated_duration": scene.get("duration_seconds"),
            "words": result["words"],
            "error": None,
        }

    results = await asyncio.gather(
        *(run(index, scene) for index, scene in enumerate(scenes))
    )
    return list(results)


def total_narrated_duration(scene_results: Sequence[Dict[str, Any]]) -> float:
    return round(sum(scene.get("duration") or 0.0 for scene in scene_results), 2)


def retimed_scenes(
    scenes: Sequence[Dict[str, Any]],
    scene_results: Sequence[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Rewrite scene durations from what the narration actually took.

    A scene whose narration failed keeps its estimate: dropping it to zero would
    silently remove it from the timeline.
    """
    by_order = {result["order"]: result for result in scene_results}

    retimed: List[Dict[str, Any]] = []
    for index, scene in enumerate(scenes):
        order = scene.get("order", index + 1)
        measured = by_order.get(order, {}).get("duration") or 0.0
        updated = dict(scene)
        if measured > 0:
            updated["duration_seconds"] = round(measured, 2)
        retimed.append(updated)
    return retimed
