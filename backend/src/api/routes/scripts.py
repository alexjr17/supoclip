"""
Script generation routes for AI-authored videos.

This is the first step of the generation flow: turn an idea into an editable
script. Nothing is rendered or persisted here — the user reviews and edits the
result before any video work starts.
"""

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from ...auth_headers import resolve_authenticated_user_id
from ...config import get_config
from ...database import get_db
from ...script_ai import (
    MAX_SCENES,
    MAX_TOTAL_SECONDS,
    MIN_TOTAL_SECONDS,
    ScriptTone,
    generate_video_script,
)
from ...services import stock_footage_service, tts_service

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


class SceneLookup(BaseModel):
    order: int = 1
    stock_keywords: List[str] = Field(default_factory=list)


class FindFootageRequest(BaseModel):
    scenes: List[SceneLookup] = Field(min_length=1, max_length=MAX_SCENES)


@router.get("/stock-status")
async def stock_status():
    """Whether stock footage lookup is available on this deployment."""
    return {"configured": stock_footage_service.is_configured(), "provider": "pexels"}


@router.post("/find-footage")
async def find_footage(
    payload: FindFootageRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Find candidate stock clips for each scene of a script.

    Returns a short list per scene rather than one pick: stock search is
    imprecise, and which near-miss actually fits is the author's call.
    """
    user_id = await resolve_authenticated_user_id(request, db, get_config())
    logger.info("Finding stock footage for %s scenes (user %s)", len(payload.scenes), user_id)

    try:
        results = await stock_footage_service.find_for_scenes(
            [scene.model_dump() for scene in payload.scenes]
        )
    except stock_footage_service.StockFootageUnavailable as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        logger.exception("Stock footage lookup failed")
        raise HTTPException(status_code=502, detail="Stock footage lookup failed") from error

    return {
        "scenes": results,
        "scenes_without_footage": stock_footage_service.missing_scene_orders(results),
    }


class NarrateScene(BaseModel):
    order: int = 1
    narration: str = ""
    duration_seconds: float = 0.0


class NarrateRequest(BaseModel):
    scenes: List[NarrateScene] = Field(min_length=1, max_length=MAX_SCENES)
    language: str = Field(default="English", max_length=40)
    gender: str = Field(default="female", pattern="^(female|male)$")
    voice: Optional[str] = Field(default=None, max_length=80)


@router.get("/voices")
async def list_voices(language: str = "English"):
    """Voices available for a language, for the narration picker."""
    try:
        return {"voices": await tts_service.list_voices_for_language(language)}
    except Exception as error:
        logger.exception("Listing voices failed")
        raise HTTPException(status_code=502, detail="Could not list voices") from error


@router.post("/narrate")
async def narrate_script(
    payload: NarrateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Synthesise the narration for each scene and re-time the script from it.

    The script's own durations are a word-count estimate and run long — measured
    against real narration they were off by more than double. The response
    carries the measured duration per scene plus word-level timings from the
    synthesiser, which is what lets captions land on the word.
    """
    user_id = await resolve_authenticated_user_id(request, db, get_config())

    output_dir = (
        Path(get_config().temp_dir) / "narration" / str(user_id)
    )

    try:
        results = await tts_service.narrate_scenes(
            [scene.model_dump() for scene in payload.scenes],
            output_dir,
            language=payload.language,
            gender=payload.gender,
            voice=payload.voice,
        )
    except Exception as error:
        logger.exception("Narration failed")
        raise HTTPException(status_code=502, detail="Narration failed") from error

    scenes = [scene.model_dump() for scene in payload.scenes]

    return {
        "scenes": [
            # The audio path stays server-side; the client only needs timing.
            {key: value for key, value in result.items() if key != "audio_path"}
            for result in results
        ],
        "total_duration": tts_service.total_narrated_duration(results),
        "retimed_scenes": tts_service.retimed_scenes(scenes, results),
    }


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
