"""
Profile API routes - per-user publishing profiles with connected accounts.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ...database import get_db
from ...auth_headers import resolve_authenticated_user_id
from ...config import get_config
from ...services import profile_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/profiles", tags=["profiles"])

PROFILE_ID_HEADER = "x-supoclip-profile-id"


class CreateProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class RenameProfileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100)


async def _require_user(request: Request, db: AsyncSession) -> str:
    user_id = await resolve_authenticated_user_id(request, db, get_config())
    if not user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user_id


def _active_profile_id(request: Request) -> str | None:
    value = request.headers.get(PROFILE_ID_HEADER)
    return value.strip() if value and value.strip() else None


@router.get("")
async def list_profiles(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """List the user's publishing profiles with their connected accounts."""
    user_id = await _require_user(request, db)
    profiles = await profile_service.list_profiles(db, user_id)
    active = await profile_service.resolve_active_profile(
        db, user_id, _active_profile_id(request)
    )
    return {"profiles": profiles, "active_profile_id": active["id"]}


@router.post("")
async def create_profile(
    req: CreateProfileRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Create a new publishing profile."""
    user_id = await _require_user(request, db)
    profile = await profile_service.create_profile(db, user_id, req.name)
    return {"profile": profile}


@router.patch("/{profile_id}")
async def rename_profile(
    profile_id: str,
    req: RenameProfileRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Rename an existing profile."""
    user_id = await _require_user(request, db)
    try:
        profile = await profile_service.rename_profile(db, profile_id, user_id, req.name)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile}


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Delete a non-default profile (its connected accounts are removed too)."""
    user_id = await _require_user(request, db)
    try:
        await profile_service.delete_profile(db, profile_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True}


@router.get("/{profile_id}/accounts")
async def get_profile_accounts(
    profile_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Return the connected accounts of a profile (display info only)."""
    user_id = await _require_user(request, db)
    try:
        await profile_service.get_profile(db, profile_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    accounts = await profile_service.get_profile_accounts(db, profile_id)
    return {"accounts": accounts}


@router.delete("/{profile_id}/accounts/{platform}")
async def delete_profile_account(
    profile_id: str,
    platform: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Disconnect a platform account from a profile."""
    user_id = await _require_user(request, db)
    try:
        await profile_service.get_profile(db, profile_id, user_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if platform not in profile_service.PLATFORMS:
        raise HTTPException(status_code=400, detail="Unsupported platform")
    await profile_service.delete_account(db, profile_id, platform)
    return {"ok": True}
