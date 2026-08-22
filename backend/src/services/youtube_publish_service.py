"""
YouTube direct publishing via the YouTube Data API v3.

Schedules clips to YouTube without Upload-Post: uploads the video as private
with a ``publishAt`` timestamp, and YouTube makes it public automatically at
that time. This is free (no monthly upload quota) and is the default publishing
provider for SupoClip.

OAuth 2.0 setup (one-time):
1. Create a project at https://console.cloud.google.com/
2. Enable the YouTube Data API v3.
3. Create OAuth 2.0 credentials (Web application) and add the redirect URI
   ``YOUTUBE_REDIRECT_URI`` (default http://localhost:8000/api/publish/youtube/callback).
4. Configure the OAuth consent screen with the ``youtube.upload`` and
   ``youtube.force-ssl`` scopes (use "Testing" mode for personal use).
5. Set YOUTUBE_CLIENT_ID / YOUTUBE_CLIENT_SECRET and run the "connect" flow
   to obtain and persist the refresh token.

Note: YouTube Data API quota allows roughly 6 uploads/day on the default
10,000 units/day budget (videos.insert costs ~1600 units). Unlike Upload-Post
there is no hard monthly cap.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..runtime_settings import (
    encrypt_setting_value,
    get_cached_setting,
    load_runtime_settings_cache,
)
from .profile_context import get_profile_token_overrides

logger = logging.getLogger(__name__)

YOUTUBE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
YOUTUBE_TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_UPLOAD_URL = "https://www.googleapis.com/upload/youtube/v3/videos"
YOUTUBE_API_URL = "https://www.googleapis.com/youtube/v3"

# Scope for uploading + managing the channel owner's videos (needed for
# private/scheduled uploads).
YOUTUBE_SCOPES = " ".join(
    [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube.force-ssl",
    ]
)

VIDEO_CATEGORY_ID = "22"  # People & Blogs
UPLOAD_TIMEOUT = httpx.Timeout(300.0, connect=15.0)


def _setting_or_env(name: str) -> Optional[str]:
    value = get_profile_token_overrides().get(name) or get_cached_setting(
        name
    ) or os.getenv(name)
    return value.strip() if value and value.strip() else None


def get_youtube_client_id() -> Optional[str]:
    return _setting_or_env("YOUTUBE_CLIENT_ID")


def get_youtube_client_secret() -> Optional[str]:
    return _setting_or_env("YOUTUBE_CLIENT_SECRET")


def get_youtube_refresh_token() -> Optional[str]:
    return _setting_or_env("YOUTUBE_REFRESH_TOKEN")


def get_youtube_redirect_uri() -> str:
    default = os.getenv("BACKEND_PUBLIC_URL") or "http://localhost:8000"
    return os.getenv("YOUTUBE_REDIRECT_URI") or f"{default.rstrip('/')}/api/publish/youtube/callback"


def is_youtube_configured() -> bool:
    return bool(
        get_youtube_client_id()
        and get_youtube_client_secret()
        and get_youtube_refresh_token()
    )


def build_youtube_auth_url(profile_id: Optional[str] = None) -> Tuple[str, str]:
    """Return the Google OAuth URL and a fresh state token (CSRF guard).

    When ``profile_id`` is provided it is encoded in the state so the callback
    can store the tokens on the right profile.
    """
    client_id = get_youtube_client_id()
    if not client_id:
        raise RuntimeError("YOUTUBE_CLIENT_ID is not configured")
    state = secrets.token_urlsafe(24)
    if profile_id:
        state = f"{state}|{profile_id}"
    params = {
        "client_id": client_id,
        "redirect_uri": get_youtube_redirect_uri(),
        "response_type": "code",
        "scope": YOUTUBE_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    }
    return f"{YOUTUBE_AUTH_URL}?{urlencode(params)}", state


async def _exchange_code_for_tokens(code: str, state: str) -> Dict[str, Any]:
    client_id = get_youtube_client_id()
    client_secret = get_youtube_client_secret()
    if not client_id or not client_secret:
        raise RuntimeError("YouTube OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        response = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "code": code,
                "state": state,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": get_youtube_redirect_uri(),
                "grant_type": "authorization_code",
            },
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"Google token exchange failed ({response.status_code}): {response.text[:500]}"
        )
    return response.json()


async def complete_youtube_oauth(
    db: AsyncSession, code: str, state: str, profile_id: Optional[str] = None
) -> Dict[str, Any]:
    """Exchange the OAuth code, persist the refresh token, return channel info.

    When ``profile_id`` is provided the tokens are stored on that profile's
    connected account; otherwise they are stored globally (legacy behavior).
    """
    payload = await _exchange_code_for_tokens(code, state)
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("Google did not return a refresh token (offline access missing)")

    channel = None
    access_token = payload.get("access_token")
    if access_token:
        try:
            channel = await _fetch_channel_info(access_token)
        except Exception as exc:  # noqa: BLE001 - channel info is best-effort
            logger.warning("Unable to fetch channel after OAuth: %s", exc)

    if profile_id:
        from .profile_service import save_youtube_account

        await save_youtube_account(
            db,
            profile_id,
            {"YOUTUBE_REFRESH_TOKEN": refresh_token},
            display_data={
                "channel_id": (channel or {}).get("id"),
                "title": (channel or {}).get("title"),
                "handle": (channel or {}).get("handle"),
            },
        )
        return {"channel": channel}

    from sqlalchemy import text

    encrypted = encrypt_setting_value(refresh_token)
    await db.execute(
        text(
            """
            INSERT INTO app_settings (setting_key, encrypted_value)
            VALUES (:setting_key, :encrypted_value)
            ON CONFLICT (setting_key) DO UPDATE
            SET encrypted_value = EXCLUDED.encrypted_value,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"setting_key": "YOUTUBE_REFRESH_TOKEN", "encrypted_value": encrypted},
    )
    await db.commit()
    await load_runtime_settings_cache(db)

    return {"channel": channel}


async def _refresh_access_token() -> str:
    client_id = get_youtube_client_id()
    client_secret = get_youtube_client_secret()
    refresh_token = get_youtube_refresh_token()
    if not client_id or not client_secret or not refresh_token:
        raise RuntimeError("YouTube publishing is not configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        response = await client.post(
            YOUTUBE_TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
                "client_secret": client_secret,
            },
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"Google token refresh failed ({response.status_code}): {response.text[:500]}"
        )
    access_token = response.json().get("access_token")
    if not access_token:
        raise RuntimeError("Google did not return an access token")
    return access_token


async def _fetch_channel_info(access_token: str) -> Dict[str, Any]:
    """Return the authenticated user's primary YouTube channel."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        response = await client.get(
            f"{YOUTUBE_API_URL}/channels",
            params={"part": "snippet", "mine": "true"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"YouTube channels.list failed ({response.status_code}): {response.text[:500]}"
        )
    items = response.json().get("items", [])
    if not items:
        raise RuntimeError("No YouTube channel is associated with this account")
    snippet = items[0].get("snippet", {})
    return {
        "id": items[0].get("id"),
        "title": snippet.get("title"),
        "handle": snippet.get("customUrl"),
    }


async def fetch_youtube_channel() -> Optional[Dict[str, Any]]:
    if not is_youtube_configured():
        return None
    access_token = await _refresh_access_token()
    return await _fetch_channel_info(access_token)


def _normalize_title(title: str) -> str:
    """Normalize a video title for duplicate matching across sync runs."""
    normalized = re.sub(r"[\s\-—_·•|/\\#\[\]()]+", " ", title or "")
    normalized = normalized.strip().lower()
    return re.sub(r"\s+", " ", normalized)


async def list_channel_videos(max_results: int = 50) -> list[Dict[str, Any]]:
    """List the authenticated user's uploaded videos (id + title + publish time).

    Used by the sync action to detect clips that were already uploaded
    (including through Upload-Post before YouTube direct publishing was
    configured).
    """
    if not is_youtube_configured():
        return []
    access_token = await _refresh_access_token()
    headers = {"Authorization": f"Bearer {access_token}"}

    # 1. Find the uploads playlist of the authenticated channel.
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        channel_resp = await client.get(
            f"{YOUTUBE_API_URL}/channels",
            params={"part": "contentDetails", "mine": "true"},
            headers=headers,
        )
    if channel_resp.status_code != 200:
        raise RuntimeError(
            f"YouTube channels.list failed ({channel_resp.status_code}): {channel_resp.text[:500]}"
        )
    channel_items = channel_resp.json().get("items", [])
    if not channel_items:
        return []
    uploads_playlist = (
        channel_items[0].get("contentDetails", {})
        .get("relatedPlaylists", {})
        .get("uploads")
    )
    if not uploads_playlist:
        return []

    # 2. Page through the uploads playlist collecting video ids.
    video_ids: list[str] = []
    page_token = None
    while len(video_ids) < max_results:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist,
            "maxResults": 50,
        }
        if page_token:
            params["pageToken"] = page_token
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
            resp = await client.get(
                f"{YOUTUBE_API_URL}/playlistItems",
                params=params,
                headers=headers,
            )
        if resp.status_code != 200:
            raise RuntimeError(
                f"YouTube playlistItems.list failed ({resp.status_code}): {resp.text[:500]}"
            )
        payload = resp.json()
        for item in payload.get("items", []):
            video_ids.append(
                item.get("contentDetails", {}).get("videoId")
            )
        page_token = payload.get("nextPageToken")
        if not page_token or len(video_ids) >= max_results:
            break

    if not video_ids:
        return []

    # 3. Fetch snippet (title) for all collected video ids.
    videos: list[Dict[str, Any]] = []
    for offset in range(0, len(video_ids), 50):
        batch = video_ids[offset : offset + 50]
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
            videos_resp = await client.get(
                f"{YOUTUBE_API_URL}/videos",
                params={
                    "part": "snippet,status",
                    "id": ",".join(batch),
                    "maxResults": 50,
                },
                headers=headers,
            )
        if videos_resp.status_code != 200:
            raise RuntimeError(
                f"YouTube videos.list failed ({videos_resp.status_code}): {videos_resp.text[:500]}"
            )
        for item in videos_resp.json().get("items", []):
            snippet = item.get("snippet", {})
            status = item.get("status", {})
            videos.append(
                {
                    "video_id": item.get("id"),
                    "title": snippet.get("title", ""),
                    "privacy_status": status.get("privacyStatus", "public"),
                    "published_at": status.get("publishAt")
                    or snippet.get("publishedAt"),
                }
            )

    return videos


def clip_title(clip: Dict[str, Any]) -> str:
    title = (clip.get("hook_title") or "").strip()
    if title:
        return title[:100]
    text = (clip.get("text") or "").strip()
    if text:
        return text.splitlines()[0].strip()[:100]
    return "SupoClip Short"


def _clip_description(clip: Dict[str, Any]) -> str:
    text = (clip.get("text") or "").strip()
    hook = (clip.get("hook_title") or "").strip()
    parts = [part for part in (hook, text) if part]
    description = "\n\n".join(parts)[:1500]
    return description or f"Clip #{clip.get('clip_order') or ''}".rstrip()


async def upload_video_scheduled(
    clip: Dict[str, Any],
    scheduled_at: datetime,
) -> Dict[str, Any]:
    """Schedule one clip to YouTube (private upload + publishAt)."""
    if scheduled_at <= datetime.now(scheduled_at.tzinfo):
        raise ValueError("publishAt must be in the future")
    return await upload_video(clip, scheduled_at)


async def upload_video_now(clip: Dict[str, Any]) -> Dict[str, Any]:
    """Publish one clip to YouTube immediately (public upload)."""
    return await upload_video(clip, None)


async def upload_video(
    clip: Dict[str, Any],
    scheduled_at: Optional[datetime],
) -> Dict[str, Any]:
    """Upload one clip to YouTube, optionally scheduling its publish time.

    If ``scheduled_at`` is None the video is uploaded as public right away;
    otherwise it is uploaded as private with a ``publishAt`` timestamp.
    """
    file_path = clip.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise FileNotFoundError(f"Clip file not found: {file_path}")

    filename = clip.get("filename") or Path(file_path).name
    if not filename.lower().endswith(".mp4"):
        filename = f"{Path(filename).stem or 'clip'}.mp4"

    title = clip_title(clip)
    description = _clip_description(clip)
    file_size = Path(file_path).stat().st_size
    publish_at = scheduled_at.astimezone().isoformat() if scheduled_at else None

    status: Dict[str, Any] = {
        "selfDeclaredMadeForKids": False,
    }
    if publish_at:
        status["privacyStatus"] = "private"
        status["publishAt"] = publish_at
    else:
        status["privacyStatus"] = "public"

    metadata = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": VIDEO_CATEGORY_ID,
            "defaultLanguage": "es",
        },
        "status": status,
    }

    access_token = await _refresh_access_token()

    # Step 1: initiate a resumable upload session.
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(file_size),
    }
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.post(
            f"{YOUTUBE_UPLOAD_URL}?uploadType=resumable&part=snippet,status",
            headers=headers,
            json=metadata,
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"YouTube upload session failed ({response.status_code}): {response.text[:800]}"
        )
    session_uri = response.headers.get("Location")
    if not session_uri:
        raise RuntimeError("YouTube upload session URI missing from response")

    # Step 2: upload the bytes to the session URI.
    content = await asyncio.to_thread(Path(file_path).read_bytes)
    upload_headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "video/mp4",
    }
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        upload_response = await client.put(
            session_uri, headers=upload_headers, content=content
        )
    if upload_response.status_code not in (200, 201):
        raise RuntimeError(
            f"YouTube video upload failed ({upload_response.status_code}): {upload_response.text[:800]}"
        )
    video_id = upload_response.json().get("id")

    logger.info(
        "YouTube video %s uploaded (publish_at=%s)", video_id, publish_at or "now"
    )
    return {
        "video_id": video_id,
        "title": title,
        "publish_at": publish_at,
    }


async def set_video_privacy_public(video_id: str) -> None:
    """Make an already-uploaded video public immediately.

    Videos scheduled via ``upload_video`` sit on YouTube as private with a
    ``publishAt`` timestamp. This updates the existing video (no re-upload, so
    no duplicates) to go live right now, clearing the scheduled publish time.
    """
    access_token = await _refresh_access_token()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    body = {
        "id": video_id,
        "status": {
            # Omitting publishAt deletes the existing scheduled value; it can
            # only be set alongside privacyStatus=private, so we never send it.
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.put(
            f"{YOUTUBE_API_URL}/videos?part=status",
            headers=headers,
            json=body,
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"YouTube video privacy update failed ({response.status_code}): {response.text[:800]}"
        )
    logger.info("YouTube video %s made public", video_id)
