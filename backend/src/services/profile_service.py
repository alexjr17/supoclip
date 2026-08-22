"""
ProfileService - per-user publishing profiles with connected platform accounts.

A user can own multiple publishing profiles ("channels"). Each profile groups
one YouTube account and one TikTok account. Tasks remain per-user; profiles
only determine which channel clips are published to.

Token storage:
- Secrets are stored encrypted (AESGCM, same scheme as ``app_settings``) as a
  JSON object in ``connected_accounts.token_data`` keyed by the exact setting
  names the publishing services read (``YOUTUBE_REFRESH_TOKEN``,
  ``TIKTOK_ACCESS_TOKEN``, ...).
- Non-secret display metadata (channel title, handle, avatar...) is stored
  plain in ``connected_accounts.display_data``.

Legacy migration: on first creation of a user's default profile, the global
accounts from ``app_settings`` (``YOUTUBE_REFRESH_TOKEN`` / ``TIKTOK_*``) are
copied into it so existing setups keep working out of the box.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from ..models import ConnectedAccount, Profile, generate_uuid_string
from ..runtime_settings import decrypt_setting_value, encrypt_setting_value
from .profile_context import profile_token_context

logger = logging.getLogger(__name__)

PLATFORMS = ("youtube", "tiktok")

# Mapping of app_settings-style token keys handled per platform.
PLATFORM_TOKEN_KEYS: Dict[str, tuple[str, ...]] = {
    "youtube": ("YOUTUBE_REFRESH_TOKEN",),
    "tiktok": (
        "TIKTOK_ACCESS_TOKEN",
        "TIKTOK_REFRESH_TOKEN",
        "TIKTOK_OPEN_ID",
        "TIKTOK_ACCESS_TOKEN_EXPIRES_AT",
    ),
}


def _encrypt_or_plain(value: str) -> str:
    try:
        return encrypt_setting_value(value)
    except Exception as exc:  # noqa: BLE001 - fall back to plain storage
        logger.warning("Unable to encrypt profile token data: %s", exc)
        return value


def _decrypt_or_plain(value: str) -> str:
    try:
        return decrypt_setting_value(value)
    except Exception:  # noqa: BLE001 - stored plain (degraded fallback)
        return value


async def _get_user_name(db: AsyncSession, user_id: str) -> str:
    row = await db.execute(
        sa_text("SELECT name, first_name FROM users WHERE id = :user_id"),
        {"user_id": user_id},
    )
    result = row.fetchone()
    if result:
        return (result.first_name or result.name or "").strip() or "Canal principal"
    return "Canal principal"


async def ensure_default_profile(db: AsyncSession, user_id: str) -> Dict[str, Any]:
    """Return the user's default profile, creating it on first access.

    The first time a default profile is created the legacy global accounts are
    migrated into it (see ``migrate_global_accounts``).
    """
    row = await db.execute(
        sa_text(
            """
            SELECT id FROM profiles
            WHERE user_id = :user_id AND is_default = TRUE
            ORDER BY created_at ASC LIMIT 1
            """
        ),
        {"user_id": user_id},
    )
    result = row.fetchone()
    if result:
        return await get_profile(db, result.id, user_id)

    # Create the user's default profile.
    profile = Profile(
        user_id=user_id,
        name=await _get_user_name(db, user_id),
        is_default=True,
    )
    db.add(profile)
    await db.flush()
    await db.commit()
    await migrate_global_accounts(db, profile.id)
    logger.info("Created default profile %s for user %s", profile.id, user_id)
    return await get_profile(db, profile.id, user_id)


async def migrate_global_accounts(db: AsyncSession, profile_id: str) -> None:
    """Copy the legacy global accounts from app_settings into a profile.

    Runs once per profile that has no connected accounts yet. Global tokens
    (if any) are cloned so existing deployments keep publishing to the same
    channels through their default profile.
    """
    existing = await db.execute(
        sa_text(
            "SELECT platform FROM connected_accounts WHERE profile_id = :profile_id"
        ),
        {"profile_id": profile_id},
    )
    platforms = {row[0] for row in existing.fetchall()}

    if "youtube" not in platforms:
        refresh_token = _global_setting("YOUTUBE_REFRESH_TOKEN")
        if refresh_token:
            await save_youtube_account(
                db,
                profile_id,
                {"YOUTUBE_REFRESH_TOKEN": refresh_token},
                display_data={"source": "global"},
            )
            logger.info("Migrated global YouTube account into profile %s", profile_id)

    if "tiktok" not in platforms:
        tiktok_tokens = {
            key: _global_setting(key)
            for key in PLATFORM_TOKEN_KEYS["tiktok"]
        }
        if tiktok_tokens.get("TIKTOK_REFRESH_TOKEN") and tiktok_tokens.get("TIKTOK_OPEN_ID"):
            await save_tiktok_account(
                db,
                profile_id,
                {k: v for k, v in tiktok_tokens.items() if v},
                display_data={"source": "global"},
            )
            logger.info("Migrated global TikTok account into profile %s", profile_id)


def _global_setting(name: str) -> Optional[str]:
    import os

    from ..runtime_settings import get_cached_setting

    value = get_cached_setting(name) or os.getenv(name)
    return value.strip() if value and value.strip() else None


async def list_profiles(db: AsyncSession, user_id: str) -> List[Dict[str, Any]]:
    """List the user's profiles with their connected account summaries."""
    await ensure_default_profile(db, user_id)
    rows = await db.execute(
        sa_text(
            """
            SELECT id, name, is_default FROM profiles
            WHERE user_id = :user_id
            ORDER BY is_default DESC, created_at ASC
            """
        ),
        {"user_id": user_id},
    )
    profiles = []
    for row in rows.fetchall():
        accounts = await get_profile_accounts(db, row.id)
        profiles.append(
            {
                "id": row.id,
                "name": row.name,
                "is_default": bool(row.is_default),
                "accounts": accounts,
            }
        )
    return profiles


async def get_profile(
    db: AsyncSession, profile_id: str, user_id: str
) -> Dict[str, Any]:
    """Return a profile owned by the user or raise."""
    row = await db.execute(
        sa_text(
            """
            SELECT id, name, is_default FROM profiles
            WHERE id = :profile_id AND user_id = :user_id
            """
        ),
        {"profile_id": profile_id, "user_id": user_id},
    )
    result = row.fetchone()
    if not result:
        raise LookupError("Profile not found")
    return {
        "id": result.id,
        "name": result.name,
        "is_default": bool(result.is_default),
        "accounts": await get_profile_accounts(db, result.id),
    }


async def resolve_active_profile(
    db: AsyncSession, user_id: str, profile_id: Optional[str] = None
) -> Dict[str, Any]:
    """Resolve the active profile from a client-supplied id (falls back to default)."""
    if profile_id:
        try:
            return await get_profile(db, profile_id, user_id)
        except LookupError:
            logger.warning(
                "User %s sent unknown profile %s; falling back to default",
                user_id,
                profile_id,
            )
    return await ensure_default_profile(db, user_id)


async def create_profile(
    db: AsyncSession, user_id: str, name: str
) -> Dict[str, Any]:
    """Create a new (non-default) profile."""
    name = (name or "").strip() or "Canal"
    profile = Profile(user_id=user_id, name=name, is_default=False)
    db.add(profile)
    await db.flush()
    await db.commit()
    logger.info("Created profile %s (%s) for user %s", profile.id, name, user_id)
    return {
        "id": profile.id,
        "name": profile.name,
        "is_default": False,
        "accounts": {"youtube": {"connected": False}, "tiktok": {"connected": False}},
    }


async def rename_profile(
    db: AsyncSession, profile_id: str, user_id: str, name: str
) -> Dict[str, Any]:
    name = (name or "").strip()
    if not name:
        raise ValueError("Profile name cannot be empty")
    profile = await _owned_profile(db, profile_id, user_id)
    profile.name = name[:100]
    await db.commit()
    return {"id": profile.id, "name": profile.name, "is_default": profile.is_default}


async def delete_profile(
    db: AsyncSession, profile_id: str, user_id: str
) -> None:
    profile = await _owned_profile(db, profile_id, user_id)
    if profile.is_default:
        raise ValueError("The default profile cannot be deleted")
    await db.delete(profile)
    await db.commit()


async def _owned_profile(
    db: AsyncSession, profile_id: str, user_id: str
) -> Profile:
    from sqlalchemy import select

    result = await db.execute(
        select(Profile).where(Profile.id == profile_id, Profile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise LookupError("Profile not found")
    return profile


async def get_profile_accounts(
    db: AsyncSession, profile_id: str
) -> Dict[str, Dict[str, Any]]:
    """Return display-only summaries of the profile's connected accounts."""
    result = {
        "youtube": {"connected": False},
        "tiktok": {"connected": False},
    }
    rows = await db.execute(
        sa_text(
            """
            SELECT platform, display_data FROM connected_accounts
            WHERE profile_id = :profile_id
            """
        ),
        {"profile_id": profile_id},
    )
    for row in rows.fetchall():
        platform = row.platform
        display: Dict[str, Any] = {"connected": True}
        if row.display_data:
            try:
                display.update(json.loads(row.display_data))
            except Exception:  # noqa: BLE001 - tolerate corrupt display data
                pass
        result[platform] = display
    return result


async def _account_token_values(
    db: AsyncSession, profile_id: str, platform: str
) -> Dict[str, str]:
    row = await db.execute(
        sa_text(
            """
            SELECT token_data FROM connected_accounts
            WHERE profile_id = :profile_id AND platform = :platform
            """
        ),
        {"profile_id": profile_id, "platform": platform},
    )
    result = row.fetchone()
    if not result:
        return {}
    try:
        tokens = json.loads(_decrypt_or_plain(result.token_data))
    except Exception:  # noqa: BLE001 - tolerate corrupt token data
        return {}
    return tokens if isinstance(tokens, dict) else {}


async def profile_token_overrides(
    db: AsyncSession, profile_id: str
) -> Dict[str, str]:
    """Merge the profile's account tokens into app_settings-style overrides."""
    overrides: Dict[str, str] = {}
    for platform in PLATFORMS:
        tokens = await _account_token_values(db, profile_id, platform)
        overrides.update(tokens)
    return overrides


async def _persist_tokens(
    db: AsyncSession, profile_id: str, values: Dict[str, str]
) -> None:
    """Merge and persist refreshed tokens back into the profile's account."""
    platform = "tiktok" if any(k.startswith("TIKTOK_") for k in values) else "youtube"
    tokens = await _account_token_values(db, profile_id, platform)
    tokens.update(values)
    await db.execute(
        sa_text(
            """
            UPDATE connected_accounts
            SET token_data = :token_data, updated_at = CURRENT_TIMESTAMP
            WHERE profile_id = :profile_id AND platform = :platform
            """
        ),
        {
            "token_data": _encrypt_or_plain(json.dumps(tokens)),
            "profile_id": profile_id,
            "platform": platform,
        },
    )
    await db.commit()


def _make_persist_sink(
    db: AsyncSession, profile_id: str
):
    """Return an async sink bound to the profile for token refresh persistence."""
    async def _sink(_db: AsyncSession, values: Dict[str, str]) -> None:
        await _persist_tokens(_db or db, profile_id, values)

    return _sink


def profile_token_context_for(
    db: AsyncSession, profile_id: str
):
    """Async context manager installing the profile's token overrides + sink."""
    return profile_token_context_async(db, profile_id)


def profile_token_context_async(
    db: AsyncSession, profile_id: str
):
    """Async context manager installing the profile's token overrides + sink.

    Used by routes and the scheduler; requires an async session to lazily load
    the profile's tokens.
    """
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _cm():
        overrides = await profile_token_overrides(db, profile_id)
        sink = _make_persist_sink(db, profile_id)
        with profile_token_context(overrides or None, sink):
            yield

    return _cm()


async def save_youtube_account(
    db: AsyncSession,
    profile_id: str,
    tokens: Dict[str, str],
    display_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Store/replace the profile's YouTube account."""
    await _upsert_account(
        db, profile_id, "youtube", tokens, display_data or {}
    )


async def save_tiktok_account(
    db: AsyncSession,
    profile_id: str,
    tokens: Dict[str, str],
    display_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Store/replace the profile's TikTok account."""
    await _upsert_account(
        db, profile_id, "tiktok", tokens, display_data or {}
    )


async def _upsert_account(
    db: AsyncSession,
    profile_id: str,
    platform: str,
    tokens: Dict[str, str],
    display_data: Dict[str, Any],
) -> None:
    encrypted = _encrypt_or_plain(json.dumps(tokens))
    display_json = json.dumps(display_data) if display_data else None
    await db.execute(
        sa_text(
            """
            INSERT INTO connected_accounts
                (id, profile_id, platform, token_data, display_data, created_at, updated_at)
            VALUES (:id, :profile_id, :platform, :token_data, :display_data, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT (profile_id, platform) DO UPDATE
            SET token_data = EXCLUDED.token_data,
                display_data = COALESCE(EXCLUDED.display_data, connected_accounts.display_data),
                updated_at = CURRENT_TIMESTAMP
            """
        ),
        {
            "id": generate_uuid_string(),
            "profile_id": profile_id,
            "platform": platform,
            "token_data": encrypted,
            "display_data": display_json,
        },
    )
    await db.commit()


async def delete_account(
    db: AsyncSession, profile_id: str, platform: str
) -> None:
    if platform not in PLATFORMS:
        raise ValueError("Unsupported platform")
    await db.execute(
        sa_text(
            "DELETE FROM connected_accounts WHERE profile_id = :profile_id AND platform = :platform"
        ),
        {"profile_id": profile_id, "platform": platform},
    )
    await db.commit()


async def resolve_profile_for_clip(
    db: AsyncSession, clip: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Resolve the publishing profile for a clip (its stored one or the owner's default).

    Returns ``None`` when no profile can be resolved (clip missing a user).
    """
    user_id = clip.get("user_id")
    profile_id = clip.get("publish_profile_id")
    if user_id:
        profile = await resolve_active_profile(db, user_id, profile_id)
        overrides = await profile_token_overrides(db, profile["id"])
        return {
            "profile_id": profile["id"],
            "user_id": user_id,
            "overrides": overrides,
            "sink": _make_persist_sink(db, profile["id"]),
        }
    return None


def has_any_accounts(overrides: Dict[str, str]) -> bool:
    return any(
        overrides.get(key) for key in PLATFORM_TOKEN_KEYS["youtube"] + PLATFORM_TOKEN_KEYS["tiktok"]
    )
