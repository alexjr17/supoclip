"""
Script generation routes for AI-authored videos.

This is the first step of the generation flow: turn an idea into an editable
script. Nothing is rendered or persisted here — the user reviews and edits the
result before any video work starts.
"""

import logging
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
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
from ...services.generated_video_service import DEFAULT_TITLE, GeneratedVideoService

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

    return {
        "scenes": [
            {
                **{k: v for k, v in result.items() if k != "audio_path"},
                # The path itself stays server-side; the client gets only the
                # name, which it turns into a /scripts/narration/<name> URL.
                "audio_filename": (
                    Path(result["audio_path"]).name if result.get("audio_path") else None
                ),
            }
            for result in results
        ],
        # No re-timed script is returned. This endpoint is sent only
        # order/narration/duration, so echoing "scenes" back would hand the
        # caller stripped-down copies missing stock_keywords, character_names
        # and the visual description — which is exactly the trap the client
        # fell into. The measured duration per scene above is all that is
        # needed to re-time a script the caller already holds.
        "total_duration": tts_service.total_narrated_duration(results),
    }


@router.post("/save-video")
async def save_generated_video(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(DEFAULT_TITLE),
    duration: float = Form(0.0),
    text_content: str = Form(""),
    hook_title: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    """
    Store a rendered generated video so it can be published like any clip.

    It lands as a completed task with kind='generated' holding one clip, so the
    listing, the task page, scheduling and the YouTube/TikTok publishers all
    work on it unchanged.
    """
    user_id = await resolve_authenticated_user_id(request, db, get_config())

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded video is empty")

    try:
        service = GeneratedVideoService(db)
        return await service.save(
            user_id,
            data,
            title=title,
            duration=duration,
            text_content=text_content,
            hook_title=hook_title or None,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Exception as error:
        logger.exception("Saving the generated video failed")
        raise HTTPException(status_code=500, detail="Could not save the video") from error


@router.get("/narration/{filename}")
async def serve_narration(
    filename: str, request: Request, db: AsyncSession = Depends(get_db)
):
    """
    Serve a synthesised narration file.

    Needed because assembly renders in a browser, which can only reach audio
    over HTTP. Files are scoped to the requesting user's own directory and the
    name is checked against traversal, so one user cannot read another's.
    """
    user_id = await resolve_authenticated_user_id(request, db, get_config())

    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    path = Path(get_config().temp_dir) / "narration" / str(user_id) / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Narration not found")

    return FileResponse(path, media_type="audio/mpeg", filename=filename)


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
