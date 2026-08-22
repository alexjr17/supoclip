-- Publishing profiles: a user can own multiple channels, each with its own
-- connected YouTube/TikTok accounts.
CREATE TABLE IF NOT EXISTS profiles (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_profiles_user_id ON profiles (user_id);

-- Connected platform accounts, scoped to a profile.
CREATE TABLE IF NOT EXISTS connected_accounts (
    id VARCHAR(36) PRIMARY KEY,
    profile_id VARCHAR(36) NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
    platform VARCHAR(20) NOT NULL,
    token_data TEXT NOT NULL,
    display_data TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_connected_accounts_profile_platform UNIQUE (profile_id, platform)
);

CREATE INDEX IF NOT EXISTS idx_connected_accounts_profile_id ON connected_accounts (profile_id);

-- Track which profile a clip was marked for publishing with, so the scheduler
-- uploads to the right channel.
ALTER TABLE generated_clips
    ADD COLUMN IF NOT EXISTS publish_profile_id VARCHAR(36) REFERENCES profiles(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_generated_clips_publish_profile_id ON generated_clips (publish_profile_id);
