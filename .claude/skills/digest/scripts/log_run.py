#!/usr/bin/env python3
"""Append a digest run entry to the JSONL run log.

Usage:
    python log_run.py \
        --url "https://..." --mode quick --pipeline youtube \
        --title "Video Title" --video-id "abc123" \
        --caption-source youtube-api \
        --output-file "outputs/digests/Title.md" \
        --step fetch=3200 --step agent=38100 --step assemble=2400

Each --step is name=milliseconds. Total duration is computed from steps.
Run ID format: d<YYYYMMDD>-<HHMM>-<4hex> (date-time plus random suffix).
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime

LOG_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
LOG_FILE = os.path.join(LOG_DIR, "run-log.jsonl")


def generate_run_id():
    """Generate a unique run ID: d<YYYYMMDD>-<HHMM>-<4hex>."""
    now = datetime.now()
    suffix = f"{random.randint(0, 0xFFFF):04x}"
    return f"d{now.strftime('%Y%m%d')}-{now.strftime('%H%M')}-{suffix}"


def parse_step(step_str):
    """Parse 'name=ms' into (name, milliseconds)."""
    if "=" not in step_str:
        raise ValueError(f"Step must be name=ms, got: {step_str}")
    name, ms_str = step_str.split("=", 1)
    return name.strip(), int(ms_str.strip())


def main():
    parser = argparse.ArgumentParser(description="Log a digest run")
    parser.add_argument("--url", required=True, help="Source URL")
    parser.add_argument("--mode", required=True, help="quick or full")
    parser.add_argument("--pipeline", required=True,
                        help="youtube, blog, x-twitter, podcast, audio")
    parser.add_argument("--title", default="", help="Content title")
    parser.add_argument("--video-id", default="", help="YouTube video ID")
    parser.add_argument("--caption-source", default="",
                        help="Caption source layer (youtube-api, yt-dlp, apify, whisper)")
    parser.add_argument("--output-file", default="", help="Output digest path")
    parser.add_argument("--step", action="append", default=[],
                        help="Step timing as name=ms (repeatable)")
    args = parser.parse_args()

    # Parse steps
    steps = {}
    for s in args.step:
        name, ms = parse_step(s)
        steps[name] = round(ms / 1000, 1)  # Store as seconds

    total_s = round(sum(steps.values()), 1)

    entry = {
        "run_id": generate_run_id(),
        "url": args.url,
        "video_id": args.video_id,
        "title": args.title,
        "date": datetime.now().strftime("%Y-%m-%d"),
        "time": datetime.now().strftime("%H:%M"),
        "mode": args.mode,
        "pipeline": args.pipeline,
        "caption_source": args.caption_source,
        "duration_s": total_s,
        "steps": steps,
        "output_file": args.output_file.replace("\\", "/"),
    }

    # Remove empty optional fields
    entry = {k: v for k, v in entry.items() if v != "" and v != {}}

    os.makedirs(LOG_DIR, exist_ok=True)

    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")

    print(f"Logged run {entry['run_id']}: {args.mode}/{args.pipeline} "
          f"{total_s}s", file=sys.stderr)
    # Echo the run_id to stdout for the caller
    print(entry["run_id"])


if __name__ == "__main__":
    main()
