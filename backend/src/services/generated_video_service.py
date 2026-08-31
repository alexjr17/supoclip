"""
Persisting AI-generated videos alongside clipped ones.

A generated video and a clipped one end up in the same place: a vertical mp4 the
user wants to publish. So rather than inventing a second listing, a second
detail page and a second publishing path, a generated video is stored as a task
whose `kind` is 'generated', holding a single clip.

Everything downstream — /list, the task page, scheduling, YouTube and TikTok
publishing — then works on it without changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Config, get_config
from ..repositories.clip_repository import ClipRepository
from ..repositories.task_repository import TaskRepository

logger = logging.getLogger(__name__)

# Generated videos are one clip each, so the clip inherits the task's title.
DEFAULT_TITLE = "AI generated video"


class GeneratedVideoService:
    def __init__(self, db: AsyncSession, config: Config | None = None):
        self.db = db
        self.config = config or get_config()
        self.task_repo = TaskRepository()
        self.clip_repo = ClipRepository()

    def _clips_dir(self) -> Path:
        path = Path(self.config.temp_dir) / "clips"
        path.mkdir(parents=True, exist_ok=True)
        return path

    async def save(
        self,
        user_id: str,
        video_bytes: bytes,
        *,
        title: str = DEFAULT_TITLE,
        duration: float = 0.0,
        text_content: str = "",
        hook_title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Store a rendered video as a completed task with one clip.

        A 'generated' source row is created alongside it so the video carries a
        title through the listing and the task page without any of them needing
        to special-case it.
        """
        if not video_bytes:
            raise ValueError("No video data to save")

        filename = f"generated_{uuid4().hex}.mp4"
        output_path = self._clips_dir() / filename
        output_path.write_bytes(video_bytes)

        # A source row, so the video carries its title through the listing and
        # the task page like any other. Its type is 'generated' and it has no
        # URL: the source really is the script, not a file somewhere.
        source_id = str(uuid4())
        await self.db.execute(
            text(
                """
                INSERT INTO sources (id, type, title, url, created_at, updated_at)
                VALUES (:id, 'generated', :title, NULL, NOW(), NOW())
                """
            ),
            {"id": source_id, "title": title[:500]},
        )

        task_id = str(uuid4())
        await self.db.execute(
            text(
                """
                INSERT INTO tasks (
                    id, user_id, source_id, status, kind,
                    progress, progress_message,
                    created_at, updated_at, completed_at
                ) VALUES (
                    :id, :user_id, :source_id, 'completed', 'generated',
                    100, 'Generated from a script',
                    NOW(), NOW(), NOW()
                )
                """
            ),
            {"id": task_id, "user_id": user_id, "source_id": source_id},
        )

        clip_id = await self.clip_repo.create_clip(
            self.db,
            task_id=task_id,
            filename=filename,
            file_path=str(output_path),
            start_time="00:00",
            end_time=self._seconds_to_mmss(duration),
            duration=duration,
            text=text_content or title,
            relevance_score=1.0,
            reasoning="Assembled from an AI-written script",
            clip_order=1,
            virality_score=0,
            hook_score=0,
            engagement_score=0,
            value_score=0,
            shareability_score=0,
            hook_type=None,
            hook_title=hook_title,
        )

        await self.task_repo.update_task_clips(self.db, task_id, [clip_id])
        await self.db.commit()

        logger.info(
            "Saved generated video %s as task %s (%.2fs, %s bytes)",
            filename,
            task_id,
            duration,
            len(video_bytes),
        )

        return {
            "task_id": task_id,
            "clip_id": clip_id,
            "filename": filename,
            "duration": duration,
        }

    @staticmethod
    def _seconds_to_mmss(seconds: float) -> str:
        total = max(0, int(seconds))
        return f"{total // 60:02d}:{total % 60:02d}"
