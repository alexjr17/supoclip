"""
Clip repository - handles all database operations for generated clips.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text as sa_text
from typing import List, Dict, Any, Optional
from datetime import date, time as dtime
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger(__name__)


class ClipRepository:
    """Repository for clip-related database operations."""

    @staticmethod
    async def create_clip(
        db: AsyncSession,
        task_id: str,
        filename: str,
        file_path: str,
        start_time: str,
        end_time: str,
        duration: float,
        text: str,
        relevance_score: float,
        reasoning: str,
        clip_order: int,
        virality_score: int = 0,
        hook_score: int = 0,
        engagement_score: int = 0,
        value_score: int = 0,
        shareability_score: int = 0,
        hook_type: Optional[str] = None,
        hook_title: Optional[str] = None,
    ) -> str:
        """Create a new clip record and return its ID."""
        try:
            result = await db.execute(
                sa_text("""
                    INSERT INTO generated_clips
                    (task_id, filename, file_path, start_time, end_time, duration,
                     text, relevance_score, reasoning, clip_order,
                     virality_score, hook_score, engagement_score, value_score, shareability_score, hook_type,
                     hook_title, created_at)
                    VALUES
                    (:task_id, :filename, :file_path, :start_time, :end_time, :duration,
                     :text, :relevance_score, :reasoning, :clip_order,
                     :virality_score, :hook_score, :engagement_score, :value_score, :shareability_score, :hook_type,
                     :hook_title, NOW())
                    RETURNING id
                """),
                {
                    "task_id": task_id,
                    "filename": filename,
                    "file_path": file_path,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "text": text,
                    "relevance_score": relevance_score,
                    "reasoning": reasoning,
                    "clip_order": clip_order,
                    "virality_score": virality_score,
                    "hook_score": hook_score,
                    "engagement_score": engagement_score,
                    "value_score": value_score,
                    "shareability_score": shareability_score,
                    "hook_type": hook_type,
                    "hook_title": hook_title,
                },
            )
        except Exception:
            await db.rollback()
            result = await db.execute(
                sa_text("""
                    INSERT INTO generated_clips
                    (task_id, filename, file_path, start_time, end_time, duration,
                     text, relevance_score, reasoning, clip_order, created_at)
                    VALUES
                    (:task_id, :filename, :file_path, :start_time, :end_time, :duration,
                     :text, :relevance_score, :reasoning, :clip_order, NOW())
                    RETURNING id
                """),
                {
                    "task_id": task_id,
                    "filename": filename,
                    "file_path": file_path,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": duration,
                    "text": text,
                    "relevance_score": relevance_score,
                    "reasoning": reasoning,
                    "clip_order": clip_order,
                },
            )
        clip_id = result.scalar()
        if not clip_id:
            raise RuntimeError("Failed to create clip: no ID returned")
        logger.debug(f"Created clip {clip_id} for task {task_id}")
        return str(clip_id)

    @staticmethod
    async def get_clips_by_task(db: AsyncSession, task_id: str) -> List[Dict[str, Any]]:
        """Get all clips for a specific task, ordered by clip_order."""
        try:
            result = await db.execute(
                sa_text("""
                    SELECT id, filename, file_path, start_time, end_time, duration,
                           text, relevance_score, reasoning, clip_order, created_at,
                           virality_score, hook_score, engagement_score, value_score, shareability_score, hook_type,
                           hook_title,
                           publish_requested, publish_status, scheduled_publish_at, published_at, publish_error,
                           youtube_video_id, tiktok_video_id,
                           tiktok_publish_requested, tiktok_publish_status, tiktok_scheduled_at,
                           tiktok_published_at, tiktok_publish_error
                    FROM generated_clips
                    WHERE task_id = :task_id
                    ORDER BY clip_order ASC
                """),
                {"task_id": task_id},
            )
        except Exception:
            await db.rollback()
            result = await db.execute(
                sa_text("""
                    SELECT id, filename, file_path, start_time, end_time, duration,
                           text, relevance_score, reasoning, clip_order, created_at
                    FROM generated_clips
                    WHERE task_id = :task_id
                    ORDER BY clip_order ASC
                """),
                {"task_id": task_id},
            )

        clips = []
        for row in result.fetchall():
            clips.append(
                {
                    "id": row.id,
                    "filename": row.filename,
                    "file_path": row.file_path,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "duration": row.duration,
                    "text": row.text,
                    "relevance_score": row.relevance_score,
                    "reasoning": row.reasoning,
                    "clip_order": row.clip_order,
                    "created_at": row.created_at.isoformat(),
                    "video_url": f"/tasks/{task_id}/clips/{row.id}/file",
                    "virality_score": row.virality_score or 0,
                    "hook_score": row.hook_score or 0,
                    "engagement_score": row.engagement_score or 0,
                    "value_score": row.value_score or 0,
                    "shareability_score": row.shareability_score or 0,
                    "hook_type": row.hook_type,
                    "hook_title": getattr(row, "hook_title", None),
                    "publish_requested": getattr(row, "publish_requested", False) or False,
                    "publish_status": getattr(row, "publish_status", None) or "none",
                    "scheduled_publish_at": (
                        getattr(row, "scheduled_publish_at", None).isoformat()
                        if getattr(row, "scheduled_publish_at", None)
                        else None
                    ),
                    "published_at": (
                        getattr(row, "published_at", None).isoformat()
                        if getattr(row, "published_at", None)
                        else None
                    ),
                    "publish_error": getattr(row, "publish_error", None),
                    "youtube_video_id": getattr(row, "youtube_video_id", None),
                    "tiktok_video_id": getattr(row, "tiktok_video_id", None),
                    "tiktok_publish_requested": (
                        getattr(row, "tiktok_publish_requested", False) or False
                    ),
                    "tiktok_publish_status": (
                        getattr(row, "tiktok_publish_status", None) or "none"
                    ),
                    "tiktok_scheduled_at": (
                        getattr(row, "tiktok_scheduled_at", None).isoformat()
                        if getattr(row, "tiktok_scheduled_at", None)
                        else None
                    ),
                    "tiktok_published_at": (
                        getattr(row, "tiktok_published_at", None).isoformat()
                        if getattr(row, "tiktok_published_at", None)
                        else None
                    ),
                    "tiktok_publish_error": getattr(row, "tiktok_publish_error", None),
                }
            )

        return clips

    @staticmethod
    async def get_clips_count(db: AsyncSession, task_id: str) -> int:
        """Get the count of clips for a task."""
        result = await db.execute(
            sa_text(
                "SELECT COUNT(*) as count FROM generated_clips WHERE task_id = :task_id"
            ),
            {"task_id": task_id},
        )
        return result.scalar()

    @staticmethod
    async def delete_clips_by_task(db: AsyncSession, task_id: str) -> int:
        """Delete all clips for a task. Returns count of deleted clips."""
        result = await db.execute(
            sa_text("DELETE FROM generated_clips WHERE task_id = :task_id"),
            {"task_id": task_id},
        )
        await db.commit()
        deleted_count = result.rowcount
        logger.info(f"Deleted {deleted_count} clips for task {task_id}")
        return deleted_count

    @staticmethod
    async def delete_clip(db: AsyncSession, clip_id: str) -> None:
        """Delete a single clip by ID."""
        await db.execute(
            sa_text("DELETE FROM generated_clips WHERE id = :clip_id"),
            {"clip_id": clip_id},
        )
        await db.commit()
        logger.info(f"Deleted clip {clip_id}")

    @staticmethod
    async def get_clip_by_id(
        db: AsyncSession, clip_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get one clip by ID."""
        try:
            result = await db.execute(
                sa_text(
                    """
                    SELECT id, task_id, filename, file_path, start_time, end_time, duration,
                           text, relevance_score, reasoning, clip_order,
                           virality_score, hook_score, engagement_score, value_score, shareability_score, hook_type,
                           hook_title, created_at,
                           publish_requested, publish_status, scheduled_publish_at, published_at, publish_error,
                           youtube_video_id, tiktok_video_id,
                           tiktok_publish_requested, tiktok_publish_status, tiktok_scheduled_at,
                           tiktok_published_at, tiktok_publish_error
                    FROM generated_clips
                    WHERE id = :clip_id
                    """
                ),
                {"clip_id": clip_id},
            )
        except Exception:
            await db.rollback()
            result = await db.execute(
                sa_text(
                    """
                    SELECT id, task_id, filename, file_path, start_time, end_time, duration,
                           text, relevance_score, reasoning, clip_order, created_at
                    FROM generated_clips
                    WHERE id = :clip_id
                    """
                ),
                {"clip_id": clip_id},
            )
        row = result.fetchone()
        if not row:
            return None

        return {
            "id": row.id,
            "task_id": row.task_id,
            "filename": row.filename,
            "file_path": row.file_path,
            "start_time": row.start_time,
            "end_time": row.end_time,
            "duration": row.duration,
            "text": row.text,
            "relevance_score": row.relevance_score,
            "reasoning": row.reasoning,
            "clip_order": row.clip_order,
            "virality_score": row.virality_score or 0,
            "hook_score": row.hook_score or 0,
            "engagement_score": row.engagement_score or 0,
            "value_score": row.value_score or 0,
            "shareability_score": row.shareability_score or 0,
            "hook_type": row.hook_type,
            "hook_title": getattr(row, "hook_title", None),
            "created_at": row.created_at.isoformat(),
            "video_url": f"/tasks/{row.task_id}/clips/{row.id}/file",
            "publish_requested": getattr(row, "publish_requested", False) or False,
            "publish_status": getattr(row, "publish_status", None) or "none",
            "scheduled_publish_at": (
                getattr(row, "scheduled_publish_at", None).isoformat()
                if getattr(row, "scheduled_publish_at", None)
                else None
            ),
            "published_at": (
                getattr(row, "published_at", None).isoformat()
                if getattr(row, "published_at", None)
                else None
            ),
            "publish_error": getattr(row, "publish_error", None),
            "youtube_video_id": getattr(row, "youtube_video_id", None),
            "tiktok_video_id": getattr(row, "tiktok_video_id", None),
            "tiktok_publish_requested": (
                getattr(row, "tiktok_publish_requested", False) or False
            ),
            "tiktok_publish_status": (
                getattr(row, "tiktok_publish_status", None) or "none"
            ),
            "tiktok_scheduled_at": (
                getattr(row, "tiktok_scheduled_at", None).isoformat()
                if getattr(row, "tiktok_scheduled_at", None)
                else None
            ),
            "tiktok_published_at": (
                getattr(row, "tiktok_published_at", None).isoformat()
                if getattr(row, "tiktok_published_at", None)
                else None
            ),
            "tiktok_publish_error": getattr(row, "tiktok_publish_error", None),
        }

    @staticmethod
    async def update_clip(
        db: AsyncSession,
        clip_id: str,
        filename: str,
        file_path: str,
        start_time: str,
        end_time: str,
        duration: float,
        text: str,
    ) -> None:
        """Update core clip metadata and file path."""
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET filename = :filename,
                    file_path = :file_path,
                    start_time = :start_time,
                    end_time = :end_time,
                    duration = :duration,
                    text = :text,
                    updated_at = NOW()
                WHERE id = :clip_id
                """
            ),
            {
                "clip_id": clip_id,
                "filename": filename,
                "file_path": file_path,
                "start_time": start_time,
                "end_time": end_time,
                "duration": duration,
                "text": text,
            },
        )
        await db.commit()

    @staticmethod
    async def reorder_task_clips(db: AsyncSession, task_id: str) -> None:
        """Normalize clip_order sequence after edits."""
        result = await db.execute(
            sa_text(
                "SELECT id FROM generated_clips WHERE task_id = :task_id ORDER BY clip_order ASC, created_at ASC"
            ),
            {"task_id": task_id},
        )
        clip_ids = [row.id for row in result.fetchall()]
        for idx, cid in enumerate(clip_ids, start=1):
            await db.execute(
                sa_text(
                    "UPDATE generated_clips SET clip_order = :clip_order, updated_at = NOW() WHERE id = :clip_id"
                ),
                {"clip_order": idx, "clip_id": cid},
            )
        await db.commit()

    @staticmethod
    async def set_clip_publish_request(
        db: AsyncSession, clip_ids: list[str], requested: bool
    ) -> None:
        """Mark/unmark clips for auto-publishing."""
        if not clip_ids:
            return
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET publish_requested = :requested,
                    publish_status = CASE
                        WHEN :requested THEN CASE WHEN publish_status = 'none' THEN 'pending' ELSE publish_status END
                        ELSE CASE WHEN publish_status IN ('none', 'pending') THEN 'none' ELSE publish_status END
                    END,
                    scheduled_publish_at = CASE
                        WHEN NOT :requested AND publish_status IN ('none', 'pending') THEN NULL
                        ELSE scheduled_publish_at
                    END,
                    publish_error = CASE WHEN NOT :requested AND publish_status IN ('none', 'pending') THEN NULL ELSE publish_error END,
                    updated_at = NOW()
                WHERE id = ANY(:clip_ids)
                """
            ),
            {"requested": requested, "clip_ids": clip_ids},
        )
        await db.commit()

    @staticmethod
    async def set_clip_publish_profile(
        db: AsyncSession, clip_ids: list[str], profile_id: str | None
    ) -> None:
        """Record which profile a set of clips was marked for publishing with."""
        if not clip_ids:
            return
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET publish_profile_id = :profile_id, updated_at = NOW()
                WHERE id = ANY(:clip_ids)
                """
            ),
            {"profile_id": profile_id, "clip_ids": clip_ids},
        )
        await db.commit()

    @staticmethod
    async def count_scheduled_per_day(db: AsyncSession, tz: str = "UTC") -> Dict[str, int]:
        result = await db.execute(
            sa_text(
                """
                SELECT TO_CHAR(scheduled_publish_at AT TIME ZONE :tz, 'YYYY-MM-DD') AS day, COUNT(*) AS cnt
                FROM generated_clips
                WHERE publish_status = 'scheduled' AND scheduled_publish_at IS NOT NULL
                GROUP BY day
                """
            ),
            {"tz": tz},
        )
        return {row.day: int(row.cnt) for row in result.fetchall()}

    @staticmethod
    async def scheduled_slot_times_per_day(
        db: AsyncSession, tz: str = "UTC"
    ) -> Dict[str, list]:
        """Map each local day to the publishing slot times already used that day.

        Both scheduled and already-published clips count towards a day's slots,
        so the daily publish limit is never exceeded.
        """
        result = await db.execute(
            sa_text(
                """
                SELECT scheduled_publish_at
                FROM generated_clips
                WHERE publish_status IN ('scheduled', 'published')
                  AND scheduled_publish_at IS NOT NULL
                """
            ),
        )
        days: Dict[str, list] = {}
        for row in result.fetchall():
            local = row.scheduled_publish_at.astimezone(ZoneInfo(tz))
            days.setdefault(local.date().isoformat(), []).append(
                local.time().replace(tzinfo=None)
            )
        return days

    @staticmethod
    async def count_publish_status_by_user(
        db: AsyncSession, user_id: str
    ) -> Dict[str, int]:
        """Count clips publish statuses for a user's tasks."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.publish_status AS status, COUNT(*) AS cnt
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id AND c.publish_status IS NOT NULL
                GROUP BY c.publish_status
                """
            ),
            {"user_id": user_id},
        )
        return {row.status: int(row.cnt) for row in result.fetchall()}

    @staticmethod
    async def list_publish_pending_clips(db: AsyncSession) -> list[Dict[str, Any]]:
        """Clips marked for publishing that still need to be scheduled."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order,
                       c.publish_requested, c.publish_status, c.scheduled_publish_at,
                       c.publish_error,
                       c.youtube_video_id, c.tiktok_video_id, c.publish_profile_id,
                       t.user_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE c.publish_requested = TRUE AND c.publish_status IN ('pending', 'failed')
                ORDER BY c.created_at ASC
                """
            ),
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "publish_requested": row.publish_requested,
                "publish_status": row.publish_status,
                "scheduled_publish_at": row.scheduled_publish_at,
                "publish_error": row.publish_error,
                "youtube_video_id": row.youtube_video_id,
                "tiktok_video_id": row.tiktok_video_id,
                "publish_profile_id": row.publish_profile_id,
                "user_id": row.user_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def mark_past_scheduled_as_published(db: AsyncSession) -> int:
        """Clips whose scheduled publish time has passed are considered published."""
        result = await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET publish_status = 'published',
                    published_at = COALESCE(published_at, scheduled_publish_at),
                    updated_at = NOW()
                WHERE publish_status = 'scheduled'
                  AND scheduled_publish_at IS NOT NULL
                  AND scheduled_publish_at <= NOW()
                """
            ),
        )
        await db.commit()
        return result.rowcount

    @staticmethod
    async def list_user_clips_for_publish(
        db: AsyncSession, user_id: str
    ) -> list[Dict[str, Any]]:
        """All completed clips for a user that are not yet uploaded/scheduled.

        Used by the mass-upload action. Clips that are already published,
        scheduled or already carrying a youtube_video_id are excluded.
        """
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order, c.publish_requested, c.publish_status,
                       c.scheduled_publish_at, c.publish_error, c.youtube_video_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id
                  AND t.status = 'completed'
                  AND c.file_path IS NOT NULL
                  AND c.publish_status NOT IN ('published', 'scheduled')
                  AND c.youtube_video_id IS NULL
                ORDER BY c.created_at ASC
                """
            ),
            {"user_id": user_id},
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "publish_requested": row.publish_requested,
                "publish_status": row.publish_status,
                "scheduled_publish_at": row.scheduled_publish_at,
                "publish_error": row.publish_error,
                "youtube_video_id": row.youtube_video_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def list_user_clips_for_sync(db: AsyncSession, user_id: str) -> list[Dict[str, Any]]:
        """All completed clips for a user, used to reconcile with YouTube."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order, c.publish_requested, c.publish_status,
                       c.scheduled_publish_at, c.published_at, c.publish_error,
                       c.youtube_video_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id
                  AND t.status = 'completed'
                ORDER BY c.created_at ASC
                """
            ),
            {"user_id": user_id},
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "publish_requested": row.publish_requested,
                "publish_status": row.publish_status,
                "scheduled_publish_at": row.scheduled_publish_at,
                "published_at": row.published_at,
                "publish_error": row.publish_error,
                "youtube_video_id": row.youtube_video_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def list_user_clips_scheduled_for_date(
        db: AsyncSession, user_id: str, tz: str, date: date
    ) -> list[Dict[str, Any]]:
        """Completed clips of a user scheduled to be published on a given local day.

        ``date`` is a ``datetime.date`` in the publishing timezone ``tz`` (a
        plain ``str`` fails asyncpg's date-typed bind inference).
        """
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order, c.publish_requested, c.publish_status,
                       c.scheduled_publish_at, c.publish_error, c.youtube_video_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id
                  AND t.status = 'completed'
                  AND c.publish_status = 'scheduled'
                  AND c.scheduled_publish_at IS NOT NULL
                  AND (c.scheduled_publish_at AT TIME ZONE :tz)::date = :date
                ORDER BY c.scheduled_publish_at ASC
                """
            ),
            {"user_id": user_id, "tz": tz, "date": date},
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "publish_requested": row.publish_requested,
                "publish_status": row.publish_status,
                "scheduled_publish_at": row.scheduled_publish_at,
                "publish_error": row.publish_error,
                "youtube_video_id": row.youtube_video_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def find_clip_by_youtube_video_id(
        db: AsyncSession, video_id: str
    ) -> Optional[Dict[str, Any]]:
        """Return a clip that already references a given YouTube video id."""
        result = await db.execute(
            sa_text(
                """
                SELECT id, task_id, publish_status, youtube_video_id
                FROM generated_clips
                WHERE youtube_video_id = :video_id
                LIMIT 1
                """
            ),
            {"video_id": video_id},
        )
        row = result.mappings().first()
        if not row:
            return None
        return dict(row)

    @staticmethod
    async def list_all_youtube_video_ids(db: AsyncSession) -> set[str]:
        """All YouTube video ids already recorded across clips (for dedup)."""
        result = await db.execute(
            sa_text(
                """
                SELECT youtube_video_id FROM generated_clips
                WHERE youtube_video_id IS NOT NULL
                """
            ),
        )
        return {row.youtube_video_id for row in result.fetchall()}

    @staticmethod
    async def set_clip_youtube_video_id(
        db: AsyncSession, clip_id: str, video_id: str
    ) -> None:
        """Record the YouTube video id for a clip (uploaded via direct API)."""
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET youtube_video_id = :video_id, updated_at = NOW()
                WHERE id = :clip_id
                """
            ),
            {"clip_id": clip_id, "video_id": video_id},
        )
        await db.commit()

    @staticmethod
    async def set_clip_tiktok_video_id(
        db: AsyncSession, clip_id: str, video_id: str
    ) -> None:
        """Record the TikTok publish id for a clip (uploaded via direct API)."""
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET tiktok_video_id = :video_id,
                    tiktok_publish_status = 'published',
                    tiktok_published_at = COALESCE(tiktok_published_at, NOW()),
                    tiktok_publish_error = NULL,
                    updated_at = NOW()
                WHERE id = :clip_id
                """
            ),
            {"clip_id": clip_id, "video_id": video_id},
        )
        await db.commit()

    @staticmethod
    async def list_user_clips_for_tiktok(
        db: AsyncSession, user_id: str
    ) -> list[Dict[str, Any]]:
        """All completed clips for a user that are not yet published to TikTok.

        Used by the TikTok mass-upload action. Clips that already carry a
        ``tiktok_video_id`` are excluded (no duplicates are posted).
        """
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order, c.publish_requested, c.publish_status,
                       c.scheduled_publish_at, c.publish_error, c.tiktok_video_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id
                  AND t.status = 'completed'
                  AND c.file_path IS NOT NULL
                  AND c.tiktok_video_id IS NULL
                ORDER BY c.created_at ASC
                """
            ),
            {"user_id": user_id},
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "publish_requested": row.publish_requested,
                "publish_status": row.publish_status,
                "scheduled_publish_at": row.scheduled_publish_at,
                "publish_error": row.publish_error,
                "tiktok_video_id": row.tiktok_video_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def mark_user_clips_published_from_sync(
        db: AsyncSession,
        clip_id: str,
        video_id: str,
        title: str,
    ) -> None:
        """Mark a clip as published because it already exists on YouTube."""
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET publish_status = 'published',
                    youtube_video_id = :video_id,
                    published_at = COALESCE(published_at, NOW()),
                    publish_requested = TRUE,
                    updated_at = NOW()
                WHERE id = :clip_id
                  AND youtube_video_id IS NULL
                """
            ),
            {"clip_id": clip_id, "video_id": video_id},
        )
        await db.commit()

    @staticmethod
    async def update_clip_publish(
        db: AsyncSession,
        clip_id: str,
        status: str,
        scheduled_at: Any = None,
        published_at: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """Update the publish state of a clip."""
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET publish_status = :status,
                    scheduled_publish_at = :scheduled_at,
                    published_at = :published_at,
                    publish_error = :error,
                    updated_at = NOW()
                WHERE id = :clip_id
                """
            ),
            {
                "clip_id": clip_id,
                "status": status,
                "scheduled_at": scheduled_at,
                "published_at": published_at,
                "error": error,
            },
        )

    @staticmethod
    async def set_clip_tiktok_publish_request(
        db: AsyncSession, clip_ids: list[str], requested: bool
    ) -> None:
        """Mark/unmark clips for TikTok auto-publishing."""
        if not clip_ids:
            return
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET tiktok_publish_requested = :requested,
                    tiktok_publish_status = CASE
                        WHEN :requested THEN CASE WHEN tiktok_publish_status = 'none' THEN 'pending' ELSE tiktok_publish_status END
                        ELSE CASE WHEN tiktok_publish_status IN ('none', 'pending') THEN 'none' ELSE tiktok_publish_status END
                    END,
                    tiktok_scheduled_at = CASE
                        WHEN NOT :requested AND tiktok_publish_status IN ('none', 'pending') THEN NULL
                        ELSE tiktok_scheduled_at
                    END,
                    tiktok_publish_error = CASE WHEN NOT :requested AND tiktok_publish_status IN ('none', 'pending') THEN NULL ELSE tiktok_publish_error END,
                    updated_at = NOW()
                WHERE id = ANY(:clip_ids)
                """
            ),
            {"requested": requested, "clip_ids": clip_ids},
        )
        await db.commit()

    @staticmethod
    async def count_tiktok_publish_status_by_user(
        db: AsyncSession, user_id: str
    ) -> Dict[str, int]:
        """Count clips TikTok publish statuses for a user's tasks."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.tiktok_publish_status AS status, COUNT(*) AS cnt
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id AND c.tiktok_publish_status IS NOT NULL
                GROUP BY c.tiktok_publish_status
                """
            ),
            {"user_id": user_id},
        )
        return {row.status: int(row.cnt) for row in result.fetchall()}

    @staticmethod
    async def list_tiktok_publish_pending_clips(db: AsyncSession) -> list[Dict[str, Any]]:
        """Clips marked for TikTok publishing that still need a slot assigned."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order,
                       c.tiktok_publish_requested, c.tiktok_publish_status,
                       c.tiktok_scheduled_at, c.tiktok_publish_error,
                       c.tiktok_video_id, c.publish_profile_id,
                       t.user_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE c.tiktok_publish_requested = TRUE
                  AND c.tiktok_publish_status IN ('pending', 'failed')
                ORDER BY c.created_at ASC
                """
            ),
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "tiktok_publish_requested": row.tiktok_publish_requested,
                "tiktok_publish_status": row.tiktok_publish_status,
                "tiktok_scheduled_at": row.tiktok_scheduled_at,
                "tiktok_publish_error": row.tiktok_publish_error,
                "tiktok_video_id": row.tiktok_video_id,
                "publish_profile_id": row.publish_profile_id,
                "user_id": row.user_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def list_tiktok_publish_due_clips(db: AsyncSession) -> list[Dict[str, Any]]:
        """Clips whose TikTok slot time has arrived and need to be published now."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order,
                       c.tiktok_publish_requested, c.tiktok_publish_status,
                       c.tiktok_scheduled_at, c.tiktok_publish_error,
                       c.tiktok_video_id, c.publish_profile_id,
                       t.user_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE c.tiktok_publish_status = 'scheduled'
                  AND c.tiktok_scheduled_at IS NOT NULL
                  AND c.tiktok_scheduled_at <= NOW()
                ORDER BY c.tiktok_scheduled_at ASC
                """
            ),
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "tiktok_publish_requested": row.tiktok_publish_requested,
                "tiktok_publish_status": row.tiktok_publish_status,
                "tiktok_scheduled_at": row.tiktok_scheduled_at,
                "tiktok_publish_error": row.tiktok_publish_error,
                "tiktok_video_id": row.tiktok_video_id,
                "publish_profile_id": row.publish_profile_id,
                "user_id": row.user_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def update_clip_tiktok_publish(
        db: AsyncSession,
        clip_id: str,
        status: str,
        scheduled_at: Any = None,
        published_at: Any = None,
        error: Optional[str] = None,
    ) -> None:
        """Update the TikTok publish state of a clip."""
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET tiktok_publish_status = :status,
                    tiktok_scheduled_at = :scheduled_at,
                    tiktok_published_at = :published_at,
                    tiktok_publish_error = :error,
                    updated_at = NOW()
                WHERE id = :clip_id
                """
            ),
            {
                "clip_id": clip_id,
                "status": status,
                "scheduled_at": scheduled_at,
                "published_at": published_at,
                "error": error,
            },
        )

    @staticmethod
    async def count_tiktok_scheduled_per_day(
        db: AsyncSession, tz: str = "UTC"
    ) -> Dict[str, int]:
        result = await db.execute(
            sa_text(
                """
                SELECT TO_CHAR(tiktok_scheduled_at AT TIME ZONE :tz, 'YYYY-MM-DD') AS day, COUNT(*) AS cnt
                FROM generated_clips
                WHERE tiktok_publish_status = 'scheduled' AND tiktok_scheduled_at IS NOT NULL
                GROUP BY day
                """
            ),
            {"tz": tz},
        )
        return {row.day: int(row.cnt) for row in result.fetchall()}

    @staticmethod
    async def tiktok_scheduled_slot_times_per_day(
        db: AsyncSession, tz: str = "UTC"
    ) -> Dict[str, list]:
        """Map each local day to the TikTok slot times already used that day."""
        result = await db.execute(
            sa_text(
                """
                SELECT tiktok_scheduled_at
                FROM generated_clips
                WHERE tiktok_publish_status IN ('scheduled', 'published')
                  AND tiktok_scheduled_at IS NOT NULL
                """
            ),
        )
        days: Dict[str, list] = {}
        for row in result.fetchall():
            local = row.tiktok_scheduled_at.astimezone(ZoneInfo(tz))
            days.setdefault(local.date().isoformat(), []).append(
                local.time().replace(tzinfo=None)
            )
        return days

    @staticmethod
    async def list_user_clips_for_tiktok_schedule(
        db: AsyncSession, user_id: str
    ) -> list[Dict[str, Any]]:
        """All completed clips for a user that are not yet scheduled for TikTok.

        Used by the mass-schedule action. Clips that are already published,
        scheduled or already carrying a tiktok_video_id are excluded.
        """
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order, c.tiktok_publish_requested, c.tiktok_publish_status,
                       c.tiktok_scheduled_at, c.tiktok_publish_error, c.tiktok_video_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id
                  AND t.status = 'completed'
                  AND c.file_path IS NOT NULL
                  AND c.tiktok_publish_status NOT IN ('published', 'scheduled')
                  AND c.tiktok_video_id IS NULL
                ORDER BY c.created_at ASC
                """
            ),
            {"user_id": user_id},
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "tiktok_publish_requested": row.tiktok_publish_requested,
                "tiktok_publish_status": row.tiktok_publish_status,
                "tiktok_scheduled_at": row.tiktok_scheduled_at,
                "tiktok_publish_error": row.tiktok_publish_error,
                "tiktok_video_id": row.tiktok_video_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def list_user_clips_for_tiktok_sync(
        db: AsyncSession, user_id: str
    ) -> list[Dict[str, Any]]:
        """All completed clips for a user, used to reconcile with TikTok."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order, c.tiktok_publish_requested, c.tiktok_publish_status,
                       c.tiktok_scheduled_at, c.tiktok_published_at, c.tiktok_publish_error,
                       c.tiktok_video_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id
                  AND t.status = 'completed'
                ORDER BY c.created_at ASC
                """
            ),
            {"user_id": user_id},
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "tiktok_publish_requested": row.tiktok_publish_requested,
                "tiktok_publish_status": row.tiktok_publish_status,
                "tiktok_scheduled_at": row.tiktok_scheduled_at,
                "tiktok_published_at": row.tiktok_published_at,
                "tiktok_publish_error": row.tiktok_publish_error,
                "tiktok_video_id": row.tiktok_video_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def list_user_clips_tiktok_scheduled_for_date(
        db: AsyncSession, user_id: str, tz: str, date: date
    ) -> list[Dict[str, Any]]:
        """Completed clips of a user scheduled to be published on a given local day."""
        result = await db.execute(
            sa_text(
                """
                SELECT c.id, c.task_id, c.filename, c.file_path, c.text, c.hook_title,
                       c.clip_order, c.tiktok_publish_requested, c.tiktok_publish_status,
                       c.tiktok_scheduled_at, c.tiktok_publish_error, c.tiktok_video_id
                FROM generated_clips c
                JOIN tasks t ON t.id = c.task_id
                WHERE t.user_id = :user_id
                  AND t.status = 'completed'
                  AND c.tiktok_publish_status = 'scheduled'
                  AND c.tiktok_scheduled_at IS NOT NULL
                  AND c.tiktok_video_id IS NULL
                  AND (c.tiktok_scheduled_at AT TIME ZONE :tz)::date = :date
                ORDER BY c.tiktok_scheduled_at ASC
                """
            ),
            {"user_id": user_id, "tz": tz, "date": date},
        )
        return [
            {
                "id": row.id,
                "task_id": row.task_id,
                "filename": row.filename,
                "file_path": row.file_path,
                "text": row.text,
                "hook_title": row.hook_title,
                "clip_order": row.clip_order,
                "tiktok_publish_requested": row.tiktok_publish_requested,
                "tiktok_publish_status": row.tiktok_publish_status,
                "tiktok_scheduled_at": row.tiktok_scheduled_at,
                "tiktok_publish_error": row.tiktok_publish_error,
                "tiktok_video_id": row.tiktok_video_id,
            }
            for row in result.fetchall()
        ]

    @staticmethod
    async def list_all_tiktok_video_ids(db: AsyncSession) -> set[str]:
        """All TikTok video ids already recorded across clips (for dedup)."""
        result = await db.execute(
            sa_text(
                """
                SELECT tiktok_video_id FROM generated_clips
                WHERE tiktok_video_id IS NOT NULL
                """
            ),
        )
        return {row.tiktok_video_id for row in result.fetchall()}

    @staticmethod
    async def mark_user_clips_published_from_tiktok_sync(
        db: AsyncSession,
        clip_id: str,
        video_id: str,
        title: str,
    ) -> None:
        """Mark a clip as published because it already exists on TikTok."""
        await db.execute(
            sa_text(
                """
                UPDATE generated_clips
                SET tiktok_publish_status = 'published',
                    tiktok_video_id = :video_id,
                    tiktok_published_at = COALESCE(tiktok_published_at, NOW()),
                    tiktok_publish_requested = TRUE,
                    updated_at = NOW()
                WHERE id = :clip_id
                  AND tiktok_video_id IS NULL
                """
            ),
            {"clip_id": clip_id, "video_id": video_id},
        )
        await db.commit()
