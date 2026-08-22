ALTER TABLE generated_clips
    ADD COLUMN IF NOT EXISTS tiktok_video_id VARCHAR(255);
