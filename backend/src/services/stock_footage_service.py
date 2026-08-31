"""
Stock footage lookup for AI-generated scripts.

The script step produces `stock_keywords` per scene; this turns them into actual
candidate clips so the user can see and choose the visuals before anything is
rendered.

Why candidates rather than one pick: stock search is imprecise. "woman typing
laptop" returns a usable shot and four near-misses, and which one fits is a
judgement the person writing the video should make, not a scorer. So each scene
comes back with a short list and the first one pre-selected.

Reuses the existing Pexels client in `broll.py`, which already handles the API
key, orientation and quality selection.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, Sequence

from ..broll import get_video_download_url, search_broll_videos
from ..config import get_config

logger = logging.getLogger(__name__)

# Candidates offered per scene. Enough to choose from without turning the
# review screen into a contact sheet.
CANDIDATES_PER_SCENE = 4

# Scenes are looked up concurrently, but not unboundedly: Pexels rate-limits,
# and a 20-scene script would otherwise fire 20 requests at once.
MAX_CONCURRENT_LOOKUPS = 4


class StockFootageUnavailable(RuntimeError):
    """Raised when no stock provider is configured."""


def is_configured() -> bool:
    return bool(get_config().pexels_api_key)


# Output is 1080x1920. Pexels serves the same clip in several renditions, and
# the largest is often 2160x4096 — four times the pixels that survive the
# render, for four times the download. Renders were spending minutes pulling
# hundreds of megabytes that were immediately scaled away.
TARGET_WIDTH = 1080
TARGET_HEIGHT = 1920


def pick_rendition(video: Dict[str, Any]) -> Optional[str]:
    """
    Choose the rendition closest to the output size.

    Prefers the smallest file that still covers 1080x1920, so nothing is
    upscaled; if every rendition is smaller than that, the largest of them is
    the best available.
    """
    files = [
        item
        for item in (video.get("video_files") or [])
        if item.get("link") and item.get("width") and item.get("height")
    ]
    if not files:
        return None

    def pixels(item: Dict[str, Any]) -> int:
        return int(item["width"]) * int(item["height"])

    covering = [
        item
        for item in files
        if int(item["width"]) >= TARGET_WIDTH and int(item["height"]) >= TARGET_HEIGHT
    ]
    if covering:
        return min(covering, key=pixels)["link"]

    return max(files, key=pixels)["link"]


def _summarize(video: Dict[str, Any]) -> Dict[str, Any]:
    """Reduce a Pexels result to what the review screen needs."""
    return {
        "id": video.get("id"),
        "width": video.get("width"),
        "height": video.get("height"),
        "duration": video.get("duration"),
        "thumbnail": video.get("image"),
        "preview_url": get_video_download_url(video, quality="sd"),
        "download_url": pick_rendition(video)
        or get_video_download_url(video, quality="hd"),
        "author": (video.get("user") or {}).get("name"),
        "author_url": (video.get("user") or {}).get("url"),
        "source": "pexels",
    }


async def find_for_keywords(
    keywords: Sequence[str],
    limit: int = CANDIDATES_PER_SCENE,
) -> List[Dict[str, Any]]:
    """
    Search each keyword in turn and merge the results.

    Keywords are ordered most-specific first by the script agent, so the first
    that returns anything usually gives the best match; later ones only fill
    remaining slots. Duplicates across keywords are dropped.
    """
    found: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for keyword in keywords:
        if len(found) >= limit:
            break
        if not keyword or not keyword.strip():
            continue

        try:
            results = await search_broll_videos(
                keyword.strip(), orientation="portrait", per_page=limit
            )
        except Exception as exc:
            logger.warning("Stock search failed for %r: %s", keyword, exc)
            continue

        for video in results:
            video_id = video.get("id")
            if video_id in seen_ids:
                continue
            seen_ids.add(video_id)
            found.append(_summarize(video))
            if len(found) >= limit:
                break

    return found


async def find_for_scenes(
    scenes: Sequence[Dict[str, Any]],
    limit: int = CANDIDATES_PER_SCENE,
) -> List[Dict[str, Any]]:
    """
    Look up candidates for every scene in a script.

    A scene with no results still comes back, with an empty list, so the review
    screen can show which scenes need different keywords rather than silently
    dropping them.
    """
    if not is_configured():
        raise StockFootageUnavailable(
            "Stock footage needs PEXELS_API_KEY. Set it to search for scene visuals."
        )

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LOOKUPS)

    async def lookup(index: int, scene: Dict[str, Any]) -> Dict[str, Any]:
        keywords = scene.get("stock_keywords") or []
        async with semaphore:
            candidates = await find_for_keywords(keywords, limit)

        return {
            "order": scene.get("order", index + 1),
            "keywords": list(keywords),
            "candidates": candidates,
            # Pre-select the first result so a script is usable without
            # touching every scene, while staying overridable.
            "selected_id": candidates[0]["id"] if candidates else None,
        }

    results = await asyncio.gather(
        *(lookup(index, scene) for index, scene in enumerate(scenes))
    )
    return list(results)


def missing_scene_orders(scene_results: Sequence[Dict[str, Any]]) -> List[int]:
    """Scenes that found nothing, so the caller can prompt for new keywords."""
    return [
        result["order"] for result in scene_results if not result.get("candidates")
    ]
