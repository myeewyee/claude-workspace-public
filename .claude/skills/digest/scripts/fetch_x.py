#!/usr/bin/env python3
"""
X/Twitter content fetcher for /digest skill.
Fetches post data via fxtwitter API, converts article Draft.js to markdown.

Outputs compact JSON to stdout. Progress goes to stderr.
No external dependencies - stdlib only (urllib, json, re, datetime, argparse).
"""

import argparse
import datetime
import json
import re
import sys
import time
import urllib.request
import urllib.error


def sanitize(name):
    """Remove characters invalid in filenames."""
    name = re.sub(r'[<>:"/\\|?*]', "", name)
    return name.strip(". ")[:200]


def x_url_to_api(url):
    """Convert x.com or twitter.com URL to api.fxtwitter.com equivalent."""
    return re.sub(
        r"https?://(www\.)?(twitter\.com|x\.com)",
        "https://api.fxtwitter.com",
        url,
    )


def fetch_tweet(url):
    """Fetch tweet data from fxtwitter API. Returns parsed dict or raises."""
    api_url = x_url_to_api(url)
    print(f"Fetching: {api_url}", file=sys.stderr)
    req = urllib.request.Request(
        api_url, headers={"User-Agent": "digest-skill/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    if data.get("code") != 200:
        raise RuntimeError(
            f"API error {data.get('code')}: {data.get('message')}"
        )
    return data["tweet"]


def detect_content_type(tweet):
    """Detect X content type. Returns 'article' or 'single'."""
    if tweet.get("article") is not None:
        return "article"
    # v1: treat reply chains as single post (thread reconstruction is future)
    return "single"


def parse_date(tweet, article=None):
    """Parse published date. Returns YYYY-MM-DD HH:mm string when time is available.

    Prefers article.created_at (ISO 8601), falls back to
    tweet.created_timestamp (int), then tweet.created_at (RFC 822).
    """
    if article and article.get("created_at"):
        try:
            dt = datetime.datetime.fromisoformat(
                article["created_at"].replace("Z", "+00:00")
            )
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass

    ts = tweet.get("created_timestamp")
    if ts:
        dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M")

    raw = tweet.get("created_at", "")
    if raw:
        try:
            dt = datetime.datetime.strptime(raw, "%a %b %d %H:%M:%S %z %Y")
            return dt.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass

    return "unknown"


def apply_inline_styles(text, ranges):
    """Apply Bold inline style ranges. Returns markdown-annotated string."""
    if not ranges:
        return text
    bold_ranges = [
        (r["offset"], r["offset"] + r["length"])
        for r in ranges
        if r.get("style") == "Bold"
    ]
    if not bold_ranges:
        return text
    # Insert from end to avoid index shifting
    result = list(text)
    for start, end in sorted(bold_ranges, reverse=True):
        result.insert(end, "**")
        result.insert(start, "**")
    return "".join(result)


def blocks_to_markdown(blocks, entity_by_key, media_url_map):
    """Convert Draft.js content blocks to markdown string."""
    output = []

    for block in blocks:
        btype = block["type"]
        text = block.get("text", "")
        ranges = block.get("inlineStyleRanges", [])

        if btype == "header-two":
            # Strip Bold ranges: ## heading is already visually distinct
            output.append(f"## {text}")

        elif btype == "unstyled":
            styled = apply_inline_styles(text, ranges)
            output.append(styled if styled.strip() else "")

        elif btype == "blockquote":
            styled = apply_inline_styles(text, ranges)
            output.append(f"> {styled}")

        elif btype in ("unordered-list-item", "ordered-list-item"):
            styled = apply_inline_styles(text, ranges)
            prefix = "-" if btype == "unordered-list-item" else "1."
            output.append(f"{prefix} {styled}")

        elif btype == "atomic":
            entity_ranges = block.get("entityRanges", [])
            if not entity_ranges:
                continue
            ekey = str(entity_ranges[0]["key"])
            entity = entity_by_key.get(ekey, {})
            etype = entity.get("type")

            if etype == "MEDIA":
                items = entity.get("data", {}).get("mediaItems", [])
                caption = entity.get("data", {}).get("caption", "")
                for item in items:
                    url = media_url_map.get(item.get("mediaId", ""))
                    if url:
                        output.append(f"![{caption}]({url})")
                    else:
                        print(
                            f"  Warning: unresolvable mediaId "
                            f"{item.get('mediaId')}",
                            file=sys.stderr,
                        )

            elif etype == "TWEET":
                tid = entity.get("data", {}).get("tweetId", "")
                if tid:
                    output.append(
                        f"![Embedded tweet](https://x.com/i/status/{tid})"
                    )
        # Unknown block types: silently skip

    return "\n\n".join(output)


def extract_headings(markdown_text):
    """Extract H2 headings from markdown content for ToC.

    Returns list of heading strings (without ## prefix).
    """
    headings = []
    for line in markdown_text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        md_match = re.match(r"^##\s+(.+)$", stripped)
        if md_match:
            headings.append(md_match.group(1).strip())
    return headings


def build_toc(headings):
    """Build Table of Contents from headings list.

    Returns empty string if fewer than 3 headings.
    Uses Obsidian wiki-link anchors: [[#Heading Text]].
    """
    if len(headings) < 3:
        return ""
    lines = []
    for heading in headings:
        lines.append(f"- [[#{heading}]]")
    return "\n".join(lines)


def nest_content_headings(content):
    """Downgrade H2->H3 so article headings nest under ## Full Content."""
    lines = content.split("\n")
    result = []
    for line in lines:
        stripped = line.strip()
        h_match = re.match(r"^(##)\s+(.+)$", stripped)
        if h_match:
            text = h_match.group(2)
            result.append(f"### {text}")
        else:
            result.append(line)
    return "\n".join(result)


def convert_article(tweet):
    """Extract and convert article content. Returns content markdown string."""
    article = tweet["article"]
    content = article["content"]
    blocks = content["blocks"]
    entity_map_raw = content.get("entityMap", [])

    # Build lookup: draft.js entity key string -> entity value
    entity_by_key = {str(e["key"]): e["value"] for e in entity_map_raw}

    # Build lookup: media_id -> image URL
    media_url_map = {}
    for m in article.get("media_entities") or []:
        mid = m.get("media_id")
        url = (m.get("media_info") or {}).get("original_img_url", "")
        if mid and url:
            media_url_map[mid] = url

    return blocks_to_markdown(blocks, entity_by_key, media_url_map)


def main():
    parser = argparse.ArgumentParser(
        description="X/Twitter content fetcher for /digest skill"
    )
    parser.add_argument("url", help="X/Twitter post URL")
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
    args = parser.parse_args()
    _start_time = time.time()

    try:
        tweet = fetch_tweet(args.url)
    except urllib.error.HTTPError as e:
        print(json.dumps({"error": f"HTTP {e.code}: {e.reason}"}))
        sys.exit(1)
    except urllib.error.URLError as e:
        print(json.dumps({"error": f"Network error: {e.reason}"}))
        sys.exit(1)
    except RuntimeError as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)

    content_type = detect_content_type(tweet)
    author = tweet["author"]
    screen_name = author["screen_name"]
    display_name = author["name"]

    result = {
        "content_type": content_type,
        "url": args.url,
        "screen_name": screen_name,
        "display_name": display_name,
        "avatar_url": author.get("avatar_url", ""),
        "followers": author.get("followers", 0),
        "tweet_text": tweet.get("text", ""),
        "likes": tweet.get("likes", 0),
        "retweets": tweet.get("retweets", 0),
        "views": tweet.get("views", 0),
        "published": parse_date(tweet, tweet.get("article")),
    }

    if content_type == "article":
        article = tweet["article"]
        cover_url = (
            (article.get("cover_media") or {})
            .get("media_info", {})
            .get("original_img_url", "")
        )
        content_md = convert_article(tweet)

        # Extract headings for ToC (before nesting)
        headings = extract_headings(content_md)
        toc = build_toc(headings)

        # Nest H2->H3 so article headings sit under ## Full Content
        content_nested = nest_content_headings(content_md)

        result.update(
            {
                "title": article.get("title", ""),
                "preview_text": article.get("preview_text", ""),
                "cover_url": cover_url,
                "image": cover_url or author.get("avatar_url", ""),
                "safe_title": sanitize(article.get("title", screen_name)),
                "safe_author": sanitize(screen_name),
                "content_markdown": content_nested,
                "headings": headings,
                "toc": toc,
                "word_count": len(content_nested.split()),
            }
        )

        # Write content/ToC files if requested (for assembly pipeline)
        if args.content_out:
            with open(args.content_out, "w", encoding="utf-8") as f:
                f.write(content_nested)
        if args.toc_out:
            with open(args.toc_out, "w", encoding="utf-8") as f:
                f.write(toc)
    else:
        # Single post: minimal output, no file needed
        result.update(
            {
                "title": (tweet.get("text") or "")[:60].strip(),
                "safe_title": sanitize(
                    (tweet.get("text") or screen_name)[:60]
                ),
                "safe_author": sanitize(screen_name),
                "image": author.get("avatar_url", ""),
            }
        )

    result["execution_ms"] = int((time.time() - _start_time) * 1000)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
