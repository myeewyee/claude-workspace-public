#!/usr/bin/env python3
"""
Speaker diarization for /digest skill.
Uploads audio to pyannoteAI, runs diarization, merges speaker labels
into an existing transcript markdown file.

Usage: python diarize.py <audio_path> <transcript_path> [--speakers N]

Modifies the transcript file in-place, inserting [SPEAKER_XX] tags
after each timestamp. Outputs JSON summary to stdout.
Progress and errors go to stderr.

Requires: PYANNOTEAI_API_KEY environment variable.
"""

import argparse
import json
import os
import re
import sys
import time

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests",
          file=sys.stderr)
    sys.exit(1)

API_BASE = "https://api.pyannote.ai/v1"
POLL_INTERVAL = 5  # seconds between status checks


def upload_audio(audio_path, api_key):
    """Upload audio to pyannoteAI temporary storage. Returns media:// URL."""
    # Sanitize filename for use as object key (alphanumeric, hyphens, underscores only)
    safe_name = re.sub(r"[^a-zA-Z0-9_-]", "-", os.path.basename(audio_path)[:80])
    safe_name = re.sub(r"-+", "-", safe_name).strip("-")
    object_key = f"digest-{int(time.time())}-{safe_name}"

    # Get presigned upload URL
    print("  Creating upload slot...", file=sys.stderr)
    resp = requests.post(
        f"{API_BASE}/media/input",
        json={"url": f"media://{object_key}"},
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    if not resp.ok:
        print(f"  Upload slot error {resp.status_code}: {resp.text}", file=sys.stderr)
    resp.raise_for_status()
    presigned_url = resp.json()["url"]

    # Upload file
    file_size = os.path.getsize(audio_path)
    print(f"  Uploading ({file_size / 1024 / 1024:.1f}MB)...", file=sys.stderr)
    with open(audio_path, "rb") as f:
        resp = requests.put(
            presigned_url,
            data=f,
            headers={"Content-Type": "application/octet-stream"},
        )
    resp.raise_for_status()
    print("  Upload complete.", file=sys.stderr)

    return f"media://{object_key}"


def submit_diarization(media_url, api_key, num_speakers=None):
    """Submit diarization job. Returns job ID."""
    data = {"url": media_url, "model": "precision-2"}
    if num_speakers and num_speakers > 0:
        data["numSpeakers"] = num_speakers

    resp = requests.post(
        f"{API_BASE}/diarize",
        json=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    resp.raise_for_status()
    result = resp.json()
    return result["jobId"]


def poll_job(job_id, api_key, timeout=600):
    """Poll until job completes. Returns output dict."""
    start = time.time()
    while True:
        resp = requests.get(
            f"{API_BASE}/jobs/{job_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        result = resp.json()
        status = result.get("status", "unknown")

        if status == "succeeded":
            return result.get("output", {})
        elif status in ("failed", "canceled"):
            raise RuntimeError(
                f"Diarization job {status}: {json.dumps(result, indent=2)}"
            )

        elapsed = time.time() - start
        if elapsed > timeout:
            raise RuntimeError(
                f"Diarization timed out after {timeout}s (status: {status})"
            )

        print(f"  Status: {status} ({elapsed:.0f}s)...", file=sys.stderr)
        time.sleep(POLL_INTERVAL)


def parse_transcript_timestamps(transcript_path):
    """Parse transcript markdown to extract line timestamps.

    Returns list of (line_number, timestamp_seconds, line_text) for
    lines that have [HH:MM:SS] or [MM:SS] timestamps.
    """
    entries = []
    with open(transcript_path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f):
            stripped = line.rstrip("\n")
            m = re.match(r"\[(\d{1,2}):(\d{2}):?(\d{2})?\]\s*(.*)", stripped)
            if m:
                if m.group(3):  # HH:MM:SS
                    secs = (
                        int(m.group(1)) * 3600
                        + int(m.group(2)) * 60
                        + int(m.group(3))
                    )
                else:  # MM:SS
                    secs = int(m.group(1)) * 60 + int(m.group(2))
                entries.append((i, secs, stripped))
    return entries


def find_speaker_at(timestamp, speaker_turns):
    """Find which speaker is active at a given timestamp.

    Uses containment first (timestamp falls within a turn),
    then nearest-start fallback.
    """
    # Containment check
    for turn in speaker_turns:
        if turn["start"] <= timestamp < turn["end"]:
            return turn["speaker"]

    # Nearest start fallback
    if not speaker_turns:
        return "UNKNOWN"
    best = min(speaker_turns, key=lambda t: abs(t["start"] - timestamp))
    return best["speaker"]


def rewrite_transcript(transcript_path, entries, speaker_turns):
    """Rewrite transcript with speaker labels inserted after timestamps.

    [00:05:12] text  ->  [00:05:12] [SPEAKER_00] text
    """
    with open(transcript_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # Build map: line_number -> speaker
    line_speakers = {}
    for line_num, timestamp, _ in entries:
        speaker = find_speaker_at(timestamp, speaker_turns)
        line_speakers[line_num] = speaker

    # Rewrite lines
    new_lines = []
    for i, line in enumerate(lines):
        if i in line_speakers:
            # Skip lines that already have a speaker tag (idempotent)
            if re.search(r'\[SPEAKER_\w+\]', line):
                new_lines.append(line)
                continue
            speaker = line_speakers[i]
            # Insert [SPEAKER_XX] after the timestamp bracket
            new_line = re.sub(
                r"(\[\d{1,2}:\d{2}:?\d{0,2}\])\s*",
                rf"\1 [{speaker}] ",
                line,
                count=1,
            )
            new_lines.append(new_line)
        else:
            new_lines.append(line)

    with open(transcript_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def main():
    parser = argparse.ArgumentParser(
        description="Speaker diarization for /digest skill"
    )
    parser.add_argument("audio_path", help="Path to audio file (MP3, WAV, etc.)")
    parser.add_argument("transcript_path", help="Path to raw transcript .md file")
    parser.add_argument(
        "--speakers",
        type=int,
        default=0,
        help="Expected number of speakers (0 = auto-detect)",
    )
    args = parser.parse_args()
    _start_time = time.time()

    api_key = os.environ.get("PYANNOTE_API_KEY", "") or os.environ.get("PYANNOTEAI_API_KEY", "")
    if not api_key:
        print(json.dumps({"error": "PYANNOTE_API_KEY not set"}))
        sys.exit(1)

    if not os.path.exists(args.audio_path):
        print(json.dumps({"error": f"Audio file not found: {args.audio_path}"}))
        sys.exit(1)

    if not os.path.exists(args.transcript_path):
        print(json.dumps({"error": f"Transcript not found: {args.transcript_path}"}))
        sys.exit(1)

    # Parse transcript to get segment timestamps
    entries = parse_transcript_timestamps(args.transcript_path)
    if not entries:
        print(json.dumps({"error": "No timestamped segments found in transcript"}))
        sys.exit(1)
    print(f"Parsed {len(entries)} transcript segments.", file=sys.stderr)

    # Upload audio to pyannoteAI
    print("Uploading audio to pyannoteAI...", file=sys.stderr)
    media_url = upload_audio(args.audio_path, api_key)

    # Submit diarization job
    print("Submitting diarization job...", file=sys.stderr)
    job_id = submit_diarization(
        media_url, api_key,
        num_speakers=args.speakers if args.speakers > 0 else None,
    )
    print(f"Job ID: {job_id}", file=sys.stderr)

    # Poll for results
    print("Waiting for diarization...", file=sys.stderr)
    output = poll_job(job_id, api_key)

    # Extract speaker turns from output
    # pyannoteAI returns: {"diarization": [{"start": 0.5, "end": 5.2, "speaker": "SPEAKER_00"}, ...]}
    # or possibly under "output" key with different structure
    speaker_turns = []
    if "diarization" in output:
        speaker_turns = output["diarization"]
    elif isinstance(output, list):
        speaker_turns = output
    else:
        # Try to find the segments in the output
        for key in output:
            if isinstance(output[key], list) and output[key]:
                first = output[key][0]
                if isinstance(first, dict) and "speaker" in first:
                    speaker_turns = output[key]
                    break

    if not speaker_turns:
        print(json.dumps({
            "error": "No speaker segments in diarization output",
            "raw_output": output,
        }))
        sys.exit(1)

    # Collect unique speakers
    speakers = sorted(set(t["speaker"] for t in speaker_turns))
    print(
        f"Diarization complete: {len(speaker_turns)} turns, "
        f"{len(speakers)} speakers ({', '.join(speakers)}).",
        file=sys.stderr,
    )

    # Merge speaker labels into transcript
    print("Merging speaker labels into transcript...", file=sys.stderr)
    rewrite_transcript(args.transcript_path, entries, speaker_turns)
    print(f"Transcript updated: {args.transcript_path}", file=sys.stderr)

    # Output summary JSON
    print(json.dumps({
        "num_speakers": len(speakers),
        "speakers": speakers,
        "num_turns": len(speaker_turns),
        "transcript_path": args.transcript_path.replace("\\", "/"),
        "execution_ms": int((time.time() - _start_time) * 1000),
    }, indent=2))


if __name__ == "__main__":
    main()
