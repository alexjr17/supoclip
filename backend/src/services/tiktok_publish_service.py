"""
TikTok direct publishing via the TikTok Content Posting API (Direct Post).

Publishes clips to TikTok immediately (no native scheduling is available).
The flow mirrors the YouTube integration: one-time OAuth connection stores the
tokens (encrypted in ``app_settings``), and ``upload_video_now`` pushes each
clip through TikTok's Direct Post flow:

1. ``POST /v2/post/publish/video/init/`` with the video size and post metadata
   (caption, privacy level). TikTok returns a ``publish_id`` and an
   ``upload_url``.
2. ``PUT`` the video file to ``upload_url`` (chunked, with ``Content-Range``).
3. Poll ``POST /v2/post/publish/status/fetch/`` until the post is published.

OAuth 2.0 setup (one-time):
1. Register an app at https://developers.tiktok.com/ with the
   "Content Posting API" product.
2. Request the ``video.publish`` and ``user.info.basic`` scopes.
3. Add ``TIKTOK_REDIRECT_URI`` (default
   http://localhost:8000/api/publish/tiktok/callback) as a redirect URI.
4. Set TIKTOK_CLIENT_KEY / TIKTOK_CLIENT_SECRET and run the "connect" flow
   from Settings to obtain and persist the tokens.

Notes:
- Access tokens last 24h; refresh tokens 365 days. This service refreshes the
  access token automatically when it expires or is missing.
- Unaudited apps can only post to private accounts (``SELF_ONLY``). Configure
  ``TIKTOK_PRIVACY_LEVEL`` (or the admin runtime setting) to control the post
  privacy; default is ``PUBLIC_TO_EVERYONE``.
- Posts are labelled as AI-generated (``is_aigc: true``).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from ..runtime_settings import (
    encrypt_setting_value,
    get_cached_setting,
    load_runtime_settings_cache,
)
from .profile_context import get_profile_token_overrides, get_profile_token_sink

logger = logging.getLogger(__name__)

TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_API_URL = "https://open.tiktokapis.com/v2"
TIKTOK_VIDEO_INIT_URL = f"{TIKTOK_API_URL}/post/publish/video/init/"
TIKTOK_STATUS_URL = f"{TIKTOK_API_URL}/post/publish/status/fetch/"
TIKTOK_VIDEO_LIST_URL = f"{TIKTOK_API_URL}/video/list/"

# Scopes: user.info.basic (account display info), video.upload (draft/inbox),
# video.publish (Direct Post), video.list (query the account's videos for sync).
# NOTE: only request scopes that are actually assigned to the app in the
# developer portal — requesting an unassigned scope makes TikTok return
# invalid_scope. Requires Direct Post enabled + video.publish/video.list
# assigned in the portal. TikTok requires a comma-separated list; the comma
# must NOT be URL-encoded.
TIKTOK_SCOPES = ",".join(
    [
        "user.info.basic",
        "video.upload",
        "video.publish",
        "video.list",
    ]
)

# Content-Range upload is required for FILE_UPLOAD. We upload in a single
# chunk (chunk_size == video_size) which TikTok accepts for any file size.
UPLOAD_TIMEOUT = httpx.Timeout(300.0, connect=15.0)
STATUS_POLL_INTERVAL_SECONDS = 10
STATUS_POLL_MAX_ATTEMPTS = 18  # ~3 minutes of polling
TITLE_MAX_LENGTH = 2200  # UTF-16 runes per TikTok caption limit

# Default privacy level; can be overridden via TIKTOK_PRIVACY_LEVEL.
DEFAULT_PRIVACY_LEVEL = "PUBLIC_TO_EVERYONE"

# User info fields returned by /v2/user/info/. Only fields granted by the
# user.info.basic scope are requested (union_id and profile_deep_link require
# additional scopes and cause scope_not_authorized).
USER_INFO_FIELDS = ",".join(
    [
        "open_id",
        "avatar_url",
        "display_name",
    ]
)


def _setting_or_env(name: str) -> Optional[str]:
    value = get_profile_token_overrides().get(name) or get_cached_setting(
        name
    ) or os.getenv(name)
    return value.strip() if value and value.strip() else None


def get_tiktok_client_key() -> Optional[str]:
    return _setting_or_env("TIKTOK_CLIENT_KEY")


def get_tiktok_client_secret() -> Optional[str]:
    return _setting_or_env("TIKTOK_CLIENT_SECRET")


def get_tiktok_refresh_token() -> Optional[str]:
    return _setting_or_env("TIKTOK_REFRESH_TOKEN")


def get_tiktok_access_token() -> Optional[str]:
    return _setting_or_env("TIKTOK_ACCESS_TOKEN")


def get_tiktok_access_token_expires_at() -> Optional[datetime]:
    value = _setting_or_env("TIKTOK_ACCESS_TOKEN_EXPIRES_AT")
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def get_tiktok_open_id() -> Optional[str]:
    return _setting_or_env("TIKTOK_OPEN_ID")


def get_tiktok_privacy_level() -> str:
    value = _setting_or_env("TIKTOK_PRIVACY_LEVEL")
    return (value or DEFAULT_PRIVACY_LEVEL).strip().upper()


def get_tiktok_redirect_uri() -> str:
    default = os.getenv("BACKEND_PUBLIC_URL") or "http://localhost:8000"
    return os.getenv("TIKTOK_REDIRECT_URI") or f"{default.rstrip('/')}/api/publish/tiktok/callback"


def is_tiktok_configured() -> bool:
    return bool(
        get_tiktok_client_key()
        and get_tiktok_client_secret()
        and get_tiktok_refresh_token()
        and get_tiktok_open_id()
    )


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _generate_pkce_pair() -> Tuple[str, str]:
    """Return a (code_verifier, code_challenge) pair for TikTok's PKCE flow.

    TikTok requires PKCE (``code_challenge`` / ``code_challenge_method=S256``)
    for web apps. The verifier is URL-safe and 43 characters long.
    """
    code_verifier = _b64url_encode(os.urandom(32))
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = _b64url_encode(digest)
    return code_verifier, code_challenge


async def store_tiktok_pkce(db: AsyncSession, state: str, code_verifier: str) -> None:
    """Persist the PKCE verifier keyed by the OAuth state token."""
    from sqlalchemy import text

    await db.execute(
        text(
            """
            INSERT INTO app_settings (setting_key, encrypted_value, updated_at)
            VALUES (:setting_key, :code_verifier, CURRENT_TIMESTAMP)
            ON CONFLICT (setting_key) DO UPDATE
            SET encrypted_value = EXCLUDED.encrypted_value,
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {"setting_key": f"tiktok_pkce:{state}", "code_verifier": code_verifier},
    )
    await db.commit()


async def pop_tiktok_pkce(db: AsyncSession, state: str) -> Optional[str]:
    """Fetch and delete the PKCE verifier for an OAuth state token."""
    from sqlalchemy import text

    result = await db.execute(
        text(
            """
            SELECT encrypted_value FROM app_settings
            WHERE setting_key = :setting_key
            """
        ),
        {"setting_key": f"tiktok_pkce:{state}"},
    )
    row = result.fetchone()
    if not row:
        return None
    await db.execute(
        text("DELETE FROM app_settings WHERE setting_key = :setting_key"),
        {"setting_key": f"tiktok_pkce:{state}"},
    )
    await db.commit()
    return row[0]


def build_tiktok_auth_url(profile_id: Optional[str] = None) -> Tuple[str, str, str]:
    """Return the TikTok OAuth URL, a state token, and the PKCE verifier.

    The verifier must be stored (keyed by the state) and supplied when
    exchanging the authorization code for tokens. When ``profile_id`` is
    provided it is encoded in the state so the callback can store the tokens
    on the right profile.
    """
    client_key = get_tiktok_client_key()
    if not client_key:
        raise RuntimeError("TIKTOK_CLIENT_KEY is not configured")
    state = secrets.token_urlsafe(24)
    if profile_id:
        state = f"{state}|{profile_id}"
    code_verifier, code_challenge = _generate_pkce_pair()
    params = {
        "client_key": client_key,
        "scope": TIKTOK_SCOPES,
        "response_type": "code",
        "redirect_uri": get_tiktok_redirect_uri(),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{TIKTOK_AUTH_URL}?{urlencode(params, safe=',')}", state, code_verifier


async def _exchange_code_for_tokens(code: str, state: str, code_verifier: str) -> Dict[str, Any]:
    client_key = get_tiktok_client_key()
    client_secret = get_tiktok_client_secret()
    if not client_key or not client_secret:
        raise RuntimeError("TikTok OAuth credentials are not configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        response = await client.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": get_tiktok_redirect_uri(),
                "code_verifier": code_verifier,
            },
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"TikTok token exchange failed ({response.status_code}): {response.text[:500]}"
        )
    return response.json()


async def _save_settings(db: AsyncSession, values: Dict[str, str]) -> None:
    """Encrypt and upsert a batch of runtime settings (TikTok tokens).

    When a profile token context is active the values are persisted to that
    profile's connected account instead of the global app_settings table.
    """
    sink = get_profile_token_sink()
    if sink is not None:
        await sink(db, values)
        return

    from sqlalchemy import text

    for key, value in values.items():
        encrypted = encrypt_setting_value(value)
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
            {"setting_key": key, "encrypted_value": encrypted},
        )
    await db.commit()
    await load_runtime_settings_cache(db)


async def complete_tiktok_oauth(
    db: AsyncSession, code: str, state: str, profile_id: Optional[str] = None
) -> Dict[str, Any]:
    """Exchange the OAuth code, persist the tokens, return user info.

    When ``profile_id`` is provided the tokens are stored on that profile's
    connected account; otherwise they are stored globally (legacy behavior).
    """
    code_verifier = await pop_tiktok_pkce(db, state)
    if not code_verifier:
        raise RuntimeError(
            "TikTok OAuth state expired or did not match; start the connect flow again"
        )
    payload = await _exchange_code_for_tokens(code, state, code_verifier)
    access_token = payload.get("access_token")
    refresh_token = payload.get("refresh_token")
    if not access_token or not refresh_token:
        raise RuntimeError("TikTok did not return access/refresh tokens")

    open_id = payload.get("open_id")
    if not open_id:
        raise RuntimeError("TikTok did not return an open_id for the user")

    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(payload.get("expires_in", 86400))
    )

    values = {
        "TIKTOK_ACCESS_TOKEN": access_token,
        "TIKTOK_REFRESH_TOKEN": refresh_token,
        "TIKTOK_OPEN_ID": open_id,
        "TIKTOK_ACCESS_TOKEN_EXPIRES_AT": expires_at.isoformat(),
    }

    try:
        user = await _fetch_user_info(access_token)
    except Exception as exc:  # noqa: BLE001 - token saved even if user fetch fails
        logger.warning("Unable to fetch TikTok user info after connect: %s", exc)
        user = None

    if profile_id:
        from .profile_service import save_tiktok_account

        await save_tiktok_account(
            db,
            profile_id,
            values,
            display_data={
                "open_id": open_id,
                "display_name": (user or {}).get("display_name"),
                "avatar_url": (user or {}).get("avatar_url"),
            },
        )
        return {"connected": True, "user": user}

    await _save_settings(db, values)
    return {"connected": True, "user": user}


async def _refresh_access_token(db: AsyncSession) -> str:
    """Refresh the access token using the stored refresh token and persist it."""
    client_key = get_tiktok_client_key()
    client_secret = get_tiktok_client_secret()
    refresh_token = get_tiktok_refresh_token()
    if not client_key or not client_secret or not refresh_token:
        raise RuntimeError("TikTok publishing is not configured")
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        response = await client.post(
            TIKTOK_TOKEN_URL,
            data={
                "client_key": client_key,
                "client_secret": client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
            },
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"TikTok token refresh failed ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    access_token = payload.get("access_token")
    if not access_token:
        raise RuntimeError("TikTok did not return an access token")
    new_refresh_token = payload.get("refresh_token")
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=int(payload.get("expires_in", 86400))
    )
    values = {
        "TIKTOK_ACCESS_TOKEN": access_token,
        "TIKTOK_ACCESS_TOKEN_EXPIRES_AT": expires_at.isoformat(),
    }
    if new_refresh_token:
        values["TIKTOK_REFRESH_TOKEN"] = new_refresh_token
    await _save_settings(db, values)
    return access_token


async def get_tiktok_access_token_refreshed(db: AsyncSession) -> str:
    """Return a valid access token, refreshing it first when needed."""
    access_token = get_tiktok_access_token()
    expires_at = get_tiktok_access_token_expires_at()
    if access_token and (expires_at is None or expires_at > datetime.now(timezone.utc)):
        return access_token
    return await _refresh_access_token(db)


async def _fetch_user_info(access_token: str) -> Dict[str, Any]:
    """Return the TikTok user's profile information."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=15.0)) as client:
        response = await client.get(
            f"{TIKTOK_API_URL}/user/info/",
            params={"fields": USER_INFO_FIELDS},
            headers={"Authorization": f"Bearer {access_token}"},
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"TikTok user info request failed ({response.status_code}): {response.text[:500]}"
        )
    payload = response.json()
    error = payload.get("error", {}) or {}
    if error.get("code") and error["code"] != "ok":
        raise RuntimeError(
            f"TikTok user info error: {error.get('code')} {error.get('message', '')}"
        )
    user = (payload.get("data", {}) or {}).get("user", {}) or {}
    return {
        "open_id": user.get("open_id"),
        "display_name": user.get("display_name"),
        "avatar_url": user.get("avatar_url"),
        "profile_deep_link": user.get("profile_deep_link"),
    }


async def fetch_tiktok_user(db: AsyncSession) -> Optional[Dict[str, Any]]:
    if not is_tiktok_configured():
        return None
    access_token = await get_tiktok_access_token_refreshed(db)
    return await _fetch_user_info(access_token)


def _clip_caption(clip: Dict[str, Any]) -> str:
    hook = (clip.get("hook_title") or "").strip()
    text = (clip.get("text") or "").strip()
    parts = [part for part in (hook, text) if part]
    caption = "\n\n".join(parts).strip()
    if not caption:
        return f"Clip #{clip.get('clip_order') or ''}".rstrip()
    # TikTok captions are limited to 2200 UTF-16 runes.
    return caption[:TITLE_MAX_LENGTH]


def _tiktok_error(response_body: str) -> str:
    return response_body[:800]


async def _init_video_upload(
    access_token: str, clip: Dict[str, Any], video_size: int
) -> Tuple[str, str]:
    """Initialize a Direct Post upload, returning (publish_id, upload_url)."""
    post_info: Dict[str, Any] = {
        "title": _clip_caption(clip),
        "privacy_level": get_tiktok_privacy_level(),
        "disable_comment": False,
        "disable_duet": False,
        "disable_stitch": False,
        "brand_content_toggle": False,
        "brand_organic_toggle": False,
        "is_aigc": True,
    }
    source_info: Dict[str, Any] = {
        "source": "FILE_UPLOAD",
        "video_size": video_size,
        "chunk_size": video_size,
        "total_chunk_count": 1,
    }
    body = {"post_info": post_info, "source_info": source_info}

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.post(TIKTOK_VIDEO_INIT_URL, headers=headers, json=body)
    if response.status_code != 200:
        raise RuntimeError(
            f"TikTok upload init failed ({response.status_code}): {_tiktok_error(response.text)}"
        )
    payload = response.json()
    error = payload.get("error", {}) or {}
    if error.get("code") and error["code"] != "ok":
        raise RuntimeError(
            f"TikTok upload init error: {error.get('code')} {error.get('message', '')}"
        )
    data = payload.get("data", {}) or {}
    publish_id = data.get("publish_id")
    upload_url = data.get("upload_url")
    if not publish_id or not upload_url:
        raise RuntimeError("TikTok upload init response missing publish_id/upload_url")
    return publish_id, upload_url


async def _put_video_file(file_path: Path, upload_url: str) -> None:
    """Upload the video file to the TikTok upload URL (single chunk)."""
    content = await asyncio.to_thread(file_path.read_bytes)
    total = len(content)
    headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(total),
        "Content-Range": f"bytes 0-{total - 1}/{total}",
    }
    async with httpx.AsyncClient(timeout=UPLOAD_TIMEOUT) as client:
        response = await client.put(upload_url, headers=headers, content=content)
    if response.status_code not in (200, 201, 204):
        raise RuntimeError(
            f"TikTok video upload failed ({response.status_code}): {_tiktok_error(response.text)}"
        )


async def _fetch_publish_status(access_token: str, publish_id: str) -> Dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
        response = await client.post(
            TIKTOK_STATUS_URL, headers=headers, json={"publish_id": publish_id}
        )
    if response.status_code != 200:
        raise RuntimeError(
            f"TikTok status fetch failed ({response.status_code}): {_tiktok_error(response.text)}"
        )
    payload = response.json()
    error = payload.get("error", {}) or {}
    if error.get("code") and error["code"] != "ok":
        raise RuntimeError(
            f"TikTok status fetch error: {error.get('code')} {error.get('message', '')}"
        )
    return (payload.get("data", {}) or {}).get("status_info", {}) or {}


async def upload_video_now(db: AsyncSession, clip: Dict[str, Any]) -> Dict[str, Any]:
    """Publish one clip to TikTok immediately.

    Returns ``{publish_id, status, title}`` where ``status`` is TikTok's final
    status (``PUBLISH_COMPLETE`` or ``PROCESSING_*`` if still being processed).
    """
    file_path = clip.get("file_path")
    if not file_path or not Path(file_path).exists():
        raise FileNotFoundError(f"Clip file not found: {file_path}")

    access_token = await get_tiktok_access_token_refreshed(db)
    video_size = Path(file_path).stat().st_size

    publish_id, upload_url = await _init_video_upload(access_token, clip, video_size)
    await _put_video_file(Path(file_path), upload_url)

    status = ""
    fail_reason = None
    for _ in range(STATUS_POLL_MAX_ATTEMPTS):
        await asyncio.sleep(STATUS_POLL_INTERVAL_SECONDS)
        status_info = await _fetch_publish_status(access_token, publish_id)
        status = (status_info.get("status") or "").upper()
        fail_reason = status_info.get("fail_reason") or status_info.get("reason")
        if status in ("PUBLISH_COMPLETE", "FAILED"):
            break

    if status == "FAILED":
        reason = fail_reason if isinstance(fail_reason, str) else str(fail_reason or "")
        raise RuntimeError(f"TikTok publish failed: {reason[:500]}")

    logger.info(
        "TikTok post %s uploaded (status=%s)", publish_id, status or "processing"
    )
    return {
        "publish_id": publish_id,
        "status": status or "PROCESSING",
        "title": _clip_caption(clip),
    }


def _normalize_title(title: str) -> str:
    """Normalize a caption/title for duplicate matching across sync runs."""
    normalized = re.sub(r"[\s\-—_·•|/\\#\[\]()]+", " ", title or "")
    normalized = normalized.strip().lower()
    return re.sub(r"\s+", " ", normalized)


def clip_title(clip: Dict[str, Any]) -> str:
    """Short title used to identify a clip for duplicate matching."""
    return _clip_caption(clip)[:100]


async def list_tiktok_videos(db: AsyncSession, max_count: int = 50) -> List[Dict[str, Any]]:
    """List the connected account's published videos (id + title).

    Used by the sync action to detect clips already posted to TikTok
    (including through the manual upload flow or other tools). Requires the
    ``video.list`` scope on the TikTok app.
    """
    if not is_tiktok_configured():
        return []
    access_token = await get_tiktok_access_token_refreshed(db)
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
    }
    videos: List[Dict[str, Any]] = []
    cursor = 0
    while len(videos) < max_count:
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=15.0)) as client:
            response = await client.post(
                f"{TIKTOK_VIDEO_LIST_URL}?fields=id,title,create_time",
                headers=headers,
                json={"max_count": 20, "cursor": cursor},
            )
        if response.status_code != 200:
            raise RuntimeError(
                f"TikTok video list failed ({response.status_code}): {_tiktok_error(response.text)}"
            )
        payload = response.json()
        error = payload.get("error", {}) or {}
        if error.get("code") and error["code"] != "ok":
            raise RuntimeError(
                f"TikTok video list error: {error.get('code')} {error.get('message', '')}"
            )
        data = payload.get("data", {}) or {}
        for video in data.get("videos", []):
            videos.append(
                {
                    "video_id": video.get("id"),
                    "title": video.get("title") or "",
                }
            )
        if not data.get("has_more"):
            break
        cursor = data.get("cursor", 0) or cursor + 20
    return videos
