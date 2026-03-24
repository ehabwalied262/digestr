# Architecture — Content Intelligence Pipeline

> **Purpose:** This document defines how every module communicates, what data structures flow between them, and the exact contracts each component must fulfill. Any developer or AI model should be able to implement any module in isolation using only this document.

---

## System Overview

The system is a linear pipeline with four stages: **Source → Transcription → Summarization → Delivery**. Each stage is a separate Python module. Stages communicate exclusively through defined data classes — never by sharing state, global variables, or direct imports of internal logic.

```
┌──────────┐    ┌───────────────┐    ┌─────────────┐    ┌──────────┐
│  Source   │───▶│ Transcription │───▶│ Summarizer  │───▶│ Delivery │
│          │    │               │    │             │    │          │
│ VideoMeta │    │  Transcript   │    │ Extractor   │    │ .md file │
│ dataclass │    │  dataclass    │    │ dataclass   │    │ Telegram │
└──────────┘    └───────────────┘    └─────────────┘    └──────────┘
                                                              │
                                                              ▼
                                                        ┌──────────┐
                                                        │  SQLite  │
                                                        │  (state) │
                                                        └──────────┘
```

---

## Data Contracts

These are the exact data structures that flow between modules. Every module accepts and returns these — nothing else.

### VideoMeta (Source → Transcription)

Produced by every source module. Contains everything needed to fetch a transcript.

```python
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
```

**Rules:**
- `platform_id` must be unique per platform. This is the deduplication key.
- `posted_at` must be UTC. Convert from platform-local time at the source level.
- `content_type` of "photo" or "carousel" (with no video) should still be emitted by the source but will be skipped by the pipeline orchestrator — the source does not decide what to skip.
- `language` is the creator's primary language from config, not auto-detected. Detection happens at the transcription layer if needed.

### Transcript (Transcription → Summarizer)

Produced by the transcription layer. Contains the raw text extracted from the video.

```python
@dataclass
class Transcript:
    video_meta: VideoMeta        # Pass-through from previous stage
    text: str                    # Full transcript text, cleaned
    segments: list[TranscriptSegment] | None  # Timestamped segments if available
    source: str                  # "native_caption" | "supadata_ai" | "whisper"
    language_detected: str       # Actual language detected in the audio/captions
    confidence: float | None     # Transcription confidence 0.0-1.0, None if unavailable

@dataclass
class TranscriptSegment:
    text: str
    start_seconds: float
    end_seconds: float
```

**Rules:**
- `text` must be cleaned: no leading/trailing whitespace, no double spaces, no SRT/VTT formatting tags. Just plain text.
- `segments` can be None if the transcription source doesn't provide timestamps (some Supadata native captions don't).
- `source` must accurately reflect which method produced this transcript. This gets stored in the database and is important for quality tracking.
- If `text` is empty or whitespace-only, the transcription layer must raise `TranscriptionError`, not return an empty Transcript.

### Summary (Summarizer → Delivery)

Produced by the Gemini structured extraction step. This is NOT a prose summary — it is a structured intelligence extraction. The LLM's job is to extract searchable, filterable data from the transcript, with a prose summary as just one component.

```python
@dataclass
class Summary:
    video_meta: VideoMeta        # Pass-through
    transcript: Transcript       # Pass-through
    summary_text: str            # 2-4 paragraph prose summary
    topics: list[str]            # Extracted topic tags, lowercase, hyphenated
    key_claims: list[str]        # Specific factual claims made by the creator
    people_mentioned: list[str]  # Names of people referenced
    products_mentioned: list[str]  # Tools, apps, services, books mentioned
    action_items: list[str]      # Actionable advice given ("do X", "try Y")
    sentiment: str               # "positive" | "negative" | "neutral" | "mixed"
    markdown: str                # Complete .md file content (YAML frontmatter + body)
    file_path: str               # Where the .md file should be saved
```

**Rules:**
- `topics` are lowercase, hyphenated: `"content-strategy"`, not `"Content Strategy"`.
- `key_claims` are specific factual assertions the creator stated. Written as the creator stated them, not as opinions about the video. Example: `"Posting 3 times per week is optimal for growth"` not `"The creator talks about posting frequency"`.
- `products_mentioned` captures any tool, app, platform, book, course, or service referenced by name. Example: `["Canva", "ChatGPT", "The 4-Hour Workweek"]`.
- `action_items` are concrete, actionable pieces of advice. Example: `["Create a content calendar for the next 30 days", "Use trending audio in the first 3 seconds"]`. Not vague statements like "be consistent."
- `sentiment` reflects the overall tone of the video: is the creator enthusiastic/optimistic (positive), critical/warning (negative), informational/neutral (neutral), or a mix?
- `markdown` is the fully assembled file content. The delivery layer writes this to disk as-is. The delivery layer does not construct markdown — that's the summarizer's job.
- `file_path` follows the pattern: `output/@{creator_username}/{date}_{slugified-title}.md`

---

## Module Specifications

### Source Modules (`sources/`)

**Interface:** Every source module must implement the `Source` abstract class.

```python
from abc import ABC, abstractmethod

class Source(ABC):
    @abstractmethod
    def get_profile_stats(self, username: str) -> ProfileStats:
        """Fetch total post count and basic profile info.
        Must NOT paginate through all posts — use the profile 
        metadata endpoint only. Should complete in < 5 seconds."""
        ...

    @abstractmethod
    def get_recent_posts(self, username: str, limit: int) -> list[VideoMeta]:
        """Fetch the N most recent posts, newest first.
        Returns ALL content types (including photos/carousels).
        The pipeline orchestrator decides what to skip, not the source."""
        ...

    @abstractmethod
    def get_posts_since(self, username: str, since: datetime) -> list[VideoMeta]:
        """Fetch posts newer than the given timestamp, newest first.
        Stop pagination as soon as we hit a post older than `since`.
        This is the cursor-based reload mechanism."""
        ...

    @abstractmethod
    def get_single_post(self, url: str) -> VideoMeta:
        """Extract metadata from a single post URL.
        Used in Phase 1 single-URL mode."""
        ...

@dataclass
class ProfileStats:
    username: str
    platform: str
    total_posts: int
    follower_count: int | None
    bio: str | None
    scanned_at: datetime  # UTC
```

**Rate limiting:** Each source module is responsible for its own rate limiting. Implement as a minimum delay between requests:
- Instagram: 3 seconds between requests
- TikTok: 2 seconds between requests
- YouTube: 1 second between requests (generous API limits)
- Twitter: Per API tier limits

**Error behavior:**
- Network timeout → retry up to 3 times with 5/15/45 second delays
- 404 (post deleted, profile doesn't exist) → raise `SourceNotFoundError`
- 429 (rate limited) → wait for `Retry-After` header value, or 60 seconds if no header
- Any other HTTP error → raise `SourceError` with status code and message
- Never silently return empty results on error. Always raise.

### Transcription Module (`transcription/`)

**The fallback chain is executed in this exact order. No step is skipped.**

```
Step 1: supadata_client.get_transcript(url, mode="native")
        ├── Success (text returned) → return Transcript(source="native_caption")
        └── Failure (no captions exist) → proceed to Step 2

Step 2: supadata_client.get_transcript(url, mode="auto")
        ├── Success (text returned) → return Transcript(source="supadata_ai")
        └── Failure (API error or empty) → proceed to Step 3

Step 3: whisper_fallback.transcribe(url, language=language)
        ├── Success → return Transcript(source="whisper")
        └── Failure → raise TranscriptionError
```

**When to force-skip to Whisper:** If `language` is `"ar"` AND Step 1 returned a transcript AND the transcript confidence (if available) is below 0.7, discard the Step 1 result and proceed to Step 3 directly. Arabic auto-captions are often low quality. This is the ONLY case where a "successful" step gets overridden.

**Supadata client specifics:**
- API base: `https://api.supadata.ai/v1/transcript`
- Auth: `x-api-key` header
- Parameters: `url` (required), `mode` ("native" | "auto" | "generate"), `text` (true for plain text), `lang` (ISO 639-1)
- Async jobs: Videos > 20 minutes return HTTP 202 with a `job_id`. Poll `GET /v1/jobs/{job_id}` every 2 seconds until status is "completed" or "failed". Timeout after 5 minutes.
- Credit awareness: `native` mode costs 1 credit. `auto`/`generate` costs 2 credits per minute of audio. Log credit usage.

**Whisper fallback specifics:**
- Uses `faster-whisper` library with `large-v3` model
- Process: download audio (yt-dlp → extract audio → temp file) → transcribe → delete temp file
- Always set `language` parameter explicitly. Never rely on auto-detection for Arabic.
- Temp file lifecycle:

```python
import tempfile
import os

with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
    temp_path = f.name
try:
    download_audio(url, temp_path)    # yt-dlp
    transcript = whisper.transcribe(temp_path, language=language)
finally:
    if os.path.exists(temp_path):
        os.unlink(temp_path)          # ALWAYS cleanup
```

**Error behavior:**
- Supadata API returns error → log warning, proceed to next step in chain
- Supadata returns empty text → treat as failure, proceed to next step
- Whisper model not loaded (Phase 1–3) → raise `TranscriptionError` with message "Whisper fallback not available. Install faster-whisper for local transcription."
- All three steps fail → raise `TranscriptionError`. The pipeline logs this and skips the video. It does NOT retry transcription — the video gets flagged as failed in the database and can be retried manually later.

### Summarizer Module (`summarizer/`)

**This is a structured data extractor, not a summarizer.** The LLM's primary job is to extract searchable, filterable intelligence from the transcript. The prose summary is secondary — the structured fields (topics, claims, products, action items, sentiment) are what make the data valuable long-term.

**Gemini API call specifics:**
- Model: `gemini-2.0-flash` (free tier, generous rate limits)
- SDK: `google-generativeai` Python package
- Temperature: 0 (deterministic output for structured extraction)
- Response MIME type: `application/json` when using structured output mode

**Why Gemini over Claude:** Free tier available with generous rate limits. Sufficient quality for structured extraction tasks. Swap to Claude or another provider later by changing only this module — the rest of the pipeline doesn't care which LLM runs here.

**The system prompt (exact prompt to use):**

```
You are a content intelligence extractor. You receive a transcript from a social media video and extract structured data from it.

You MUST respond in the following exact format — YAML frontmatter between --- delimiters, followed by markdown sections. No other output. No preamble. No explanation.

---
topics:
  - topic-one-lowercase-hyphenated
  - topic-two
key_claims:
  - First specific factual claim the creator stated, written as they said it
  - Second specific claim with concrete details (numbers, names, timeframes)
people_mentioned:
  - Full Name
products_mentioned:
  - Tool, app, book, service, or platform mentioned by name
action_items:
  - Specific actionable advice given (concrete, not vague)
  - Another concrete action the viewer could take
sentiment: positive | negative | neutral | mixed
---

## Summary

Write a 2-4 paragraph summary. Focus on:
1. The main argument or thesis
2. Specific strategies, frameworks, or methods shared
3. Any data points, statistics, case studies, or examples
4. What makes this content unique vs generic advice

Be factual and specific. Extract, don't interpret. Write in third person.

## Full Transcript

{transcript_text}
```

**Extraction rules the LLM must follow (enforced in the prompt):**
- `topics`: Extract 2-6 topic tags. Be specific: `"instagram-reels-algorithm"` not `"social-media"`. Lowercase, hyphenated.
- `key_claims`: Only include claims with concrete substance. "You should post consistently" is too vague — skip it. "Posting 3x per week increased my reach by 40%" is a key claim — include it. Aim for 2-5 claims.
- `people_mentioned`: Full names only. Skip vague references like "my friend" or "this guy."
- `products_mentioned`: Named tools, apps, books, courses, platforms. "I use Notion for planning" → include "Notion". Skip generic references like "a scheduling tool."
- `action_items`: Concrete and actionable. "Start batch-creating content every Sunday" is good. "Be more creative" is not. Aim for 1-4 items.
- `sentiment`: One word. Positive = enthusiastic, optimistic, motivational. Negative = critical, warning, cautionary. Neutral = informational, educational, factual. Mixed = contains both positive and negative elements.

**The user message format:**

```
Creator: @{username} ({platform})
Posted: {date}
Language: {language}
Duration: {duration} seconds

Transcript:
{transcript_text}
```

**Post-processing the Gemini response:**
1. Parse the YAML frontmatter between `---` delimiters
2. Validate that `topics`, `key_claims`, `people_mentioned`, `products_mentioned`, and `action_items` are all lists
3. Validate that `sentiment` is one of: "positive", "negative", "neutral", "mixed"
4. If YAML parsing fails → retry the API call once. If it fails again → use empty lists and "neutral" for sentiment, log a warning.
5. Prepend the full file frontmatter (adding fields from VideoMeta that the LLM doesn't generate):

```yaml
---
source: "@creator_handle"
platform: instagram
url: "https://instagram.com/reel/..."
date: 2026-03-19
language: en
duration_seconds: 47
transcript_source: native_caption
topics:
  - instagram-reels-algorithm
  - audience-growth-strategy
key_claims:
  - Posting 3x per week increased reach by 40%
  - Short-form content outperforms long-form for discovery
people_mentioned:
  - Gary Vee
products_mentioned:
  - Canva
  - CapCut
action_items:
  - Create a 30-day content calendar with themed days
  - Use trending audio in the first 3 seconds of every reel
sentiment: positive
---
```

6. Assemble final markdown: frontmatter + LLM's summary section + full transcript section
7. Generate `file_path`: `output/@{username}/{YYYY-MM-DD}_{slug}.md` where `slug` is the first 50 chars of the summary, lowercased, spaces replaced with hyphens, non-alphanumeric removed.

**Error behavior:**
- Gemini API returns error → retry up to 2 times with 10 second delay
- Gemini response doesn't match expected format → retry once, then use raw response wrapped in a basic template
- Gemini API is down for all retries → raise `SummarizerError`. The pipeline logs this. The transcript is NOT lost — it can be re-summarized later since the transcript is cached in the database.
- Gemini rate limit hit (free tier) → wait 60 seconds, retry. If still limited, raise `SummarizerError`.

### Delivery Module (`delivery/`)

**Telegram bot specifics:**
- Library: `python-telegram-bot` (v21+, async)
- Send as a single message with Markdown formatting
- If message exceeds Telegram's 4096 char limit → split into: first message = summary + metadata, second message = "Full transcript available in the .md file"
- Never send the full transcript via Telegram. Summary + key claims + link only.

**File writing:**
- Create directory `output/@{username}/` if it doesn't exist
- Write the `summary.markdown` content to `summary.file_path`
- Use UTF-8 encoding (critical for Arabic content)
- Overwrite if file already exists (idempotent)

**ChromaDB indexing (Phase 5):**
- Collection name: `content_summaries`
- Document: the summary text (not the full transcript — too noisy for retrieval)
- Metadata: all YAML frontmatter fields as a flat dict
- Embedding: use the default ChromaDB embedding function (sentence-transformers)
- Chunk strategy: one document per summary (summaries are short enough to embed whole)

---

## Pipeline Orchestrator (`pipeline.py`)

This is the module that wires everything together. Here is the exact flow:

```python
def process_single_url(url: str) -> Summary:
    """Phase 1 entry point: single URL → .md file"""
    
    # 1. Detect platform from URL
    platform = detect_platform(url)  # raises ValueError if unrecognized
    
    # 2. Get source module
    source = get_source(platform)    # returns Instagram/TikTok/etc Source instance
    
    # 3. Extract metadata
    video_meta = source.get_single_post(url)
    
    # 4. Skip non-video content
    if video_meta.content_type in ("photo", "carousel"):
        raise SkipError(f"Content type '{video_meta.content_type}' has no video to transcribe")
    
    # 5. Get transcript (runs the fallback chain)
    transcript = transcription.get_transcript(
        url=video_meta.url,
        language=video_meta.language
    )
    
    # 6. Summarize
    summary = summarizer.summarize(transcript)
    
    # 7. Write .md file
    write_markdown(summary)
    
    # 8. Return for delivery (Telegram, etc.)
    return summary


def process_profile(username: str, platform: str, mode: str, limit: int = None, since: datetime = None):
    """Phase 2+ entry point: process multiple posts from a profile"""
    
    source = get_source(platform)
    db = Database()
    
    # Get or create profile
    profile = db.get_or_create_profile(username, platform)
    
    # Fetch posts based on mode
    if since:
        posts = source.get_posts_since(username, since)
    elif limit:
        posts = source.get_recent_posts(username, limit)
    else:
        posts = source.get_posts_since(username, profile.newest_post_date)
    
    results = []
    for video_meta in posts:
        # Skip already processed
        if db.is_processed(video_meta.platform_id):
            continue
        
        # Skip non-video content
        if video_meta.content_type in ("photo", "carousel"):
            continue
        
        try:
            transcript = transcription.get_transcript(
                url=video_meta.url,
                language=video_meta.language
            )
            summary = summarizer.summarize(transcript)
            write_markdown(summary)
            db.mark_processed(video_meta, summary.file_path, transcript.source)
            results.append(summary)
        except (TranscriptionError, SummarizerError) as e:
            # Log error, skip this video, continue with next
            logger.error(f"Failed to process {video_meta.url}: {e}")
            db.mark_failed(video_meta, str(e))
            continue
    
    # Update cursor to newest post we've seen
    if posts:
        newest = max(posts, key=lambda p: p.posted_at)
        db.update_cursor(username, platform, newest.posted_at)
    
    return results
```

**Platform detection from URL:**

```python
def detect_platform(url: str) -> str:
    """Detect platform from URL. Raises ValueError if unrecognized."""
    if "instagram.com" in url:
        return "instagram"
    elif "tiktok.com" in url:
        return "tiktok"
    elif "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    elif "twitter.com" in url or "x.com" in url:
        return "twitter"
    else:
        raise ValueError(f"Unrecognized platform URL: {url}")
```

---

## Error Handling Philosophy

**Principle: Never lose data. Never crash the loop. Always log.**

1. **Per-video errors are caught and logged.** If one video in a batch of 10 fails, the other 9 still process. The failed video gets a `failed_at` timestamp and `error_message` in the database. It can be retried later.

2. **Per-profile errors are caught and logged.** If scanning a profile fails (rate limit, network issue), log the error, skip this profile in the current polling cycle, and move to the next creator. The scheduler will retry on the next cycle.

3. **API outages do not crash the process.** If Supadata is down, the fallback chain handles it. If Gemini is down, the transcript is preserved and can be summarized later. If Telegram is down, the .md file is still written to disk — Telegram delivery is best-effort.

4. **The main scheduler loop NEVER exits on exception.** Wrap the entire polling cycle in try/except. Log the exception. Sleep. Try again next cycle.

```python
# In main.py scheduler
def polling_cycle():
    try:
        for profile in db.get_monitored_profiles():
            try:
                results = process_profile(profile.username, profile.platform, mode="monitor")
                for summary in results:
                    try:
                        telegram.send_summary(summary)
                    except TelegramError as e:
                        logger.error(f"Telegram delivery failed: {e}")
                        # .md file already written — delivery is best-effort
            except SourceError as e:
                logger.error(f"Source error for {profile.username}: {e}")
                continue
    except Exception as e:
        logger.critical(f"Unexpected error in polling cycle: {e}", exc_info=True)
        # NEVER re-raise. The scheduler must keep running.
```

5. **Retries use exponential backoff with jitter:**

```python
import random
import time

def retry_with_backoff(fn, max_retries=3, base_delay=5):
    for attempt in range(max_retries):
        try:
            return fn()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 1)
            logger.warning(f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s: {e}")
            time.sleep(delay)
```

---

## Configuration Schema

```yaml
# config.yaml

creators:
  - username: "creator_handle"
    platform: instagram          # instagram | tiktok | youtube | twitter
    language: en                 # ISO 639-1 language code
    monitoring_enabled: true     # whether the scheduler polls this creator

  - username: "arabic_creator"
    platform: tiktok
    language: ar
    monitoring_enabled: true

settings:
  poll_interval_minutes: 45      # how often the scheduler runs
  request_delay_seconds: 3       # minimum delay between source API requests
  supadata_mode: auto            # native | auto | generate
  whisper_enabled: false         # set to true in Phase 4 when whisper is installed
  whisper_model: large-v3        # faster-whisper model name
  llm_provider: gemini           # gemini | claude | openai (swappable)
  output_dir: ./output           # where .md files are written

telegram:
  bot_token: ${TELEGRAM_BOT_TOKEN}   # from .env
  chat_id: ${TELEGRAM_CHAT_ID}       # from .env
  send_full_transcript: false        # never send full transcript, only summary

logging:
  level: INFO                    # DEBUG | INFO | WARNING | ERROR
  file: ./logs/pipeline.log
  max_size_mb: 50
  backup_count: 3
```

**Config loading rules:**
- Values containing `${...}` are resolved from environment variables
- Missing required env vars → raise on startup, not at runtime
- Config is loaded once at startup and passed to modules. Modules never read config directly from disk.

---

## Logging Standards

Every log message follows this format:

```
{timestamp} | {level} | {module} | {message} | {context}
```

Example:
```
2026-03-19T01:49:00Z | INFO  | transcription | Transcript extracted | url=https://instagram.com/reel/ABC source=native_caption chars=1247
2026-03-19T01:49:02Z | ERROR | transcription | Supadata API failed  | url=https://instagram.com/reel/DEF status=429 retry_in=60s
2026-03-19T01:49:05Z | INFO  | extractor     | Structured data extracted | creator=@handle topics=3 claims=4 products=2 actions=3 sentiment=positive
```

**What to log:**
- Every API call (Supadata, Gemini, Telegram) with URL and response status
- Every video processed: URL, transcript source, character count
- Every video skipped: URL, reason (photo, already processed, failed)
- Every error with full context
- Cursor updates: old value → new value
- Polling cycle start/end with duration

**What NOT to log:**
- API keys or tokens (never, even at DEBUG level)
- Full transcript text (too verbose — log character count instead)
- Full API response bodies (log status + relevant fields only)

---

## File Naming Convention

```
output/
└── @creator_username/
    └── {YYYY-MM-DD}_{slug}.md
```

- `slug` = first 50 characters of the video caption or summary title
- Lowercase, spaces → hyphens, strip non-alphanumeric except hyphens
- If slug is empty (no caption), use the platform_id
- If file already exists, overwrite (processing is idempotent)

Example:
```
output/@garyvee/2026-03-19_how-i-grew-to-100k-followers.md
output/@arabic_creator/2026-03-18_نصائح-للتسويق.md
output/@creator/2026-03-15_ABC123DEF.md  (no caption fallback)
```

UTF-8 filenames are fine on Linux. The system runs on Linux only.

---

## Security and Secrets

- All API keys live in `.env` file, loaded via `python-dotenv`
- `.env` is in `.gitignore` — never committed
- A `.env.example` file with placeholder values is committed
- No API keys in config.yaml, logs, or error messages
- Supadata and Gemini API keys have no special permissions — they're standard API tokens. If leaked, the risk is unauthorized usage charges, not data exposure.
- Telegram bot token: if leaked, someone could send messages as your bot. Low risk for a personal tool, but still keep it in `.env`.
