#!/usr/bin/env python3
"""
Review scraper: pulls hotel/resort reviews from Google Maps and Booking.com
via Apify actors. Outputs structured JSON to stdout.

Usage:
    python .scripts/review_scraper.py --platform google --url <GOOGLE_MAPS_URL>
    python .scripts/review_scraper.py --platform booking --url <BOOKING_URL>
    python .scripts/review_scraper.py --platform airbnb --url <AIRBNB_URL>

Environment variables:
    APIFY_API_TOKEN - Apify API token (used for both platforms)
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows (avoids cp1252 encoding errors with non-ASCII review text)
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

CACHE_DIR = Path(__file__).parent / "review_data"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_request(url, *, data=None, headers=None, method=None, timeout=30):
    """Make an HTTP request and return parsed JSON (or raw bytes on failure)."""
    headers = headers or {}
    if data is not None and isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        try:
            return json.loads(body)
        except json.JSONDecodeError:
            return body


def sanitize_filename(text, max_len=80):
    """Turn arbitrary text into a safe filename fragment."""
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[^a-zA-Z0-9_-]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_len]


def log(msg):
    """Print a status message to stderr."""
    print(f"[review_scraper] {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def cache_path(platform, url):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = sanitize_filename(url)
    today = datetime.now().strftime("%Y-%m-%d")
    return CACHE_DIR / f"{slug}_{platform}_{today}.json"


def load_cache(platform, url):
    path = cache_path(platform, url)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(platform, url, data):
    path = cache_path(platform, url)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Cached to {path}")
    return path


# ---------------------------------------------------------------------------
# Google Maps provider (Apify REST API)
# ---------------------------------------------------------------------------

APIFY_ACTOR = "automation-lab~google-maps-reviews-scraper"


def fetch_google_reviews(url, max_reviews=100):
    """Fetch Google Maps reviews via Apify's synchronous run endpoint."""
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Get one at https://console.apify.com/account#/integrations"
        )

    actor_input = {
        "placeUrls": [url],
        "maxReviewsPerPlace": max_reviews,
        "language": "en",
        "personalData": False,
    }

    api_url = (
        f"https://api.apify.com/v2/acts/{APIFY_ACTOR}"
        f"/run-sync-get-dataset-items?token={token}&format=json"
    )

    log(f"Starting Apify actor for {url} (max {max_reviews} reviews)...")
    log("This may take 1-3 minutes for the actor to complete.")

    try:
        items = api_request(api_url, data=actor_input, timeout=300)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Apify API error {e.code}: {body}") from e

    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected Apify response (expected list): {str(items)[:500]}")

    reviews = []
    for item in items:
        reviews.append({
            "text": item.get("text") or item.get("textTranslated") or "",
            "rating": item.get("stars"),
            "date": item.get("publishedAt", ""),
            "author": item.get("reviewerName", ""),
            "review_url": item.get("reviewUrl", ""),
            "likes": item.get("likesCount"),
            "language": item.get("originalLanguage", ""),
            "response_from_owner": item.get("responseFromOwnerText"),
        })

    # Extract place metadata from the first item (all items share it)
    place_info = {}
    if items:
        first = items[0]
        place_info = {
            "name": first.get("title", ""),
            "address": first.get("address", ""),
            "overall_rating": first.get("totalScore"),
            "category": first.get("categoryName", ""),
            "place_id": first.get("placeId", ""),
        }

    return {
        "platform": "google",
        "url": url,
        "fetched_at": datetime.now().isoformat(),
        "place": place_info,
        "review_count": len(reviews),
        "reviews": reviews,
    }


# ---------------------------------------------------------------------------
# Booking.com provider (Apify REST API)
# ---------------------------------------------------------------------------

APIFY_BOOKING_ACTOR = "voyager~booking-reviews-scraper"


def fetch_booking_reviews(url, max_reviews=100):
    """Fetch Booking.com reviews via Apify's Booking Reviews Scraper actor."""
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Get one at https://console.apify.com/account#/integrations"
        )

    actor_input = {
        "startUrls": [{"url": url}],
    }

    api_url = (
        f"https://api.apify.com/v2/acts/{APIFY_BOOKING_ACTOR}"
        f"/run-sync-get-dataset-items?token={token}&format=json"
    )

    log(f"Starting Apify Booking actor for {url}...")
    log("This may take 1-3 minutes for the actor to complete.")

    try:
        items = api_request(api_url, data=actor_input, timeout=300)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Apify API error {e.code}: {body}") from e

    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected Apify response (expected list): {str(items)[:500]}")

    # Normalize reviews. Booking reviews have separate liked/disliked fields.
    reviews = []
    for item in items[:max_reviews]:
        liked = item.get("likedText", "")
        disliked = item.get("dislikedText", "")
        # Combine into a single text field for unified querying
        parts = []
        if liked:
            parts.append(f"Liked: {liked}")
        if disliked:
            parts.append(f"Disliked: {disliked}")
        combined_text = " | ".join(parts)

        reviews.append({
            "text": combined_text,
            "liked": liked,
            "disliked": disliked,
            "rating": item.get("rating"),
            "date": item.get("reviewDate", ""),
            "author": item.get("userName", ""),
            "title": item.get("reviewTitle", ""),
            "room_type": item.get("roomInfo", ""),
            "check_in": item.get("checkInDate", ""),
            "check_out": item.get("checkOutDate", ""),
            "nights": item.get("numberOfNights"),
            "traveller_type": item.get("travelerType", ""),
            "user_location": item.get("userLocation", ""),
            "language": item.get("reviewLanguage", ""),
        })

    # Extract hotel metadata from the first item
    place_info = {}
    if items:
        first = items[0]
        place_info = {
            "name": url.split("/hotel/")[1].split("/")[1].split(".")[0].replace("-", " ").title() if "/hotel/" in url else "",
            "overall_rating": first.get("hotelRating"),
            "rating_label": first.get("hotelRatingLabel", ""),
            "total_reviews": first.get("hotelReviews"),
            "rating_scores": {
                s["name"]: round(s["score"], 1)
                for s in first.get("hotelRatingScores", [])
            },
        }

    return {
        "platform": "booking",
        "url": url,
        "fetched_at": datetime.now().isoformat(),
        "place": place_info,
        "review_count": len(reviews),
        "reviews": reviews,
    }


# ---------------------------------------------------------------------------
# Airbnb provider (Apify REST API)
# ---------------------------------------------------------------------------

APIFY_AIRBNB_REVIEWS_ACTOR = "tri_angle~airbnb-reviews-scraper"


def fetch_airbnb_reviews(url, max_reviews=50):
    """Fetch Airbnb reviews via Apify tri_angle/airbnb-reviews-scraper.

    Note: the search actor (tri_angle~airbnb-scraper) cannot accept listing
    detail URLs. The dedicated reviews actor must be used instead.
    """
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Get one at https://console.apify.com/account#/integrations"
        )

    actor_input = {
        "startUrls": [{"url": url}],
        "maxReviews": max_reviews,
    }

    api_url = (
        f"https://api.apify.com/v2/acts/{APIFY_AIRBNB_REVIEWS_ACTOR}"
        f"/run-sync-get-dataset-items?token={token}&format=json"
    )

    log(f"Starting Apify Airbnb reviews actor for {url}...")
    log("This may take 1-3 minutes for the actor to complete.")

    try:
        items = api_request(api_url, data=actor_input, timeout=300)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Apify API error {e.code}: {body}") from e

    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected Apify response: {str(items)[:500]}")

    # Reviews actor returns reviews directly (not nested inside a listing)
    reviews = []
    for r in items[:max_reviews]:
        text = r.get("localizedText", "") or r.get("text", "")
        # Strip HTML tags from review text
        text = re.sub(r"<br\s*/?>", "\n", text)
        text = re.sub(r"<[^>]+>", "", text)

        reviewer = r.get("reviewer", {})
        author = ""
        if isinstance(reviewer, dict):
            author = reviewer.get("firstName", "")

        reviews.append({
            "text": text,
            "rating": r.get("rating"),
            "date": r.get("createdAt", ""),
            "author": author,
            "language": r.get("language", ""),
            "stay_highlight": r.get("reviewHighlight", ""),
        })

    # No listing metadata from the reviews actor, construct minimal info
    place_info = {
        "name": "",
        "overall_rating": None,
        "review_count_total": len(items),
    }

    return {
        "platform": "airbnb",
        "url": url,
        "fetched_at": datetime.now().isoformat(),
        "place": place_info,
        "review_count": len(reviews),
        "reviews": reviews,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Scrape hotel/resort reviews from Google Maps or Booking.com"
    )
    parser.add_argument(
        "--platform",
        choices=["google", "booking", "airbnb"],
        required=True,
        help="Which platform to scrape",
    )
    parser.add_argument("--url", required=True, help="Property URL")
    parser.add_argument(
        "--max-reviews",
        type=int,
        default=50,
        help="Maximum reviews to fetch (default: 50)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Skip cache, force a fresh fetch",
    )

    args = parser.parse_args()

    # Check cache
    if not args.no_cache:
        cached = load_cache(args.platform, args.url)
        if cached:
            log(f"Using cached data from {cached.get('fetched_at', 'unknown')}")
            print(json.dumps(cached, indent=2, ensure_ascii=False))
            return

    # Fetch
    try:
        if args.platform == "google":
            data = fetch_google_reviews(args.url, args.max_reviews)
        elif args.platform == "booking":
            data = fetch_booking_reviews(args.url, args.max_reviews)
        else:
            data = fetch_airbnb_reviews(args.url, args.max_reviews)
    except RuntimeError as e:
        log(f"ERROR: {e}")
        sys.exit(1)
    except urllib.error.URLError as e:
        log(f"Network error: {e}")
        sys.exit(1)

    # Cache and output
    save_cache(args.platform, args.url, data)
    print(json.dumps(data, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
