---
type: task
source: claude
created: 2026-03-04 13:14
status: 5-done
priority:
description: "Quick YouTube digests now include searchable auto-caption transcripts with chapter headings, paragraph breaks at speech pauses, and [M:SS] timestamps. Four-layer fallback chain (transcript-api, yt-dlp, Apify, Groq Whisper) for near-100% reliability. Quick mode is the new default. Persistent cache layer for all intermediate artifacts."
decision: "Four-layer caption fallback: free layers primary, managed API backup, ASR ultimate fallback. Quick mode as default."
parent: "[[Build content consumption assistant]]"
focus: internal
category: improvement
pillar: workflow
completed: 2026-03-04 16:55
---
# Add transcript to quick digest mode
## Context
**Trigger:** While batch-digesting 15 YouTube videos in quick mode, the user wanted to trace claims across all videos. Quick mode digests had no transcript text, so cross-video analysis was impossible without re-digesting.

**Scope:** Three changes bundled together: (1) include auto-caption transcript with chapter headings in quick digests, (2) flip default mode so `/digest URL` = quick and `/digest full URL` = full, (3) add rate-limit retry logic and batch stagger guidance after a YouTube 429 error on 15 concurrent caption fetches.
## Links
### Related
### Subtasks
```base
filters:
  and:
    - type == "task"
    - parent == "[[Add transcript to quick digest mode]]"
properties:
  file.name:
    displayName: Subtask
  status:
    displayName: Status
  description:
    displayName: Description
views:
  - type: table
    name: Subtasks
    order:
      - file.mtime
      - status
      - file.name
    sort:
      - property: file.mtime
        direction: DESC
    indentProperties: false
    markers: none
    columnSize:
      file.mtime: 175

```
### Outputs
```base
filters:
  and:
    - type == "artifact"
    - parent == "[[Add transcript to quick digest mode]]"
properties:
  file.name:
    displayName: Output
  description:
    displayName: Description
  created:
    displayName: Created
views:
  - type: table
    name: Outputs
    order:
      - file.mtime
      - file.name
    sort:
      - property: file.mtime
        direction: DESC
      - property: created
        direction: ASC
    indentProperties: false
    markers: none
    columnSize:
      file.mtime: 175

```
## Success Criteria
- Quick YouTube digests include auto-caption transcript with `### Chapter Title` headings
- Transcript paragraphs broken at natural speech pauses (4s threshold) with `[M:SS]` timestamps
- `## Chapters` entries link to the `###` headings (clickable in Obsidian)
- Transcript header caveats it's quick mode with promotion hint to `/digest full`
- `/digest URL` defaults to quick mode; `/digest full URL` triggers full mode
- `fetch_captions.py` has four-layer fallback: transcript-api, yt-dlp subs, Apify actor, Groq Whisper ASR
- Rate-limit retry with exponential backoff on layers 1-2; Apify (layer 3) bypasses IP limits; Whisper (layer 4) bypasses caption system entirely
- Batch mode staggers YouTube caption fetches (groups of 5) to prevent rate limiting
## Approach
Minimal changes to existing pipeline:
1. Modify `fetch_captions.py` to use chapters from yt-dlp metadata and insert `### headings` into caption text
2. Add retry wrapper with exponential backoff for both yt-dlp and caption API calls
3. Update `quick-youtube.md` agent prompt: new transcript header, clickable chapter links, paste caption text as-is
4. Flip Step 0 in SKILL.md: quick default, `full` override
5. Add batch stagger guidance to `batch.md`
## Work Done
- Modified `fetch_captions.py`: chapter heading insertion, `retry_on_rate_limit()` wrapper for both yt-dlp and caption fetch, better error messages
- Updated `quick-youtube.md`: transcript header with `/digest full` promotion, clickable chapter links, transcript instructions
- Flipped SKILL.md Step 0: quick is now default, `full` triggers full mode
- Added rate-limit stagger guidance to `batch.md` (groups of 5, 3s pause)
- Added Apify actor as third fallback layer in `fetch_captions.py`, using existing `APIFY_API_TOKEN`
- Backfilled all 15 digests with transcripts (14 via Apify batch, 1 re-digested after detecting silent agent failure)
- Fixed Apify fallback bug: empty caption segments caused falsy check to miss empty strings
- Added silent agent failure detection: Step B-Verify in `batch.md` checks each agent created its output file
- Wrapped each fallback layer in try/except to prevent uncaught exceptions from breaking the chain
- Added transcript paragraph formatting: `_timed_to_paragraphs()` breaks at 4-second speech pauses, `_untimed_to_paragraphs()` groups every 15 segments for Apify fallback
- Added `[M:SS]` timestamps at the start of each paragraph
- Swapped Apify actor to one with residential proxies (~99% success vs ~50% block rate)
- Added Groq Whisper ASR as 4th fallback layer: downloads audio via yt-dlp, transcribes via Groq Whisper, handles >25MB files by chunking via ffmpeg
- Added persistent cache layer: `outputs/.cache/{video_id}/` stores metadata, captions, whisper segments. Cache hit skips all network calls.
- MP3s persist to `outputs/.media/{video_id}.mp3` with cache-hit skip on re-runs
## Rollback
To revert all changes from this task:
1. Find the commit: `git log --grep="Complete: Add transcript to quick digest mode"`
2. Files changed:
   - `.claude/skills/digest/scripts/fetch_captions.py` (chapter headings, fallback chain, cache layer, paragraph formatting)
   - `.claude/skills/digest/SKILL.md` (Step 0 mode flip)
   - `.claude/skills/digest/references/quick-youtube.md` (transcript section, chapter links)
   - `.claude/skills/digest/references/batch.md` (rate-limit stagger, Step B-Verify)
   - `.claude/skills/digest/references/reference.md` (file lifecycle updates)
   - `.claude/skills/digest/references/youtube.md` (removed audio deletion)
   - `.claude/skills/digest/references/audio.md` (removed audio deletion)
   - `.gitignore` (added `.cache/`)
   - `context/captains-log.md` (added entry)
3. Revert: `git revert <commit-hash>` or selectively restore each file
4. Delete cache/media: `rm -rf outputs/.cache/ outputs/.media/*.mp3`
## Progress Log
### 2026-03-04
4:55 PM *Status -> Done*

4:55 PM **Task completion verification sweep**
- All 8 success criteria verified against implementation
- No missing edges found
- Reconciliation: updated description, set decision field, added captain's log entry, added rollback section

4:33 PM **Added persistent cache and stopped auto-deleting working files**
- Cache layer in `outputs/.cache/{video_id}/`: metadata.json, captions.txt, whisper_segments.json
- Cache hit skips all network calls (instant re-runs)
- MP3s persist with download-skip on cache hit

4:16 PM **Added Groq Whisper ASR as 4th fallback layer for 100% reliability**
- Downloads audio via yt-dlp + transcribes via Groq Whisper (whisper-large-v3-turbo)
- Handles >25MB files by chunking via ffmpeg (10-min segments)
- Returns real timestamps for proper paragraph formatting and chapter heading placement

4:05 PM **Batch-reformatted all 15 existing digests**
- Wall-of-text transcripts to 4-sentence paragraphs
- Fixed broken `/digest full` promotion lines

3:48 PM **Upgraded Apify fallback actor for reliable caption fetching**
- Swapped actor for one with residential proxies (~99% success)
- Fixed input/output format differences
- Added dataset fetch retry for race condition

2:40 PM **Added transcript paragraph formatting with timestamps**
- Paragraph breaks at 4-second speech pauses
- [M:SS] timestamps at start of each paragraph
- Wrapped fallback layers in try/except to prevent chain breakage

1:55 PM **Fixed silent failures + completed backfill**
- Created missing digest (silent agent failure from original batch)
- Fixed Apify fallback bug: empty caption segments
- Added Step B-Verify to batch.md: verifies each agent created its output file

1:44 PM **Added Apify fallback + backfilled transcripts**
- Three-layer fallback chain: transcript-api, yt-dlp subs, Apify actor
- Backfilled 14/15 digests with transcripts via Apify batch

1:27 PM **Implemented all changes**
- Modified fetch_captions.py, updated agent prompts, flipped default mode, added batch guidance

1:14 PM *Status -> Active*

1:14 PM *Status -> Idea (task created)*
