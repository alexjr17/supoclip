"""
SCREENCAST layout: full-width content on top, the presenter underneath.

The default vertical crop keeps a centre strip of the frame. That is right for a
talking head and wrong for a screen recording: a spreadsheet, slide or terminal
spans the whole width, so the crop slices the very thing the shot is about.
Neither the tracked crop nor the blurred-background fit fixes it — the first
discards the sides, the second shrinks the content to an unreadable band.

Stacking solves it directly. The content keeps its **entire width**, scaled down
to whatever height that implies, and the presenter is framed on their face in
the band below.

Geometry ported from OpenShorts (https://github.com/mutonby/openshorts),
MIT licensed, Copyright (c) 2024 OpenShorts.

One deliberate divergence: OpenShorts asks Gemini whether a scene is a
screencast and how much width the content spans. SupoClip already lets the user
pick the output format per task, so this is an explicit `vertical_screencast`
choice instead — no extra model call, and no misclassification to recover from.
"""

from __future__ import annotations

from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# A source this close to vertical has no width worth preserving, so stacking
# buys nothing over the normal crop.
#
# This threshold also settles the speaker band on its own: at 1.2 the content
# occupies at most 900px of a 1920px frame, leaving the presenter over 1000px.
# A separate minimum-height guard would be unreachable, so there isn't one.
MIN_SOURCE_ASPECT = 1.2


def content_bands(
    source_width: int,
    source_height: int,
    out_width: int,
    out_height: int,
) -> Tuple[int, int]:
    """
    Split the output frame into (content_height, speaker_height).

    The content keeps its full width — the entire point of this layout — so its
    height falls out of the source aspect ratio: a 16:9 source scaled to 1080
    wide occupies 608px of a 1920px frame, leaving 1312px for the presenter.
    """
    if source_width <= 0 or source_height <= 0:
        raise ValueError("Source dimensions must be positive")

    content_h = int(round(out_width * source_height / float(source_width)))
    content_h -= content_h % 2  # h264 needs even dimensions
    content_h = max(2, min(content_h, out_height - 2))
    speaker_h = out_height - content_h
    return content_h, speaker_h


def speaker_crop(
    source_width: int,
    source_height: int,
    out_width: int,
    speaker_height: int,
    face_center: Tuple[float, float],
) -> Tuple[int, int, int, int]:
    """
    Crop box (w, h, x, y) for the speaker band, framed on the face.

    The vertical anchor sits at 0.42 of the crop height rather than the centre:
    faces read better with a little headroom and more body below than above.
    """
    if speaker_height <= 0:
        raise ValueError("Speaker band has no height")

    aspect = out_width / float(speaker_height)

    crop_h = source_height
    crop_w = int(round(crop_h * aspect))
    if crop_w > source_width:
        crop_w = source_width
        crop_h = int(round(crop_w / aspect))

    crop_w -= crop_w % 2
    crop_h -= crop_h % 2

    center_x, center_y = face_center
    x = int(round(center_x - crop_w / 2.0))
    x = max(0, min(x, source_width - crop_w))
    y = int(round(center_y - crop_h * 0.42))
    y = max(0, min(y, source_height - crop_h))

    return crop_w, crop_h, x - (x % 2), y - (y % 2)


def build_screencast_filtergraph(
    source_width: int,
    source_height: int,
    face_center: Tuple[float, float],
    out_width: int = 1080,
    out_height: int = 1920,
    subtitles_filter: str = "",
) -> str:
    """
    ffmpeg filtergraph placing the whole frame above a face-framed crop.

    Returns a graph ending in `[v]`, matching how the split layout is wired.
    """
    content_h, speaker_h = content_bands(
        source_width, source_height, out_width, out_height
    )
    crop_w, crop_h, crop_x, crop_y = speaker_crop(
        source_width, source_height, out_width, speaker_h, face_center
    )

    tail = f",{subtitles_filter}" if subtitles_filter else ""

    return (
        f"[0:v]split=2[ca][sa];"
        # The content band is the WHOLE frame scaled down: nothing is cropped
        # off the sides, which is the one guarantee this layout exists for.
        f"[ca]scale={out_width}:{content_h}:flags=lanczos,setsar=1[content];"
        f"[sa]crop={crop_w}:{crop_h}:{crop_x}:{crop_y},"
        f"scale={out_width}:{speaker_h}:flags=lanczos,setsar=1[speaker];"
        f"[content][speaker]vstack=inputs=2,setsar=1{tail}[v]"
    )


def is_suitable(
    source_width: int,
    source_height: int,
    out_width: int = 1080,
    out_height: int = 1920,
) -> bool:
    """
    Whether stacking makes sense for this source.

    Only sources wide enough for the crop to be destroying something qualify;
    see MIN_SOURCE_ASPECT for why that single test is sufficient.
    """
    if source_width <= 0 or source_height <= 0:
        return False
    return source_width / float(source_height) >= MIN_SOURCE_ASPECT


def default_face_center(
    source_width: int, source_height: int
) -> Tuple[float, float]:
    """
    Fallback framing when no face is found.

    Presenters in a screen recording are most often keyed into a lower corner,
    but guessing a corner wrongly crops to empty desktop. The horizontal centre,
    low in the frame, is the safest wrong answer.
    """
    return (source_width / 2.0, source_height * 0.62)


def resolve_face_center(
    face_centers: Optional[list],
    source_width: int,
    source_height: int,
) -> Tuple[float, float]:
    """
    Pick the framing point from detected faces, falling back when there are none.

    Uses the median rather than the mean so one spurious detection on a face in
    the shared content cannot drag the framing away from the presenter.
    """
    if not face_centers:
        logger.info("No faces detected for screencast layout; centring the speaker band")
        return default_face_center(source_width, source_height)

    xs = sorted(float(center[0]) for center in face_centers)
    ys = sorted(float(center[1]) for center in face_centers)
    middle = len(xs) // 2
    return (xs[middle], ys[middle])
