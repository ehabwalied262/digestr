-- storage/schema.sql

CREATE TABLE IF NOT EXISTS profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    platform TEXT NOT NULL,        -- instagram, tiktok, youtube
    total_posts INTEGER,
    last_scanned_at DATETIME,
    newest_post_date DATETIME,     -- This is our "cursor" for deduplication
    monitoring_enabled BOOLEAN DEFAULT 1,
    UNIQUE(username, platform)
);

CREATE TABLE IF NOT EXISTS content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id),
    platform_id TEXT NOT NULL,     -- The shortcode/ID from the platform
    url TEXT,
    content_type TEXT,             -- reel, video
    posted_at DATETIME,
    discovered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    processed_at DATETIME,
    transcript_source TEXT,        -- native_caption, supadata_ai
    file_path TEXT,                -- Path to the generated .md file
    UNIQUE(platform_id)
);

-- ==========================================
-- PHASE 2: NLP & CLUSTERING TABLES
-- ==========================================

-- Table to store discovered topics (clusters)
CREATE TABLE IF NOT EXISTS clusters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id INTEGER REFERENCES profiles(id),
    topic_name TEXT,
    video_count INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Table to store processed versions of transcripts
CREATE TABLE IF NOT EXISTS processed_transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER REFERENCES content(id) UNIQUE, -- Link to original video
    text_for_llm TEXT,                                -- Clean text with fillers (for Groq)
    text_for_math TEXT,                               -- Stripped text (for Vectorization/Math)
    cluster_id INTEGER REFERENCES clusters(id)        -- Assigned during Step 3
);