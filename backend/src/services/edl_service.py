"""
Non-destructive clip editing through an EDL (edit decision list).

The editor this replaces cut the *rendered* clip file: `trim_clip_file` took the
finished mp4 and re-encoded a shorter one. That has two costs the user pays for
every edit — material trimmed away is gone for good, so a clip can only ever
shrink, and each pass re-encodes an already-encoded file, so quality decays with
every adjustment.

Here a clip is instead a recipe: an ordered list of time ranges in the *source*
video, already persisted per clip by `clip_source_map`. Editing rewrites the
recipe and re-renders from the original master, so segments can be extended back
out again and quality never depends on how many times the clip was touched.

The rendering itself reuses `VideoService.create_video_clips` with `keep_ranges`,
which is the same path `regenerate_all_clips_for_task` already takes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional
import logging

from ..clip_source_map import (
    MIN_RANGE_SECONDS,
    load_clip_source_ranges,
    normalize_source_ranges,
    save_clip_source_ranges,
    total_source_duration,
)
from ..config import Config, get_config
from ..repositories.clip_repository import ClipRepository
from ..repositories.task_repository import TaskRepository

logger = logging.getLogger(__name__)

# Cuts land on a word boundary when one is this close, so an edit never clips
# the first or last syllable of a word.
SNAP_WINDOW_SECONDS = 0.35


class EdlError(ValueError):
    """Raised when an EDL cannot be read or applied."""


def snap_to_words(
    time_seconds: float,
    words: List[Dict[str, Any]],
    *,
    prefer: str = "nearest",
) -> float:
    """
    Move `time_seconds` onto the nearest word boundary within the snap window.

    `prefer` biases which boundary wins for a segment edge: "start" snaps to
    word starts (so a segment opens on a whole word), "end" to word ends.
    Returns the input untouched when no boundary is close enough.
    """
    if not words:
        return time_seconds

    candidates: List[float] = []
    for word in words:
        start = word.get("start")
        end = word.get("end")
        if prefer in {"nearest", "start"} and isinstance(start, (int, float)):
            candidates.append(float(start))
        if prefer in {"nearest", "end"} and isinstance(end, (int, float)):
            candidates.append(float(end))

    if not candidates:
        return time_seconds

    best = min(candidates, key=lambda candidate: abs(candidate - time_seconds))
    if abs(best - time_seconds) <= SNAP_WINDOW_SECONDS:
        return best
    return time_seconds


def validate_segments(
    segments: List[Dict[str, Any]],
    source_duration: Optional[float] = None,
) -> List[tuple[float, float]]:
    """
    Turn the editor's segment list into normalised source ranges.

    Order is preserved rather than sorted: reordering segments is a legitimate
    edit, and the render walks them in the order given.
    """
    if not segments:
        raise EdlError("An EDL needs at least one segment")

    ranges: List[tuple[float, float]] = []
    for index, segment in enumerate(segments):
        try:
            start = float(segment["start"])
            end = float(segment["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise EdlError(f"Segment {index} is missing a numeric start/end") from exc

        if end - start <= MIN_RANGE_SECONDS:
            raise EdlError(
                f"Segment {index} is shorter than {MIN_RANGE_SECONDS}s"
            )
        if start < 0:
            raise EdlError(f"Segment {index} starts before the video does")
        if source_duration is not None and end > source_duration + 0.5:
            raise EdlError(
                f"Segment {index} ends past the source video ({end:.2f}s > {source_duration:.2f}s)"
            )

        ranges.append((start, end))

    normalized = normalize_source_ranges(ranges)
    if not normalized:
        raise EdlError("No usable segments after normalisation")
    return normalized


class EdlService:
    """Reads and applies the edit decision list for a single clip."""

    def __init__(self, db, video_service, config: Config | None = None):
        self.db = db
        self.video_service = video_service
        self.config = config or get_config()
        self.task_repo = TaskRepository()
        self.clip_repo = ClipRepository()

    async def _load_clip(self, task_id: str, clip_id: str) -> Dict[str, Any]:
        clips = await self.clip_repo.get_clips_by_task(self.db, task_id)
        for clip in clips:
            if str(clip.get("id")) == str(clip_id):
                return clip
        raise EdlError("Clip not found")

    @staticmethod
    def _ranges_for_clip(clip: Dict[str, Any]) -> List[tuple[float, float]]:
        file_path = clip.get("file_path")
        if file_path:
            persisted = load_clip_source_ranges(Path(file_path))
            if persisted:
                return persisted
        return []

    async def get_edl(self, task_id: str, clip_id: str) -> Dict[str, Any]:
        """
        Return the clip's recipe plus everything the editor needs to draw it:
        the source ranges, the source video duration, and the transcript words
        used for snapping.
        """
        task = await self.task_repo.get_task_by_id(self.db, task_id)
        if not task:
            raise EdlError("Task not found")

        clip = await self._load_clip(task_id, clip_id)
        ranges = self._ranges_for_clip(clip)

        if not ranges:
            # Clips rendered before source maps existed have no recipe. The
            # editor still opens: it falls back to the clip's own bounds, which
            # allows trimming inwards but not extending.
            logger.info("Clip %s has no source map; falling back to clip bounds", clip_id)

        video_path = self._resolve_local_source(task)

        return {
            "clip_id": str(clip_id),
            "task_id": str(task_id),
            "segments": [
                {"start": round(start, 3), "end": round(end, 3)}
                for start, end in ranges
            ],
            "has_source_map": bool(ranges),
            "source_duration": self._source_duration(video_path),
            "total_duration": round(total_source_duration(ranges), 3),
            "snap_window_seconds": SNAP_WINDOW_SECONDS,
            "words": self._transcript_words(video_path),
        }

    def _resolve_local_source(self, task: Dict[str, Any]) -> Optional[Path]:
        """
        The master video on disk, when it is already there.

        A YouTube source is never fetched here: opening the editor should not
        trigger a download. The editor copes with the missing duration and
        transcript by trusting the segments it was given.
        """
        source_url = task.get("source_url")
        if not source_url:
            return None

        try:
            path = self.video_service.resolve_local_video_path(source_url)
        except Exception:
            return None

        return path if path.exists() else None

    @staticmethod
    def _source_duration(video_path: Optional[Path]) -> Optional[float]:
        if video_path is None:
            return None
        try:
            from ..clip_editor import _ffprobe_duration

            return round(float(_ffprobe_duration(video_path)), 3)
        except Exception as exc:
            logger.warning("Could not probe source duration: %s", exc)
            return None

    def _transcript_words(self, video_path: Optional[Path]) -> List[Dict[str, Any]]:
        """
        Word-level timings for snapping, in seconds.

        The cache stores AssemblyAI's own units (milliseconds); the editor works
        in seconds throughout, so the conversion happens here rather than being
        repeated on the client.
        """
        if video_path is None or not video_path.exists():
            return []

        try:
            from ..video_utils import load_cached_transcript_data

            payload = load_cached_transcript_data(video_path)
        except Exception as exc:
            logger.warning("Could not load transcript cache: %s", exc)
            return []

        if not payload:
            return []

        words: List[Dict[str, Any]] = []
        for word in payload.get("words") or []:
            start = word.get("start")
            end = word.get("end")
            if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
                continue
            words.append(
                {
                    "text": word.get("text") or "",
                    "start": round(float(start) / 1000.0, 3),
                    "end": round(float(end) / 1000.0, 3),
                }
            )
        return words

    async def rerender(
        self,
        task_id: str,
        clip_id: str,
        segments: List[Dict[str, Any]],
        style: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Re-render a clip from an edited EDL, always starting from the master.
        """
        task = await self.task_repo.get_task_by_id(self.db, task_id)
        if not task:
            raise EdlError("Task not found")

        clip = await self._load_clip(task_id, clip_id)

        source_url = task.get("source_url")
        source_type = task.get("source_type")
        if not source_url or not source_type:
            raise EdlError("Task has no source video; cannot re-render")

        if source_type == "youtube":
            downloaded = await self.video_service.download_video(source_url)
            if not downloaded:
                raise EdlError("Failed to fetch the source video")
            video_path = Path(downloaded)
        else:
            video_path = self.video_service.resolve_local_video_path(source_url)
            if not video_path.exists():
                raise EdlError("The source video is no longer available")

        ranges = validate_segments(segments, self._source_duration(video_path))

        style = style or {}
        segment_payload = {
            # keep_ranges is the EDL: create_video_clips renders exactly these
            # source windows, in this order, instead of one contiguous span.
            "keep_ranges": ranges,
            "start_time": self._seconds_to_mmss(ranges[0][0]),
            "end_time": self._seconds_to_mmss(ranges[-1][1]),
            "text": clip.get("text") or "",
            "relevance_score": clip.get("relevance_score", 0.5),
            "reasoning": clip.get("reasoning") or "Edited in the clip editor",
            "virality_score": clip.get("virality_score", 0),
            "hook_score": clip.get("hook_score", 0),
            "engagement_score": clip.get("engagement_score", 0),
            "value_score": clip.get("value_score", 0),
            "shareability_score": clip.get("shareability_score", 0),
            "hook_type": clip.get("hook_type"),
            "hook_title": clip.get("hook_title"),
        }

        rendered = await self.video_service.create_video_clips(
            video_path,
            [segment_payload],
            style.get("font_family"),
            style.get("font_size"),
            style.get("font_color"),
            style.get("caption_template", "default"),
            style.get("output_format", "vertical"),
            style.get("add_subtitles", True),
            style.get("cleanup_settings"),
            style.get("show_emojis"),
        )

        if not rendered:
            raise EdlError("Re-render produced no output")

        info = rendered[0]
        output_path = Path(info["path"])
        save_clip_source_ranges(output_path, ranges)

        await self.clip_repo.update_clip(
            self.db,
            clip_id=clip_id,
            filename=info["filename"],
            file_path=info["path"],
            start_time=info["start_time"],
            end_time=info["end_time"],
            duration=info["duration"],
            text=info.get("text") or clip.get("text") or "",
        )

        logger.info(
            "Re-rendered clip %s from %s segments (%.2fs)",
            clip_id,
            len(ranges),
            total_source_duration(ranges),
        )

        return {
            "clip_id": str(clip_id),
            "filename": info["filename"],
            "duration": info["duration"],
            "segments": [
                {"start": round(start, 3), "end": round(end, 3)}
                for start, end in ranges
            ],
        }

    @staticmethod
    def _seconds_to_mmss(seconds: float) -> str:
        total = max(0, int(seconds))
        return f"{total // 60:02d}:{total % 60:02d}"
