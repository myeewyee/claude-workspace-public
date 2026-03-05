#!/usr/bin/env python3
"""
YouTube channel browser: list recent videos from any YouTube channel.

Uses the YouTube Data API v3 to fetch channel metadata and video listings.

Usage:
    # Browse by channel handle:
    python .scripts/youtube-browse.py @LiamOttley

    # Browse by full URL:
    python .scripts/youtube-browse.py "https://www.youtube.com/@LiamOttley"

    # Browse by channel ID:
    python .scripts/youtube-browse.py UCui4jxDaMb53Gdh-AZUTPAg

    # Limit results:
    python .scripts/youtube-browse.py @LiamOttley --max 5

    # Filter to last 3 months:
    python .scripts/youtube-browse.py @LiamOttley --months 3

    # Sort by views instead of date:
    python .scripts/youtube-browse.py @LiamOttley --sort views

    # Fetch ALL videos (paginated):
    python .scripts/youtube-browse.py @LiamOttley --all

Environment variables:
    YOUTUBE_API_KEY - YouTube Data API v3 key
                     (https://console.cloud.google.com/apis/credentials)

    On Windows, if env vars aren't in the current shell, the script reads them
    from Windows User environment variables automatically.
"""

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

API_BASE = "https://www.googleapis.com/youtube/v3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_env(name):
    """Get an environment variable, falling back to Windows registry on Windows."""
    val = os.environ.get(name)
    if val:
        return val

    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["powershell", "-Command",
                 f"[System.Environment]::GetEnvironmentVariable('{name}', 'User')"],
                capture_output=True, text=True, timeout=10
            )
            val = result.stdout.strip()
            if val:
                return val
        except Exception:
            pass

    return None


def get_youtube_key():
    """Get the YouTube API key or raise."""
    key = get_env("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError(
            "YOUTUBE_API_KEY not set. Get one at: "
            "https://console.cloud.google.com/apis/credentials"
        )
    return key


def api_request(url, *, timeout=30):
    """Make an HTTP GET request and return parsed JSON."""
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e


def log(msg):
    """Print a status message to stderr."""
    print(f"[youtube-browse] {msg}", file=sys.stderr)


def parse_duration(iso_duration):
    """Convert ISO 8601 duration (PT#H#M#S) to human-readable string."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso_duration or "")
    if not m:
        return "0:00"
    hrs = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    secs = int(m.group(3) or 0)
    if hrs:
        return f"{hrs}:{mins:02d}:{secs:02d}"
    return f"{mins}:{secs:02d}"


def parse_channel_input(raw):
    """Extract channel identifier and type from user input.

    Returns (identifier, id_type) where id_type is one of:
        'handle'  - @Handle format
        'id'      - UC... channel ID
        'url'     - full URL (will be further parsed)
        'search'  - free text to search for
    """
    raw = raw.strip()

    # Full URL
    if "youtube.com" in raw or "youtu.be" in raw:
        # Extract handle from URL: youtube.com/@Handle
        handle_match = re.search(r"youtube\.com/@([\w.-]+)", raw)
        if handle_match:
            return "@" + handle_match.group(1), "handle"

        # Extract channel ID from URL: youtube.com/channel/UCxxx
        id_match = re.search(r"youtube\.com/channel/(UC[\w-]+)", raw)
        if id_match:
            return id_match.group(1), "id"

        # Custom URL: youtube.com/c/Name
        custom_match = re.search(r"youtube\.com/c/([\w.-]+)", raw)
        if custom_match:
            return custom_match.group(1), "search"

    # Bare handle
    if raw.startswith("@"):
        return raw, "handle"

    # Channel ID (starts with UC, 24 chars)
    if raw.startswith("UC") and len(raw) == 24:
        return raw, "id"

    # Fallback: search by name
    return raw, "search"


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def resolve_channel(identifier, id_type, key):
    """Resolve a channel identifier to channel metadata.

    Returns dict with: id, title, subscriber_count, video_count, created,
    uploads_playlist_id.
    """
    if id_type == "handle":
        handle = identifier.lstrip("@")
        url = (f"{API_BASE}/channels?part=snippet,contentDetails,statistics"
               f"&forHandle={urllib.parse.quote(handle)}&key={key}")
    elif id_type == "id":
        url = (f"{API_BASE}/channels?part=snippet,contentDetails,statistics"
               f"&id={urllib.parse.quote(identifier)}&key={key}")
    elif id_type == "search":
        # Search for the channel, then resolve by ID
        search_url = (f"{API_BASE}/search?part=snippet&type=channel"
                      f"&q={urllib.parse.quote(identifier)}&maxResults=1&key={key}")
        search_data = api_request(search_url)
        if not search_data.get("items"):
            raise RuntimeError(f"No channel found for: {identifier}")
        channel_id = search_data["items"][0]["snippet"]["channelId"]
        url = (f"{API_BASE}/channels?part=snippet,contentDetails,statistics"
               f"&id={channel_id}&key={key}")
    else:
        raise RuntimeError(f"Unknown id_type: {id_type}")

    data = api_request(url)
    if not data.get("items"):
        raise RuntimeError(f"No channel found for: {identifier}")

    ch = data["items"][0]
    stats = ch.get("statistics", {})
    return {
        "id": ch["id"],
        "title": ch["snippet"]["title"],
        "subscriber_count": int(stats.get("subscriberCount", 0)),
        "video_count": int(stats.get("videoCount", 0)),
        "created": ch["snippet"].get("publishedAt", ""),
        "uploads_playlist_id": ch["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def fetch_video_ids(playlist_id, key, *, max_results=15, fetch_all=False):
    """Fetch video IDs from an uploads playlist.

    Returns list of (video_id, published_at) tuples.
    """
    videos = []
    page_token = None
    per_page = min(max_results, 50) if not fetch_all else 50

    while True:
        url = (f"{API_BASE}/playlistItems?part=snippet"
               f"&playlistId={playlist_id}"
               f"&maxResults={per_page}&key={key}")
        if page_token:
            url += f"&pageToken={page_token}"

        data = api_request(url)

        for item in data.get("items", []):
            vid_id = item["snippet"]["resourceId"].get("videoId")
            published = item["snippet"].get("publishedAt", "")
            if vid_id:
                videos.append((vid_id, published))

        if not fetch_all and len(videos) >= max_results:
            videos = videos[:max_results]
            break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

        log(f"Fetched {len(videos)} video IDs so far...")

    return videos


def fetch_video_details(video_ids, key):
    """Fetch full details for a list of video IDs.

    Batches into groups of 50 (API limit).
    Returns list of video detail dicts.
    """
    details = []

    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        ids_str = ",".join(batch)
        url = (f"{API_BASE}/videos?part=snippet,statistics,contentDetails"
               f"&id={ids_str}&key={key}")
        data = api_request(url)

        for v in data.get("items", []):
            stats = v.get("statistics", {})
            details.append({
                "title": v["snippet"]["title"],
                "video_id": v["id"],
                "url": f"https://www.youtube.com/watch?v={v['id']}",
                "published": v["snippet"].get("publishedAt", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "like_count": int(stats.get("likeCount", 0)),
                "duration": parse_duration(v["contentDetails"].get("duration")),
                "duration_raw": v["contentDetails"].get("duration", ""),
            })

    return details


# ---------------------------------------------------------------------------
# Main logic
# ---------------------------------------------------------------------------

def browse_channel(channel_input, *, max_results=15, months=None,
                   sort_by="date", fetch_all=False):
    """Browse a YouTube channel's videos.

    Returns a JSON-serializable dict with channel metadata and video list.
    """
    key = get_youtube_key()

    # Resolve channel
    identifier, id_type = parse_channel_input(channel_input)
    log(f"Resolving channel: {identifier} (type: {id_type})")
    channel = resolve_channel(identifier, id_type, key)
    log(f"Channel: {channel['title']} ({channel['id']})")

    # Determine how many to fetch
    if fetch_all:
        log(f"Fetching all {channel['video_count']} videos...")
        effective_max = channel["video_count"]
    else:
        effective_max = max_results

    # If filtering by months, we may need more than max_results initially
    if months and not fetch_all:
        # Fetch extra to account for filtering, cap at 200
        effective_max = min(max_results * 3, 200)

    # Fetch video IDs
    video_entries = fetch_video_ids(
        channel["uploads_playlist_id"], key,
        max_results=effective_max, fetch_all=fetch_all
    )
    log(f"Got {len(video_entries)} video IDs")

    # Fetch full details
    all_ids = [vid_id for vid_id, _ in video_entries]
    videos = fetch_video_details(all_ids, key)
    log(f"Got {len(videos)} video details")

    # Filter by months
    if months:
        cutoff = datetime.now(timezone.utc)
        # Subtract months (approximate: 30 days per month)
        from datetime import timedelta
        cutoff = cutoff - timedelta(days=months * 30)
        cutoff_iso = cutoff.isoformat()

        before = len(videos)
        videos = [v for v in videos if v["published"] >= cutoff_iso]
        log(f"Filtered to last {months} months: {before} -> {len(videos)} videos")

    # Sort
    if sort_by == "views":
        videos.sort(key=lambda v: v["view_count"], reverse=True)
    else:
        videos.sort(key=lambda v: v["published"], reverse=True)

    # Apply max_results after filtering (if not --all)
    if not fetch_all and len(videos) > max_results:
        videos = videos[:max_results]

    return {
        "channel": {
            "title": channel["title"],
            "id": channel["id"],
            "subscriber_count": channel["subscriber_count"],
            "video_count": channel["video_count"],
            "created": channel["created"],
        },
        "videos": videos,
        "video_count": len(videos),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Browse YouTube channel videos via Data API v3.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
    python .scripts/youtube-browse.py @LiamOttley
    python .scripts/youtube-browse.py "https://www.youtube.com/@LiamOttley"
    python .scripts/youtube-browse.py @LiamOttley --max 5 --sort views
    python .scripts/youtube-browse.py @LiamOttley --months 3
    python .scripts/youtube-browse.py @LiamOttley --all
""",
    )
    parser.add_argument(
        "channel",
        help="Channel handle (@Name), URL, channel ID (UCxxx), or name to search",
    )
    parser.add_argument(
        "--max", type=int, default=15, dest="max_results",
        help="Maximum number of videos to return (default: 15)",
    )
    parser.add_argument(
        "--months", type=int, default=None,
        help="Only include videos from the last N months",
    )
    parser.add_argument(
        "--sort", choices=["date", "views"], default="date",
        help="Sort order: date (newest first) or views (most viewed first)",
    )
    parser.add_argument(
        "--all", action="store_true", dest="fetch_all",
        help="Fetch all videos from the channel (paginated)",
    )

    args = parser.parse_args()

    try:
        result = browse_channel(
            args.channel,
            max_results=args.max_results,
            months=args.months,
            sort_by=args.sort,
            fetch_all=args.fetch_all,
        )
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except RuntimeError as e:
        log(f"Error: {e}")
        sys.exit(1)
    except urllib.error.URLError as e:
        log(f"Network error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
