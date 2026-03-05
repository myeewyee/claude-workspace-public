---
name: digest
description: "Process content from YouTube, X/Twitter, blog/article, or podcast URLs into digestible key takeaways. Usage: /digest [full] <URL> [URL2] [URL3]. Quick mode is the default (auto-captions + transcript with chapter headings). Add 'full' for Whisper transcription + diarization. Supports YouTube, X/Twitter (articles, threads, single posts via fxtwitter API), blog/article pages (trafilatura extraction), and podcast episodes (RSS/embedded audio discovery). Multiple URLs processed in parallel."
---

# Digest: Content Triage

## Usage

`/digest [full] <URL> [URL2] [URL3] ...`

Produces content digests from YouTube videos, X/Twitter posts, blog/article pages, or podcast episodes. Designed for quick content triage: "Is this worth my time?" Accepts one or more URLs (space or newline separated).

**Architecture:** SKILL.md is the routing file: mode detection, URL classification, path dispatch, and shared reporting. Agent prompts, reference material, and extended procedures live in `references/`. Pipeline sections contain only dispatch instructions.

**Quick mode is the default.** Uses YouTube auto-captions instead of Whisper transcription, skips diarization. Produces frontmatter + Key Takeaways + auto-caption transcript with chapter headings (searchable but unformatted, no speaker labels). For podcasts, uses show notes with Whisper fallback if content is thin. ~45-60s end-to-end per item vs ~50-90s for full mode (difference is mainly Whisper transcription time).

**Full mode** (`full`): Higher fidelity. Whisper transcription, speaker diarization (when multi-speaker), formatted transcript with chapter headings. Use when you need polished output or accurate speaker attribution.

**Prerequisites, error handling, and file lifecycle:** See `references/reference.md`.

## Pipeline

### Step 0: Detect mode

Quick mode is the default. Check if the user's input contains `full` or `--full` (as a standalone word, anywhere in the message). If present:
- Set `FULL_MODE = true`
- Strip `full` / `--full` from the input before extracting URLs
- After URL classification (Step 1.5), route to full pipeline steps

If neither `full` nor `--full` is present, use quick mode. Route to quick-mode steps after URL classification.

Legacy: `--quick` is still accepted (strip it; quick mode is already the default).

Also check for `force` or `--force` (standalone word). If present:
- Set `FORCE_MODE = true`
- Strip `force` / `--force` from the input before extracting URLs

If neither is present, `FORCE_MODE = false`.

### Step 1: Get the date and time

Run `date "+%Y-%m-%d %H:%M %s"`. You need the date and time for the agent prompt's `created` frontmatter field. Save the epoch seconds (third value) as `T_START` for the run log.

### Step 1.5: Classify URLs

Extract all URLs from the user's input (split on whitespace/newlines). For each URL, classify:

**Deterministic (check first):**
- Contains `youtube.com/channel/`, `youtube.com/@`, or `youtube.com/c/` (no `/watch` or video ID in URL): **YouTube channel** → Step CH-1
- Contains `youtube.com` or `youtu.be`: **YouTube** → Step 2
- Contains `twitter.com` or `x.com`: **X/Twitter** → Step X-1
- Matches known podcast platform URL: **Podcast** → Step HA-0

**Known podcast platform URL patterns** (check domain/path):
`podcasts.apple.com`, `open.spotify.com/episode`, `open.spotify.com/show`, `*.buzzsprout.com`, `play.libsyn.com`, `*.podbean.com`, `share.transistor.fm`, `*.simplecast.com`, `player.megaphone.fm`, `play.acast.com`, `*.spreaker.com`, `overcast.fm`, `pca.st`

**Smart classification (everything else):**
For URLs that don't match the patterns above, determine the content type using your judgment:

1. **Extract identifiers** from the URL and user's message: domain name, path keywords, show/episode names the user included (podcast players often share names alongside URLs).
2. **Vault search**: `vault_search` for the show or site name (e.g., "Modern Wisdom", "Peter Attia", "Unchained"). If existing notes have `subtype: podcast`, classify as **Podcast**. If existing notes have `subtype: article`, classify as **Blog/article**. This is the fastest path for recurring shows.
3. **LLM knowledge**: If you recognize the site or show as a podcast from general knowledge (e.g., `peterattiamd.com` is Peter Attia's podcast site), classify as **Podcast**.
4. **If still unsure**: Run `fetch_blog.py` (Step B-1). Check the JSON output:
   - `content_type: "podcast"` → reclassify as **Podcast** (use metadata from the `podcast` object)
   - `youtube_ids` in the output → note these for Step P-0
   - Otherwise → **Blog/article**

**Podcast** → Step HA-0 (search for YouTube version first)
**Blog/article** → Step B-1 (fetch_blog.py)

**If single URL:** Follow the corresponding path directly.
**If multiple URLs:** Read `references/batch.md` and follow the batch workflow.

### Step 1.7: Duplicate check

Read `references/duplicate-check.md` and follow the procedure. If all URLs are skipped, stop. Otherwise continue with remaining URLs.

## YouTube Channel Path

### Step CH-1: Browse channel videos

```bash
python ".scripts/youtube-browse.py" "<channel_url_or_handle>"
```

Parse the JSON output. Present to the user as a numbered list:

```
Channel: [channel.title] ([channel.subscriber_count] subscribers, [channel.video_count] videos)

 #  | Title                                              | Date       | Views   | Duration
----+----------------------------------------------------+------------+---------+---------
 1. | [title]                                            | [date]     | [views] | [dur]
```

Wait for the user to pick video numbers or give other instructions (the list is a general-purpose tool, not just for digesting). When videos are selected for digesting, extract the corresponding URLs and proceed with the normal YouTube path (Step 2) for each. If multiple videos are selected, follow the batch workflow (`references/batch.md`).

**Options:** Pass `--months N`, `--max N`, `--sort views`, or `--all` if the user requests filtering or sorting.

## YouTube Path

### Step 2: Launch YouTube digest agent

Run `date +%s` → save as `T_AGENT_START`. Read prompt from `references/youtube.md`. Fill in all `[bracketed]` values. Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 15`. After agent returns, run `date +%s` → save as `T_AGENT_END`. Compute `AGENT_MS = (T_AGENT_END - T_AGENT_START) * 1000`. The agent runs transcribe.py internally; save its `execution_ms` as `TRANSCRIBE_MS` (agent will include this in its return). Report per **Reporting** section, then **Run Logging** section.

## X/Twitter Path

### Step X-1: Fetch X/Twitter content

```bash
python ".claude/skills/digest/scripts/fetch_x.py" "<URL>" --date "[YYYY-MM-DD]" --time "[HH:MM]" --content-out "outputs/temp/x_content.txt" --toc-out "outputs/temp/x_toc.txt"
```

Parse the JSON output. If `"error"`, report and stop. Check `content_type`:
- `"single"`: Display inline. Format: **@screen_name** (display_name), tweet text, engagement stats, published date, URL. No subagent needed.
- `"article"`: Read prompt from `references/x-twitter.md`. Fill in `[bracketed]` values from JSON. Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 8`. Report per **Reporting** section below.

## Blog/Article Path

### Step B-1: Fetch blog content

```bash
python ".claude/skills/digest/scripts/fetch_blog.py" "<URL>" --date "[YYYY-MM-DD]" --time "[HH:MM]" --depth deep --content-out "outputs/temp/blog_content.txt" --toc-out "outputs/temp/blog_toc.txt"
```

Parse the JSON output. If `"error"`, report and stop.

**Podcast reclassification:** If JSON contains `content_type: "podcast"`, route to **Step HA-1** with metadata from the `podcast` object (`--rss`, `--audio-url`, `--show-name`, `--episode-title` flags as available). If `podcast.chapters` is present, save `show_notes_chapters` for `--chapters` in Step HA-1. Do NOT continue to Step B-2.

Save from JSON: `title`, `author`, `published`, `image`, `url`, `content_markdown`, `headings`, `frontmatter`, `toc`, `safe_title`, `safe_author`, `word_count`.

### Step B-2: Launch blog digest agent

Read prompt from `references/blog.md`. Fill in `[bracketed]` values from JSON. Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 8`. Report per **Reporting** section below.

## Hosted Audio Path

Read `references/hosted-audio.md` and follow Steps HA-0 through HA-2. Report per **Reporting** section below.

## Quick Mode Paths (Default)

Quick mode is the default. These steps are used unless `FULL_MODE = true`. URL classification (Step 1.5) is the same. Batch mode works the same (parallel agents). The only difference is which agent prompt and scripts are used.

### Quick YouTube: Step Q-YT

1. **Fetch captions + thumbnail (parallel Bash calls):**

```bash
mkdir -p outputs/temp outputs/digests outputs/.media && python ".claude/skills/digest/scripts/fetch_captions.py" "<URL>" --date "[YYYY-MM-DD]" --output-dir "outputs/temp"
```

```bash
curl -s -o "outputs/.media/[video_id]_thumb.jpg" "https://img.youtube.com/vi/[video_id]/maxresdefault.jpg"
```

Extract `video_id` from the URL (`v=` parameter or youtu.be path segment) before launching these. Parse the JSON from `fetch_captions.py`. If `"error"`, report and stop. Save `execution_ms` from JSON as `FETCH_MS`.

2. **Launch quick agent:** Run `date +%s` → save as `T_AGENT_START`. Read prompt from `references/quick-youtube.md`. Fill in `[bracketed]` values from the JSON output (includes `caption_source` for provenance tracking). Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 8`. After agent returns, run `date +%s` → save as `T_AGENT_END`. Compute `AGENT_MS = (T_AGENT_END - T_AGENT_START) * 1000`. Report per **Reporting** section, then **Run Logging** section.

### Quick X/Twitter: Step Q-X

Same as full mode Step X-1 (`fetch_x.py`). Single posts display inline (unchanged). For articles: use `references/quick-article.md` instead of `references/x-twitter.md`. Set `[pipeline]` = `x-twitter`. Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 8`.

### Quick Blog/Article: Step Q-B

Same as full mode Step B-1 (`fetch_blog.py`) but pass `--depth shallow` instead of `--depth deep`. Same podcast reclassification check. For articles: use `references/quick-article.md` instead of `references/blog.md`. Set `[pipeline]` = `blog`. Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 8`.

### Quick Podcast: Step Q-P

1. **Fetch show notes** via `fetch_blog.py` (same as Step B-1 / Step HA-0, with `--depth shallow`).
2. **Content check:** If `word_count` from `fetch_blog.py` JSON is >= 200, the show notes have enough content. Use `references/quick-article.md` with the show notes content. Launch agent: `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 8`.
3. **Thin content fallback:** If `word_count` < 200, fall back to full podcast pipeline (Step HA-0 through HA-2). This adds ~15-30s but guarantees quality.

## Reporting

After any agent returns:

1. **Verify output file exists.** Parse the agent's response for the digest file path. Check the file exists on disk. If the agent returned without creating the file (silent failure), re-launch the agent once with the same inputs. If the retry also fails, report the failure with the URL.

2. **Read the digest file** (first 30 lines covers frontmatter + Key Takeaways). For batch runs, read all digest files in parallel. Extract from the actual file: `author`, `title`, `duration`/`published`, and the Key Takeaways content. Do NOT use the agent's return text for any of these fields.

3. **Display in chat** (derived from the file, not the agent):
   - Content identifier: title, author/channel/show, and duration (if audio/video) or published date (if article)
   - The bold summary line and first 2 dash points from Key Takeaways (verbatim from file)
   - The digest file path (e.g. `outputs/digests/Title.md`)
   - "Open the digest for the full breakdown."

## Run Logging

After Reporting completes for each digest, log the run. Call `log_run.py` with timing data collected during the pipeline:

```bash
python ".claude/skills/digest/scripts/log_run.py" \
  --url "[source_url]" --mode [quick|full] --pipeline [youtube|blog|x-twitter|podcast] \
  --title "[title]" --video-id "[video_id]" \
  --caption-source "[caption_source]" \
  --output-file "[digest_path]" \
  --step fetch=[FETCH_MS] --step agent=[AGENT_MS]
```

**Timing sources by pipeline:**

| Pipeline | Steps to log | How to get timing |
|----------|-------------|-------------------|
| Quick YouTube | `fetch`, `agent` | `execution_ms` from fetch_captions.py JSON; `date +%s` before/after agent |
| Full YouTube | `agent` | `date +%s` before/after agent (agent runs transcribe.py + assemble internally) |
| Blog/Article | `fetch`, `agent` | `execution_ms` from fetch_blog.py JSON; `date +%s` before/after agent |
| X/Twitter | `fetch`, `agent` | `execution_ms` from fetch_x.py JSON; `date +%s` before/after agent |
| Podcast | `fetch`, `agent` | `execution_ms` from fetch_podcast.py JSON; `date +%s` before/after agent |

Omit `--video-id` and `--caption-source` for non-YouTube pipelines. Omit `--step` entries you don't have (e.g., if fetch timing wasn't captured from cache hit).

**Query the log:** `python ".claude/skills/digest/scripts/query_runs.py"` with `--last N`, `--url`, `--mode`, `--pipeline`, `--title`, `--stats`, or `--json`. See script `--help` for details.
