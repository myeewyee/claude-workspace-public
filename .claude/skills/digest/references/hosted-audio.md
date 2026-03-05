# Hosted Audio Path

### Step HA-0: Search for YouTube version

Before downloading podcast audio, check if a YouTube version exists. YouTube versions are preferred because they have cleaner audio (no ad breaks) and often include creator-curated chapter timestamps.

**Discovery methods (try in order):**

1. **Page HTML**: Many podcast show notes pages embed the YouTube video directly — fetching the page is faster than a yt-dlp search and returns the exact video ID.
   - If `fetch_blog.py` already ran (URL was reclassified from blog path): check its JSON for `youtube_ids`. If present, use the first ID.
   - If this is a smart-classified URL (classified by vault search or LLM knowledge, not a platform pattern match): run `fetch_blog.py` now to check for embedded YouTube IDs and chapters:
     ```bash
     python ".claude/skills/digest/scripts/fetch_blog.py" "<URL>" --date "[YYYY-MM-DD]" --time "[HH:MM]"
     ```
     Check the JSON for `youtube_ids`. If present, use the first ID. Also save `podcast.chapters` as `show_notes_chapters` if present (used in Step HA-1 when YouTube is not found).
   - Skip this step for pattern-matched platform URLs (Apple Podcasts, Spotify, etc.) — those pages don't embed YouTube videos.

2. **YouTube search**: If no `youtube_ids` were found in step 1. Extract the show name and episode title from available context (user's message, `fetch_blog.py` metadata, or vault knowledge). Run:
```bash
yt-dlp --dump-json "ytsearch1:[show_name] [episode_title]" 2>/dev/null
```
Set Bash timeout to 30000. Parse the JSON output. Save: `id`, `title`, `duration`, `chapters`, `channel`.

3. **Validate the match**: The YouTube video title should share key terms with the podcast episode (guest name, topic, episode number). Duration should be >10 minutes (a real podcast episode, not a clip). If validation fails, treat as no match.

**For YouTube video IDs from page HTML** (method 1), validate by fetching metadata:
```bash
yt-dlp --dump-json "https://www.youtube.com/watch?v=[video_id]" 2>/dev/null
```
Parse the JSON. Save the same fields as method 2.

**Routing decision:**
- **YouTube found** → Route to **YouTube pipeline** (Step 2) with URL `https://www.youtube.com/watch?v=[id]`. Pass podcast context to the agent: show name (for `author:` frontmatter) and `subtype: podcast` override. See "Podcast routing override" in `references/youtube.md`.
- **No YouTube found** → Continue to **Hosted audio path** (Step HA-1) as before.

### Step HA-1: Fetch podcast metadata and audio

**For direct podcast URLs** (detected by URL pattern in Step 1.5):

```bash
python ".claude/skills/digest/scripts/fetch_podcast.py" "<URL>" --date "[YYYY-MM-DD]" --time "[HH:MM]"
```

**For podcast URLs reclassified from blog fetch** (content_type: "podcast" in fetch_blog.py JSON):

Pass whatever hints were discovered by `fetch_blog.py` in the `podcast` object:

```bash
python ".claude/skills/digest/scripts/fetch_podcast.py" "<URL>" --rss "[rss_url]" --audio-url "[audio_url]" --show-name "[show_name]" --episode-title "[episode_title]" --date "[YYYY-MM-DD]" --time "[HH:MM]"
```

Only include flags for hints that were actually discovered (don't pass empty strings). If `show_notes_chapters` was saved from the `podcast.chapters` field, add `--chapters '[show_notes_chapters_json]'` too.

Set Bash timeout to 300000 (5 min for audio download).

Parse the JSON output. If it contains `"error"`, report the error to the user and stop.

Save from the JSON: `title`, `show_name`, `safe_title`, `safe_show`, `published`, `duration`, `duration_seconds`, `image`, `url`, `audio_path`, `episode_url`, `rss_url`. Also save `chapters` and `chapters_source` if present.

### Step HA-2: Launch podcast digest agent

Read prompt from `references/audio.md`. Fill in `[bracketed]` values from JSON. Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 15`. Report per **Reporting** section below.
