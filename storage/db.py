import sqlite3
import os
from datetime import datetime

class Database:
    def __init__(self, db_path="storage/digestr.db"):
        self.db_path = db_path
        # Ensure the storage directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._init_db()

    def _get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # Allows accessing columns by name
        return conn

    def _init_db(self):
        """Run the schema.sql file if the database is new."""
        schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
        with open(schema_path, "r") as f:
            schema_script = f.read()
        
        with self._get_connection() as conn:
            conn.executescript(schema_script)

    def add_profile(self, username: str, platform: str):
        """Registers a new creator in the system."""
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO profiles (username, platform) VALUES (?, ?)",
                (username.replace("@", ""), platform.lower())
            )

    def is_processed(self, platform_id: str) -> bool:
        """Checks if we've already handled this specific video."""
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT 1 FROM content WHERE platform_id = ?", (platform_id,))
            return cursor.fetchone() is not None

    def mark_processed(self, video_meta, file_path, transcript_source):
        """Saves a successful processing run to the DB."""
        with self._get_connection() as conn:
            # 1. Get the profile ID
            profile = conn.execute(
                "SELECT id FROM profiles WHERE username = ? AND platform = ?",
                (video_meta.creator_username, video_meta.platform)
            ).fetchone()
            
            if not profile: return

            # 2. Insert into content table
            conn.execute(
                """INSERT INTO content 
                   (profile_id, platform_id, url, content_type, posted_at, processed_at, transcript_source, file_path) 
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    profile['id'], video_meta.platform_id, video_meta.url, 
                    video_meta.content_type, video_meta.posted_at, 
                    datetime.now(), transcript_source, file_path
                )
            )

    def get_monitored_profiles(self):
        with self._get_connection() as conn:
            return conn.execute("SELECT * FROM profiles WHERE monitoring_enabled = 1").fetchall()
    

    # ==========================================
    # NEW METHODS FOR PHASE 2 (NLP & CLUSTERING)
    # ==========================================

    def get_content_id_by_platform_id(self, platform_id: str):
        """Retrieves the internal primary key ID for a specific video platform ID."""
        with self._get_connection() as conn:
            row = conn.execute("SELECT id FROM content WHERE platform_id = ?", (platform_id,)).fetchone()
            return row['id'] if row else None

    def save_processed_transcript(self, content_id: int, text_for_llm: str, text_for_math: str):
        """Saves both the LLM-friendly and Math-friendly versions of a transcript."""
        with self._get_connection() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO processed_transcripts 
                   (content_id, text_for_llm, text_for_math) 
                   VALUES (?, ?, ?)""",
                (content_id, text_for_llm, text_for_math)
            )

    def get_unprocessed_transcripts(self, username: str):
        """Fetches videos that have been mined but not yet cleaned/processed for NLP."""
        with self._get_connection() as conn:
            return conn.execute(
                """SELECT c.id, c.platform_id, c.file_path 
                   FROM content c
                   JOIN profiles p ON c.profile_id = p.id
                   LEFT JOIN processed_transcripts pt ON c.id = pt.content_id
                   WHERE p.username = ? AND pt.id IS NULL""",
                (username.replace("@", ""),)
            ).fetchall()

db = Database()