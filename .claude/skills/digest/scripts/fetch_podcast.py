#!/usr/bin/env python3
"""
Podcast episode fetcher for /digest skill.
Detects podcast platform, resolves RSS feed, matches episode,
downloads audio for transcription.

Uses stdlib only (xml.etree.ElementTree, urllib).
Outputs compact JSON to stdout. Progress/errors go to stderr.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from urllib.parse import urlparse, urljoin


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


# Known podcast platform URL patterns
PLATFORM_PATTERNS = [
    ("apple", re.compile(
        r"https?://podcasts\.apple\.com/(?:[^/]+/)?podcast(?:/[^/]+){1,2}"
    )),
    ("spotify", re.compile(
        r"https?://open\.spotify\.com/(show|episode)/([a-zA-Z0-9]+)"
    )),
    ("buzzsprout", re.compile(
        r"https?://www\.buzzsprout\.com/(\d+)/(\d+)"
    )),
    ("libsyn", re.compile(
        r"https?://[^/]+\.libsyn\.com/"
    )),
    ("podbean", re.compile(
        r"https?://[^/]+\.podbean\.com/e/"
    )),
    ("transistor", re.compile(
        r"https?://share\.transistor\.fm/"
    )),
    ("simplecast", re.compile(
        r"https?://player\.simplecast\.com/[a-f0-9-]+"
    )),
    ("megaphone", re.compile(
        r"https?://player\.megaphone\.fm/"
    )),
    ("acast", re.compile(
        r"https?://(shows|embed)\.acast\.com/"
    )),
    ("spreaker", re.compile(
        r"https?://www\.spreaker\.com/episode/"
    )),
    ("overcast", re.compile(
        r"https?://overcast\.fm/\+"
    )),
    ("pocketcasts", re.compile(
        r"https?://pca\.st/"
    )),
]

# Known podcast player iframe/embed domains
PODCAST_PLAYER_DOMAINS = [
    "play.libsyn.com",
    "html5-player.libsyn.com",
    "player.megaphone.fm",
    "player.simplecast.com",
    "share.transistor.fm",
    "embed.acast.com",
    "widget.spreaker.com",
    "open.spotify.com/embed/episode",
    "open.spotify.com/embed-podcast",
    "embed.podcasts.apple.com",
    "www.podbean.com/player-v2",
]

# iTunes namespace
ITUNES_NS = "http://www.itunes.com/dtds/podcast-1.0.dtd"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


def sanitize(name):
    """Remove invalid filename characters."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120]


def detect_platform(url):
    """Check URL against known podcast platform patterns.
    Returns (platform_name, match) or (None, None)."""
    for name, pattern in PLATFORM_PATTERNS:
        m = pattern.search(url)
        if m:
            return name, m
    return None, None


def fetch_url(url, timeout=30, max_size=10 * 1024 * 1024):
    """Fetch URL content with timeout and size guard."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    resp = urllib.request.urlopen(req, timeout=timeout)

    content_length = resp.headers.get("Content-Length")
    if content_length and int(content_length) > max_size:
        raise ValueError(f"Response too large: {int(content_length)} bytes")

    return resp.read()


def resolve_rss_from_apple(url):
    """Extract show ID from Apple Podcasts URL, look up RSS via iTunes API."""
    # Extract show ID: podcasts.apple.com/.../id{show_id}
    m = re.search(r"/id(\d+)", url)
    if not m:
        return None

    show_id = m.group(1)
    api_url = (
        f"https://itunes.apple.com/lookup"
        f"?id={show_id}&entity=podcast"
    )

    print(f"  Looking up Apple Podcasts ID {show_id}...", file=sys.stderr)
    try:
        data = fetch_url(api_url, timeout=10)
        result = json.loads(data)
        if result.get("resultCount", 0) > 0:
            feed_url = result["results"][0].get("feedUrl")
            if feed_url:
                print(f"  Found RSS: {feed_url}", file=sys.stderr)
                return feed_url
    except Exception as e:
        print(f"  Apple lookup failed: {e}", file=sys.stderr)

    return None


def resolve_rss_from_spotify(url):
    """Try to find RSS for a Spotify podcast by searching iTunes."""
    # Extract show/episode metadata from Spotify oEmbed
    oembed_url = f"https://open.spotify.com/oembed?url={url}"
    show_name = None

    try:
        data = fetch_url(oembed_url, timeout=10)
        result = json.loads(data)
        show_name = result.get("provider_name")
        if not show_name:
            # Try title, which might be "Episode - Show"
            title = result.get("title", "")
            if " - " in title:
                show_name = title.split(" - ")[-1].strip()
    except Exception as e:
        print(f"  Spotify oEmbed failed: {e}", file=sys.stderr)

    if not show_name:
        return None, None

    # Search iTunes for the show
    search_url = (
        f"https://itunes.apple.com/search"
        f"?term={urllib.request.quote(show_name)}"
        f"&entity=podcast&limit=5"
    )

    print(
        f"  Searching iTunes for '{show_name}'...",
        file=sys.stderr,
    )
    try:
        data = fetch_url(search_url, timeout=10)
        result = json.loads(data)
        for item in result.get("results", []):
            # Fuzzy match: check if show names are close enough
            itunes_name = item.get("collectionName", "").lower()
            if (
                show_name.lower() in itunes_name
                or itunes_name in show_name.lower()
            ):
                feed_url = item.get("feedUrl")
                if feed_url:
                    print(f"  Found RSS: {feed_url}", file=sys.stderr)
                    return feed_url, show_name
    except Exception as e:
        print(f"  iTunes search failed: {e}", file=sys.stderr)

    return None, show_name


def find_rss_from_page(url, html=None):
    """Find RSS feed URL from a web page.
    Checks link tags and probes common paths."""
    if html is None:
        try:
            html = fetch_url(url, timeout=15).decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  Page fetch failed: {e}", file=sys.stderr)
            return None

    # Check <link rel="alternate" type="application/rss+xml">
    rss_links = re.findall(
        r'<link[^>]+type=["\']application/rss\+xml["\'][^>]*'
        r'href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not rss_links:
        # Try reversed attribute order
        rss_links = re.findall(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]*'
            r'type=["\']application/rss\+xml["\']',
            html, re.IGNORECASE,
        )

    if rss_links:
        rss_url = rss_links[0]
        if not rss_url.startswith("http"):
            rss_url = urljoin(url, rss_url)
        print(f"  Found RSS link in HTML: {rss_url}", file=sys.stderr)
        return rss_url

    # Check for known hosting platform URLs in page
    # Buzzsprout: feeds.buzzsprout.com/{pod_id}.rss
    bz_match = re.search(
        r'buzzsprout\.com/(\d+)', html
    )
    if bz_match:
        pod_id = bz_match.group(1)
        rss_url = f"https://feeds.buzzsprout.com/{pod_id}.rss"
        print(f"  Derived Buzzsprout RSS: {rss_url}", file=sys.stderr)
        return rss_url

    # Libsyn: check for libsyn player/traffic URLs
    lib_match = re.search(
        r'(?:play|traffic|html5-player)\.libsyn\.com', html
    )
    if lib_match:
        # Libsyn RSS is typically at the show's subdomain /rss
        parsed = urlparse(url)
        rss_url = f"{parsed.scheme}://{parsed.netloc}/rss"
        print(
            f"  Detected Libsyn, trying RSS at: {rss_url}",
            file=sys.stderr,
        )
        return rss_url

    # Probe common RSS paths
    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"
    common_paths = ["/feed", "/rss", "/feed.xml", "/podcast.xml"]

    for path in common_paths:
        probe_url = base + path
        try:
            req = urllib.request.Request(
                probe_url,
                headers={"User-Agent": USER_AGENT},
                method="HEAD",
            )
            resp = urllib.request.urlopen(req, timeout=5)
            content_type = resp.headers.get("Content-Type", "")
            if "xml" in content_type or "rss" in content_type:
                print(
                    f"  Found RSS at common path: {probe_url}",
                    file=sys.stderr,
                )
                return probe_url
        except Exception:
            continue

    return None


def parse_rss(rss_url):
    """Parse RSS feed and extract show + episode metadata."""
    print(f"  Parsing RSS feed...", file=sys.stderr)
    data = fetch_url(rss_url, timeout=30, max_size=20 * 1024 * 1024)
    root = ET.fromstring(data)

    channel = root.find("channel")
    if channel is None:
        raise ValueError("Invalid RSS feed: no <channel> element")

    # Show-level metadata
    show_name = ""
    show_image = ""

    title_el = channel.find("title")
    if title_el is not None and title_el.text:
        show_name = title_el.text.strip()

    # iTunes image (preferred, higher resolution)
    itunes_img = channel.find(f"{{{ITUNES_NS}}}image")
    if itunes_img is not None:
        show_image = itunes_img.get("href", "")
    else:
        # Fallback to standard RSS image
        img_el = channel.find("image/url")
        if img_el is not None and img_el.text:
            show_image = img_el.text.strip()

    # Parse episodes
    episodes = []
    for item in channel.findall("item"):
        ep = {}

        title_el = item.find("title")
        ep["title"] = title_el.text.strip() if title_el is not None and title_el.text else ""

        link_el = item.find("link")
        ep["link"] = link_el.text.strip() if link_el is not None and link_el.text else ""

        guid_el = item.find("guid")
        ep["guid"] = guid_el.text.strip() if guid_el is not None and guid_el.text else ""

        pub_el = item.find("pubDate")
        ep["pub_date"] = pub_el.text.strip() if pub_el is not None and pub_el.text else ""

        # Duration from itunes:duration
        dur_el = item.find(f"{{{ITUNES_NS}}}duration")
        ep["duration"] = dur_el.text.strip() if dur_el is not None and dur_el.text else ""

        # Enclosure (audio file)
        enc_el = item.find("enclosure")
        if enc_el is not None:
            ep["enclosure_url"] = enc_el.get("url", "")
            ep["enclosure_type"] = enc_el.get("type", "")
        else:
            ep["enclosure_url"] = ""
            ep["enclosure_type"] = ""

        # Description
        desc_el = item.find("description")
        ep["description"] = desc_el.text.strip() if desc_el is not None and desc_el.text else ""

        episodes.append(ep)

    print(
        f"  Found {len(episodes)} episodes in '{show_name}'",
        file=sys.stderr,
    )
    return {
        "show_name": show_name,
        "show_image": show_image,
        "episodes": episodes,
    }


def parse_duration(duration_str):
    """Parse iTunes duration string to seconds.
    Formats: 'HH:MM:SS', 'MM:SS', or plain seconds."""
    if not duration_str:
        return 0

    # Plain seconds
    if duration_str.isdigit():
        return int(duration_str)

    parts = duration_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass

    return 0


def format_duration(seconds):
    """Format seconds as human-readable duration."""
    if seconds <= 0:
        return ""
    h, remainder = divmod(seconds, 3600)
    m = remainder // 60
    if h:
        return f"{h}h {m}m"
    return f"{m}m"


def parse_pub_date(pub_date_str):
    """Parse RSS pubDate to YYYY-MM-DD HH:mm (includes time when available)."""
    if not pub_date_str:
        return ""

    # RFC 2822 format: "Mon, 01 Jan 2026 00:00:00 +0000"
    # Try multiple formats. Formats with time info return HH:mm, date-only returns date-only.
    formats_with_time = [
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ]
    formats_date_only = [
        "%Y-%m-%d",
    ]

    for fmt in formats_with_time:
        try:
            dt = datetime.strptime(pub_date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            continue

    for fmt in formats_date_only:
        try:
            dt = datetime.strptime(pub_date_str.strip(), fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Last resort: extract YYYY-MM-DD pattern
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", pub_date_str)
    if m:
        return m.group(0)

    return ""


def extract_slug(url):
    """Extract the last meaningful path segment from a URL for matching."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    if not path:
        return ""
    slug = path.split("/")[-1]
    # Remove common extensions
    slug = re.sub(r"\.(html?|php|aspx?)$", "", slug, flags=re.IGNORECASE)
    return slug.lower()


def match_episode(episodes, url, title_hint=None):
    """Match a specific episode from the RSS feed.
    Priority: URL slug match, title match, most recent."""

    if not episodes:
        return None

    slug = extract_slug(url)

    # Strategy 1: URL slug match against episode links/guids
    if slug and len(slug) > 3:
        for ep in episodes:
            ep_link_slug = extract_slug(ep.get("link", ""))
            ep_guid_slug = extract_slug(ep.get("guid", ""))
            if slug in ep_link_slug or ep_link_slug in slug:
                print(
                    f"  Matched by link slug: '{ep['title']}'",
                    file=sys.stderr,
                )
                return ep
            if slug in ep_guid_slug or ep_guid_slug in slug:
                print(
                    f"  Matched by guid slug: '{ep['title']}'",
                    file=sys.stderr,
                )
                return ep

        # Partial slug match: check if slug words appear in episode link/guid
        slug_words = set(re.split(r"[-_]", slug))
        slug_words = {w for w in slug_words if len(w) > 3}
        if slug_words:
            best_match = None
            best_score = 0
            for ep in episodes:
                ep_slug = extract_slug(ep.get("link", ""))
                ep_words = set(re.split(r"[-_]", ep_slug))
                overlap = len(slug_words & ep_words)
                if overlap > best_score:
                    best_score = overlap
                    best_match = ep
            if best_match and best_score >= 2:
                print(
                    f"  Matched by slug words ({best_score} overlap): "
                    f"'{best_match['title']}'",
                    file=sys.stderr,
                )
                return best_match

    # Strategy 2: Title hint match
    if title_hint:
        title_lower = title_hint.lower()
        for ep in episodes:
            if title_lower in ep.get("title", "").lower():
                print(
                    f"  Matched by title hint: '{ep['title']}'",
                    file=sys.stderr,
                )
                return ep
            if ep.get("title", "").lower() in title_lower:
                print(
                    f"  Matched by reverse title: '{ep['title']}'",
                    file=sys.stderr,
                )
                return ep

    # Strategy 3: Most recent episode
    print("  No slug/title match, using most recent episode", file=sys.stderr)
    return episodes[0]


def download_audio(enclosure_url, media_dir, safe_filename):
    """Download audio file from enclosure URL.
    Follows redirects (podcast analytics chains)."""
    os.makedirs(media_dir, exist_ok=True)

    # Determine extension from URL or default to .mp3
    ext = ".mp3"
    url_path = urlparse(enclosure_url).path.lower()
    if url_path.endswith(".m4a"):
        ext = ".m4a"
    elif url_path.endswith(".ogg"):
        ext = ".ogg"

    filename = f"{safe_filename}{ext}"
    filepath = os.path.join(media_dir, filename)

    # Skip if already downloaded
    if os.path.exists(filepath) and os.path.getsize(filepath) > 1000:
        print(
            f"  Audio already exists: {filepath} "
            f"({os.path.getsize(filepath) / 1024 / 1024:.1f}MB)",
            file=sys.stderr,
        )
        return filepath

    print(f"  Downloading audio...", file=sys.stderr)
    req = urllib.request.Request(
        enclosure_url,
        headers={"User-Agent": USER_AGENT},
    )

    resp = urllib.request.urlopen(req, timeout=300)
    content_length = resp.headers.get("Content-Length")
    if content_length:
        print(
            f"  Size: {int(content_length) / 1024 / 1024:.1f}MB",
            file=sys.stderr,
        )

    # Stream download to file
    with open(filepath, "wb") as f:
        while True:
            chunk = resp.read(1024 * 1024)  # 1MB chunks
            if not chunk:
                break
            f.write(chunk)

    size_mb = os.path.getsize(filepath) / 1024 / 1024
    print(f"  Downloaded: {filepath} ({size_mb:.1f}MB)", file=sys.stderr)
    return filepath


def try_ytdlp(url, media_dir, safe_filename):
    """Fallback: try yt-dlp for URLs it might support
    (Apple Podcasts, SoundCloud, RSS feeds)."""
    print("  Trying yt-dlp fallback...", file=sys.stderr)
    os.makedirs(media_dir, exist_ok=True)

    output_template = os.path.join(media_dir, f"{safe_filename}.%(ext)s")

    try:
        # First check if yt-dlp can handle this URL
        result = subprocess.run(
            [
                YT_DLP,
                "--print", "title",
                "--print", "duration",
                "--no-download",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            print(
                f"  yt-dlp cannot handle this URL",
                file=sys.stderr,
            )
            return None, {}

        lines = result.stdout.strip().split("\n")
        title = lines[0] if lines else ""
        duration = 0
        if len(lines) > 1:
            try:
                duration = int(float(lines[1]))
            except (ValueError, IndexError):
                pass

        # Download audio
        dl_result = subprocess.run(
            [
                YT_DLP,
                "-x",
                "--audio-format", "mp3",
                "-o", output_template,
                url,
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )

        if dl_result.returncode != 0:
            print(
                f"  yt-dlp download failed: {dl_result.stderr[:200]}",
                file=sys.stderr,
            )
            return None, {}

        # Find the downloaded file
        audio_path = os.path.join(media_dir, f"{safe_filename}.mp3")
        if not os.path.exists(audio_path):
            # yt-dlp might sanitize filename differently
            for f in os.listdir(media_dir):
                if f.startswith(safe_filename[:20]) and f.endswith(".mp3"):
                    audio_path = os.path.join(media_dir, f)
                    break

        if os.path.exists(audio_path):
            print(
                f"  yt-dlp downloaded: {audio_path}",
                file=sys.stderr,
            )
            return audio_path, {
                "title": title,
                "duration_seconds": duration,
            }

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        print(f"  yt-dlp fallback failed: {e}", file=sys.stderr)

    return None, {}


def main():
    parser = argparse.ArgumentParser(
        description="Podcast episode fetcher for /digest skill"
    )
    parser.add_argument("url", help="Podcast episode URL")
    parser.add_argument(
        "--rss", default=None,
        help="RSS feed URL (hint from detection phase)",
    )
    parser.add_argument(
        "--audio-url", default=None,
        help="Direct audio URL (hint from detection phase)",
    )
    parser.add_argument(
        "--show-name", default=None,
        help="Show name (hint from detection phase)",
    )
    parser.add_argument(
        "--episode-title", default=None,
        help="Episode title (hint from detection phase)",
    )
    parser.add_argument(
        "--chapters", default=None,
        help="Pre-built chapters JSON string (from show notes). "
             "Passed through to output unchanged.",
    )
    parser.add_argument(
        "--date", required=True,
        help="Date for frontmatter (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--time", required=True,
        help="Time for frontmatter (HH:MM)",
    )
    args = parser.parse_args()

    media_dir = "outputs/.media"
    url = args.url
    _start_time = time.time()

    print(f"Fetching podcast: {url}", file=sys.stderr)

    # Detect platform
    platform, platform_match = detect_platform(url)
    if platform:
        print(f"  Platform detected: {platform}", file=sys.stderr)

    # Resolution strategy
    rss_url = args.rss
    audio_url = args.audio_url
    show_name = args.show_name
    episode_title = args.episode_title
    show_image = ""
    episode = None

    # Strategy 1: Direct audio URL provided
    if audio_url:
        print("  Using provided audio URL", file=sys.stderr)
        safe_name = sanitize(episode_title or "podcast_episode")
        audio_path = download_audio(audio_url, media_dir, safe_name)
        # Minimal metadata, try RSS for more
        if rss_url:
            try:
                feed = parse_rss(rss_url)
                show_name = show_name or feed["show_name"]
                show_image = feed["show_image"]
                episode = match_episode(
                    feed["episodes"], url, episode_title
                )
            except Exception as e:
                print(f"  RSS parse failed: {e}", file=sys.stderr)

    else:
        # Strategy 2: RSS provided
        if not rss_url:
            # Strategy 3: Platform-specific RSS resolution
            if platform == "apple":
                rss_url = resolve_rss_from_apple(url)
            elif platform == "spotify":
                rss_url, spotify_show = resolve_rss_from_spotify(url)
                show_name = show_name or spotify_show
                if not rss_url:
                    print(json.dumps({
                        "error": (
                            "Spotify podcast detected but no public RSS feed "
                            "found. This may be a Spotify exclusive. "
                            "Try finding the episode on YouTube or the "
                            "podcast's own website instead."
                        ),
                        "show_name": show_name or "",
                        "platform": "spotify",
                    }))
                    sys.exit(1)
            else:
                # Strategy 4: Find RSS from page
                rss_url = find_rss_from_page(url)

        # Parse RSS and match episode
        if rss_url:
            try:
                feed = parse_rss(rss_url)
                show_name = show_name or feed["show_name"]
                show_image = feed["show_image"]
                episode = match_episode(
                    feed["episodes"], url, episode_title
                )

                if episode and episode["enclosure_url"]:
                    safe_name = sanitize(
                        f"{show_name} - {episode['title']}"
                        if show_name
                        else episode["title"]
                    )
                    audio_path = download_audio(
                        episode["enclosure_url"],
                        media_dir,
                        safe_name,
                    )
                else:
                    print(
                        "  No enclosure URL in matched episode",
                        file=sys.stderr,
                    )
                    audio_path = None
            except Exception as e:
                print(f"  RSS resolution failed: {e}", file=sys.stderr)
                audio_path = None
                episode = None
        else:
            audio_path = None

        # Strategy 5: yt-dlp fallback
        if not audio_path:
            audio_path, ytdlp_meta = try_ytdlp(
                url, media_dir,
                sanitize(episode_title or show_name or "podcast"),
            )
            if audio_path and ytdlp_meta:
                episode_title = (
                    episode_title or ytdlp_meta.get("title", "")
                )

        # All methods exhausted
        if not audio_path:
            hints = []
            if rss_url:
                hints.append(f"RSS feed found: {rss_url}")
            if platform:
                hints.append(f"Platform: {platform}")
            if show_name:
                hints.append(f"Show: {show_name}")

            print(json.dumps({
                "error": (
                    "Could not download podcast audio. "
                    + (
                        " ".join(hints) + ". "
                        if hints
                        else ""
                    )
                    + "Try sending the RSS feed URL or a YouTube "
                    "link for this episode instead."
                ),
                "rss_url": rss_url or "",
                "show_name": show_name or "",
                "platform": platform or "",
            }))
            sys.exit(1)

    # Build output
    if episode:
        title = episode.get("title", episode_title or "Unknown Episode")
        published = parse_pub_date(episode.get("pub_date", ""))
        duration_seconds = parse_duration(episode.get("duration", ""))
        episode_url = episode.get("link", url)
    else:
        title = episode_title or "Unknown Episode"
        published = ""
        duration_seconds = 0
        episode_url = url

    safe_title = sanitize(title)
    safe_show = sanitize(show_name) if show_name else ""

    output = {
        "title": title,
        "show_name": show_name or "",
        "safe_title": safe_title,
        "safe_show": safe_show,
        "published": published,
        "duration": format_duration(duration_seconds),
        "duration_seconds": duration_seconds,
        "image": show_image,
        "url": url,
        "audio_path": audio_path.replace("\\", "/"),
        "episode_url": episode_url,
        "rss_url": rss_url or "",
    }

    # Pass through pre-built chapters if provided
    if args.chapters:
        try:
            chapters = json.loads(args.chapters)
            output["chapters"] = chapters
            output["chapters_source"] = "show_notes"
        except (ValueError, TypeError) as e:
            print(f"  Warning: could not parse --chapters JSON: {e}", file=sys.stderr)

    output["execution_ms"] = int((time.time() - _start_time) * 1000)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
