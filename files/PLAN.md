# Content Intelligence Pipeline — Project Plan

> **Last updated:** March 19, 2026
> **Status:** Pre-development — Phase 1 ready to build
> **Author:** [You]

---

## What This Is

An automated pipeline that monitors specific creators across Instagram and TikTok (expandable to YouTube, Twitter/X, LinkedIn later), extracts transcripts from their video content, generates structured summaries using AI, and delivers them to you via Telegram. Over time, it becomes a searchable knowledge base of everything these creators have ever said.

---

## Core Architecture

```
Source Platforms (IG, TikTok, YT, Twitter)
    │
    ▼
Profile Scanner → Stats + Cursor Tracking (SQLite)
    │
    ▼
Supadata API (mode="native" → captions first)
    │ fallback: faster-whisper (local, for Arabic / missing captions)
    │
    ▼
Gemini API (free tier) → Structured .md with YAML frontmatter
    │
    ▼
Delivery: Telegram Bot / ChromaDB RAG / Client Reports
```

**Key design decisions:**

- Caption-first approach: Supadata `mode="native"` extracts existing captions without downloading video or running transcription. Falls back to `mode="auto"` (AI transcription) or local `faster-whisper` for Arabic content or missing captions.
- Cursor-based tracking: We never store all video IDs. We store the timestamp of the newest post seen. On reload, we fetch backward from newest and stop at the cursor. Only processed posts get rows in the database.
- No video/audio storage: Everything is transient. If we ever need to download media (whisper fallback), it goes to `/tmp` and gets deleted immediately after transcription.
- Modular sources: Each platform is a separate module implementing the same interface. Adding a new platform means adding one file, zero changes elsewhere.

---

## Tech Stack

| Component              | Tool                          | Cost          |
|------------------------|-------------------------------|---------------|
| Language               | Python 3.11+                  | Free          |
| Instagram scraping     | Instaloader                   | Free          |
| TikTok scraping        | yt-dlp                        | Free          |
| YouTube scraping       | yt-dlp (later)                | Free          |
| Twitter scraping       | Tweepy + API (later)          | Free tier     |
| Transcript extraction  | Supadata API                  | Free tier → ~$19/mo |
| Whisper fallback       | faster-whisper (large-v3)     | Free (local)  |
| Structured extraction  | Gemini API (gemini-2.0-flash) | Free tier     |
| State tracking         | SQLite                        | Free          |
| Knowledge base (RAG)   | ChromaDB                      | Free          |
| Scheduling             | APScheduler                   | Free          |
| Telegram delivery      | python-telegram-bot           | Free          |
| Server                 | VPS (Hetzner/DigitalOcean)    | $5–10/mo      |

**Estimated running cost:** $5–25/month for monitoring 5–10 creators across 2 platforms (Gemini free tier eliminates LLM costs).

---

## Database Schema

```sql
CREATE TABLE profiles (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    platform TEXT NOT NULL,        -- instagram, tiktok, youtube, twitter
    total_posts INTEGER,
    last_scanned_at DATETIME,
    newest_post_date DATETIME,     -- cursor: only fetch posts newer than this
    monitoring_enabled BOOLEAN DEFAULT 0,
    UNIQUE(username, platform)
);

CREATE TABLE content (
    id INTEGER PRIMARY KEY,
    profile_id INTEGER REFERENCES profiles(id),
    platform_id TEXT NOT NULL,     -- platform's internal ID for this post
    url TEXT,
    content_type TEXT,             -- reel, video, carousel, photo
    posted_at DATETIME,
    discovered_at DATETIME,
    processed_at DATETIME,
    transcript_source TEXT,        -- native_caption, supadata_ai, whisper
    transcript_path TEXT,          -- path to generated .md file
    UNIQUE(platform_id)
);
```

Only processed posts get rows in `content`. The cursor (`newest_post_date`) handles everything else.

---

## Output Format (.md files)

Every processed video produces a structured intelligence file, not just a summary. The YAML frontmatter is the primary value — it makes every file searchable, filterable, and queryable in the RAG knowledge base.

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

## Summary

The creator argues that short-form video remains the highest-ROI
content format in 2026, sharing specific metrics from their
own account showing a 40% reach increase after switching to
a 3x/week posting cadence...

## Full Transcript

[Timestamped transcript text here]
```

The structured fields are extracted by the Gemini API using a strict extraction prompt (see ARCHITECTURE.md for the exact prompt). The prose summary is secondary — the structured data is what makes this system valuable over time.

---

## File System Layout

```
content-pipeline/
├── config.yaml              ← Creator profiles + settings
├── main.py                  ← Entry point, scheduler
├── pipeline.py              ← URL → transcript → summary → .md
│
├── sources/
│   ├── base.py              ← Abstract source interface
│   ├── instagram.py         ← Instaloader wrapper
│   ├── tiktok.py            ← yt-dlp for TikTok
│   ├── youtube.py           ← (Phase 5+)
│   └── twitter.py           ← (Phase 5+)
│
├── transcription/
│   ├── supadata_client.py   ← Supadata API (primary)
│   └── whisper_fallback.py  ← faster-whisper (Phase 4)
│
├── summarizer/
│   └── gemini_extractor.py  ← Gemini API → structured extraction → .md
│
├── delivery/
│   ├── telegram_bot.py      ← Telegram notifications
│   └── rag_indexer.py       ← ChromaDB indexing (Phase 5)
│
├── storage/
│   ├── db.py                ← SQLite operations
│   └── schema.sql           ← Table definitions
│
├── output/                  ← Generated .md files
│   └── @creator/
│       └── 2026-03-19_video-title.md
│
├── requirements.txt
├── .env                     ← API keys (never committed)
└── README.md
```

---

## Phase Plan

---

### Phase 1 — Single URL Pipeline (2–3 days)

**Goal:** Given one Instagram Reel or TikTok URL, produce one structured `.md` file.

**What we build:**
- `pipeline.py` — Orchestrator: takes a URL, runs it through the full chain
- `sources/base.py` — Abstract `Source` class with the interface all platforms implement
- `sources/instagram.py` — Extract metadata (creator, date, type) from an IG reel URL
- `sources/tiktok.py` — Extract metadata from a TikTok URL
- `transcription/supadata_client.py` — Call Supadata API, try `native` first, fall back to `auto`
- `summarizer/gemini_extractor.py` — Send transcript to Gemini with structured extraction prompt, extract topics/claims/products/actions/sentiment, output YAML + markdown
- `.env` template — Supadata API key, Gemini API key placeholders
- `requirements.txt` — All dependencies pinned

**What we do NOT build yet:**
- No database (state is not needed for single URLs)
- No scheduling
- No Telegram delivery
- No Whisper fallback
- No profile scanning

**How to run:**
```bash
python pipeline.py "https://www.instagram.com/reel/ABC123/"
# → outputs: output/@creator/2026-03-19_video-title.md
```

**Done when:** You paste any public IG Reel or TikTok URL and get a readable, structured `.md` file with accurate transcript and structured intelligence extraction. Test with at least 5 URLs across both platforms, including one Arabic video.

**Validation checklist:**
- [ ] English IG Reel → correct transcript and structured extraction
- [ ] English TikTok → correct transcript and structured extraction
- [ ] Arabic IG Reel → transcript extracted (quality may vary)
- [ ] Video with no captions → Supadata `auto` fallback works
- [ ] Output .md has valid YAML frontmatter
- [ ] Output .md has topics, key_claims, products_mentioned, action_items, and sentiment extracted
- [ ] key_claims are specific (contain numbers/names/details), not vague
- [ ] products_mentioned captures named tools/apps/books, not generic references
- [ ] action_items are concrete and actionable, not vague advice
- [ ] sentiment field is one of: positive, negative, neutral, mixed
- [ ] File saved in correct directory structure

---

### Phase 2 — Profile Scanner + Registry (3–4 days)

**Goal:** Add a creator by username, see their profile stats, choose what to process, track progress with cursor-based deduplication.

**What we build:**
- `storage/schema.sql` — profiles and content tables
- `storage/db.py` — SQLite wrapper (add profile, update cursor, check if processed, get stats)
- Profile scanning in `sources/instagram.py` — Fetch total post count, scan recent posts
- Profile scanning in `sources/tiktok.py` — Same for TikTok
- `config.yaml` — Creator list with platform and language settings
- CLI commands in `pipeline.py`:
  - `python pipeline.py add @username instagram` — Scan and register profile
  - `python pipeline.py status @username` — Show stats and processing progress
  - `python pipeline.py process @username --latest 10` — Process N most recent posts
  - `python pipeline.py process @username --since 2026-01-01` — Process from date
  - `python pipeline.py reload @username` — Re-scan, show new posts since cursor

**The user interaction flow:**
```
$ python pipeline.py add @creator instagram

Scanning @creator...
┌──────────────────────────────┐
│ @creator                     │
│ 847 posts total              │
│                              │
│ Scanned: Mar 19, 2026 1:49AM │
│ Processed: 0                 │
└──────────────────────────────┘

$ python pipeline.py process @creator --latest 10

Found 10 posts. Processing...
✓ Reel  - "How I grew to 100k" (Mar 18)
✓ Reel  - "Morning routine tips" (Mar 15)
⊘ Photo - skipped (no video content)
✓ Reel  - "Why most people fail" (Mar 12)
...
8 transcripts generated. Cursor set to Mar 18, 2026.

$ python pipeline.py reload @creator

2 new posts since Mar 18. Process them? [y/n]
```

**Database behavior:**
- `add` stores the profile with total_posts, sets `newest_post_date` to now
- `process --latest N` fetches N most recent posts, processes videos, stores only processed ones in `content`, updates cursor
- `reload` fetches posts from newest backward, stops at cursor, reports the delta
- Posts already in `content` table are skipped automatically (dedup by `platform_id`)

**Done when:** You can add 5+ creators, see their stats, process selected videos, reload to find new content, and never reprocess the same video twice.

**Validation checklist:**
- [ ] `add` correctly fetches and stores profile stats
- [ ] `process --latest N` processes only video content, skips photos
- [ ] `reload` correctly identifies new posts since last cursor
- [ ] Duplicate processing never happens (platform_id uniqueness)
- [ ] `status` shows accurate processed/total counts
- [ ] Works for both Instagram and TikTok profiles
- [ ] Rate limiting respected (2–5 second delays between requests)

---

### Phase 3 — Automated Monitoring + Telegram (3–4 days)

**Goal:** The system runs unattended on a schedule, processes new content from all monitored creators, and sends summaries to your Telegram.

**What we build:**
- `main.py` — Entry point with APScheduler, loads config, runs polling loop
- `delivery/telegram_bot.py` — Send `.md` content as formatted Telegram messages
- Telegram bot setup (BotFather token, chat ID)
- `config.yaml` additions: `poll_interval_minutes`, `telegram_chat_id`, `telegram_bot_token`
- Systemd service file (`content-pipeline.service`) for deployment
- Logging (structured, to both console and file)

**Scheduling logic:**
- APScheduler runs every N minutes (configurable, default 45)
- For each creator with `monitoring_enabled: true`:
  1. Scan profile for new posts (cursor-based)
  2. If new video posts found → process through pipeline
  3. Send each summary to Telegram
  4. Update cursor
- If no new posts → log silently, do nothing

**Telegram message format:**
```
📌 New from @creator (Instagram)
📅 Mar 19, 2026

**Summary:**
The creator discusses three strategies for...

**Key claims:**
• Short-form > long-form for reach
• Consistency > frequency

**Topics:** #content-strategy #growth

🔗 [Original post](https://instagram.com/reel/...)
```

**Deployment:**
```bash
# On VPS
git clone <repo>
cd content-pipeline
pip install -r requirements.txt
cp .env.example .env  # fill in API keys
sudo cp content-pipeline.service /etc/systemd/system/
sudo systemctl enable content-pipeline
sudo systemctl start content-pipeline
```

**Done when:** You start the service, walk away, and come back to Telegram messages for every new video your tracked creators posted.

**Validation checklist:**
- [ ] Scheduler runs at correct intervals
- [ ] Only new posts (post-cursor) get processed
- [ ] Telegram messages arrive with correct formatting
- [ ] Service auto-restarts on crash (systemd)
- [ ] Service starts on server boot
- [ ] Logs capture errors without crashing the loop
- [ ] Multiple creators polled in sequence with rate limiting
- [ ] No duplicate Telegram messages for same video

---

### Phase 4 — Hardening + Whisper Fallback (3–4 days)

**Goal:** Make the system reliable for unattended operation and improve Arabic transcript quality.

**What we build:**
- `transcription/whisper_fallback.py` — Local `faster-whisper` with `large-v3` model
- Fallback logic in pipeline: Supadata native → Supadata auto → Whisper local
- Arabic-specific handling: force `--language ar` in Whisper, post-process dialect cleanup in Gemini prompt
- Retry logic with exponential backoff for all API calls (Supadata, Gemini, Telegram)
- Error handling: catch and log failures per-video without stopping the batch
- Health check endpoint or Telegram `/status` command
- Temp file cleanup: try/finally blocks ensuring no media files persist on disk
- Rate limit awareness: per-platform delays, backoff on 429 responses

**Whisper integration logic:**
```python
async def get_transcript(url, language):
    # Step 1: Try Supadata native captions
    result = supadata.transcript(url=url, mode="native")
    if result and result.content:
        return result.content, "native_caption"
    
    # Step 2: Try Supadata AI transcription
    result = supadata.transcript(url=url, mode="auto")
    if result and result.content:
        return result.content, "supadata_ai"
    
    # Step 3: Local Whisper fallback (especially for Arabic)
    if language == "ar" or not result:
        audio_path = download_audio(url)  # temp file
        try:
            transcript = whisper_transcribe(audio_path, language=language)
            return transcript, "whisper"
        finally:
            os.unlink(audio_path)  # always cleanup
```

**Server requirements change:** If using Whisper locally, the VPS needs at least 4GB RAM (8GB preferred for large-v3). Cost goes from $5/mo to ~$12/mo.

**Done when:** The system runs unattended for 7+ days without silent failures, handles Arabic content well, and recovers gracefully from API outages.

**Validation checklist:**
- [ ] Whisper fallback activates when Supadata returns no transcript
- [ ] Arabic content gets better transcription via Whisper large-v3
- [ ] API failures don't crash the polling loop
- [ ] Retries work with exponential backoff
- [ ] No temp files left on disk after processing (check /tmp)
- [ ] `/status` command in Telegram shows system health
- [ ] System survives Supadata downtime gracefully
- [ ] System survives Gemini API downtime gracefully
- [ ] 7-day unattended run with zero manual intervention needed

---

### Phase 5 — RAG Knowledge Base + Querying (5–7 days)

**Goal:** All processed summaries become searchable via semantic search. You can ask questions across your entire creator archive.

**What we build:**
- `delivery/rag_indexer.py` — Index `.md` files into ChromaDB on creation
- Embedding generation (using Gemini or a local model)
- Telegram `/ask` command: type a question, get an answer with citations
- Weekly digest generation: summarize themes across all creators for the past 7 days
- Telegram `/digest` command: trigger a weekly summary on demand

**How RAG works in this system:**
1. Every `.md` file gets chunked (by section: summary, transcript paragraphs)
2. Each chunk gets embedded (vector representation of its meaning)
3. Chunks stored in ChromaDB with metadata (creator, date, platform, topics)
4. When you ask a question:
   - Your question gets embedded
   - ChromaDB finds the 5–10 most semantically similar chunks
   - Those chunks + your question go to Gemini
   - Gemini synthesizes an answer with citations: "According to @creator on Mar 15..."

**Telegram interaction:**
```
You: /ask what do my creators say about pricing digital courses?

Bot: Based on 8 relevant posts from 3 creators:

@creator_a (Mar 15): Recommends tiered pricing starting 
at $47 for entry-level, scaling to $497 for premium...

@creator_b (Feb 28): Argues against low-price courses, 
says anything under $200 signals low value...

@creator_c (Mar 10): Suggests a free → paid funnel where 
the free course builds trust for a $997 upsell...

Key consensus: All three agree that pricing below $100 
hurts perceived value. Divergence on whether free tiers 
help or cannibalize paid offerings.
```

**Weekly digest:**
```
You: /digest

Bot: 📊 Weekly Digest (Mar 12–19, 2026)
Processed: 23 new videos from 8 creators

Top themes this week:
1. AI tools for content creation (mentioned by 5/8 creators)
2. Instagram algorithm changes (4/8)
3. Email list building strategies (3/8)

Notable claims:
• @creator_a: "Instagram reach dropped 40% for accounts 
  not using Reels in March"
• @creator_b: Contradicts — says reach is stable if you 
  post consistently

Full summaries available via /ask
```

**Done when:** You can ask natural language questions about anything your creators have said, and get accurate, cited answers.

**Validation checklist:**
- [ ] All new .md files auto-indexed in ChromaDB
- [ ] `/ask` returns relevant results with correct citations
- [ ] Semantic search works across creators and platforms
- [ ] `/digest` generates coherent weekly summary
- [ ] Metadata filters work (search within one creator, one platform, date range)
- [ ] ChromaDB persists across restarts
- [ ] Index handles 500+ documents without performance issues

---

## Future Phases (Not Planned Yet)

These are ideas validated during planning. Build them only after Phase 5 is solid and you have real usage patterns.

**Phase 6 — YouTube + Twitter sources:** Add `sources/youtube.py` and `sources/twitter.py`. YouTube is easy (yt-dlp, auto-captions). Twitter requires API access and is text-focused.

**Phase 7 — Competitive Intelligence mode:** Different summarization prompts focused on strategy extraction, positioning, pricing. Weekly comparative digests across competitors. This is the first sellable service.

**Phase 8 — Topic Monitoring (Scout mode):** Discovery-based monitoring. Search by topic/hashtag across platforms. Find creators you don't already follow. Hardest mode technically.

**Phase 9 — Client-Facing Service:** Multi-user support, onboarding flow, billing, client dashboards. This is product territory.

**Phase 10 — LinkedIn:** Hardest platform. Official API is limited, scraping is risky. Add only if client demand justifies the effort.

---

## Monetization Path

**Month 1:** Build Phases 1–3. Use it yourself daily. You're your own first customer.

**Month 2:** Offer free 2-week trials to 3–5 creators or small agencies. "I'll monitor your competitors and deliver weekly briefings." This validates demand.

**Month 3:** Start charging. $500–2,000/month retainer depending on scope. Simultaneously list on Upwork as "AI Automation Specialist" with portfolio showing the pipeline.

**Freelance positioning:** The skills built here (RAG pipelines, social media intelligence, AI automation) map directly to high-paying freelance categories: "AI Automation Specialist" ($2K–10K/project), "RAG/Knowledge Base Developer" ($5K–20K), "Content Intelligence Consultant" ($500–2K/month retainer).

---

## Common Traps to Avoid

1. **Don't build the scheduler before the pipeline works.** If video → .md doesn't work, nothing else matters.
2. **Don't use Selenium/Playwright for scraping.** Instaloader and yt-dlp use internal APIs, which are far more stable than browser automation.
3. **Don't log into Instagram for public data.** Unnecessary risk. Stay anonymous.
4. **Don't over-engineer storage.** SQLite + folders of .md files. No Postgres, no Redis, no S3 until proven necessary.
5. **Don't ignore rate limits.** 2–5 second delays between requests. Respect 429 responses. Rotate across creators.
6. **Don't store video or audio.** Extract transcript, delete media immediately. Always use try/finally for cleanup.
7. **Don't build a monolith.** Separate modules per concern. When Instagram changes something, you swap one file.
8. **Don't skip the Arabic quality check.** Platform auto-captions for Arabic dialects are unreliable. Test early, add Whisper fallback if needed.
9. **Don't try to build all three monitoring modes simultaneously.** Start with creator tracking. Add competitive intel when you have a client. Add topic monitoring when you have demand.
10. **Don't spend 3 months building in isolation.** Ship Phase 3 (working + automated), show it to people, charge early, iterate based on what people actually pay for.

---

## Dependencies

```txt
# requirements.txt
instaloader>=4.10
yt-dlp>=2024.01
supadata>=1.6
google-generativeai>=0.8
faster-whisper>=1.0      # Phase 4 only
chromadb>=0.4            # Phase 5 only
python-telegram-bot>=21
apscheduler>=3.10
python-dotenv>=1.0
```

---

## Environment Variables

```bash
# .env
SUPADATA_API_KEY=your_key_here
GEMINI_API_KEY=your_key_here
TELEGRAM_BOT_TOKEN=your_token_here
TELEGRAM_CHAT_ID=your_chat_id_here
```

---

## How to Start

1. Read this plan fully
2. Set up a Python 3.11+ environment
3. Get API keys: Supadata (free tier), Gemini (free tier via Google AI Studio), Telegram (BotFather)
4. Build Phase 1
5. Test with 5 URLs (3 English, 2 Arabic) across Instagram and TikTok
6. If Phase 1 passes all validation checks → proceed to Phase 2
7. Never skip a phase. Never start the next phase until the current one's checklist is complete.
