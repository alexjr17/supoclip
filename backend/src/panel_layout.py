"""
PANEL layout: three or four people from one wide shot, tiled into 9:16.

The existing modes each fail this case. The tracked crop picks one person and
throws away the others, which is wrong when a panel is a conversation. SPLIT
stacks exactly two. The blurred fit keeps everyone but shrinks the whole room to
a strip.

Geometry ported from OpenShorts (https://github.com/mutonby/openshorts),
MIT licensed, Copyright (c) 2024 OpenShorts.

Two of its findings are load-bearing and worth keeping visible:

- The grid is 2x2, never three horizontal bands. A 1080x640 band is *landscape*,
  so filling it from a 1080-tall source needs a ~1551px-wide crop; on a 1920px
  frame holding three people that reaches the neighbours, and every band ends up
  showing two faces. A 2x2 grid has portrait tiles (540x960), which ask for the
  tall narrow crop a person actually occupies.
- The distance to the nearest neighbour is a hard constraint on crop width, not
  a refinement. Clamping to the space a person owns costs some upscaling, and
  that is the right trade: a tile showing the wrong person is broken, a soft one
  is merely worse.

Like SCREENCAST, this is an explicit output format rather than something
detected, because SupoClip already lets the user pick per task.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple
import logging

logger = logging.getLogger(__name__)

MIN_PEOPLE = 3
MAX_PEOPLE = 4

# Fraction of the source height a tile crop starts from before the neighbour
# clamp applies. Below 1.0 so a tile is a person, not the whole room.
PANEL_TIGHTNESS = 0.82

# A source this close to vertical cannot hold a row of people side by side.
MIN_SOURCE_ASPECT = 1.2


def tile_grid(out_width: int, out_height: int) -> Tuple[int, int]:
    """(tile_width, tile_height) for the 2x2 grid, both even for h264."""
    tile_w = out_width // 2
    tile_h = out_height // 2
    return tile_w - (tile_w % 2), tile_h - (tile_h % 2)


def neighbour_gaps(centers: Sequence[Tuple[float, float]]) -> List[Optional[float]]:
    """Horizontal distance from each person to their closest neighbour."""
    xs = [center[0] for center in centers]
    gaps: List[Optional[float]] = []
    for index, x in enumerate(xs):
        others = [abs(x - other) for j, other in enumerate(xs) if j != index]
        gaps.append(min(others) if others else None)
    return gaps


def panel_geometry(
    source_width: int,
    source_height: int,
    tile_width: int,
    tile_height: int,
    center: Tuple[float, float],
    neighbour_gap: Optional[float] = None,
    tightness: float = PANEL_TIGHTNESS,
) -> Tuple[int, int, int, int]:
    """Crop (w, h, x, y) framing one person for one tile."""
    if tile_height <= 0:
        raise ValueError("Tile has no height")

    aspect = tile_width / float(tile_height)

    crop_h = int(round(source_height * max(0.3, min(tightness, 1.0))))
    crop_w = int(round(crop_h * aspect))
    if crop_w > source_width:
        crop_w = source_width
        crop_h = int(round(crop_w / aspect))

    if neighbour_gap:
        # 0.9 leaves a sliver of margin: cropping exactly to the midpoint puts
        # the neighbour's shoulder on the edge of the tile.
        allowed = max(int(neighbour_gap * 0.9), 2)
        if crop_w > allowed:
            crop_w = allowed
            crop_h = int(round(crop_w / aspect))

    crop_w -= crop_w % 2
    crop_h -= crop_h % 2

    center_x, center_y = center
    x = max(0, min(int(round(center_x - crop_w / 2.0)), source_width - crop_w))
    y = max(0, min(int(round(center_y - crop_h * 0.42)), source_height - crop_h))
    return crop_w, crop_h, x - (x % 2), y - (y % 2)


def build_panel_filtergraph(
    source_width: int,
    source_height: int,
    centers: Sequence[Tuple[float, float]],
    out_width: int = 1080,
    out_height: int = 1920,
    subtitles_filter: str = "",
) -> str:
    """
    Tile three or four people into the vertical frame, left to right, top to
    bottom. A trio fills the fourth cell with the wide shot, which doubles as
    context for who else is in the room.
    """
    count = len(centers)
    if not MIN_PEOPLE <= count <= MAX_PEOPLE:
        raise ValueError(f"PANEL needs {MIN_PEOPLE}-{MAX_PEOPLE} people, got {count}")

    tile_w, tile_h = tile_grid(out_width, out_height)
    gaps = neighbour_gaps(centers)
    streams = count if count == MAX_PEOPLE else count + 1

    parts = ["[0:v]split=" + str(streams) + "".join(f"[s{i}]" for i in range(streams)) + ";"]

    for index, center in enumerate(centers):
        crop_w, crop_h, x, y = panel_geometry(
            source_width, source_height, tile_w, tile_h, center, gaps[index]
        )
        parts.append(
            f"[s{index}]crop={crop_w}:{crop_h}:{x}:{y},"
            f"scale={tile_w}:{tile_h}:flags=lanczos,setsar=1[t{index}];"
        )

    if count == MIN_PEOPLE:
        # Letterboxed inside the tile so the wide shot loses nothing.
        parts.append(
            f"[s3]scale={tile_w}:-2:flags=lanczos,"
            f"pad={tile_w}:{tile_h}:0:({tile_h}-ih)/2:black,setsar=1[t3];"
        )

    tail = f",{subtitles_filter}" if subtitles_filter else ""
    parts.append(
        "[t0][t1]hstack=inputs=2[top];"
        "[t2][t3]hstack=inputs=2[bot];"
        f"[top][bot]vstack=inputs=2,pad={out_width}:{out_height}:0:0,setsar=1{tail}[v]"
    )
    return "".join(parts)


def is_suitable(source_width: int, source_height: int, people: int) -> bool:
    """Whether tiling makes sense for this source and headcount."""
    if source_width <= 0 or source_height <= 0:
        return False
    if not MIN_PEOPLE <= people <= MAX_PEOPLE:
        return False
    return source_width / float(source_height) >= MIN_SOURCE_ASPECT


def cluster_people(
    face_centers: Sequence[Tuple[float, float]],
    source_width: int,
    max_people: int = MAX_PEOPLE,
) -> List[Tuple[float, float]]:
    """
    Reduce raw per-frame detections to one centre per person, left to right.

    Detections arrive as a cloud of points across sampled frames. Faces of the
    same seated person cluster tightly in x, so grouping by horizontal distance
    separates people without tracking identity across frames.
    """
    if not face_centers:
        return []

    # A person occupies roughly this fraction of the width; closer detections
    # are the same person seen on different frames.
    threshold = source_width * 0.12

    ordered = sorted(face_centers, key=lambda center: center[0])
    clusters: List[List[Tuple[float, float]]] = [[ordered[0]]]

    for center in ordered[1:]:
        if center[0] - clusters[-1][-1][0] <= threshold:
            clusters[-1].append(center)
        else:
            clusters.append([center])

    # Keep the most-detected clusters: a fleeting false positive should not
    # displace someone who is present for the whole scene.
    clusters.sort(key=len, reverse=True)
    kept = clusters[:max_people]
    kept.sort(key=lambda cluster: cluster[0][0])

    people: List[Tuple[float, float]] = []
    for cluster in kept:
        xs = sorted(center[0] for center in cluster)
        ys = sorted(center[1] for center in cluster)
        middle = len(xs) // 2
        people.append((xs[middle], ys[middle]))

    return people
