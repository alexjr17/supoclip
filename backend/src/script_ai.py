"""
Script generation for AI-authored videos.

This is the counterpart to `ai.py`: where that module *finds* the good parts of
an existing transcript, this one *writes* a short-form script from nothing but
an idea. It produces the two artefacts the generation flow needs before any
video exists — an ordered list of scenes, and the cast those scenes refer to.

Note on the cast: with a stock-footage pipeline the character sheet cannot make
the same face appear twice, because stock libraries return different people for
every query. What it does buy is narrative coherence (stable names, roles and
tone across scenes) and stable per-character stock keywords, so a given
character is at least always searched for the same way.
"""

from typing import List, Literal, Optional
import logging

from pydantic_ai import Agent
from pydantic import BaseModel, Field, field_validator

from .ai import (
    _build_transcript_model,
    _get_missing_llm_key_error,
    _split_llm_name,
)
from .config import get_config
from .runtime_settings import apply_settings_to_process_env

logger = logging.getLogger(__name__)

MIN_SCENE_SECONDS = 2
MAX_SCENE_SECONDS = 15
MIN_TOTAL_SECONDS = 15
MAX_TOTAL_SECONDS = 180
MAX_SCENES = 20

ScriptTone = Literal["informative", "energetic", "story", "calm", "funny"]


class ScriptCharacter(BaseModel):
    """One recurring person in the script."""

    name: str = Field(description="Short name used to refer to this character in scenes.")
    role: str = Field(description="What they are in the story, e.g. 'narrator', 'sceptical friend'.")
    description: str = Field(
        description="Visual and personality summary: apparent age, dress, demeanour."
    )
    voice_tone: str = Field(
        description="How this character sounds, e.g. 'warm and measured'. Guides narration."
    )
    stock_keywords: List[str] = Field(
        default_factory=list,
        description=(
            "2-4 English search terms that should be reused every time this character "
            "appears, so stock footage stays as close to consistent as it can."
        ),
    )

    @field_validator("stock_keywords")
    @classmethod
    def _cap_keywords(cls, value: List[str]) -> List[str]:
        return [keyword.strip() for keyword in value if keyword.strip()][:4]


class ScriptScene(BaseModel):
    """One beat of the video."""

    order: int = Field(description="1-based position of this scene in the video.")
    narration: str = Field(description="Exactly what the voice-over says during this scene.")
    duration_seconds: float = Field(
        description=f"How long the scene runs, between {MIN_SCENE_SECONDS} and {MAX_SCENE_SECONDS}."
    )
    visual_description: str = Field(description="What is on screen, in one sentence.")
    stock_keywords: List[str] = Field(
        default_factory=list,
        description="2-4 English search terms for finding stock footage for this scene.",
    )
    character_names: List[str] = Field(
        default_factory=list,
        description="Names from the cast that appear in this scene. Empty when nobody appears.",
    )

    @field_validator("duration_seconds")
    @classmethod
    def _clamp_duration(cls, value: float) -> float:
        return max(float(MIN_SCENE_SECONDS), min(float(MAX_SCENE_SECONDS), float(value)))

    @field_validator("stock_keywords")
    @classmethod
    def _cap_keywords(cls, value: List[str]) -> List[str]:
        return [keyword.strip() for keyword in value if keyword.strip()][:4]


class VideoScript(BaseModel):
    """A complete short-form script, ready to be reviewed and edited by hand."""

    title: str = Field(description="Working title for the video.")
    hook: str = Field(description="The opening line, 3-12 words, meant to stop the scroll.")
    scenes: List[ScriptScene] = Field(description="Scenes in playback order.")
    characters: List[ScriptCharacter] = Field(
        default_factory=list,
        description="The cast referenced by the scenes. Empty for a faceless voice-over video.",
    )

    @property
    def total_duration_seconds(self) -> float:
        return round(sum(scene.duration_seconds for scene in self.scenes), 2)


script_system_prompt = """
You write scripts for short-form vertical videos (TikTok, Reels, YouTube Shorts).

Given an idea, produce a complete script broken into scenes.

Rules:
- The hook is the first thing said. It must earn the next three seconds.
- Every scene carries one idea. Keep narration conversational and spoken, not
  written: short sentences, no bullet points, no stage directions in narration.
- Scene duration must match how long its narration actually takes to say at a
  natural pace, roughly 2.5 words per second.
- `stock_keywords` are English search terms for a stock footage library. Prefer
  concrete, filmable subjects ("woman typing laptop") over abstractions
  ("productivity"). Never use proper nouns or brand names.
- Only invent characters when the script genuinely needs recurring people. A
  straightforward explainer needs none — return an empty cast.
- When you do use characters, reuse the exact same `name` across scenes, and
  give each one stock_keywords that are reused on every appearance.
- Respect the requested total duration and language.

Return the script in the requested output language. `stock_keywords` always stay
in English, because the stock library is searched in English.
""".strip()


_script_agent = None
_script_agent_signature = None


def get_script_agent() -> Agent[None, VideoScript]:
    """Get or create the script agent, rebuilding it when LLM settings change."""
    global _script_agent, _script_agent_signature

    runtime_config = get_config()
    provider, _ = _split_llm_name(runtime_config.llm)
    signature = (
        runtime_config.llm,
        runtime_config.openai_api_key,
        runtime_config.google_api_key,
        runtime_config.anthropic_api_key,
        runtime_config.ollama_base_url,
        runtime_config.ollama_api_key,
    )

    if _script_agent is None or _script_agent_signature != signature:
        apply_settings_to_process_env(runtime_config.as_runtime_settings())
        config_error = _get_missing_llm_key_error(runtime_config.llm, runtime_config)
        if config_error:
            raise RuntimeError(config_error)

        _script_agent = Agent[None, VideoScript](
            model=_build_transcript_model(runtime_config),
            output_type=VideoScript,
            system_prompt=script_system_prompt,
            output_retries=2,
        )
        _script_agent_signature = signature

    return _script_agent


def build_script_prompt(
    idea: str,
    target_duration_seconds: int,
    tone: ScriptTone,
    language: str,
    with_characters: bool,
) -> str:
    scene_hint = max(3, min(MAX_SCENES, round(target_duration_seconds / 6)))
    cast_instruction = (
        "Use a small recurring cast (1-3 characters) and reference them by name in the scenes."
        if with_characters
        else "This is a faceless voice-over video. Return an empty `characters` list."
    )

    return f"""
Idea: {idea}

Target total duration: about {target_duration_seconds} seconds (aim for roughly
{scene_hint} scenes; the sum of scene durations should land close to the target).
Tone: {tone}
Output language: {language}
{cast_instruction}
""".strip()


async def generate_video_script(
    idea: str,
    target_duration_seconds: int = 45,
    tone: ScriptTone = "informative",
    language: str = "English",
    with_characters: bool = False,
) -> VideoScript:
    """Write a script for the given idea and normalise the model's output."""
    target_duration_seconds = max(
        MIN_TOTAL_SECONDS, min(MAX_TOTAL_SECONDS, int(target_duration_seconds))
    )

    agent = get_script_agent()
    prompt = build_script_prompt(
        idea=idea,
        target_duration_seconds=target_duration_seconds,
        tone=tone,
        language=language,
        with_characters=with_characters,
    )

    result = await agent.run(prompt)
    script: VideoScript = result.output

    # Models drift on ordering and occasionally overrun the scene cap, so the
    # order is reassigned here rather than trusted from the response.
    script.scenes = script.scenes[:MAX_SCENES]
    for index, scene in enumerate(script.scenes, start=1):
        scene.order = index

    if not with_characters:
        script.characters = []
    else:
        # Drop cast entries no scene ever mentions: they only add noise to the
        # sheet the user is about to edit.
        referenced = {
            name.strip().lower()
            for scene in script.scenes
            for name in scene.character_names
        }
        script.characters = [
            character
            for character in script.characters
            if character.name.strip().lower() in referenced
        ]

    logger.info(
        "Generated script '%s' with %s scenes (%.1fs) and %s characters",
        script.title,
        len(script.scenes),
        script.total_duration_seconds,
        len(script.characters),
    )
    return script
