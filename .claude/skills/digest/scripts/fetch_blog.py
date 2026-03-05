#!/usr/bin/env python3
"""
Blog/article content fetcher for /digest skill.
Fetches any web page, extracts article content via trafilatura,
and pre-builds mechanical parts (frontmatter, ToC) for the digest agent.

Uses trafilatura for article extraction (HTML mode for proper list structure),
then markdownify for HTML-to-markdown conversion.

Outputs compact JSON to stdout. Progress/errors go to stderr.
Dependencies: trafilatura, markdownify (pip install trafilatura markdownify).
"""

import argparse
import json
import re
import sys
import time
import urllib.request
import urllib.error

import markdownify
import trafilatura


MAX_RESPONSE_BYTES = 5 * 1024 * 1024  # 5MB
FETCH_TIMEOUT = 15  # seconds
MIN_CONTENT_LENGTH = 100  # characters

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

# Known podcast oEmbed provider domains
PODCAST_OEMBED_DOMAINS = [
    "oembed.libsyn.com",
    "open.spotify.com",
    "share.transistor.fm",
    "embed.podigee.com",
    "widget.spreaker.com",
    "www.buzzsprout.com",
]


def sanitize(name):
    """Remove characters invalid in filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    return name.strip(". ")[:200]


def fetch_html(url):
    """Fetch HTML from URL with size and timeout guards.

    Returns HTML string or raises with a clear message.
    """
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (compatible; digest-skill/1.0)"},
    )
    print(f"Fetching: {url}", file=sys.stderr)

    with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
        # Check content length header if available
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Page too large: {int(content_length)} bytes "
                f"(limit: {MAX_RESPONSE_BYTES})"
            )

        # Read with size limit
        data = resp.read(MAX_RESPONSE_BYTES + 1)
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError(
                f"Page exceeds {MAX_RESPONSE_BYTES // (1024*1024)}MB size limit"
            )

    return data.decode("utf-8", errors="replace")


def fix_html_spacing(html):
    """Fix trafilatura's space-stripping around inline HTML tags.

    Trafilatura removes whitespace between closing inline tags and
    adjacent text, producing broken output like:
        </strong>- the gold-standard  (missing space before -)
        </a>because                  (missing space before word)
        I'd get<a href=...>          (missing space before link)
        </a>(on plastics)            (missing space before paren)

    This function restores the missing spaces.
    """
    inline_tags = r"(?:strong|b|i|em|a)"
    # Space after closing tag when followed by word char or dash or open paren
    html = re.sub(
        rf"(</{inline_tags}>)([A-Za-z0-9(\-])",
        r"\1 \2",
        html,
    )
    # Space before opening tag when preceded by word char
    html = re.sub(
        rf"([A-Za-z0-9])(<(?:{inline_tags})[\s>])",
        r"\1 \2",
        html,
    )
    # Space after punctuation before opening <a> tag
    html = re.sub(r"([.!?,])(<a\s)", r"\1 \2", html)
    # Space between consecutive links
    html = re.sub(r"(</a>)(<a\s)", r"\1 \2", html)
    return html


def normalize_heading_levels(markdown, title=""):
    """Normalize heading levels in article content for digest embedding.

    1. Strips the article's title heading if it matches the metadata title
       (redundant with digest's own H1 and source link).
    2. Downgrades remaining H1s to H2 (digest provides the only H1).
    3. Strips redundant bold from headings (e.g. ## **Text** -> ## Text).
    """
    lines = markdown.split("\n")
    result = []
    title_stripped = False
    title_lower = title.lower().strip() if title else ""

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Match any heading (H1-H3)
        h_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if h_match:
            level = h_match.group(1)
            text = h_match.group(2)

            # Strip bold markers from heading text
            text = re.sub(r"^\*\*(.+)\*\*$", r"\1", text)

            # Strip the first heading that matches the article title
            if not title_stripped and title_lower and text.lower().strip() == title_lower:
                title_stripped = True
                # Also skip trailing blank line
                continue

            # Downgrade H1 to H2
            if level == "#":
                result.append(f"## {text}")
            else:
                result.append(f"{level} {text}")
            continue

        # Skip blank line after stripped title heading
        if title_stripped and not result and not stripped:
            continue

        result.append(line)

    return "\n".join(result)


def extract_headings(markdown_text):
    """Extract section headings from markdown content.

    Detects two patterns:
    1. Proper markdown headings: ## Text, ### Text
    2. Bold-only lines used as section headings: **Text**

    Returns list of heading strings (without markdown syntax).
    """
    headings = []
    for line in markdown_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue

        # Pattern 1: proper markdown H2/H3
        md_match = re.match(r"^(#{2,3})\s+(.+)$", stripped)
        if md_match:
            headings.append(md_match.group(2).strip())
            continue

        # Pattern 2: standalone bold line (entire line is **text**)
        bold_match = re.match(r"^\*\*([^*]+)\*\*$", stripped)
        if bold_match:
            headings.append(bold_match.group(1).strip())

    return headings


def build_toc(headings):
    """Build Table of Contents markdown from headings list.

    Returns empty string if fewer than 3 headings.
    Uses Obsidian wiki-link anchors: [[#Heading Text]].
    """
    if len(headings) < 3:
        return ""

    lines = []
    for heading in headings:
        lines.append(f"- [[#{heading}]]")
    return "\n".join(lines)


def build_frontmatter(title, author, published, image, url, created_date, created_time, depth="deep"):
    """Build YAML frontmatter string, ready to paste."""
    lines = ["---"]
    lines.append(f'author: "[[{author}]]"')
    lines.append(f'title: "{title}"')
    lines.append(f"created: {created_date} {created_time}")
    if published:
        lines.append(f"published: {published}")
    lines.append('description: "[FILL: one-line summary of the article\'s core claim or topic]"')
    if image:
        lines.append(f"image: {image}")
    lines.append("parent: '[FILL: active task wiki-link]'")
    lines.append("source: claude")
    lines.append(f"depth: {depth}")
    lines.append("subtype: article")
    lines.append("type: content")
    lines.append(f"url: {url}")
    lines.append("---")
    return "\n".join(lines)


def normalize_headings_in_content(content):
    """Convert standalone bold lines to proper ## headings in content.

    This normalizes articles that use **Bold** as section headings
    so the digest has consistent heading formatting.
    """
    lines = content.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        bold_match = re.match(r"^\*\*([^*]+)\*\*$", stripped)
        if bold_match:
            result.append(f"## {bold_match.group(1)}")
        else:
            result.append(line)
    return "\n".join(result)


def strip_small_headings(content):
    """Strip H5/H6 headings from content.

    These are typically navigation artifacts or category labels
    (e.g., Psychology Today's H6 category tags) rather than real
    content sections. Removes the line entirely.
    """
    lines = content.split("\n")
    result = []
    for line in lines:
        if re.match(r"^#{5,6}\s+", line.strip()):
            continue
        result.append(line)
    return "\n".join(result)


def nest_content_headings(content):
    """Downgrade H2->H3 and H3->H4 so article headings nest under ## Full Content.

    The digest template uses H2 for structural sections (Key Takeaways,
    Table of Contents, Full Content). Article headings need to be one level
    deeper so they collapse under ## Full Content in Obsidian.

    Must run AFTER extract_headings (which needs H2/H3 to build ToC).
    """
    lines = content.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        h_match = re.match(r"^(#{2,3})\s+(.+)$", stripped)
        if h_match:
            level = h_match.group(1)
            text = h_match.group(2)
            result.append(f"#{level} {text}")
        else:
            result.append(line)
    return "\n".join(result)


def strip_heading_blank_lines(content):
    """Remove blank lines immediately before and after headings.

    Headings are visual separators; blank lines around them add
    unnecessary whitespace in Obsidian rendering.
    """
    lines = content.split("\n")
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()

        # Skip blank line if next line is a heading
        if not stripped and i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if re.match(r"^#{1,6}\s+", next_line):
                continue

        # Skip blank line if previous line is a heading
        if not stripped and i > 0:
            prev_line = lines[i - 1].strip()
            if re.match(r"^#{1,6}\s+", prev_line):
                continue

        result.append(line)
    return "\n".join(result)


def domain_from_url(url):
    """Extract domain name from URL for author fallback."""
    match = re.match(r"https?://(?:www\.)?([^/]+)", url)
    if match:
        domain = match.group(1)
        # Strip common suffixes for cleaner names
        for suffix in [".bearblog.dev", ".substack.com", ".medium.com",
                       ".ghost.io", ".wordpress.com", ".blogspot.com"]:
            if domain.endswith(suffix):
                return domain[: -len(suffix)]
        return domain
    return "unknown"


def detect_podcast_signals(html, url):
    """Detect podcast signals in page HTML.

    Checks for structured data, embedded players, audio tags, and RSS feeds
    that indicate this page is a podcast episode rather than a blog article.

    Returns dict with detected signals, or empty dict if none found.
    All detection is regex-based on the already-fetched HTML (no extra requests).
    """
    signals = {}

    # 1. Schema.org JSON-LD with PodcastEpisode
    jsonld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL | re.IGNORECASE,
    )
    for block in jsonld_blocks:
        try:
            import json as _json
            data = _json.loads(block)
            # Handle both single objects and arrays
            items = data if isinstance(data, list) else [data]
            for item in items:
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    item_type = " ".join(item_type)
                if "PodcastEpisode" in item_type or "PodcastSeries" in item_type:
                    signals["jsonld_podcast"] = True
                    # Try to extract audio URL
                    media = item.get("associatedMedia", {})
                    if isinstance(media, dict):
                        audio = media.get("contentUrl", "")
                        if audio:
                            signals["audio_url"] = audio
                    # Extract episode metadata
                    if item.get("name"):
                        signals["episode_title"] = item["name"]
                    part_of = item.get("partOfSeries", {})
                    if isinstance(part_of, dict) and part_of.get("name"):
                        signals["show_name"] = part_of["name"]
        except (ValueError, TypeError, KeyError):
            continue

    # 2. Iframe src matching known podcast player domains
    iframe_srcs = re.findall(
        r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE,
    )
    for src in iframe_srcs:
        for domain in PODCAST_PLAYER_DOMAINS:
            if domain in src:
                signals["podcast_player"] = domain
                break

    # 3. Buzzsprout script embed pattern
    if re.search(
        r'<script[^>]+src=["\'][^"\']*buzzsprout\.com/\d+/\d+',
        html, re.IGNORECASE,
    ):
        signals["buzzsprout_embed"] = True

    # 4. oEmbed link pointing to known podcast provider
    oembed_links = re.findall(
        r'<link[^>]+type=["\']application/json\+oembed["\'][^>]*'
        r'href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not oembed_links:
        oembed_links = re.findall(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]*'
            r'type=["\']application/json\+oembed["\']',
            html, re.IGNORECASE,
        )
    for link in oembed_links:
        for domain in PODCAST_OEMBED_DOMAINS:
            if domain in link:
                signals["podcast_oembed"] = domain
                break

    # 5. og:audio or twitter:player:stream meta tags
    og_audio = re.findall(
        r'<meta[^>]+property=["\']og:audio["\'][^>]*'
        r'content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not og_audio:
        og_audio = re.findall(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*'
            r'property=["\']og:audio["\']',
            html, re.IGNORECASE,
        )
    if og_audio:
        signals["og_audio"] = og_audio[0]
        if not signals.get("audio_url"):
            signals["audio_url"] = og_audio[0]

    twitter_stream = re.findall(
        r'<meta[^>]+(?:name|property)=["\']twitter:player:stream["\'][^>]*'
        r'content=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not twitter_stream:
        twitter_stream = re.findall(
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]*'
            r'(?:name|property)=["\']twitter:player:stream["\']',
            html, re.IGNORECASE,
        )
    if twitter_stream:
        signals["twitter_stream"] = twitter_stream[0]
        if not signals.get("audio_url"):
            signals["audio_url"] = twitter_stream[0]

    # 6. <audio> or <source type="audio/mpeg"> elements
    audio_srcs = re.findall(
        r'<audio[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE,
    )
    source_srcs = re.findall(
        r'<source[^>]+src=["\']([^"\']+)["\'][^>]*'
        r'type=["\']audio/(?:mpeg|mp3|mp4|ogg)["\']',
        html, re.IGNORECASE,
    )
    if audio_srcs or source_srcs:
        signals["audio_element"] = True
        audio_url = (audio_srcs or source_srcs)[0]
        if not signals.get("audio_url"):
            signals["audio_url"] = audio_url

    # 7. Podcast hosting platform URLs anywhere in the page
    # (body links, scripts, inline references to known podcast hosts)
    hosting_patterns = [
        ("libsyn", re.compile(r"(?:play|traffic|html5-player|[a-z0-9]+)\.libsyn\.com", re.IGNORECASE)),
        ("buzzsprout", re.compile(r"(?:feeds|www)\.buzzsprout\.com/\d+", re.IGNORECASE)),
        ("megaphone", re.compile(r"(?:traffic|player)\.megaphone\.fm", re.IGNORECASE)),
        ("podbean", re.compile(r"[a-z0-9]+\.podbean\.com", re.IGNORECASE)),
        ("transistor", re.compile(r"share\.transistor\.fm", re.IGNORECASE)),
        ("simplecast", re.compile(r"player\.simplecast\.com", re.IGNORECASE)),
        ("acast", re.compile(r"(?:shows|embed)\.acast\.com", re.IGNORECASE)),
        ("spreaker", re.compile(r"(?:www|widget)\.spreaker\.com", re.IGNORECASE)),
    ]
    for platform_name, pattern in hosting_patterns:
        match = pattern.search(html)
        if match and "podcast_player" not in signals:
            signals["hosting_platform"] = platform_name
            # Try to extract the full RSS URL if it's a known pattern
            if platform_name == "libsyn":
                rss_match = re.search(
                    r'href=["\']?(https?://[a-z0-9]+\.libsyn\.com/rss)["\']?',
                    html, re.IGNORECASE,
                )
                if rss_match:
                    signals["rss_url"] = rss_match.group(1)
            elif platform_name == "buzzsprout":
                bz_id = re.search(r'buzzsprout\.com/(\d+)', html)
                if bz_id:
                    signals["rss_url"] = f"https://feeds.buzzsprout.com/{bz_id.group(1)}.rss"
            break

    # 8. RSS feed link (not definitive alone, but record it)
    rss_links = re.findall(
        r'<link[^>]+type=["\']application/rss\+xml["\'][^>]*'
        r'href=["\']([^"\']+)["\']',
        html, re.IGNORECASE,
    )
    if not rss_links:
        rss_links = re.findall(
            r'<link[^>]+href=["\']([^"\']+)["\'][^>]*'
            r'type=["\']application/rss\+xml["\']',
            html, re.IGNORECASE,
        )
    if rss_links:
        from urllib.parse import urljoin
        rss_url = rss_links[0]
        if not rss_url.startswith("http"):
            rss_url = urljoin(url, rss_url)
        signals["rss_url"] = rss_url

    return signals


def extract_youtube_references(html):
    """Extract YouTube video IDs from page HTML.

    Finds YouTube embeds (iframe src), watch links, and short links.
    Returns list of unique 11-char video IDs, or empty list.
    """
    video_ids = []

    # Iframe embeds: youtube.com/embed/ID or youtube-nocookie.com/embed/ID
    video_ids.extend(re.findall(
        r'(?:youtube\.com|youtube-nocookie\.com)/embed/([a-zA-Z0-9_-]{11})',
        html,
    ))

    # Watch links: youtube.com/watch?v=ID
    video_ids.extend(re.findall(
        r'youtube\.com/watch\?v=([a-zA-Z0-9_-]{11})',
        html,
    ))

    # Short links: youtu.be/ID
    video_ids.extend(re.findall(
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        html,
    ))

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for vid in video_ids:
        if vid not in seen:
            seen.add(vid)
            unique.append(vid)

    return unique


def extract_show_notes_chapters(content_markdown):
    """Extract creator-curated chapter timestamps from show notes content.

    Matches [HH:MM:SS] Title format commonly used in podcast show notes
    (e.g. Peter Attia, Tim Ferriss). Requires at least 3 entries to avoid
    false positives from stray timestamps in non-chapter content.

    Returns list of {"start_time": <seconds>, "title": "<title>"} dicts,
    or empty list if fewer than 3 entries found.
    """
    pattern = re.compile(
        r'\[(\d{1,2}):(\d{2}):(\d{2})\]\s*(.+)',
    )
    matches = pattern.findall(content_markdown)
    if len(matches) < 3:
        return []

    chapters = []
    for hours, minutes, seconds, title in matches:
        start_time = int(hours) * 3600 + int(minutes) * 60 + int(seconds)
        # Clean up title: strip trailing punctuation, normalize whitespace
        title = title.strip().rstrip(".,;:")
        chapters.append({"start_time": start_time, "title": title})
    return chapters


def main():
    parser = argparse.ArgumentParser(
        description="Blog/article content fetcher for /digest skill"
    )
    parser.add_argument("url", help="Blog or article URL")
    parser.add_argument(
        "--date",
        default="",
        help="Created date (YYYY-MM-DD) for frontmatter",
    )
    parser.add_argument(
        "--time",
        default="",
        help="Created time (HH:MM) for frontmatter",
    )
    parser.add_argument(
        "--content-out",
        default=None,
        help="Write article content markdown to this file (for assembly pipeline)",
    )
    parser.add_argument(
        "--toc-out",
        default=None,
        help="Write Table of Contents to this file (for assembly pipeline)",
    )
    parser.add_argument(
        "--depth",
        default="deep",
        choices=["shallow", "deep"],
        help="Processing depth for frontmatter (shallow=quick, deep=full)",
    )
    args = parser.parse_args()
    _start_time = time.time()

    # Step 1: Fetch HTML
    try:
        html = fetch_html(args.url)
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.code}: {e.reason}"}))
        sys.exit(1)
    except urllib.error.URLError as e:
        print(json.dumps({"error": f"Network error: {e.reason}"}))
        sys.exit(1)
    except ValueError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Fetch failed: {e}"}))
        sys.exit(1)

    # Step 1.5: Detect podcast signals and YouTube references
    podcast_signals = detect_podcast_signals(html, args.url)
    if podcast_signals:
        # Filter to meaningful signals (RSS alone is not definitive)
        strong_signals = {
            k: v for k, v in podcast_signals.items()
            if k != "rss_url"
        }
        if strong_signals:
            print(
                f"Podcast detected: {', '.join(strong_signals.keys())}",
                file=sys.stderr,
            )

    youtube_ids = extract_youtube_references(html)
    if youtube_ids:
        print(f"YouTube references found: {youtube_ids}", file=sys.stderr)

    print("Extracting content...", file=sys.stderr)

    # Step 2: Extract metadata
    metadata = trafilatura.extract_metadata(html, default_url=args.url)
    title = (metadata.title if metadata and metadata.title else "") or "Untitled"
    author = (metadata.author if metadata and metadata.author else "") or (
        metadata.sitename if metadata and metadata.sitename else ""
    ) or domain_from_url(args.url)
    published = (metadata.date if metadata and metadata.date else "") or ""
    image = (metadata.image if metadata and metadata.image else "") or ""

    # Step 3: Extract article as HTML (preserves list structure and formatting)
    article_html = trafilatura.extract(
        html,
        output_format="html",
        include_links=True,
        include_images=True,
        include_tables=True,
        include_formatting=True,
    )

    if not article_html:
        print(json.dumps({
            "error": "Could not extract article content. "
                     "This URL may not be a standard blog or article page."
        }))
        sys.exit(1)

    if len(article_html) < MIN_CONTENT_LENGTH:
        print(json.dumps({
            "error": f"Extracted content too short ({len(article_html)} chars). "
                     "Page may not contain a substantial article."
        }))
        sys.exit(1)

    # Step 4: Fix trafilatura space-stripping, convert to markdown
    article_html = fix_html_spacing(article_html)
    content = markdownify.markdownify(
        article_html,
        heading_style="ATX",
        bullets="-",
    )

    # Step 5: Strip title heading, downgrade H1s to H2s, strip bold from headings
    content = normalize_heading_levels(content, title=title)

    # Step 6: Normalize bold-as-heading lines to ## headings
    content_normalized = normalize_headings_in_content(content)

    # Step 7: Strip H5/H6 artifacts (category labels, navigation)
    content_normalized = strip_small_headings(content_normalized)

    # Step 8: Extract headings for ToC (before nesting downgrade)
    headings = extract_headings(content_normalized)

    # Step 9: Downgrade H2->H3, H3->H4 for nesting under ## Full Content
    content_normalized = nest_content_headings(content_normalized)

    # Step 10: Strip blank lines around headings
    content_normalized = strip_heading_blank_lines(content_normalized)

    # Step 11: Build mechanical parts
    safe_title = sanitize(title)
    safe_author = sanitize(author)
    toc = build_toc(headings)
    frontmatter = build_frontmatter(
        title, author, published, image, args.url,
        args.date, args.time, args.depth,
    )

    word_count = len(content_normalized.split())

    # Step 10.5: Extract show notes chapters (before content/ToC output)
    show_notes_chapters = extract_show_notes_chapters(content_normalized)
    if show_notes_chapters:
        print(
            f"Show notes chapters found: {len(show_notes_chapters)} entries",
            file=sys.stderr,
        )

    print(f"Extracted: {word_count} words, {len(headings)} headings", file=sys.stderr)

    # Step 11: Write content/ToC files if requested (for assembly pipeline)
    if args.content_out:
        with open(args.content_out, "w", encoding="utf-8") as f:
            f.write(content_normalized)
    if args.toc_out:
        with open(args.toc_out, "w", encoding="utf-8") as f:
            f.write(toc)

    # Step 12: Output JSON
    result = {
        "title": title,
        "author": author,
        "published": published,
        "image": image,
        "url": args.url,
        "content_markdown": content_normalized,
        "headings": headings,
        "frontmatter": frontmatter,
        "toc": toc,
        "safe_title": safe_title,
        "safe_author": safe_author,
        "word_count": word_count,
    }

    # Add podcast signals if detected (strong signals only)
    if podcast_signals:
        strong_signals = {
            k: v for k, v in podcast_signals.items()
            if k != "rss_url"
        }
        if strong_signals:
            result["content_type"] = "podcast"
            result["podcast"] = podcast_signals
            # Include YouTube IDs in podcast object if found
            if youtube_ids:
                result["podcast"]["youtube_ids"] = youtube_ids
            # Include show notes chapters in podcast object if found
            if show_notes_chapters:
                result["podcast"]["chapters"] = show_notes_chapters
                result["podcast"]["chapters_source"] = "show_notes"
        elif podcast_signals.get("rss_url"):
            # RSS alone: include as metadata but don't classify as podcast
            result["rss_url"] = podcast_signals["rss_url"]

    # Add YouTube IDs at top level when found (regardless of podcast detection)
    if youtube_ids:
        result["youtube_ids"] = youtube_ids

    # Add show notes chapters at top level when found (applies to article pages
    # like Tim Ferriss that aren't classified as podcast but still have timestamps)
    if show_notes_chapters and "podcast" not in result:
        result["podcast"] = {
            "chapters": show_notes_chapters,
            "chapters_source": "show_notes",
        }

    result["execution_ms"] = int((time.time() - _start_time) * 1000)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
