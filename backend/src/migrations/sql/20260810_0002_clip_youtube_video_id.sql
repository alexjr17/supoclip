ALTER TABLE generated_clips
    ADD COLUMN IF NOT EXISTS youtube_video_id VARCHAR(255);
