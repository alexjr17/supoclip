"""
Script generation routes for AI-authored videos.

This is the first step of the generation flow: turn an idea into an editable
script. Nothing is rendered or persisted here — the user reviews and edits the
result before any video work starts.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth_headers import resolve_authenticated_user_id
from ...config import get_config
from ...database import get_db
from ...script_ai import (
    MAX_TOTAL_SECONDS,
    MIN_TOTAL_SECONDS,
    ScriptTone,
    generate_video_script,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/scripts", tags=["scripts"])


class GenerateScriptRequest(BaseModel):
    idea: str = Field(min_length=3, max_length=2000)
    target_duration_seconds: int = Field(default=45, ge=MIN_TOTAL_SECONDS, le=MAX_TOTAL_SECONDS)
    tone: ScriptTone = "informative"
    language: str = Field(default="English", max_length=40)
    with_characters: bool = False

    @field_validator("idea")
    @classmethod
    def _strip_idea(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Idea cannot be empty")
        return stripped


@router.post("/generate")
async def generate_script(
    payload: GenerateScriptRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Write a short-form script from an idea."""
    user_id = await resolve_authenticated_user_id(request, db, get_config())
    logger.info("Generating script for user %s", user_id)

    try:
        script = await generate_video_script(
            idea=payload.idea,
            target_duration_seconds=payload.target_duration_seconds,
            tone=payload.tone,
            language=payload.language,
            with_characters=payload.with_characters,
        )
    except RuntimeError as config_error:
        # Raised when the configured LLM has no matching API key. This is a
        # setup problem the user can fix, so surface the message verbatim.
        raise HTTPException(status_code=503, detail=str(config_error)) from config_error
    except Exception as error:
        logger.exception("Script generation failed")
        raise HTTPException(status_code=502, detail="Script generation failed") from error

    return {
        **script.model_dump(),
        "total_duration_seconds": script.total_duration_seconds,
    }
