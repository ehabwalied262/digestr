from dataclasses import dataclass
from datetime import datetime

@dataclass
class VideoMeta:
    platform: str          # "instagram" | "tiktok" | "youtube" | "twitter"
    platform_id: str       # Platform's internal ID for this content
    url: str               # Direct URL to the content
    creator_username: str  # @handle without the @
    posted_at: datetime    # When the creator posted it (UTC)
    content_type: str      # "reel" | "video" | "carousel" | "photo" | "story"
    language: str          # ISO 639-1 code: "en", "ar", "fr". Default "en"
    duration_seconds: int | None  # Video duration if available, None if unknown
    caption_text: str | None      # Platform caption/description text if available

@dataclass
class TranscriptSegment:
    text: str
    start_seconds: float
    end_seconds: float

@dataclass
class Transcript:
    video_meta: VideoMeta        # Pass-through from previous stage
    text: str                    # Full transcript text, cleaned
    segments: list[TranscriptSegment] | None  # Timestamped segments if available
    source: str                  # "native_caption" | "supadata_ai" | "whisper"
    language_detected: str       # Actual language detected in the audio/captions
    confidence: float | None     # Transcription confidence 0.0-1.0, None if unavailable

@dataclass
class Summary:
    video_meta: VideoMeta        # Pass-through
    transcript: Transcript       # Pass-through
    summary_text: str            # 2-4 paragraph prose summary
    topics: list[str]            # Extracted topic tags, lowercase, hyphenated
    key_claims: list[str]        # Specific claims made in the video
    people_mentioned: list[str]  # Names of people referenced
    markdown: str                # Complete .md file content (YAML frontmatter + body)
    file_path: str               # Where the .md file should be saved
    products_mentioned: list[str] # <-- NEW
    action_items: list[str]       # <-- NEW
    sentiment: str                # <-- NEW

    
@dataclass
class ProfileStats:
    username: str
    platform: str
    total_posts: int
    follower_count: int | None
    bio: str | None
    scanned_at: datetime  # UTC

@dataclass
class SummaryMeta:
    file_path: str
    markdown: str