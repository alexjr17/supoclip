"""
PublishService - schedules and uploads clips to YouTube.

Primary provider is the YouTube Data API v3 (see
``youtube_publish_service``): the clip is uploaded as private with a
``publishAt`` timestamp and YouTube makes it public at that time. No monthly
upload quota, only the daily API quota (~6 uploads/day by default).

Upload-Post remains as a fallback provider when YouTube OAuth is not
configured (multipart POST to https://api.upload-post.com/api/upload with a
scheduled_date).

Scheduling fills each calendar day up to DAILY_PUBLISH_LIMIT clips. If a day
already has its limit, the next clip goes to the following day. If a day has
fewer, the missing slots are filled first.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..repositories.clip_repository import ClipRepository
from ..runtime_settings import get_cached_setting
from . import profile_service
from .profile_context import profile_token_context
from .tiktok_publish_service import (
    _normalize_title as _normalize_tiktok_title,
    clip_title as tiktok_clip_title,
    is_tiktok_configured,
    list_tiktok_videos,
    upload_video_now as upload_tiktok_video_now,
)
from .youtube_publish_service import (
    _normalize_title,
    clip_title,
    is_youtube_configured,
    list_channel_videos,
    upload_video_scheduled,
)

logger = logging.getLogger(__name__)

UPLOAD_POST_UPLOAD_URL = "https://api.upload-post.com/api/upload"
UPLOAD_POST_USERS_URL = "https://api.upload-post.com/api/uploadposts/users"

DAILY_PUBLISH_LIMIT = int(os.getenv("PUBLISH_DAILY_LIMIT", "10"))
SCHEDULING_HORIZON_DAYS = 14
SCHEDULER_INTERVAL_SECONDS = int(
    os.getenv("PUBLISH_SCHEDULER_INTERVAL_SECONDS", "1800")
)

# Generic (non-quota) failure backoff between retries of the same clip.
GENERIC_RETRY_BACKOFF_MINUTES = int(
    os.getenv("PUBLISH_RETRY_BACKOFF_MINUTES", "60")
)

# In-memory retry throttle keyed by clip id (single scheduler process). A clip
# that failed is not retried before its timestamp, avoiding quota-burn loops
# that keep a failed clip hammering the YouTube API every scheduler run.
_next_retry_at: dict[str, datetime] = {}


def _quota_window_reset() -> datetime:
    """Next midnight Pacific Time, when Google resets the daily API quota."""
    pacific = ZoneInfo("America/Los_Angeles")
    tomorrow = datetime.now(pacific).date() + timedelta(days=1)
    return datetime.combine(tomorrow, dtime.min, tzinfo=pacific)

# Spread ten publishing slots across the day (local time of PUBLISH_TIMEZONE).
PUBLISH_SLOT_TIMES: tuple[dtime, ...] = (
    dtime(9, 0),
    dtime(10, 30),
    dtime(12, 0),
    dtime(13, 30),
    dtime(15, 0),
    dtime(16, 30),
    dtime(18, 0),
    dtime(19, 30),
    dtime(21, 0),
    dtime(22, 30),
)


def get_publish_timezone() -> str:
    return os.getenv("PUBLISH_TIMEZONE", "UTC")


def get_upload_post_api_key() -> Optional[str]:
    value = get_cached_setting("UPLOAD_POST_API_KEY") or os.getenv(
        "UPLOAD_POST_API_KEY"
    )
    return value.strip() if value and value.strip() else None


def get_upload_post_profile() -> Optional[str]:
    value = get_cached_setting("UPLOAD_POST_PROFILE") or os.getenv(
        "UPLOAD_POST_PROFILE"
    )
    return value.strip() if value and value.strip() else None


def is_publish_configured() -> bool:
    if is_youtube_configured():
        return True
    return bool(get_upload_post_api_key() and get_upload_post_profile())


def get_publish_provider() -> str:
    return "youtube" if is_youtube_configured() else "upload_post"


async def fetch_upload_post_profiles(
    api_key: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Fetch the profiles (connected accounts) available on an Upload-Post key."""
    key = api_key or get_upload_post_api_key()
    if not key:
        raise ValueError("Upload-Post API key is not configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        response = await client.get(
            UPLOAD_POST_USERS_URL, headers={"Authorization": f"Apikey {key}"}
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"Upload-Post profiles request failed ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    profiles = payload.get("profiles", []) if isinstance(payload, dict) else []
    return [
        p if isinstance(p, dict) else {"username": str(p)}
        for p in profiles
        if p
    ]


def _clip_title(clip: Dict[str, Any]) -> str:
    title = (clip.get("hook_title") or "").strip()
    if title:
        return title[:100]
    text = (clip.get("text") or "").strip()
    if text:
        first_line = text.splitlines()[0].strip()
        if first_line:
            return first_line[:100]
    return "SupoClip Short"


def _clip_description(clip: Dict[str, Any]) -> str:
    text = (clip.get("text") or "").strip()
    hook = (clip.get("hook_title") or "").strip()
    parts = [part for part in (hook, text) if part]
    description = "\n\n".join(parts)[:1500]
    return description or f"Clip #{clip.get('clip_order') or ''}".rstrip()


def _find_next_slot(
    used_slots: Dict[str, list],
    now: datetime,
    tz: ZoneInfo,
    claimed: Optional[Dict[str, list]] = None,
) -> Optional[datetime]:
    """Next free publishing slot, filling days in order up to the limit."""
    if claimed is None:
        claimed = {}
    today = now.date()
    for offset in range(SCHEDULING_HORIZON_DAYS):
        day = today + timedelta(days=offset)
        day_key = day.isoformat()
        taken = set(used_slots.get(day_key, [])) | set(claimed.get(day_key, []))
        if len(taken) >= DAILY_PUBLISH_LIMIT:
            continue
        for slot_time in PUBLISH_SLOT_TIMES:
            if slot_time in taken:
                continue
            slot_dt = datetime.combine(day, slot_time, tzinfo=tz)
            if offset == 0 and slot_dt <= now + timedelta(minutes=5):
                continue
            claimed.setdefault(day_key, []).append(slot_time)
            return slot_dt
    return None


async def _upload_to_upload_post(
    clip: Dict[str, Any],
    scheduled_at: datetime,
    api_key: str,
    profile: str,
    tz_name: str,
) -> Dict[str, Any]:
    """Send one clip to Upload-Post with a scheduled publish date."""
    file_path = clip.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise FileNotFoundError(f"Clip file not found: {file_path}")

    filename = clip.get("filename") or Path(file_path).name
    if not filename.lower().endswith(".mp4"):
        filename = f"{Path(filename).stem or 'clip'}.mp4"

    title = _clip_title(clip)
    description = _clip_description(clip)

    data: Dict[str, Any] = {
        "user": profile,
        "title": title,
        "platform[]": ["youtube"],
        "async_upload": "true",
        "scheduled_date": scheduled_at.isoformat(),
        "timezone": tz_name,
        "youtube_title": title,
        "youtube_description": description,
        "privacyStatus": "public",
    }

    content = await asyncio.to_thread(Path(file_path).read_bytes)
    files = {"video": (filename, content, "video/mp4")}
    headers = {"Authorization": f"Apikey {api_key}"}

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(180.0, connect=15.0)
    ) as client:
        response = await client.post(
            UPLOAD_POST_UPLOAD_URL, headers=headers, data=data, files=files
        )

    if response.status_code not in (200, 201, 202):
        raise RuntimeError(
            f"Upload-Post upload failed ({response.status_code}): {response.text[:500]}"
        )
    return response.json()


async def run_publish_schedule_once(db: AsyncSession) -> Dict[str, Any]:
    """Schedule all pending clips to the next free slots and upload.

    Uses the YouTube Data API (direct, free) when OAuth is configured, falling
    back to Upload-Post otherwise.

    Duplicate protection: before uploading, clips whose title already exists
    on the connected YouTube channel (or that already carry a recorded
    ``youtube_video_id``) are marked as already published and skipped.
    """
    if not is_publish_configured():
        return {
            "configured": False,
            "provider": get_publish_provider(),
            "skipped": True,
            "scheduled": 0,
            "failed": 0,
            "already_published": 0,
        }

    api_key = get_upload_post_api_key()
    profile = get_upload_post_profile()

    tz_name = get_publish_timezone()
    tz = ZoneInfo(tz_name)

    published_now = await ClipRepository.mark_past_scheduled_as_published(db)
    used_slots = await ClipRepository.scheduled_slot_times_per_day(db, tz_name)
    pending = await ClipRepository.list_publish_pending_clips(db)

    if not pending:
        await db.commit()
        return {
            "configured": True,
            "provider": get_publish_provider(),
            "skipped": True,
            "scheduled": 0,
            "failed": 0,
            "already_published": 0,
            "published_now": published_now,
        }

    # Resolve the publishing profile (and its connected account tokens) for
    # every pending clip so each clip uploads to the right channel.
    profile_contexts: dict[str, dict[str, Any]] = {}
    for clip in pending:
        ctx = await profile_service.resolve_profile_for_clip(db, clip)
        if ctx is None:
            continue
        profile_contexts.setdefault(ctx["profile_id"], ctx)

    has_profile_youtube = any(
        ctx["overrides"].get("YOUTUBE_REFRESH_TOKEN")
        for ctx in profile_contexts.values()
    )
    use_upload_post = not (is_youtube_configured() or has_profile_youtube)

    # Build a lookup of YouTube titles already on each profile's channel
    # (dedup guard), fetched under that profile's token context.
    existing_titles_by_profile: dict[str, dict[str, str]] = {}
    if not use_upload_post:
        for profile_id, ctx in profile_contexts.items():
            if not ctx["overrides"].get("YOUTUBE_REFRESH_TOKEN"):
                continue
            try:
                with profile_token_context(ctx["overrides"], ctx["sink"]):
                    channel_videos = await list_channel_videos()
                existing_titles_by_profile[profile_id] = {
                    _normalize_title(v["title"]): v["video_id"]
                    for v in channel_videos
                    if v.get("title")
                }
            except Exception:  # noqa: BLE001 - dedup is best-effort
                logger.warning(
                    "Unable to fetch channel videos for profile %s dedup; continuing",
                    profile_id,
                    exc_info=True,
                )
    existing_video_ids = await ClipRepository.list_all_youtube_video_ids(db)

    now = datetime.now(tz)
    scheduled = 0
    failed = 0
    already_published = 0
    deferred = 0
    failures: list[dict] = []
    quota_blocked = False
    claimed: Dict[str, list] = {}
    for clip in pending:
        clip_id = clip["id"]

        ctx = profile_contexts.get(clip.get("publish_profile_id"))
        if ctx is None and clip.get("user_id"):
            ctx = await profile_service.resolve_profile_for_clip(db, clip)
            if ctx:
                profile_contexts[ctx["profile_id"]] = ctx
        if ctx is None:
            failed += 1
            await ClipRepository.update_clip_publish(
                db, clip_id, "failed", error="No publishing profile could be resolved"
            )
            continue

        if clip.get("youtube_video_id"):
            # Already uploaded previously: mark published, don't re-upload.
            already_published += 1
            await ClipRepository.update_clip_publish(db, clip_id, "published")
            continue

        if not use_upload_post:
            existing_titles = existing_titles_by_profile.get(ctx["profile_id"], {})
            title_key = _normalize_title(clip_title(clip))
            match_video_id = existing_titles.get(title_key)
            if match_video_id:
                already_published += 1
                await ClipRepository.mark_user_clips_published_from_sync(
                    db, clip_id, match_video_id, clip_title(clip)
                )
                continue

        # Skip clips still in retry backoff so we don't burn quota/errors on a
        # clip that just failed, and report them as deferred instead.
        retry_at = _next_retry_at.get(clip_id)
        if retry_at and retry_at > now:
            deferred += 1
            continue

        slot = _find_next_slot(used_slots, now, tz, claimed)
        if slot is None:
            failed += 1
            await ClipRepository.update_clip_publish(
                db,
                clip_id,
                "failed",
                error="No free publishing slots within the scheduling horizon",
            )
            continue
        try:
            result: Dict[str, Any] = {}
            with profile_token_context(ctx["overrides"], ctx["sink"]):
                if use_upload_post:
                    if not api_key or not profile:
                        raise RuntimeError("Upload-Post provider is not configured")
                    await _upload_to_upload_post(clip, slot, api_key, profile, tz_name)
                else:
                    result = await upload_video_scheduled(clip, slot)
            await ClipRepository.update_clip_publish(
                db, clip_id, "scheduled", slot
            )
            video_id = result.get("video_id") if isinstance(result, dict) else None
            if video_id:
                await ClipRepository.set_clip_youtube_video_id(db, clip_id, video_id)
            scheduled += 1
        except Exception as exc:  # noqa: BLE001 - record per-clip failure
            logger.exception("Publish scheduling failed for clip %s", clip_id)
            error_text = str(exc)
            failed += 1
            if "429" in error_text or "quota" in error_text.lower():
                quota_blocked = True
                _next_retry_at[clip_id] = _quota_window_reset()
            else:
                _next_retry_at[clip_id] = now + timedelta(
                    minutes=GENERIC_RETRY_BACKOFF_MINUTES
                )
            failures.append({"clip_id": clip_id, "error": error_text[:500]})
            await ClipRepository.update_clip_publish(
                db, clip_id, "failed", error=error_text[:1000]
            )

    await db.commit()
    return {
        "configured": True,
        "provider": get_publish_provider(),
        "skipped": False,
        "scheduled": scheduled,
        "failed": failed,
        "already_published": already_published,
        "deferred": deferred,
        "failures": failures,
        "quota_blocked": quota_blocked,
        "quota_reset_at": _quota_window_reset().isoformat() if quota_blocked else None,
        "published_now": published_now,
    }


async def _any_pending_tiktok_profile(db: AsyncSession) -> bool:
    """Whether any pending/due clip resolves to a profile with TikTok tokens."""
    clips = (
        await ClipRepository.list_tiktok_publish_due_clips(db)
        + await ClipRepository.list_tiktok_publish_pending_clips(db)
    )
    for clip in clips:
        ctx = await profile_service.resolve_profile_for_clip(db, clip)
        if ctx and ctx["overrides"].get("TIKTOK_REFRESH_TOKEN") and ctx["overrides"].get("TIKTOK_OPEN_ID"):
            return True
    return False


async def run_tiktok_publish_schedule_once(db: AsyncSession) -> Dict[str, Any]:
    """Run the TikTok publishing schedule once.

    TikTok's Content Posting API has no native scheduling, so this worker owns
    the schedule: it assigns each pending clip a slot time (using the same
    daily slots as YouTube) and, when a slot time arrives, uploads the clip
    immediately through TikTok's Direct Post flow.

    Steps:
    1. Publish every scheduled clip whose slot time has passed (``due``).
    2. Dedup pending clips against videos already on the TikTok account (and
       clips that already carry a recorded ``tiktok_video_id``).
    3. Assign the next free slots to the remaining pending clips.
    """
    if not (is_tiktok_configured() or await _any_pending_tiktok_profile(db)):
        return {
            "configured": False,
            "provider": "tiktok",
            "skipped": True,
            "published_now": 0,
            "scheduled": 0,
            "failed": 0,
            "already_published": 0,
        }

    tz_name = get_publish_timezone()
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)

    published_now = 0
    failed = 0

    # 1. Publish clips whose slot time has arrived.
    due_clips = await ClipRepository.list_tiktok_publish_due_clips(db)
    profile_contexts: dict[str, dict[str, Any]] = {}
    for clip in due_clips:
        if clip.get("tiktok_video_id"):
            await ClipRepository.update_clip_tiktok_publish(
                db, clip["id"], "published", scheduled_at=clip.get("tiktok_scheduled_at")
            )
            continue
        ctx = await profile_service.resolve_profile_for_clip(db, clip)
        if ctx is None:
            failed += 1
            await ClipRepository.update_clip_tiktok_publish(
                db, clip["id"], "failed", error="No publishing profile could be resolved"
            )
            continue
        profile_contexts.setdefault(ctx["profile_id"], ctx)
        try:
            with profile_token_context(ctx["overrides"], ctx["sink"]):
                result = await upload_tiktok_video_now(db, clip)
            await ClipRepository.update_clip_tiktok_publish(
                db,
                clip["id"],
                "published",
                scheduled_at=clip.get("tiktok_scheduled_at"),
                published_at=datetime.now(tz),
            )
            publish_id = result.get("publish_id") if isinstance(result, dict) else None
            if publish_id:
                await ClipRepository.set_clip_tiktok_video_id(db, clip["id"], publish_id)
            published_now += 1
        except Exception as exc:  # noqa: BLE001 - record per-clip failure
            logger.exception("TikTok due publish failed for clip %s", clip["id"])
            failed += 1
            await ClipRepository.update_clip_tiktok_publish(
                db, clip["id"], "failed", error=str(exc)[:1000]
            )

    # 2-3. Schedule the pending clips.
    used_slots = await ClipRepository.tiktok_scheduled_slot_times_per_day(db, tz_name)
    pending = await ClipRepository.list_tiktok_publish_pending_clips(db)

    if pending:
        # Build a lookup of captions already on each profile's TikTok account
        # (dedup guard), fetched under that profile's token context.
        for clip in pending:
            ctx = await profile_service.resolve_profile_for_clip(db, clip)
            if ctx:
                profile_contexts.setdefault(ctx["profile_id"], ctx)

        existing_titles_by_profile: dict[str, dict[str, str]] = {}
        existing_tiktok_ids = await ClipRepository.list_all_tiktok_video_ids(db)
        for profile_id, ctx in profile_contexts.items():
            if not ctx["overrides"].get("TIKTOK_REFRESH_TOKEN"):
                continue
            try:
                with profile_token_context(ctx["overrides"], ctx["sink"]):
                    account_videos = await list_tiktok_videos(db)
                existing_titles_by_profile[profile_id] = {
                    _normalize_tiktok_title(v["title"]): v["video_id"]
                    for v in account_videos
                    if v.get("title")
                }
            except Exception:  # noqa: BLE001 - dedup is best-effort
                logger.warning(
                    "Unable to fetch TikTok videos for profile %s dedup; continuing",
                    profile_id,
                    exc_info=True,
                )

        scheduled = 0
        already_published = 0
        claimed: Dict[str, list] = {}
        for clip in pending:
            clip_id = clip["id"]

            ctx = profile_contexts.get(clip.get("publish_profile_id"))
            if ctx is None and clip.get("user_id"):
                ctx = await profile_service.resolve_profile_for_clip(db, clip)
                if ctx:
                    profile_contexts[ctx["profile_id"]] = ctx
            if ctx is None:
                failed += 1
                await ClipRepository.update_clip_tiktok_publish(
                    db, clip_id, "failed", error="No publishing profile could be resolved"
                )
                continue

            if clip.get("tiktok_video_id"):
                already_published += 1
                await ClipRepository.update_clip_tiktok_publish(
                    db, clip_id, "published"
                )
                continue

            existing_titles = existing_titles_by_profile.get(ctx["profile_id"], {})
            title_key = _normalize_tiktok_title(tiktok_clip_title(clip))
            match_video_id = existing_titles.get(title_key)
            if match_video_id and match_video_id not in existing_tiktok_ids:
                already_published += 1
                await ClipRepository.mark_user_clips_published_from_tiktok_sync(
                    db, clip_id, match_video_id, tiktok_clip_title(clip)
                )
                existing_tiktok_ids.add(match_video_id)
                continue

            slot = _find_next_slot(used_slots, now, tz, claimed)
            if slot is None:
                failed += 1
                await ClipRepository.update_clip_tiktok_publish(
                    db,
                    clip_id,
                    "failed",
                    error="No free TikTok publishing slots within the scheduling horizon",
                )
                continue
            await ClipRepository.update_clip_tiktok_publish(
                db, clip_id, "scheduled", scheduled_at=slot
            )
            scheduled += 1

        await db.commit()
        return {
            "configured": True,
            "provider": "tiktok",
            "skipped": False,
            "published_now": published_now,
            "scheduled": scheduled,
            "failed": failed,
            "already_published": already_published,
        }

    await db.commit()
    return {
        "configured": True,
        "provider": "tiktok",
        "skipped": True,
        "published_now": published_now,
        "scheduled": 0,
        "failed": failed,
        "already_published": 0,
    }
