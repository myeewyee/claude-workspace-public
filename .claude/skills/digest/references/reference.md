# Digest: Reference

Prerequisites, error handling tables, file lifecycle notes, and content taxonomy. Consult when troubleshooting failures or during task reviews.

## Content Taxonomy

Authoritative definitions in [[Vault frontmatter conventions]] § "Digest-produced content properties" and "Subtype". Quick rules:

- `subtype:` — `podcast` = show that distributes audio on podcast apps (Spotify, Apple Podcasts, RSS), even if via YouTube. `video` = video-native content (YouTube-only channels, clips, standalone explainers). `article` = text. Test: "Does this show publish audio on podcast apps?" Not determined by pipeline.
- `author:` — YouTube path: channel name verbatim. Hosted audio path: RSS show name verbatim. No lookup.
- `people:` — wiki-linked external guests only (never the host or regular co-hosts). Omit field for solo content and standard panels with no external guest.

## Prerequisites

- **YouTube path:** `GROQ_API_KEY` environment variable set. Installed: `yt-dlp`, `ffmpeg`, `groq` Python package. On Windows: disable Python App Execution Aliases in Settings to prevent Windows Store popups.
- **X/Twitter path:** No additional dependencies. `fetch_x.py` uses Python stdlib only.
- **Blog/article path:** `trafilatura` Python package installed (`pip install trafilatura`).
- **Hosted audio path:** `GROQ_API_KEY` environment variable set (same as YouTube). `fetch_podcast.py` uses Python stdlib only (no new dependencies). Audio download via `urllib`. RSS parsing via `xml.etree.ElementTree`. `yt-dlp` used as fallback for some platform URLs.
- **Speaker diarization (optional, enhances podcast/interview transcripts):** `PYANNOTE_API_KEY` environment variable set. `requests` Python package. When not configured, diarization is silently skipped and transcripts use plain timestamps without speaker labels. See pyannote.ai for pricing and trial info.

## YouTube Error Handling

| Error | Response |
|-------|----------|
| No `GROQ_API_KEY` | Tell user to set the env var |
| Video unavailable | Report error, suggest checking URL |
| Download fails | Report yt-dlp error, check if video is private/age-restricted |
| Transcription fails | Report Groq API error |
| Agent fails | Report error. Check `outputs/temp/` for intermediate transcript, `outputs/digests/` for partial digest. |

## YouTube File Lifecycle

- **Digest** (`outputs/digests/*.md`): Permanent. Includes full transcript under `## Transcript`.
- **Audio** (`outputs/.media/*.mp3`): Kept for re-processing. Named by video_id (Whisper fallback) or safe_title (full mode).
- **Thumbnails** (`outputs/.media/*_thumb.jpg`): Kept in dot-prefixed folder. Referenced by digest frontmatter `image:` field.
- **Cache** (`outputs/.cache/{video_id}/`): Persistent cache of intermediate artifacts: `metadata.json`, `captions.txt`, `whisper_segments.json`, `apify_response.json`. Not auto-deleted.
- **Raw transcript** (`outputs/temp/*.md`): Kept after assembly for re-processing (chapter regeneration, format changes).
- **Formatted transcript** (`outputs/temp/formatted_transcript.txt`): Deleted immediately after assembly. Ephemeral intermediate.

## X/Twitter Error Handling

| Error | Response |
|-------|----------|
| HTTP 404 | Post not found. May be deleted or account may be private. |
| HTTP 403/401 | Access denied. Account may be private. |
| Network error | Could not reach fxtwitter API. Check internet connection. |
| Subagent fails | Report error. The article content is in the fetch_x.py JSON output. |

## X/Twitter File Lifecycle

- **Article Digest** (`outputs/digests/*.md`): Permanent. Same lifecycle as YouTube digests.
- No audio, transcript, or media files are created for X content.

## Blog/Article Error Handling

| Error | Response |
|-------|----------|
| Fetch timeout | Page took too long to load (15-second limit) |
| Content too large | Page exceeds 5MB size limit |
| No content extracted | Could not extract article content (may not be a standard article page) |
| Too short (<100 chars) | Page has insufficient article content |
| Subagent fails | Report error. The article content is in the fetch_blog.py JSON output. |

## Blog/Article File Lifecycle

- **Blog Digest** (`outputs/digests/*.md`): Permanent. Same lifecycle as YouTube and X/Twitter digests.
- No audio, transcript, or media files are created for blog content.

## Hosted Audio Error Handling

| Error | Response |
|-------|----------|
| No `GROQ_API_KEY` | Tell user to set the env var |
| No audio source found | Report what was tried (RSS, page scan, yt-dlp). Suggest providing a direct audio URL or RSS feed URL. |
| Spotify exclusive | No public audio available. Spotify exclusives can't be transcribed without a direct audio source. |
| Audio download fails | Report download error. May be geo-restricted or behind auth. |
| Transcription fails | Report Groq API error |
| Agent fails | Report error. Check `outputs/temp/` for intermediate transcript, `outputs/digests/` for partial digest. |

## Hosted Audio File Lifecycle

- **Digest** (`outputs/digests/*.md`): Permanent. Same lifecycle as YouTube digests.
- **Audio** (`outputs/.media/*.mp3`): Kept for re-processing. Same as YouTube lifecycle.
- **Raw transcript** (`outputs/temp/*.md`): Kept after assembly for re-processing.
- **Formatted transcript** (`outputs/temp/formatted_transcript.txt`): Deleted immediately after assembly. Ephemeral intermediate.
