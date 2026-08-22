"""
Publish API routes - mark clips for auto-publishing, query status, and trigger runs.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from ...database import get_db
from ...services.task_service import TaskService
from ...auth_headers import resolve_authenticated_user_id
from ...config import get_config
from ...repositories.clip_repository import ClipRepository
from ...services import profile_service
from ...services.profile_context import profile_token_context
from ...services.publish_service import (
    DAILY_PUBLISH_LIMIT,
    fetch_upload_post_profiles,
    is_publish_configured,
    run_publish_schedule_once,
    run_tiktok_publish_schedule_once,
    get_publish_timezone,
    get_publish_provider,
)
from ...services.youtube_publish_service import (
    build_youtube_auth_url,
    complete_youtube_oauth,
    fetch_youtube_channel,
    get_youtube_client_id,
    list_channel_videos,
    set_video_privacy_public,
    upload_video_now,
)
from ...services.tiktok_publish_service import (
    _normalize_title,
    build_tiktok_auth_url,
    clip_title,
    complete_tiktok_oauth,
    fetch_tiktok_user,
    get_tiktok_client_key,
    list_tiktok_videos,
    store_tiktok_pkce,
    upload_video_now as upload_tiktok_video_now,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["publish"])

PROFILE_ID_HEADER = "x-supoclip-profile-id"


class PublishClipsRequest(BaseModel):
    clip_ids: list[str] = Field(min_length=1)
    publish: bool = True


class PublishTikTokRequest(BaseModel):
    task_id: str
    clip_ids: list[str] = Field(min_length=1)


async def _require_user(request: Request, db: AsyncSession) -> str:
    user_id = await resolve_authenticated_user_id(request, db, get_config())
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _profile_id_from_header(request: Request) -> str | None:
    value = request.headers.get(PROFILE_ID_HEADER)
    return value.strip() if value and value.strip() else None


async def _resolve_active_profile(
    request: Request, db: AsyncSession, user_id: str
) -> dict:
    """Resolve the request's active publishing profile (falls back to default)."""
    return await profile_service.resolve_active_profile(
        db, user_id, _profile_id_from_header(request)
    )


def _platform_configured(profile: dict, platform: str) -> bool:
    accounts = profile.get("accounts", {})
    account = accounts.get(platform)
    return bool(account and account.get("connected"))


@router.post("/tasks/{task_id}/clips/publish")
async def mark_clips_for_publish(
    task_id: str,
    req: PublishClipsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark or unmark clips of a task for automatic publishing."""
    user_id = await _require_user(request, db)

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this task")

    clips = await task_service.clip_repo.get_clips_by_task(db, task_id)
    valid_ids = {clip["id"] for clip in clips}
    unknown = [cid for cid in req.clip_ids if cid not in valid_ids]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Clip(s) do not belong to this task: {unknown}",
        )

    await ClipRepository.set_clip_publish_request(db, req.clip_ids, req.publish)
    if req.publish:
        profile = await _resolve_active_profile(request, db, user_id)
        await ClipRepository.set_clip_publish_profile(
            db, req.clip_ids, profile["id"]
        )
    return {
        "ok": True,
        "publish": req.publish,
        "clip_ids": req.clip_ids,
    }


@router.post("/tasks/{task_id}/clips/tiktok-publish")
async def mark_clips_for_tiktok_publish(
    task_id: str,
    req: PublishClipsRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark or unmark clips of a task for scheduled TikTok publishing."""
    user_id = await _require_user(request, db)

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this task")

    clips = await task_service.clip_repo.get_clips_by_task(db, task_id)
    valid_ids = {clip["id"] for clip in clips}
    unknown = [cid for cid in req.clip_ids if cid not in valid_ids]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Clip(s) do not belong to this task: {unknown}",
        )

    await ClipRepository.set_clip_tiktok_publish_request(db, req.clip_ids, req.publish)
    if req.publish:
        profile = await _resolve_active_profile(request, db, user_id)
        await ClipRepository.set_clip_publish_profile(
            db, req.clip_ids, profile["id"]
        )
    return {
        "ok": True,
        "publish": req.publish,
        "clip_ids": req.clip_ids,
    }


@router.get("/publish/status")
async def publish_status(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Publishing configuration and the authenticated user's queue status."""
    user_id = await _require_user(request, db)

    counts = await ClipRepository.count_publish_status_by_user(db, user_id)
    scheduled_by_day = await ClipRepository.count_scheduled_per_day(db)
    pending = await ClipRepository.list_publish_pending_clips(db)
    tiktok_counts = await ClipRepository.count_tiktok_publish_status_by_user(db, user_id)
    tiktok_scheduled_by_day = await ClipRepository.count_tiktok_scheduled_per_day(db)
    tiktok_pending = await ClipRepository.list_tiktok_publish_pending_clips(db)

    profile = await _resolve_active_profile(request, db, user_id)
    active_profile_id = profile["id"]
    profiles = await profile_service.list_profiles(db, user_id)

    youtube_configured = _platform_configured(profile, "youtube")
    tiktok_configured = _platform_configured(profile, "tiktok")

    channel = None
    if youtube_configured:
        try:
            async with profile_service.profile_token_context_async(db, active_profile_id):
                channel = await fetch_youtube_channel()
        except Exception as exc:  # noqa: BLE001 - status should not hard-fail
            logger.warning("Unable to fetch YouTube channel: %s", exc)

    tiktok_user = None
    if tiktok_configured:
        try:
            async with profile_service.profile_token_context_async(db, active_profile_id):
                tiktok_user = await fetch_tiktok_user(db)
        except Exception as exc:  # noqa: BLE001 - status should not hard-fail
            logger.warning("Unable to fetch TikTok user: %s", exc)

    return {
        "configured": is_publish_configured(),
        "provider": get_publish_provider(),
        "youtube_configured": youtube_configured,
        "channel": channel,
        "tiktok_configured": tiktok_configured,
        "tiktok_user": tiktok_user,
        "timezone": get_publish_timezone(),
        "daily_limit": DAILY_PUBLISH_LIMIT,
        "counts": counts,
        "scheduled_by_day": scheduled_by_day,
        "pending": len(pending),
        "tiktok_counts": tiktok_counts,
        "tiktok_scheduled_by_day": tiktok_scheduled_by_day,
        "tiktok_pending": len(tiktok_pending),
        "active_profile_id": active_profile_id,
        "profiles": profiles,
    }


@router.get("/publish/youtube/auth-url")
async def youtube_auth_url(
    request: Request,
    db: AsyncSession = Depends(get_db),
    profile_id: str | None = None,
):
    """Return a Google OAuth authorization URL for connecting YouTube."""
    user_id = await _require_user(request, db)
    if not get_youtube_client_id():
        raise HTTPException(
            status_code=400,
            detail="YOUTUBE_CLIENT_ID is not configured. Set it in Admin settings or .env first.",
        )
    profile = await _resolve_active_profile(request, db, user_id)
    url, _state = build_youtube_auth_url(profile["id"])
    return {"url": url}


@router.get("/publish/youtube/callback")
async def youtube_oauth_callback(
    code: str,
    state: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """OAuth callback: exchange the code, persist the refresh token, redirect back."""
    profile_id = None
    if "|" in state:
        _, profile_id = state.split("|", 1)
    try:
        result = await complete_youtube_oauth(db, code, state, profile_id=profile_id)
    except Exception as exc:  # noqa: BLE001 - redirect with error to the frontend
        logger.exception("YouTube OAuth callback failed")
        config = get_config()
        return RedirectResponse(
            f"{config.app_base_url}/settings?youtube_error=1",
            status_code=302,
        )
    config = get_config()
    if result.get("channel"):
        return RedirectResponse(
            f"{config.app_base_url}/settings?youtube_connected=1",
            status_code=302,
        )
    return RedirectResponse(
        f"{config.app_base_url}/settings?youtube_error=1",
        status_code=302,
    )


@router.get("/publish/tiktok/auth-url")
async def tiktok_auth_url(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return a TikTok OAuth authorization URL for connecting an account."""
    user_id = await _require_user(request, db)
    if not get_tiktok_client_key():
        raise HTTPException(
            status_code=400,
            detail="TIKTOK_CLIENT_KEY is not configured. Set it in Admin settings or .env first.",
        )
    profile = await _resolve_active_profile(request, db, user_id)
    url, state, code_verifier = build_tiktok_auth_url(profile["id"])
    await store_tiktok_pkce(db, state, code_verifier)
    return {"url": url}


@router.get("/publish/tiktok/callback")
async def tiktok_oauth_callback(
    code: str,
    state: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """OAuth callback: exchange the code, persist the tokens, redirect back."""
    profile_id = None
    if "|" in state:
        _, profile_id = state.split("|", 1)
    try:
        result = await complete_tiktok_oauth(db, code, state, profile_id=profile_id)
    except Exception as exc:  # noqa: BLE001 - redirect with error to the frontend
        logger.exception("TikTok OAuth callback failed")
        config = get_config()
        return RedirectResponse(
            f"{config.app_base_url}/settings?tiktok_error=1",
            status_code=302,
        )
    config = get_config()
    if result.get("connected"):
        return RedirectResponse(
            f"{config.app_base_url}/settings?tiktok_connected=1",
            status_code=302,
        )
    return RedirectResponse(
        f"{config.app_base_url}/settings?tiktok_error=1",
        status_code=302,
    )


@router.post("/publish/tiktok/publish")
async def publish_clips_to_tiktok(
    req: PublishTikTokRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Publish the given clips of a task to TikTok immediately.

    Skips clips that already carry a ``tiktok_video_id`` (no duplicates).
    """
    user_id = await _require_user(request, db)

    task_service = TaskService(db)
    task = await task_service.task_repo.get_task_by_id(db, req.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.get("user_id") != user_id:
        raise HTTPException(status_code=403, detail="Not authorized for this task")

    clips = await task_service.clip_repo.get_clips_by_task(db, req.task_id)
    valid_ids = {clip["id"] for clip in clips}
    unknown = [cid for cid in req.clip_ids if cid not in valid_ids]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Clip(s) do not belong to this task: {unknown}",
        )

    profile = await _resolve_active_profile(request, db, user_id)
    if not _platform_configured(profile, "tiktok"):
        raise HTTPException(
            status_code=400,
            detail="TikTok is not connected for this channel. Connect it from Settings first.",
        )

    clips_by_id = {clip["id"]: clip for clip in clips}
    to_publish = [
        clips_by_id[cid] for cid in req.clip_ids if not clips_by_id[cid].get("tiktok_video_id")
    ]
    skipped = len(req.clip_ids) - len(to_publish)

    published = 0
    failed = 0
    failures: list[Dict[str, Any]] = []
    async with profile_service.profile_token_context_async(db, profile["id"]):
        for clip in to_publish:
            try:
                result = await upload_tiktok_video_now(db, clip)
                await ClipRepository.update_clip_publish(
                    db,
                    clip["id"],
                    "published",
                    scheduled_at=clip.get("scheduled_publish_at"),
                    published_at=datetime.now(timezone.utc),
                )
                publish_id = result.get("publish_id")
                if publish_id:
                    await ClipRepository.set_clip_tiktok_video_id(db, clip["id"], publish_id)
                published += 1
            except Exception as exc:  # noqa: BLE001 - record per-clip failure
                logger.exception("TikTok publish failed for clip %s", clip["id"])
                failed += 1
                await ClipRepository.update_clip_publish(
                    db, clip["id"], "failed", error=str(exc)[:1000]
                )
                failures.append({"clip_id": clip["id"], "error": str(exc)[:500]})

    return {
        "ok": True,
        "published": published,
        "failed": failed,
        "skipped": skipped,
        "failures": failures,
    }


@router.post("/publish/tiktok/mass-upload")
async def mass_upload_clips_to_tiktok(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Publish every not-yet-TikTok-published completed clip immediately."""
    user_id = await _require_user(request, db)
    profile = await _resolve_active_profile(request, db, user_id)
    if not _platform_configured(profile, "tiktok"):
        raise HTTPException(
            status_code=400,
            detail="TikTok is not connected for this channel. Connect it from Settings first.",
        )

    clips = await ClipRepository.list_user_clips_for_tiktok(db, user_id)
    published = 0
    failed = 0
    failures: list[Dict[str, Any]] = []
    async with profile_service.profile_token_context_async(db, profile["id"]):
        for clip in clips:
            try:
                result = await upload_tiktok_video_now(db, clip)
                await ClipRepository.update_clip_publish(
                    db,
                    clip["id"],
                    "published",
                    scheduled_at=clip.get("scheduled_publish_at"),
                    published_at=datetime.now(timezone.utc),
                )
                publish_id = result.get("publish_id")
                if publish_id:
                    await ClipRepository.set_clip_tiktok_video_id(db, clip["id"], publish_id)
                published += 1
            except Exception as exc:  # noqa: BLE001 - record per-clip failure
                logger.exception("TikTok publish failed for clip %s", clip["id"])
                failed += 1
                await ClipRepository.update_clip_publish(
                    db, clip["id"], "failed", error=str(exc)[:1000]
                )
                failures.append({"clip_id": clip["id"], "error": str(exc)[:500]})

    return {
        "ok": True,
        "clips": len(clips),
        "published": published,
        "failed": failed,
        "failures": failures,
    }


@router.post("/publish/tiktok/schedule")
async def mass_schedule_clips_to_tiktok(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark every unpublished completed clip for TikTok and run the scheduler once.

    Assigns the next free publishing slots to each clip. Because TikTok has no
    native scheduling, the worker will upload each clip when its slot time
    arrives. Skips clips already published/scheduled or carrying a recorded
    ``tiktok_video_id`` (no duplicates).
    """
    user_id = await _require_user(request, db)
    profile = await _resolve_active_profile(request, db, user_id)
    if not _platform_configured(profile, "tiktok"):
        raise HTTPException(
            status_code=400,
            detail="TikTok is not connected for this channel. Connect it from Settings first.",
        )

    clips = await ClipRepository.list_user_clips_for_tiktok_schedule(db, user_id)
    clip_ids = [clip["id"] for clip in clips]
    if clip_ids:
        await ClipRepository.set_clip_tiktok_publish_request(db, clip_ids, True)
        await ClipRepository.set_clip_publish_profile(db, clip_ids, profile["id"])

    result = await run_tiktok_publish_schedule_once(db)
    return {
        "provider": "tiktok",
        "clips_marked": len(clip_ids),
        "published_now": result.get("published_now", 0),
        "scheduled": result.get("scheduled", 0),
        "already_published": result.get("already_published", 0),
        "failed": result.get("failed", 0),
        "skipped": result.get("skipped", False),
        "configured": result.get("configured", False),
    }


@router.post("/publish/tiktok/sync")
async def sync_with_tiktok(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reconcile local clips with the videos actually published to TikTok.

    Pulls the account's published videos (requires the ``video.list`` scope)
    and marks matching clips as already published (recording the
    ``tiktok_video_id``) so they are never re-uploaded.
    """
    user_id = await _require_user(request, db)
    profile = await _resolve_active_profile(request, db, user_id)
    if not _platform_configured(profile, "tiktok"):
        raise HTTPException(
            status_code=400,
            detail="TikTok is not connected for this channel. Connect it from Settings first.",
        )

    async with profile_service.profile_token_context_async(db, profile["id"]):
        account_videos = await list_tiktok_videos(db)
    existing_video_ids = await ClipRepository.list_all_tiktok_video_ids(db)

    tiktok_by_title: dict[str, str] = {}
    for video in account_videos:
        if video.get("title"):
            tiktok_by_title.setdefault(_normalize_title(video["title"]), video["video_id"])

    clips = await ClipRepository.list_user_clips_for_tiktok_sync(db, user_id)

    matched = 0
    already_recorded = 0
    new_found = []
    for clip in clips:
        if clip.get("tiktok_video_id"):
            already_recorded += 1
            continue
        if clip.get("tiktok_publish_status") == "published":
            continue
        title_key = _normalize_title(clip_title(clip))
        match_video_id = tiktok_by_title.get(title_key)
        if match_video_id and match_video_id not in existing_video_ids:
            await ClipRepository.mark_user_clips_published_from_tiktok_sync(
                db, clip["id"], match_video_id, clip_title(clip)
            )
            matched += 1
            existing_video_ids.add(match_video_id)
            new_found.append({"clip_id": clip["id"], "video_id": match_video_id})

    return {
        "ok": True,
        "matched": matched,
        "already_recorded": already_recorded,
        "tiktok_videos_checked": len(account_videos),
        "matches": new_found,
    }


@router.post("/publish/tiktok/today")
async def publish_tiktok_today_clips(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Publish immediately every clip scheduled for today on TikTok.

    Instead of waiting for the assigned slot time, this uploads each clip
    scheduled for the current local day right away.
    """
    user_id = await _require_user(request, db)
    profile = await _resolve_active_profile(request, db, user_id)
    if not _platform_configured(profile, "tiktok"):
        raise HTTPException(
            status_code=400,
            detail="TikTok is not connected for this channel. Connect it from Settings first.",
        )

    tz_name = get_publish_timezone()
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()

    clips = await ClipRepository.list_user_clips_tiktok_scheduled_for_date(
        db, user_id, tz_name, today
    )
    if not clips:
        return {
            "ok": True,
            "published": 0,
            "failed": 0,
            "clips_today": 0,
            "message": "No clips are scheduled for today on TikTok.",
        }

    # Validate the daily publishing limit (scheduled + already published).
    slots_by_day = await ClipRepository.tiktok_scheduled_slot_times_per_day(db, tz_name)
    used_slots = len(slots_by_day.get(today.isoformat(), []))
    available = max(0, DAILY_PUBLISH_LIMIT - used_slots)
    to_publish = clips[:available]
    skipped = len(clips) - len(to_publish)

    if not to_publish:
        return {
            "ok": True,
            "published": 0,
            "failed": 0,
            "clips_today": len(clips),
            "skipped": skipped,
            "daily_limit": DAILY_PUBLISH_LIMIT,
            "message": f"Today's TikTok publishing limit of {DAILY_PUBLISH_LIMIT} clips is already reached.",
        }

    published = 0
    failed = 0
    failures: list[Dict[str, Any]] = []
    async with profile_service.profile_token_context_async(db, profile["id"]):
        for clip in to_publish:
            try:
                result = await upload_tiktok_video_now(db, clip)
                now_ts = datetime.now(tz)
                await ClipRepository.update_clip_tiktok_publish(
                    db,
                    clip["id"],
                    "published",
                    scheduled_at=clip["tiktok_scheduled_at"],
                    published_at=now_ts,
                )
                publish_id = result.get("publish_id")
                if publish_id:
                    await ClipRepository.set_clip_tiktok_video_id(db, clip["id"], publish_id)
                published += 1
            except Exception as exc:  # noqa: BLE001 - record per-clip failure
                logger.exception("Immediate TikTok publish failed for clip %s", clip["id"])
                failed += 1
                await ClipRepository.update_clip_tiktok_publish(
                    db, clip["id"], "failed", error=str(exc)[:1000]
                )
                failures.append({"clip_id": clip["id"], "error": str(exc)[:500]})

    await db.commit()
    return {
        "ok": True,
        "published": published,
        "failed": failed,
        "skipped": skipped,
        "clips_today": len(clips),
        "daily_limit": DAILY_PUBLISH_LIMIT,
        "failures": failures,
    }


@router.get("/publish/profiles")
async def list_profiles(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List the connected Upload-Post profiles for the configured API key."""
    await _require_user(request, db)
    profiles = await fetch_upload_post_profiles()
    return {"profiles": profiles}


@router.post("/publish/run")
async def trigger_publish_run(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Manually run the publish scheduler once."""
    await _require_user(request, db)
    result = await run_publish_schedule_once(db)
    return result


@router.post("/publish/mass-upload")
async def mass_upload_clips(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Mark every unpublished completed clip for YouTube publishing and run once.

    Skips clips that are already published, scheduled, or carry a recorded
    ``youtube_video_id`` (no duplicates are uploaded). Returns a summary.
    """
    user_id = await _require_user(request, db)
    profile = await _resolve_active_profile(request, db, user_id)
    clips = await ClipRepository.list_user_clips_for_publish(db, user_id)

    clip_ids = [clip["id"] for clip in clips]
    if clip_ids:
        await ClipRepository.set_clip_publish_request(db, clip_ids, True)
        await ClipRepository.set_clip_publish_profile(db, clip_ids, profile["id"])

    result = await run_publish_schedule_once(db)
    return {
        "provider": result.get("provider"),
        "clips_marked": len(clip_ids),
        "uploaded": result.get("scheduled", 0),
        "scheduled": result.get("scheduled", 0),
        "already_published": result.get("already_published", 0),
        "failed": result.get("failed", 0),
        "deferred": result.get("deferred", 0),
        "failures": result.get("failures", []),
        "quota_blocked": result.get("quota_blocked", False),
        "quota_reset_at": result.get("quota_reset_at"),
        "published_now": result.get("published_now", 0),
        "skipped": result.get("skipped", False),
        "configured": result.get("configured", False),
    }


@router.post("/publish/sync")
async def sync_with_youtube(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Reconcile local clips with the videos actually on the YouTube channel.

    Pulls the channel's uploads and marks matching clips as already published
    (recording the youtube_video_id), so they are never re-uploaded.
    """
    user_id = await _require_user(request, db)
    profile = await _resolve_active_profile(request, db, user_id)
    if not _platform_configured(profile, "youtube"):
        raise HTTPException(
            status_code=400,
            detail="YouTube is not connected for this channel. Connect it from Settings first.",
        )

    async with profile_service.profile_token_context_async(db, profile["id"]):
        channel_videos = await list_channel_videos()
    existing_video_ids = await ClipRepository.list_all_youtube_video_ids(db)

    from ...services.youtube_publish_service import _normalize_title, clip_title

    yt_by_title: dict[str, str] = {}
    yt_by_video_id: dict[str, Dict[str, Any]] = {}
    for video in channel_videos:
        if video.get("title"):
            yt_by_title.setdefault(
                _normalize_title(video["title"]), video["video_id"]
            )
        if video.get("video_id"):
            yt_by_video_id.setdefault(video["video_id"], video)

    clips = await ClipRepository.list_user_clips_for_sync(db, user_id)

    matched = 0
    reconciled = 0
    already_recorded = 0
    new_found = []
    for clip in clips:
        if clip.get("youtube_video_id"):
            already_recorded += 1
            if clip.get("publish_status") == "published":
                continue
            # Clip was uploaded through SupoClip but is still marked scheduled.
            # If the video is already public on YouTube (published earlier or
            # made public manually), reflect that in the local status.
            remote = yt_by_video_id.get(clip["youtube_video_id"])
            if remote and remote.get("privacy_status") == "public":
                published_at = remote.get("published_at")
                if isinstance(published_at, str):
                    published_at = datetime.fromisoformat(
                        published_at.replace("Z", "+00:00")
                    )
                await ClipRepository.update_clip_publish(
                    db,
                    clip["id"],
                    "published",
                    published_at=published_at,
                    error=None,
                )
                reconciled += 1
                new_found.append(
                    {"clip_id": clip["id"], "video_id": clip["youtube_video_id"]}
                )
            continue
        if clip.get("publish_status") == "published":
            continue
        title_key = _normalize_title(clip_title(clip))
        match_video_id = yt_by_title.get(title_key)
        if match_video_id and match_video_id not in existing_video_ids:
            await ClipRepository.mark_user_clips_published_from_sync(
                db, clip["id"], match_video_id, clip_title(clip)
            )
            matched += 1
            existing_video_ids.add(match_video_id)
            new_found.append({"clip_id": clip["id"], "video_id": match_video_id})

    await db.commit()
    return {
        "ok": True,
        "matched": matched,
        "reconciled": reconciled,
        "already_recorded": already_recorded,
        "youtube_videos_checked": len(channel_videos),
        "matches": new_found,
    }


@router.post("/publish/today")
async def publish_today_clips(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Publish immediately every clip scheduled for today.

    Instead of waiting for the scheduled publishAt time, this uploads each
    clip that is scheduled for the current local day right away (public).
    """
    user_id = await _require_user(request, db)
    profile = await _resolve_active_profile(request, db, user_id)
    if not _platform_configured(profile, "youtube"):
        raise HTTPException(
            status_code=400,
            detail="YouTube is not connected for this channel. Connect it from Settings first.",
        )

    tz_name = get_publish_timezone()
    tz = ZoneInfo(tz_name)
    today = datetime.now(tz).date()

    clips = await ClipRepository.list_user_clips_scheduled_for_date(
        db, user_id, tz_name, today
    )
    if not clips:
        return {
            "ok": True,
            "published": 0,
            "failed": 0,
            "clips_today": 0,
            "message": "No clips are scheduled for today.",
        }

    # Validate the daily publishing limit (scheduled + already published).
    slots_by_day = await ClipRepository.scheduled_slot_times_per_day(db, tz_name)
    used_slots = len(slots_by_day.get(today.isoformat(), []))
    available = max(0, DAILY_PUBLISH_LIMIT - used_slots)
    to_publish = clips[:available]
    skipped = len(clips) - len(to_publish)

    if not to_publish:
        return {
            "ok": True,
            "published": 0,
            "failed": 0,
            "clips_today": len(clips),
            "skipped": skipped,
            "daily_limit": DAILY_PUBLISH_LIMIT,
            "message": f"Today's publishing limit of {DAILY_PUBLISH_LIMIT} clips is already reached.",
        }

    published = 0
    failed = 0
    failures: list[Dict[str, Any]] = []
    async with profile_service.profile_token_context_async(db, profile["id"]):
        for clip in to_publish:
            try:
                video_id = clip.get("youtube_video_id")
                if video_id:
                    # Already uploaded as private/scheduled: make it public now
                    # without re-uploading (avoids duplicates on the channel).
                    await set_video_privacy_public(video_id)
                else:
                    result = await upload_video_now(clip)
                    video_id = result.get("video_id")
                now_ts = datetime.now(tz)
                await ClipRepository.update_clip_publish(
                    db,
                    clip["id"],
                    "published",
                    scheduled_at=clip["scheduled_publish_at"],
                    published_at=now_ts,
                )
                if video_id:
                    await ClipRepository.set_clip_youtube_video_id(db, clip["id"], video_id)
                published += 1
            except Exception as exc:  # noqa: BLE001 - record per-clip failure
                logger.exception("Immediate publish failed for clip %s", clip["id"])
                failed += 1
                await ClipRepository.update_clip_publish(
                    db, clip["id"], "failed", error=str(exc)[:1000]
                )
                failures.append({"clip_id": clip["id"], "error": str(exc)[:500]})

    await db.commit()
    return {
        "ok": True,
        "published": published,
        "failed": failed,
        "skipped": skipped,
        "clips_today": len(clips),
        "daily_limit": DAILY_PUBLISH_LIMIT,
        "failures": failures,
    }
