"""
CAMERA INSET layout: the screen on top, the webcam inset below.

The case SCREENCAST gets wrong. There the speaker band is a large crop taken
*around* the detected face, which on a full-screen recording means the band is
mostly more screen — the output shows the same content twice, once whole and
once enlarged. What this needs instead is the inset's own rectangle, so the two
bands hold genuinely different things.

Ported from OpenShorts (https://github.com/mutonby/openshorts),
MIT licensed, Copyright (c) 2024 OpenShorts.

Their notes on why the obvious approaches fail are worth keeping. The inset has
no reliable border and is not always a rectangle, and on gameplay the background
moves as much as the person, so temporal-variance tricks do not find it. What is
reliable is that it is anchored to a corner and that a face detector fires inside
it: locate the person, decide which corner they are nearest, and grow a box from
that corner until it covers them with margin.

Like the other layouts here this is an explicit output format, so the question
of whether a video *is* a screen recording with a camera never has to be
guessed.
"""

from __future__ import annotations

from typing import Optional, Sequence, Tuple
import logging

logger = logging.getLogger(__name__)

Box = Tuple[int, int, int, int]

# A subject this far from an edge (as a fraction of the frame) still counts as
# anchored to it.
CORNER_MARGIN = 0.20

# An inset subject is small and off-centre. Requiring the detection to touch two
# edges was tried upstream and rejected: detectors return an upper-body box that
# stops at the chest, so a webcam pinned to the right edge measured 18% clear of
# the bottom and was thrown out.
MAX_SUBJECT_HEIGHT = 0.35

# Horizontal offset from centre. Horizontal specifically: a composited camera is
# pinned to one side, while a talking head is centred left-to-right even when
# their face sits high in the shot.
MIN_OFFSET = 0.18

# A webcam frames head and shoulders while detectors return the head or upper
# body, so the box has to grow to reach the inset's real edges.
INSET_PADDING = 1.45

# Below the floor there is nothing worth showing; above the ceiling it stopped
# being an inset and this layout should not be used.
MIN_INSET_HEIGHT = 0.10
MAX_INSET_HEIGHT = 0.38

INSET_ASPECT = 16 / 9.0

# The camera band never takes more than this share of the output.
MAX_CAMERA_RATIO = 0.40


def nearest_corner(box: Box, frame_width: int, frame_height: int) -> Tuple[str, str]:
    """Which corner the subject sits in, e.g. ("left", "bottom")."""
    center_x = box[0] + box[2] / 2.0
    center_y = box[1] + box[3] / 2.0
    return (
        "left" if center_x < frame_width / 2 else "right",
        "top" if center_y < frame_height / 2 else "bottom",
    )


def is_cornered(
    box: Box, frame_width: int, frame_height: int, margin: float = CORNER_MARGIN
) -> bool:
    """
    Whether the subject looks like a webcam inset rather than the shot itself.

    A sanity filter, not the decision: the user chose this layout, so the
    question is only whether the detection is plausibly an inset.
    """
    x, y, w, h = box
    if h > frame_height * MAX_SUBJECT_HEIGHT:
        return False

    center_x = (x + w / 2.0) / frame_width
    off_centre = abs(center_x - 0.5) >= MIN_OFFSET

    near_edge = (
        x <= frame_width * margin
        or (x + w) >= frame_width * (1 - margin)
        or y <= frame_height * margin
        or (y + h) >= frame_height * (1 - margin)
    )
    return off_centre and near_edge


def inset_box(
    box: Box,
    frame_width: int,
    frame_height: int,
    padding: float = INSET_PADDING,
) -> Box:
    """
    Estimate the inset's rectangle around a detected subject.

    Grown from the corner the subject is anchored to, so the box hugs the same
    edges the inset does instead of floating around the face. The height comes
    from assuming a 16:9 inset rather than scaling the detection, because the
    detection is often a torso and padding that shape upwards still cuts the
    head off.
    """
    x, y, w, h = box
    horizontal, vertical = nearest_corner(box, frame_width, frame_height)

    new_w = min(frame_width, w * padding)
    new_h = min(frame_height, max(h * padding, new_w / INSET_ASPECT))

    if horizontal == "left":
        new_x = max(0.0, min(x - (new_w - w) / 2.0, frame_width - new_w))
        if x <= frame_width * CORNER_MARGIN:
            new_x = 0.0
    else:
        new_x = max(0.0, min(x + w + (new_w - w) / 2.0 - new_w, frame_width - new_w))
        if (x + w) >= frame_width * (1 - CORNER_MARGIN):
            new_x = frame_width - new_w

    # Vertical growth is biased upwards: detectors return the head or the chest,
    # and a portrait needs headroom, not more torso.
    grow = new_h - h
    if vertical == "top":
        new_y = max(0.0, min(y - grow * 0.6, frame_height - new_h))
        if y <= frame_height * CORNER_MARGIN:
            new_y = 0.0
    else:
        new_y = frame_height - new_h
        if (y + h) < frame_height * (1 - CORNER_MARGIN):
            new_y = max(0.0, min(y - grow * 0.6, frame_height - new_h))

    return (
        int(round(new_x)),
        int(round(new_y)),
        int(round(new_w)),
        int(round(new_h)),
    )


def usable(box: Box, frame_height: int) -> bool:
    """Whether an inset of this size is worth building a layout around."""
    return MIN_INSET_HEIGHT * frame_height <= box[3] <= MAX_INSET_HEIGHT * frame_height


def build_inset_filtergraph(
    source_width: int,
    source_height: int,
    box: Box,
    out_width: int = 1080,
    out_height: int = 1920,
    subtitles_filter: str = "",
) -> str:
    """
    Screen on top at full width, the webcam inset scaled up below.

    The camera band takes its height from the inset's *own* aspect ratio rather
    than a fixed share of the frame. A fixed share stretches faces sideways: a
    16:9 inset forced into a 2:1 band is a 12% horizontal stretch, and that is
    immediately visible on a face.
    """
    box_w = max(2, box[2])
    box_h = max(2, box[3])

    camera_h = int(round(out_width * box_h / float(box_w)))
    camera_h = min(camera_h, int(out_height * MAX_CAMERA_RATIO))
    camera_h -= camera_h % 2
    camera_h = max(2, camera_h)

    screen_h = int(round(out_width * source_height / float(source_width)))
    screen_h -= screen_h % 2
    screen_h = max(2, min(screen_h, out_height - camera_h - 2))

    # Widen (or heighten) the crop to the band's aspect so the scale below is
    # uniform. Clamped to the frame, so an inset hard against an edge simply
    # keeps whatever it can reach.
    target_aspect = out_width / float(camera_h)
    x, y, w, h = box
    if w / float(h) < target_aspect:
        want_w = min(source_width, int(round(h * target_aspect)))
        x = int(round(x + w / 2.0 - want_w / 2.0))
        w = want_w
    else:
        want_h = min(source_height, int(round(w / target_aspect)))
        y = int(round(y + h / 2.0 - want_h / 2.0))
        h = want_h

    x = max(0, min(x, source_width - w))
    y = max(0, min(y, source_height - h))
    w -= w % 2
    h -= h % 2
    x -= x % 2
    y -= y % 2

    tail = f",{subtitles_filter}" if subtitles_filter else ""

    return (
        f"[0:v]split=2[sc][cam];"
        f"[sc]scale={out_width}:{screen_h}:flags=lanczos,setsar=1[screen];"
        f"[cam]crop={w}:{h}:{x}:{y},"
        f"scale={out_width}:{camera_h}:flags=lanczos,setsar=1[camera];"
        f"[screen][camera]vstack=inputs=2,"
        f"pad={out_width}:{out_height}:0:({out_height}-ih)/2:black,setsar=1{tail}[v]"
    )


# Width-to-height ratio of a detected face. `detect_faces_in_clip` reports a
# centre and an area rather than a rectangle, so the box is reconstructed from
# them; faces are taller than they are wide, and assuming a square instead makes
# the box too wide and too short, which then grows the inset off the corner.
FACE_ASPECT = 0.75


def box_from_center_and_area(
    center_x: float, center_y: float, area: float
) -> Box:
    """Rebuild a face rectangle from the detector's centre and area."""
    if area <= 0:
        return (int(center_x), int(center_y), 2, 2)

    height = (area / FACE_ASPECT) ** 0.5
    width = height * FACE_ASPECT
    return (
        int(round(center_x - width / 2.0)),
        int(round(center_y - height / 2.0)),
        max(2, int(round(width))),
        max(2, int(round(height))),
    )


def resolve_inset(
    face_boxes: Sequence[Tuple[int, int, int, int]],
    source_width: int,
    source_height: int,
) -> Optional[Box]:
    """
    Pick the inset rectangle from detected face boxes, or None.

    Detections are checked against `is_cornered` first so a centred talking head
    does not get treated as an inset, then grown to the inset's estimated
    rectangle and size-checked.
    """
    candidates = [
        box for box in face_boxes if is_cornered(box, source_width, source_height)
    ]
    if not candidates:
        logger.info("No corner-anchored subject found for the camera inset layout")
        return None

    # The largest plausible candidate: a false positive on a face inside the
    # shared content is typically smaller than the real webcam.
    best = max(candidates, key=lambda box: box[2] * box[3])
    grown = inset_box(best, source_width, source_height)

    if not usable(grown, source_height):
        logger.info(
            "Estimated inset is %spx tall on a %spx frame, outside the usable range",
            grown[3],
            source_height,
        )
        return None

    return grown
