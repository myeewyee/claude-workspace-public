# Batch Mode

When 2+ URLs are provided, process all of them in parallel:

## Step B-Fetch: Pre-fetch content, classify podcasts, and search YouTube

Before launching subagents, run classification and fetch steps. YouTube URLs don't need pre-fetching (the subagent handles transcription internally).

**Phase 1: Classify and pre-fetch.** Run fetch commands in parallel where possible, with rate-limit awareness. Use a unique prefix per URL (e.g., index number) for content/toc temp files to avoid collisions.

**YouTube rate limiting:** YouTube aggressively rate-limits concurrent requests. For batches with 6+ YouTube URLs in quick mode, stagger caption fetches in groups of 5 with a 3-second pause between groups. The `fetch_captions.py` script has built-in retry with exponential backoff (5s, 10s, 20s), but prevention is better than recovery. For full mode, this is not an issue since transcription happens inside the subagent.

- For each X/Twitter URL: `python ".claude/skills/digest/scripts/fetch_x.py" "<URL>" --date "[YYYY-MM-DD]" --time "[HH:MM]" --content-out "outputs/temp/x_content_N.txt" --toc-out "outputs/temp/x_toc_N.txt"`
- For each Blog/unknown URL: `python ".claude/skills/digest/scripts/fetch_blog.py" "<URL>" --date "[YYYY-MM-DD]" --time "[HH:MM]" --content-out "outputs/temp/blog_content_N.txt" --toc-out "outputs/temp/blog_toc_N.txt"`
- For each smart-classified Podcast URL (classified by vault search or LLM knowledge, NOT by URL pattern): run `fetch_blog.py` without `--content-out`/`--toc-out` — only the JSON stdout is needed for `youtube_ids`. This is faster than a yt-dlp search and returns the exact embedded video ID. Skip this for pattern-matched URLs (Apple Podcasts, Spotify, etc.) — those platform pages don't embed YouTube videos.
- For pattern-matched Podcast URLs (Apple Podcasts, Spotify, etc.): skip fetch_blog.py, go directly to Phase 2.

**Phase 2: YouTube search for podcasts.** After Phase 1 completes:
- Check blog fetch results for `content_type: "podcast"` or `youtube_ids`. Reclassify as Podcast.
- For each podcast URL: if `youtube_ids` are available from fetch_blog.py output (Phase 1 or earlier reclassification), use the first ID directly — skip yt-dlp search.
- For podcast URLs without `youtube_ids`: run YouTube search in parallel:
  ```bash
  yt-dlp --dump-json "ytsearch1:[show_name] [episode_title]" 2>/dev/null
  ```
- Podcast URLs with YouTube match → reclassify as YouTube (with podcast override).
- Podcast URLs without YouTube match → run `fetch_podcast.py` with discovered metadata hints (set Bash timeout to 300000).

If any fetch or search fails, note the error and URL. Don't stop the batch, just skip that URL in the next step.

## Step B-Launch: Launch all subagents in parallel

Send a **single message** with multiple Task tool calls, one per URL. Each subagent gets the prompt from its respective prompt file (see each pipeline's launch step in SKILL.md).

- **YouTube URLs (quick mode, default):** Read prompt from `references/quick-youtube.md`, with pre-fetched caption path and metadata
- **YouTube URLs (full mode):** Read prompt from `references/youtube.md`
- **Podcast→YouTube URLs (podcast with YouTube match):** Read prompt from `references/youtube.md` (always full mode) with podcast routing override (show name, subtype: podcast)
- **X/Twitter article URLs:** Read prompt from `references/x-twitter.md`, with the pre-fetched content and content/toc file paths
- **Blog URLs:** Read prompt from `references/blog.md`, with the pre-fetched content and content/toc file paths
- **Podcast URLs (no YouTube match):** Read prompt from `references/podcast.md`, with the pre-fetched `fetch_podcast.py` JSON and audio path
- **X/Twitter single posts:** No subagent needed. Display inline (Step X-2a format) in the batch summary.

All subagents use `model: "sonnet"`, `subagent_type: "general-purpose"`. Full-mode YouTube and Podcast agents get `max_turns: 15`. Quick-mode YouTube, X/Twitter, and Blog agents get `max_turns: 8`.

## Step B-Verify: Detect and retry silent failures

After all agents return, verify each one produced its output file before reporting. Silent agent failures (agent returns without creating the digest file) are the most dangerous batch failure mode because they're invisible.

**For each agent that returned:**
1. Parse the agent's response for the digest file path (e.g., `outputs/digests/Title.md`)
2. Check if the file exists on disk (Glob or Read)
3. If the file is missing or the agent returned no parseable file path, mark it as a **silent failure**

**For each silent failure:**
- Log: `Silent failure detected: [URL] - agent returned but no digest file created`
- Re-launch a single retry agent for that URL with the same prompt and inputs
- Mark the retry in the batch report

**Do not report the batch as complete until all retries have resolved.** If a retry also fails, report it as FAILED with the URL for manual retry.

## Step B-Report: Batch summary

After all agents return (including any retries from Step B-Verify), display a batch summary:

```
Batch digest: [succeeded]/[total] completed

1. [Type] - [Title] → outputs/digests/Title.md
   - [top headline point from agent]
2. [Type] - [Title] → outputs/digests/Title.md
   - [top headline point from agent]
3. FAILED - [Type] - [error message]. Retry: /digest <URL>
```

For each successful digest, show the type (YouTube/Blog/X), title, file path, and one headline point. For failures, show the error and the URL for easy retry. X/Twitter single posts appear inline (no file).
