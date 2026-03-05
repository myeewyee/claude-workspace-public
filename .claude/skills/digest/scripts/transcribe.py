#!/usr/bin/env python3
"""
YouTube transcription pipeline for /digest skill.
Downloads audio via yt-dlp, transcribes via Groq Whisper API.
Handles large files by splitting into chunks.

Outputs compact JSON to stdout (metadata + file paths).
Progress and errors go to stderr.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time

KNOWN_FFMPEG = (
    "<your-home-dir>/AppData/Local/Microsoft/WinGet/Packages/"
    "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/"
    "ffmpeg-8.0.1-full_build/bin"
)
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25MB Groq API limit
CHUNK_DURATION = 600  # 10 minutes in seconds


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
            print(f"Found yt-dlp at: {candidate}", file=sys.stderr)
            return candidate
    print("WARNING: yt-dlp not found on PATH or in Python Scripts. Install with: pip install yt-dlp", file=sys.stderr)
    return "yt-dlp"


YT_DLP = _find_yt_dlp()


def find_ffmpeg():
    """Find ffmpeg. Checks PATH first, then known platform-specific install location."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, check=True
        )
        return None  # On PATH, yt-dlp finds it automatically
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass

    if os.path.exists(os.path.join(KNOWN_FFMPEG, "ffmpeg.exe")):
        return KNOWN_FFMPEG

    print("ERROR: ffmpeg not found.", file=sys.stderr)
    print("Install via: brew install ffmpeg (macOS), apt install ffmpeg (Linux), or winget install Gyan.FFmpeg (Windows)", file=sys.stderr)
    sys.exit(1)


def get_metadata(url):
    """Extract video metadata via yt-dlp."""
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
        return {"error": f"yt-dlp metadata failed: {result.stderr.strip()}"}

    lines = result.stdout.strip().split("\n")
    duration = 0
    if len(lines) > 2 and lines[2].strip().isdigit():
        duration = int(lines[2].strip())

    video_id = lines[3].strip() if len(lines) > 3 else ""
    upload_date_raw = lines[4].strip() if len(lines) > 4 else ""

    # Format upload_date from YYYYMMDD to YYYY-MM-DD
    published = ""
    if len(upload_date_raw) == 8 and upload_date_raw.isdigit():
        published = f"{upload_date_raw[:4]}-{upload_date_raw[4:6]}-{upload_date_raw[6:8]}"

    # Parse chapters JSON (may be "NA" or empty for videos without chapters)
    chapters = []
    chapters_raw = lines[5].strip() if len(lines) > 5 else ""
    if chapters_raw and chapters_raw not in ("NA", "null", "None"):
        try:
            chapters = json.loads(chapters_raw)
        except json.JSONDecodeError:
            pass

    # Parse description (JSON-encoded to handle multi-line descriptions safely)
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
        "thumbnail": f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg" if video_id else "",
        "chapters": chapters,
        "description": description,
        "url": url,
    }


def sanitize(name):
    """Remove characters invalid in filenames and collapse whitespace."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name)
    return name.strip(". ")[:200]


def download_audio(url, media_dir, filename, ffmpeg_loc):
    """Download audio as MP3 via yt-dlp. Writes to media_dir
    so Obsidian ignores binary files (dot-prefixed folders are hidden)."""
    os.makedirs(media_dir, exist_ok=True)
    output_template = os.path.join(media_dir, f"{filename}.%(ext)s")
    cmd = [
        YT_DLP, "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "-o", output_template,
        url,
    ]
    if ffmpeg_loc:
        cmd[1:1] = ["--ffmpeg-location", ffmpeg_loc]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Download failed: {result.stderr.strip()}")

    expected = os.path.join(media_dir, f"{filename}.mp3")
    if os.path.exists(expected):
        return expected

    # yt-dlp may sanitize the filename differently
    for f in sorted(os.listdir(media_dir), reverse=True):
        if f.endswith(".mp3"):
            return os.path.join(media_dir, f)

    raise RuntimeError("Audio file not found after download")


def split_audio(audio_path, ffmpeg_loc):
    """Split audio into chunks using ffmpeg."""
    ffmpeg_bin = (
        os.path.join(ffmpeg_loc, "ffmpeg.exe") if ffmpeg_loc else "ffmpeg"
    )
    chunk_dir = tempfile.mkdtemp(prefix="digest_")
    pattern = os.path.join(chunk_dir, "chunk_%03d.mp3")

    result = subprocess.run(
        [
            ffmpeg_bin, "-i", audio_path,
            "-f", "segment",
            "-segment_time", str(CHUNK_DURATION),
            "-c", "copy",
            pattern,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Audio split failed: {result.stderr.strip()}")

    chunks = sorted(
        os.path.join(chunk_dir, f)
        for f in os.listdir(chunk_dir)
        if f.endswith(".mp3")
    )
    return chunks


def transcribe(audio_path, ffmpeg_loc):
    """Transcribe audio via Groq Whisper. Chunks automatically if over 25MB."""
    from groq import Groq

    client = Groq(api_key=os.environ["GROQ_API_KEY"])
    file_size = os.path.getsize(audio_path)

    def transcribe_one(path, max_retries=3):
        for attempt in range(max_retries):
            try:
                with open(path, "rb") as f:
                    return client.audio.transcriptions.create(
                        file=(os.path.basename(path), f.read()),
                        model="whisper-large-v3-turbo",
                        response_format="verbose_json",
                        timestamp_granularities=["segment"],
                        language="en",
                    )
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "rate_limit" in error_str.lower():
                    # Parse retry delay from error message
                    wait = 60  # default 60s
                    import re as _re
                    match = _re.search(r"try again in (\d+)m(\d+(?:\.\d+)?)s", error_str)
                    if match:
                        wait = int(match.group(1)) * 60 + float(match.group(2)) + 5
                    else:
                        match = _re.search(r"try again in (\d+(?:\.\d+)?)s", error_str)
                        if match:
                            wait = float(match.group(1)) + 5
                    print(
                        f"    Rate limited. Waiting {wait:.0f}s "
                        f"(attempt {attempt + 1}/{max_retries})...",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                else:
                    raise
        raise RuntimeError(f"Rate limit exceeded after {max_retries} retries")

    if file_size <= MAX_FILE_SIZE:
        print(
            f"Transcribing ({file_size / 1024 / 1024:.1f}MB)...",
            file=sys.stderr,
        )
        result = transcribe_one(audio_path)
        return [
            {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
            for s in result.segments
        ]

    # Chunked transcription for large files
    print(
        f"File {file_size / 1024 / 1024:.1f}MB exceeds 25MB limit. "
        f"Splitting into {CHUNK_DURATION // 60}-min chunks...",
        file=sys.stderr,
    )
    chunks = split_audio(audio_path, ffmpeg_loc)
    all_segments = []

    for i, chunk in enumerate(chunks):
        offset = i * CHUNK_DURATION
        print(
            f"  Chunk {i + 1}/{len(chunks)} (offset {offset}s)...",
            file=sys.stderr,
        )
        result = transcribe_one(chunk)
        for s in result.segments:
            all_segments.append({
                "start": s["start"] + offset,
                "end": s["end"] + offset,
                "text": s["text"].strip(),
            })
        os.remove(chunk)

    # Clean up temp chunk directory
    os.rmdir(os.path.dirname(chunks[0]))
    return all_segments


def format_ts(seconds):
    """Format seconds as [HH:MM:SS] or [MM:SS]."""
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    return f"[{m:02d}:{s:02d}]"


def format_duration(seconds):
    """Format duration for human display."""
    h, remainder = divmod(seconds, 3600)
    m = remainder // 60
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def write_transcript_md(path, metadata, segments, date):
    """Write formatted transcript markdown with frontmatter."""
    duration_str = format_duration(metadata["duration_seconds"])
    lines = [
        "---",
        "type: transcript",
        "source: groq-whisper",
        f"created: {date}",
        f'url: "{metadata["url"]}"',
        f'channel: "{metadata["channel"]}"',
        f'duration: "{duration_str}"',
        f'video-id: "{metadata["video_id"]}"',
        "---",
        f"# {metadata['title']}",
        "",
    ]
    for seg in segments:
        lines.append(f"{format_ts(seg['start'])} {seg['text']}")

    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="YouTube transcription pipeline for /digest skill"
    )
    parser.add_argument("url", help="YouTube video URL (ignored when --local is used)")
    parser.add_argument(
        "--output-dir", default="outputs/transcripts",
        help="Directory for transcript files"
    )
    parser.add_argument(
        "--media-dir", default="outputs/.media",
        help="Directory for audio and media files"
    )
    parser.add_argument(
        "--date", default="unknown",
        help="Date for frontmatter (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--local", default=None,
        help="Local audio file path (skips yt-dlp download)"
    )
    parser.add_argument(
        "--title", default=None,
        help="Title for transcript file (used with --local)"
    )
    args = parser.parse_args()
    _start_time = time.time()

    if "GROQ_API_KEY" not in os.environ:
        print(json.dumps({"error": "GROQ_API_KEY not set"}))
        sys.exit(1)

    os.makedirs(args.output_dir, exist_ok=True)
    ffmpeg_loc = find_ffmpeg()

    if args.local:
        # Local file mode: skip yt-dlp, transcribe directly
        audio_path = args.local
        if not os.path.exists(audio_path):
            print(json.dumps({"error": f"Audio file not found: {audio_path}"}))
            sys.exit(1)

        size_mb = os.path.getsize(audio_path) / 1024 / 1024
        print(f"Local audio: {audio_path} ({size_mb:.1f}MB)", file=sys.stderr)

        # Transcribe
        segments = transcribe(audio_path, ffmpeg_loc)
        print(f"Transcribed: {len(segments)} segments", file=sys.stderr)

        # Calculate duration from segments
        duration_seconds = 0
        if segments:
            duration_seconds = int(segments[-1]["end"])

        # Use provided title or derive from filename
        title = args.title or os.path.splitext(os.path.basename(audio_path))[0]
        safe_title = sanitize(title)

        # Write transcript markdown (minimal metadata)
        transcript_path = os.path.join(args.output_dir, f"{safe_title}.md")
        local_meta = {
            "title": title,
            "channel": "",
            "duration_seconds": duration_seconds,
            "video_id": "",
            "url": "",
        }
        write_transcript_md(transcript_path, local_meta, segments, args.date)
        print(f"Transcript written: {transcript_path}", file=sys.stderr)

        # Output JSON (minimal, no YouTube-specific fields)
        print(json.dumps({
            "audio_path": audio_path.replace("\\", "/"),
            "transcript_path": transcript_path.replace("\\", "/"),
            "segment_count": len(segments),
            "duration_seconds": duration_seconds,
            "duration_formatted": format_duration(duration_seconds),
            "execution_ms": int((time.time() - _start_time) * 1000),
        }, indent=2))
    else:
        # YouTube mode: full yt-dlp pipeline
        # Step 1: Metadata
        print("Fetching metadata...", file=sys.stderr)
        meta = get_metadata(args.url)
        if "error" in meta:
            print(json.dumps(meta))
            sys.exit(1)

        safe_title = sanitize(meta["title"])
        safe_channel = sanitize(meta["channel"])

        # Step 2: Download audio
        print(f"Downloading: {meta['title']}...", file=sys.stderr)
        os.makedirs(args.media_dir, exist_ok=True)
        audio_path = download_audio(
            args.url, args.media_dir, safe_title, ffmpeg_loc
        )
        size_mb = os.path.getsize(audio_path) / 1024 / 1024
        print(f"Audio: {audio_path} ({size_mb:.1f}MB)", file=sys.stderr)

        # Step 3: Transcribe
        segments = transcribe(audio_path, ffmpeg_loc)
        print(f"Transcribed: {len(segments)} segments", file=sys.stderr)

        # Step 4: Write transcript markdown
        transcript_path = os.path.join(args.output_dir, f"{safe_title}.md")
        write_transcript_md(transcript_path, meta, segments, args.date)
        print(f"Transcript written: {transcript_path}", file=sys.stderr)

        # Output compact JSON to stdout
        print(json.dumps({
            "title": meta["title"],
            "channel": meta["channel"],
            "safe_title": safe_title,
            "safe_channel": safe_channel,
            "duration_seconds": meta["duration_seconds"],
            "duration_formatted": format_duration(meta["duration_seconds"]),
            "video_id": meta["video_id"],
            "published": meta.get("published", ""),
            "thumbnail": meta.get("thumbnail", ""),
            "chapters": meta.get("chapters", []),
            "description": meta.get("description", ""),
            "url": meta["url"],
            "audio_path": audio_path.replace("\\", "/"),
            "transcript_path": transcript_path.replace("\\", "/"),
            "segment_count": len(segments),
            "execution_ms": int((time.time() - _start_time) * 1000),
        }, indent=2))


if __name__ == "__main__":
    main()
