#!/usr/bin/env python3
"""
YouTube auto-caption fetcher for /digest quick mode.

Four-layer fallback chain for resilience:
  1. youtube-transcript-api (fast, free, clean text, timestamps)
  2. yt-dlp subtitle download (free, different code path, timestamps)
  3. Apify premium actor (residential proxies, different IP)
  4. Groq Whisper ASR (audio download + speech recognition, ~100% reliable)

Outputs JSON to stdout (metadata + caption file path).
Progress and errors go to stderr.
"""

import argparse
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request


CACHE_DIR = os.path.join("outputs", ".cache")


def _cache_path(video_id, filename):
    """Return path to a cache file for a video, creating dirs as needed."""
    d = os.path.join(CACHE_DIR, video_id)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, filename)


def _save_cache(video_id, filename, data):
    """Save data to cache. Accepts str (written as-is) or dict/list (JSON)."""
    path = _cache_path(video_id, filename)
    with open(path, "w", encoding="utf-8") as f:
        if isinstance(data, str):
            f.write(data)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Cached: {path}")


def _load_cache(video_id, filename):
    """Load cached file. Returns str content or None if not cached."""
    path = _cache_path(video_id, filename)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def log(msg):
    """Print to stderr."""
    print(msg, file=sys.stderr)


def _find_yt_dlp():
    """Resolve yt-dlp path. Checks PATH, then pip Scripts directory."""
    import shutil
    import sysconfig
    path = shutil.which("yt-dlp")
    if path:
        return path
    scripts = sysconfig.get_path("scripts")
    if scripts:
        candidate = os.path.join(scripts, "yt-dlp.exe" if os.name == "nt" else "yt-dlp")
        if os.path.isfile(candidate):
            log(f"Found yt-dlp at: {candidate}")
            return candidate
    log("WARNING: yt-dlp not found on PATH or in Python Scripts. Install with: pip install yt-dlp")
    return "yt-dlp"


YT_DLP = _find_yt_dlp()


def retry_on_rate_limit(fn, description, max_retries=3, base_delay=5):
    """Retry a function on rate-limit errors with exponential backoff.
    Returns (result, None) on success, (None, error_string) on failure."""
    last_error = None
    for attempt in range(max_retries):
        try:
            return fn(), None
        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            is_rate_limit = any(
                term in error_str
                for term in ["429", "too many requests", "rate limit", "ratelimit"]
            )
            if is_rate_limit and attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt)
                log(f"Rate limited on {description}, waiting {wait}s "
                    f"(attempt {attempt + 1}/{max_retries})...")
                time.sleep(wait)
            elif is_rate_limit:
                return None, f"rate_limit:{str(e)}"
            else:
                return None, f"error:{str(e)}"
    return None, f"error:{str(last_error)}"


def get_metadata(url):
    """Extract video metadata via yt-dlp (no download)."""

    def _fetch():
        result = subprocess.run(
            [
                YT_DLP,
                "--print", "%(title)s",
                "--print", "%(channel)s",
                "--print", "%(duration)s",
                "--print", "%(id)s",
                "--print", "%(upload_date)s",
                "--print", "%(chapters)j",
                "--print", "%(description)j",
                url,
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "429" in stderr or "Too Many Requests" in stderr:
                raise Exception(f"429 rate limit: {stderr}")
            return {"error": f"yt-dlp metadata failed: {stderr}"}
        return result.stdout.strip()

    raw, err = retry_on_rate_limit(_fetch, "yt-dlp metadata")

    if err:
        return {"error": err}

    # If the inner function returned an error dict, pass it through
    if isinstance(raw, dict):
        return raw

    lines = raw.split("\n")
    duration = 0
    if len(lines) > 2 and lines[2].strip().isdigit():
        duration = int(lines[2].strip())

    video_id = lines[3].strip() if len(lines) > 3 else ""
    upload_date_raw = lines[4].strip() if len(lines) > 4 else ""

    published = ""
    if len(upload_date_raw) == 8 and upload_date_raw.isdigit():
        published = (
            f"{upload_date_raw[:4]}-{upload_date_raw[4:6]}-"
            f"{upload_date_raw[6:8]}"
        )

    chapters = []
    chapters_raw = lines[5].strip() if len(lines) > 5 else ""
    if chapters_raw and chapters_raw not in ("NA", "null", "None"):
        try:
            chapters = json.loads(chapters_raw)
        except json.JSONDecodeError:
            pass

    description = ""
    description_raw = lines[6].strip() if len(lines) > 6 else ""
    if description_raw and description_raw not in ("NA", "null", "None"):
        try:
            description = json.loads(description_raw)
        except json.JSONDecodeError:
            description = description_raw

    return {
        "title": lines[0].strip() if lines else "Unknown",
        "channel": lines[1].strip() if len(lines) > 1 else "Unknown",
        "duration_seconds": duration,
        "video_id": video_id,
        "published": published,
        "thumbnail": (
            f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
            if video_id
            else ""
        ),
        "chapters": chapters,
        "description": description,
        "url": url,
    }


def sanitize(name):
    """Remove characters invalid in filenames and collapse whitespace."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip(". ")[:200]


def format_duration(seconds):
    """Format duration for human display."""
    h, remainder = divmod(seconds, 3600)
    m = remainder // 60
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def _format_timestamp(seconds):
    """Format seconds as M:SS or H:MM:SS for caption timestamps."""
    seconds = int(seconds)
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _timed_to_paragraphs(
    timed_snippets, pause_threshold=4.0, max_words=150
):
    """Break timed caption segments into paragraphs at natural pauses.

    A paragraph break is inserted when the gap between consecutive segments
    exceeds pause_threshold seconds OR the current paragraph exceeds
    max_words. Each paragraph is prefixed with its start timestamp in
    [M:SS] format.
    """
    if not timed_snippets:
        return ""

    def _flush(start, segments):
        ts = _format_timestamp(start)
        joined = " ".join(segments).replace(">> ", "")
        return f"[{ts}] " + joined

    def _word_count(segments):
        return sum(len(s.split()) for s in segments)

    paragraphs = []
    para_start = timed_snippets[0][0]
    current = [timed_snippets[0][1]]
    for i in range(1, len(timed_snippets)):
        prev_start = timed_snippets[i - 1][0]
        curr_start = timed_snippets[i][0]
        gap = curr_start - prev_start
        if gap >= pause_threshold or _word_count(current) >= max_words:
            paragraphs.append(_flush(para_start, current))
            current = []
            para_start = curr_start
        current.append(timed_snippets[i][1])
    if current:
        paragraphs.append(_flush(para_start, current))
    return "\n\n".join(paragraphs)


def _untimed_to_paragraphs(segments, group_size=15):
    """Break untimed caption segments into paragraphs every N segments."""
    paragraphs = []
    for i in range(0, len(segments), group_size):
        paragraphs.append(" ".join(segments[i:i + group_size]))
    return "\n\n".join(paragraphs)


def insert_chapter_headings(timed_snippets, chapters):
    """Insert ### chapter headings into a list of (start_seconds, text) tuples.

    Args:
        timed_snippets: list of (start_seconds, text) tuples
        chapters: list of dicts with 'start_time' and 'title' keys

    Returns:
        Formatted text with ### headings and paragraph breaks.
    """
    if not chapters:
        return _timed_to_paragraphs(timed_snippets)

    boundaries = [
        (c.get("start_time", 0), c.get("title", ""))
        for c in sorted(chapters, key=lambda c: c.get("start_time", 0))
        if c.get("title")
    ]

    if not boundaries:
        return _timed_to_paragraphs(timed_snippets)

    # Group snippets into chapter sections
    sections = []
    current_snippets = []
    boundary_idx = 0
    current_title = None

    for start, text in timed_snippets:
        while (
            boundary_idx < len(boundaries)
            and start >= boundaries[boundary_idx][0]
        ):
            if current_snippets or current_title:
                sections.append(
                    (current_title, _timed_to_paragraphs(current_snippets))
                )
                current_snippets = []
            current_title = boundaries[boundary_idx][1]
            boundary_idx += 1
        current_snippets.append((start, text))

    if current_snippets or current_title:
        sections.append(
            (current_title, _timed_to_paragraphs(current_snippets))
        )

    parts = []
    for title, text in sections:
        if title:
            parts.append(f"### {title}\n{text}")
        else:
            parts.append(text)

    return "\n\n".join(parts)


# ── Primary: youtube-transcript-api ──────────────────────────────────


def fetch_via_transcript_api(video_id, chapters=None):
    """Fetch captions via youtube-transcript-api. Returns (text, None) or
    (None, error_type:message)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None, "missing_dep:youtube-transcript-api not installed"

    def _fetch():
        api = YouTubeTranscriptApi()
        return api.fetch(video_id)

    result, err = retry_on_rate_limit(_fetch, "caption fetch")
    if err:
        return None, err

    timed = [(snippet.start, snippet.text) for snippet in result]
    text = insert_chapter_headings(timed, chapters)
    return text, None


# ── Fallback: yt-dlp subtitle download ──────────────────────────────


def parse_srt(srt_text):
    """Parse SRT subtitle text into (start_seconds, text) tuples."""
    cues = []
    for block in re.split(r"\n\n+", srt_text.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 2:
            continue
        # Find the timestamp line (may be line 0 or 1)
        ts_line = None
        text_start = None
        for i, line in enumerate(lines):
            if "-->" in line:
                ts_line = line
                text_start = i + 1
                break
        if not ts_line or not text_start:
            continue

        match = re.match(
            r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})", ts_line
        )
        if not match:
            continue
        h, m, s, ms = int(match[1]), int(match[2]), int(match[3]), int(match[4])
        start = h * 3600 + m * 60 + s + ms / 1000.0

        raw_text = " ".join(lines[text_start:]).strip()
        # Strip HTML tags yt-dlp sometimes includes
        raw_text = re.sub(r"<[^>]+>", "", raw_text)
        # Deduplicate repeated lines (YouTube auto-subs often double)
        raw_text = raw_text.strip()
        if raw_text and (not cues or cues[-1][1] != raw_text):
            cues.append((start, raw_text))
    return cues


def fetch_via_ytdlp_subs(video_id, chapters=None):
    """Fetch captions via yt-dlp subtitle download. Returns (text, None) or
    (None, error_message)."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    with tempfile.TemporaryDirectory() as tmpdir:
        out_template = os.path.join(tmpdir, "%(id)s")
        result = subprocess.run(
            [
                YT_DLP,
                "--write-auto-sub",
                "--sub-lang", "en",
                "--convert-subs", "srt",
                "--skip-download",
                "-o", out_template,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            stderr = result.stderr.strip()
            if "429" in stderr or "Too Many Requests" in stderr:
                return None, f"yt-dlp subtitles also rate-limited: {stderr}"
            return None, f"yt-dlp subtitle download failed: {stderr}"

        # Find the SRT file
        srt_path = None
        for f in os.listdir(tmpdir):
            if f.endswith(".srt"):
                srt_path = os.path.join(tmpdir, f)
                break

        if not srt_path:
            # Check for VTT as fallback
            for f in os.listdir(tmpdir):
                if f.endswith(".vtt") or f.endswith(".en.vtt"):
                    srt_path = os.path.join(tmpdir, f)
                    break

        if not srt_path:
            return None, "No subtitle file produced by yt-dlp"

        with open(srt_path, "r", encoding="utf-8") as f:
            srt_text = f.read()

    cues = parse_srt(srt_text)
    if not cues:
        return None, "SRT file parsed but contained no text"

    text = insert_chapter_headings(cues, chapters)
    return text, None


# ── Fallback 2: Apify actor (different IP) ───────────────────────────

APIFY_ACTOR = "smartly_automated~youtube-transcript-scraper-premium-version"
APIFY_POLL_INTERVAL = 5
APIFY_MAX_WAIT = 180


def get_apify_token():
    """Get Apify API token from environment or Windows user env."""
    token = os.environ.get("APIFY_API_TOKEN")
    if token:
        return token
    # PowerShell fallback for Windows user-level env vars
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             '[System.Environment]::GetEnvironmentVariable("APIFY_API_TOKEN","User")'],
            capture_output=True, text=True, timeout=10,
        )
        token = r.stdout.strip()
        if token:
            return token
    except Exception:
        pass
    return None


def apify_request(url, data=None, timeout=30):
    """Make an HTTP request to Apify API and return parsed JSON."""
    headers = {"Content-Type": "application/json"} if data else {}
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_via_apify(video_id, chapters=None):
    """Fetch captions via Apify premium actor (residential proxies, ~99% success).
    Returns (text, None) or (None, error_message)."""
    token = get_apify_token()
    if not token:
        return None, "APIFY_API_TOKEN not set"

    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Start the actor run
    try:
        run_url = (
            f"https://api.apify.com/v2/acts/{APIFY_ACTOR}/runs?token={token}"
        )
        run_info = apify_request(
            run_url,
            data={"video_urls": [{"url": video_url}]},
            timeout=60,
        )
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")[:200]
        return None, f"Apify API error {e.code}: {body}"
    except Exception as e:
        return None, f"Apify request failed: {str(e)}"

    run_id = run_info["data"]["id"]
    dataset_id = run_info["data"]["defaultDatasetId"]
    log(f"Apify actor started (run {run_id[:8]}...)")

    # Poll for completion
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}"
    elapsed = 0
    while elapsed < APIFY_MAX_WAIT:
        time.sleep(APIFY_POLL_INTERVAL)
        elapsed += APIFY_POLL_INTERVAL
        try:
            status = apify_request(status_url, timeout=15)
        except Exception:
            continue
        run_status = status["data"]["status"]
        if run_status == "SUCCEEDED":
            break
        elif run_status in ("FAILED", "ABORTED", "TIMED-OUT"):
            msg = status["data"].get("statusMessage", run_status)
            return None, f"Apify actor {run_status}: {msg}"
    else:
        return None, f"Apify actor timed out after {APIFY_MAX_WAIT}s"

    # Brief delay for dataset items to commit after run completes
    time.sleep(3)

    # Fetch results (retry once if dataset initially empty)
    for attempt in range(2):
        try:
            items_url = (
                f"https://api.apify.com/v2/datasets/{dataset_id}"
                f"/items?token={token}"
            )
            items = apify_request(items_url, timeout=30)
        except Exception as e:
            return None, f"Apify dataset fetch failed: {str(e)}"

        if items:
            break
        if attempt == 0:
            log("Dataset empty, retrying in 5s...")
            time.sleep(5)

    if not items:
        return None, "Apify returned empty dataset"

    # Cache raw Apify response
    _save_cache(video_id, "apify_response.json", items)

    item = items[0]
    transcript = item.get("transcript", "")
    if not transcript or not transcript.strip():
        return None, "Apify returned empty transcript"

    # Premium actor returns a flat transcript string (no timestamps).
    # Clean up: decode HTML entities, normalize whitespace.
    transcript = html.unescape(transcript)

    # Split into segments. The actor may return one giant string or
    # newline-separated lines depending on the video.
    lines = [line.strip() for line in transcript.split("\n") if line.strip()]

    # If too few lines, split by sentences for chapter placement
    if len(lines) < 10:
        text_blob = " ".join(lines)
        clean_segments = [
            s.strip() for s in re.split(r'(?<=[.!?])\s+', text_blob)
            if s.strip()
        ]
    else:
        clean_segments = lines

    if not clean_segments:
        return None, "Apify transcript contained no text after cleanup"

    # Without timestamps, estimate chapter placement proportionally.
    if chapters and len(clean_segments) > 1:
        text = _insert_chapters_by_position(clean_segments, chapters)
    else:
        text = _untimed_to_paragraphs(clean_segments)

    return text, None


def _insert_chapters_by_position(segments, chapters):
    """Insert chapter headings into untimed caption segments by estimating
    position proportionally (Apify captions lack timestamps)."""
    boundaries = [
        (c.get("start_time", 0), c.get("title", ""))
        for c in sorted(chapters, key=lambda c: c.get("start_time", 0))
        if c.get("title")
    ]
    if not boundaries:
        return _untimed_to_paragraphs(segments)

    # Get max chapter time to estimate total duration
    max_time = max(b[0] for b in boundaries)
    if max_time <= 0:
        return _untimed_to_paragraphs(segments)

    total_segs = len(segments)

    # Group segments into chapter sections
    chapter_sections = []
    current_segs = []
    current_title = None
    boundary_idx = 0

    for i, seg in enumerate(segments):
        est_time = (i / total_segs) * (max_time * 1.3)
        while (
            boundary_idx < len(boundaries)
            and est_time >= boundaries[boundary_idx][0]
        ):
            if current_segs or current_title:
                chapter_sections.append(
                    (current_title, _untimed_to_paragraphs(current_segs))
                )
                current_segs = []
            current_title = boundaries[boundary_idx][1]
            boundary_idx += 1
        current_segs.append(seg)

    # Remaining chapters and segments
    while boundary_idx < len(boundaries):
        if current_segs or current_title:
            chapter_sections.append(
                (current_title, _untimed_to_paragraphs(current_segs))
            )
            current_segs = []
        current_title = boundaries[boundary_idx][1]
        boundary_idx += 1

    if current_segs or current_title:
        chapter_sections.append(
            (current_title, _untimed_to_paragraphs(current_segs))
        )

    parts = []
    for title, text in chapter_sections:
        if title:
            parts.append(f"### {title}\n{text}")
        else:
            parts.append(text)

    return "\n\n".join(parts)


# ── Fallback 3: Groq Whisper ASR (audio + speech recognition) ────────

KNOWN_FFMPEG = (
    "<your-home-dir>/AppData/Local/Microsoft/WinGet/Packages/"
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/"
    "ffmpeg-8.0.1-full_build/bin"
)
WHISPER_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB Groq API limit
WHISPER_CHUNK_DURATION = 600  # 10 minutes in seconds


def _find_ffmpeg():
    """Find ffmpeg binary. Checks PATH first, then known platform-specific location."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=True
        )
        return None  # On PATH, yt-dlp finds it automatically
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    if os.path.exists(os.path.join(KNOWN_FFMPEG, "ffmpeg.exe")):
        return KNOWN_FFMPEG
    return None


def _get_groq_key():
    """Get Groq API key from environment or Windows user env."""
    key = os.environ.get("GROQ_API_KEY")
    if key:
        return key
    try:
        r = subprocess.run(
            ["powershell", "-Command",
             '[System.Environment]::GetEnvironmentVariable'
             '("GROQ_API_KEY","User")'],
            capture_output=True, text=True, timeout=10,
        )
        key = r.stdout.strip()
        if key:
            return key
    except Exception:
        pass
    return None


def fetch_via_whisper(video_id, chapters=None):
    """Download audio and transcribe via Groq Whisper as ultimate fallback.

    Works on fundamentally different infrastructure than caption-based layers:
    audio download + speech recognition instead of caption scraping.
    Returns (text, None) or (None, error_message).
    """
    groq_key = _get_groq_key()
    if not groq_key:
        return None, "GROQ_API_KEY not set"

    try:
        from groq import Groq
    except ImportError:
        return None, "groq package not installed"

    ffmpeg_loc = _find_ffmpeg()
    video_url = f"https://www.youtube.com/watch?v={video_id}"

    # Download audio to persistent media dir (dot-prefixed, Obsidian-hidden)
    media_dir = os.path.join("outputs", ".media")
    os.makedirs(media_dir, exist_ok=True)

    # Skip download if MP3 already exists (e.g. from a previous run)
    expected_path = os.path.join(media_dir, f"{video_id}.mp3")
    if os.path.exists(expected_path):
        audio_path = expected_path
        log(f"Audio already cached: {audio_path}")
    else:
        log("Downloading audio for Whisper transcription...")
        output_template = os.path.join(media_dir, f"{video_id}.%(ext)s")
        cmd = [
            YT_DLP, "-x",
            "--audio-format", "mp3",
            "--audio-quality", "5",
            "-o", output_template,
            video_url,
        ]
        if ffmpeg_loc:
            cmd[1:1] = ["--ffmpeg-location", ffmpeg_loc]

        try:
            dl_result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=300,
            )
        except subprocess.TimeoutExpired:
            return None, "Audio download timed out (300s)"

        if dl_result.returncode != 0:
            return None, (
                f"Audio download failed: "
                f"{dl_result.stderr.strip()[:200]}"
            )

        # Find the MP3 file
        audio_path = None
        if os.path.exists(expected_path):
            audio_path = expected_path
        else:
            for f in os.listdir(media_dir):
                if f.startswith(video_id) and f.endswith(".mp3"):
                    audio_path = os.path.join(media_dir, f)
                    break

        if not audio_path:
            return None, "Audio file not found after download"

    file_size = os.path.getsize(audio_path)
    log(f"Audio: {file_size / 1024 / 1024:.1f}MB ({audio_path})")

    # Set up Groq client
    client = Groq(api_key=groq_key)

    def _transcribe_one(path, max_retries=3):
        for attempt in range(max_retries):
            try:
                with open(path, "rb") as af:
                    return client.audio.transcriptions.create(
                        file=(os.path.basename(path), af.read()),
                        model="whisper-large-v3-turbo",
                        response_format="verbose_json",
                        timestamp_granularities=["segment"],
                        language="en",
                    )
            except Exception as e:
                error_str = str(e)
                is_rate = (
                    "429" in error_str
                    or "rate_limit" in error_str.lower()
                )
                if is_rate and attempt < max_retries - 1:
                    wait = 60
                    match = re.search(
                        r"try again in (\d+)m(\d+(?:\.\d+)?)s",
                        error_str,
                    )
                    if match:
                        wait = (
                            int(match.group(1)) * 60
                            + float(match.group(2)) + 5
                        )
                    else:
                        match = re.search(
                            r"try again in (\d+(?:\.\d+)?)s",
                            error_str,
                        )
                        if match:
                            wait = float(match.group(1)) + 5
                    log(
                        f"Groq rate limited, waiting {wait:.0f}s "
                        f"(attempt {attempt + 1}/{max_retries})..."
                    )
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError(
            f"Groq rate limit exceeded after {max_retries} retries"
        )

    # Transcribe (chunk via temp dir if >25MB)
    segments = []

    if file_size <= WHISPER_MAX_FILE_SIZE:
        log("Transcribing via Groq Whisper...")
        whisper_result = _transcribe_one(audio_path)
        segments = [
            {"start": s["start"], "text": s["text"].strip()}
            for s in whisper_result.segments
        ]
    else:
        log(
            f"Audio exceeds 25MB. Splitting into "
            f"{WHISPER_CHUNK_DURATION // 60}-min chunks..."
        )
        ffmpeg_bin = (
            os.path.join(ffmpeg_loc, "ffmpeg.exe")
            if ffmpeg_loc else "ffmpeg"
        )

        with tempfile.TemporaryDirectory() as chunk_dir:
            pattern = os.path.join(chunk_dir, "chunk_%03d.mp3")

            split_result = subprocess.run(
                [
                    ffmpeg_bin, "-i", audio_path,
                    "-f", "segment",
                    "-segment_time", str(WHISPER_CHUNK_DURATION),
                    "-c", "copy",
                    pattern,
                ],
                capture_output=True, text=True,
            )
            if split_result.returncode != 0:
                return None, (
                    f"Audio split failed: "
                    f"{split_result.stderr.strip()[:200]}"
                )

            chunks = sorted(
                os.path.join(chunk_dir, cf)
                for cf in os.listdir(chunk_dir)
                if cf.endswith(".mp3")
            )

            for i, chunk in enumerate(chunks):
                offset = i * WHISPER_CHUNK_DURATION
                log(f"  Chunk {i + 1}/{len(chunks)} "
                    f"(offset {offset}s)...")
                whisper_result = _transcribe_one(chunk)
                for s in whisper_result.segments:
                    segments.append({
                        "start": s["start"] + offset,
                        "text": s["text"].strip(),
                    })

    if not segments:
        return None, "Whisper transcription returned no segments"

    log(f"Whisper transcription complete: {len(segments)} segments")

    # Cache raw Whisper segments
    _save_cache(video_id, "whisper_segments.json", segments)

    # Convert to timed tuples and apply chapter headings
    timed = [(s["start"], s["text"]) for s in segments]
    text = insert_chapter_headings(timed, chapters)
    return text, None


# ── Main: four-layer fallback chain ──────────────────────────────────


def fetch_captions(video_id, chapters=None):
    """Fetch captions with four-layer fallback for resilience.

    1. youtube-transcript-api (fast, free, has timestamps)
    2. yt-dlp subtitle download (free, different code path, has timestamps)
    3. Apify premium actor (residential proxies, no timestamps)
    4. Groq Whisper ASR (audio download + transcription, has timestamps)

    Returns (caption_text, source_name) tuple. source_name is one of:
    'youtube-api', 'yt-dlp', 'apify', 'whisper'.
    """
    errors = {}

    layers = [
        ("transcript-api", fetch_via_transcript_api, None),
        ("yt-dlp", fetch_via_ytdlp_subs, "Captions fetched via yt-dlp subtitle fallback"),
        ("apify", fetch_via_apify, "Captions fetched via Apify premium fallback"),
        ("whisper", fetch_via_whisper, "Captions fetched via Groq Whisper ASR fallback"),
    ]

    for i, (name, fn, success_msg) in enumerate(layers):
        try:
            text, err = fn(video_id, chapters)
        except Exception as e:
            text, err = None, f"unexpected:{type(e).__name__}: {e}"

        if text is not None and text.strip():
            if success_msg:
                log(success_msg)
            return text, name

        errors[name] = err or "returned empty text"
        if i < len(layers) - 1:
            err_type = err.split(":")[0] if err else "unknown"
            next_name = layers[i + 1][0]
            log(f"Layer {i + 1} failed ({err_type}), trying {next_name}...")

    # All four layers failed
    summary = "; ".join(f"{k}: {v}" for k, v in errors.items())
    raise Exception(f"All caption sources failed. {summary}")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube auto-caption fetcher for /digest quick mode"
    )
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument(
        "--output-dir",
        default="outputs/temp",
        help="Directory for caption text file",
    )
    parser.add_argument(
        "--date",
        default="unknown",
        help="Date for metadata (YYYY-MM-DD)",
    )
    args = parser.parse_args()
    _start_time = time.time()

    os.makedirs(args.output_dir, exist_ok=True)

    # Extract video_id early for cache lookups
    # (parse from URL before yt-dlp, to enable cache hit on metadata)
    url_video_id = None
    if "v=" in args.url:
        url_video_id = args.url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in args.url:
        url_video_id = args.url.split("youtu.be/")[1].split("?")[0]

    # Step 1: Get metadata (cache or fetch)
    meta = None
    if url_video_id:
        cached_meta = _load_cache(url_video_id, "metadata.json")
        if cached_meta:
            try:
                meta = json.loads(cached_meta)
                log(f"Metadata loaded from cache: {meta['title']}")
            except json.JSONDecodeError:
                meta = None

    if not meta:
        log("Fetching metadata...")
        try:
            meta = get_metadata(args.url)
        except Exception as e:
            print(json.dumps({"error": str(e)}))
            sys.exit(1)

        if "error" in meta:
            print(json.dumps(meta))
            sys.exit(1)

        # Cache metadata
        vid = meta.get("video_id", url_video_id or "unknown")
        _save_cache(vid, "metadata.json", meta)

    safe_title = sanitize(meta["title"])
    safe_channel = sanitize(meta["channel"])
    video_id = meta["video_id"]
    chapters = meta.get("chapters", [])

    # Step 2: Fetch captions (check cache first, then fallback chain)
    cached_captions = _load_cache(video_id, "captions.txt")
    cached_source = _load_cache(video_id, "caption_source.txt")
    if cached_captions:
        log(f"Captions loaded from cache ({len(cached_captions)} chars)")
        caption_text = cached_captions
        caption_source = cached_source.strip() if cached_source else "unknown"
    else:
        log(f"Fetching captions: {meta['title']}...")
        try:
            caption_text, caption_source = fetch_captions(video_id, chapters=chapters)
        except Exception as e:
            print(json.dumps({"error": f"Caption fetch failed: {str(e)}"}))
            sys.exit(1)

        # Cache the final caption text and source
        _save_cache(video_id, "captions.txt", caption_text)
        _save_cache(video_id, "caption_source.txt", caption_source)

    # Step 3: Write caption text to output file
    caption_path = os.path.join(args.output_dir, f"captions_{video_id}.txt")
    with open(caption_path, "w", encoding="utf-8") as f:
        f.write(caption_text)

    log(
        f"Captions: {len(caption_text)} chars written to {caption_path}"
        + (f" ({len(chapters)} chapters)" if chapters else "")
    )

    # Output JSON to stdout
    print(
        json.dumps(
            {
                "title": meta["title"],
                "channel": meta["channel"],
                "safe_title": safe_title,
                "safe_channel": safe_channel,
                "duration_seconds": meta["duration_seconds"],
                "duration_formatted": format_duration(
                    meta["duration_seconds"]
                ),
                "video_id": video_id,
                "published": meta.get("published", ""),
                "thumbnail": meta.get("thumbnail", ""),
                "chapters": chapters,
                "description": meta.get("description", ""),
                "url": meta["url"],
                "caption_path": caption_path.replace("\\", "/"),
                "caption_chars": len(caption_text),
                "caption_source": caption_source,
                "execution_ms": int((time.time() - _start_time) * 1000),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
