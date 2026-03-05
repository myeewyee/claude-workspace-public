#!/usr/bin/env python3
"""
Accommodation search: searches Booking.com and Airbnb for listings
via Apify actors. Outputs structured JSON to stdout.

Usage:
    python .scripts/accommodation-search.py --platform booking --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21
    python .scripts/accommodation-search.py --platform airbnb --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21
    python .scripts/accommodation-search.py --platform both --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21

Environment variables:
    APIFY_API_TOKEN - Apify API token (used for both platforms)
"""

import argparse
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

CACHE_DIR = Path(__file__).parent / "accommodation_data"

APIFY_BOOKING_ACTOR = "voyager~booking-scraper"
APIFY_AIRBNB_ACTOR = "tri_angle~airbnb-scraper"

# Property type mappings for Booking.com
BOOKING_TYPE_MAP = {
    "entire": ["Apartments", "Holiday homes", "Villas"],
    "hotel": ["Hotels"],
    "hostel": ["Hostels"],
    "guesthouse": ["Guest houses", "Bed and breakfasts"],
    "all": [],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_request(url, *, data=None, headers=None, method=None, timeout=30):
    """Make an HTTP request and return parsed JSON."""
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
    print(f"[accommodation-search] {msg}", file=sys.stderr)


def haversine_km(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two lat/lng points."""
    R = 6371
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def get_token():
    """Get Apify API token from environment."""
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Get one at https://console.apify.com/account#/integrations"
        )
    return token


def run_actor(actor_id, actor_input, token, poll_interval=15, max_wait=900):
    """Start an Apify actor run asynchronously, poll until done, return dataset items."""

    # Start the run
    start_url = f"https://api.apify.com/v2/acts/{actor_id}/runs?token={token}"
    log(f"Starting actor {actor_id}...")

    try:
        run_info = api_request(start_url, data=actor_input, timeout=60)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Apify API error {e.code}: {body[:500]}") from e

    run_id = run_info["data"]["id"]
    dataset_id = run_info["data"]["defaultDatasetId"]
    log(f"Run started: {run_id}")

    # Poll for completion
    status_url = f"https://api.apify.com/v2/actor-runs/{run_id}?token={token}"
    elapsed = 0
    while elapsed < max_wait:
        time.sleep(poll_interval)
        elapsed += poll_interval

        try:
            status = api_request(status_url, timeout=30)
        except Exception:
            log(f"Poll failed at {elapsed}s, retrying...")
            continue

        run_status = status["data"]["status"]
        log(f"Status: {run_status} ({elapsed}s elapsed)")

        if run_status == "SUCCEEDED":
            break
        elif run_status in ("FAILED", "ABORTED", "TIMED-OUT"):
            raise RuntimeError(f"Actor run {run_status}: {status['data'].get('statusMessage', '')}")
    else:
        raise RuntimeError(f"Actor run timed out after {max_wait}s")

    # Fetch dataset items
    items_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={token}&format=json"
    items = api_request(items_url, timeout=60)

    if not isinstance(items, list):
        raise RuntimeError(f"Unexpected dataset response: {str(items)[:500]}")

    return items


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def cache_key(platform, location, checkin, checkout):
    slug = sanitize_filename(f"{location}_{checkin}_{checkout}")
    today = datetime.now().strftime("%Y-%m-%d")
    return f"{slug}_{platform}_{today}"


def cache_path(platform, location, checkin, checkout):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = cache_key(platform, location, checkin, checkout)
    return CACHE_DIR / f"{key}.json"


def load_cache(platform, location, checkin, checkout):
    path = cache_path(platform, location, checkin, checkout)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(platform, location, checkin, checkout, data):
    path = cache_path(platform, location, checkin, checkout)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Cached to {path}")


# ---------------------------------------------------------------------------
# Booking.com provider
# ---------------------------------------------------------------------------

def fetch_booking(args):
    """Search Booking.com via Apify voyager/booking-scraper."""
    token = get_token()

    actor_input = {
        "search": args.location,
        "checkIn": args.checkin,
        "checkOut": args.checkout,
        "adults": args.guests,
        "rooms": 1,
        "currency": args.currency,
        "language": "en-gb",
        "simple": False,
        "maxPages": 3,
    }

    # Apply rating filter (API expects string)
    if args.min_rating:
        actor_input["minScore"] = str(args.min_rating)

    # Apply property type filter
    if args.type and args.type in BOOKING_TYPE_MAP and BOOKING_TYPE_MAP[args.type]:
        actor_input["propertyType"] = BOOKING_TYPE_MAP[args.type][0]

    # Apply sort
    actor_input["sortBy"] = "review_score_and_price"

    log(f"Searching Booking.com for '{args.location}' ({args.checkin} to {args.checkout})...")
    items = run_actor(APIFY_BOOKING_ACTOR, actor_input, token)

    log(f"Received {len(items)} raw listings from Booking.com")

    # Normalize and filter
    listings = []
    for item in items:
        listing = normalize_booking_listing(item, args)
        if listing and passes_filters(listing, args):
            listings.append(listing)

    log(f"After filtering: {len(listings)} listings")
    return listings


def normalize_booking_listing(item, args):
    """Normalize a Booking.com listing to our standard format."""
    # Extract price from rooms if available
    price = None
    room_type = ""
    if item.get("rooms"):
        for room in item["rooms"]:
            if room.get("available") and room.get("price"):
                price = room["price"]
                room_type = room.get("roomType", "")
                break

    if price is None:
        price = item.get("price")

    if price is None:
        return None

    # Calculate total price
    try:
        checkin = datetime.strptime(args.checkin, "%Y-%m-%d")
        checkout = datetime.strptime(args.checkout, "%Y-%m-%d")
        nights = (checkout - checkin).days
    except ValueError:
        nights = 1

    # Extract location
    loc = item.get("location", {})
    lat = float(loc.get("lat", 0)) if loc.get("lat") else None
    lng = float(loc.get("lng", 0)) if loc.get("lng") else None

    # Extract address
    addr = item.get("address", {})
    if isinstance(addr, dict):
        address_str = addr.get("full", "")
    else:
        address_str = str(addr) if addr else ""

    # Extract photo
    photo_urls = []
    if item.get("image"):
        photo_urls.append(item["image"])

    # Actor returns total stay price, convert to nightly
    price_total = price
    price_nightly = round(price / nights, 2) if nights > 0 else price

    return {
        "name": item.get("name", ""),
        "url": item.get("url", ""),
        "platform": "booking",
        "price_nightly": price_nightly,
        "price_total": round(price_total, 2),
        "currency": args.currency,
        "rating": item.get("rating"),
        "review_count": item.get("reviews"),
        "type": item.get("type", ""),
        "stars": item.get("stars"),
        "bedrooms": None,
        "room_type": room_type,
        "amenities": [],
        "address": address_str,
        "location": {"lat": lat, "lng": lng},
        "distance_km": None,
        "description": item.get("description", ""),
        "photo_urls": photo_urls,
        "cancellation": "",
        "checkin_time": item.get("checkIn", ""),
        "checkout_time": item.get("checkOut", ""),
        "nights": nights,
    }


# ---------------------------------------------------------------------------
# Airbnb provider
# ---------------------------------------------------------------------------

def fetch_airbnb(args):
    """Search Airbnb via Apify tri_angle/airbnb-scraper."""
    token = get_token()

    actor_input = {
        "locationQueries": [args.location],
        "checkIn": args.checkin,
        "checkOut": args.checkout,
        "currency": args.currency,
        "includeReviews": True,
        "maxReviews": 10,
        "maxListings": 50,
    }

    if args.budget:
        actor_input["maxPrice"] = args.budget
    if args.min_price:
        actor_input["minPrice"] = args.min_price

    log(f"Searching Airbnb for '{args.location}' ({args.checkin} to {args.checkout})...")
    items = run_actor(APIFY_AIRBNB_ACTOR, actor_input, token)

    log(f"Received {len(items)} raw listings from Airbnb")

    # Normalize and filter
    listings = []
    for item in items:
        listing = normalize_airbnb_listing(item, args)
        if listing and passes_filters(listing, args):
            listings.append(listing)

    log(f"After filtering: {len(listings)} listings")
    return listings


def normalize_airbnb_listing(item, args):
    """Normalize an Airbnb listing to our standard format."""
    # Extract price from nested dict with string values like "€ 890"
    price_data = item.get("price", {})
    price_total = None
    if isinstance(price_data, dict):
        # Try discountedPrice first, then price, then originalPrice
        for field in ("discountedPrice", "price", "originalPrice"):
            raw = price_data.get(field, "")
            if raw:
                # Parse number from string like "€ 890" or "$1,200"
                nums = re.findall(r"[\d,]+\.?\d*", str(raw).replace(",", ""))
                if nums:
                    price_total = float(nums[0])
                    break
    elif isinstance(price_data, (int, float)):
        price_total = float(price_data)

    if price_total is None:
        return None

    # Calculate nights
    try:
        checkin = datetime.strptime(args.checkin, "%Y-%m-%d")
        checkout = datetime.strptime(args.checkout, "%Y-%m-%d")
        nights = (checkout - checkin).days
    except ValueError:
        nights = 1

    # Price from actor is total for stay
    price_nightly = round(price_total / nights, 2) if nights > 0 else price_total

    # Extract rating from nested dict
    rating_data = item.get("rating", {})
    overall_rating = None
    review_count = 0
    if isinstance(rating_data, dict):
        overall_rating = rating_data.get("guestSatisfaction")
        review_count = rating_data.get("reviewsCount", 0)
    elif isinstance(rating_data, (int, float)):
        overall_rating = float(rating_data)

    # Extract coordinates
    coords = item.get("coordinates", {})
    lat = float(coords.get("latitude", 0)) if coords.get("latitude") else None
    lng = float(coords.get("longitude", 0)) if coords.get("longitude") else None

    # Extract photos from images list
    photo_urls = []
    images = item.get("images", [])
    if isinstance(images, list):
        for img in images[:5]:
            if isinstance(img, dict):
                photo_urls.append(img.get("imageUrl", ""))
            elif isinstance(img, str):
                photo_urls.append(img)

    # Extract reviews
    reviews = item.get("reviews", [])
    review_texts = []
    if isinstance(reviews, list):
        for r in reviews[:10]:
            if isinstance(r, dict) and r.get("comments"):
                review_texts.append(r["comments"])

    # Build URL from ID
    listing_id = item.get("id", "")
    url = item.get("url", "") or f"https://www.airbnb.com/rooms/{listing_id}" if listing_id else ""

    # Name: use seoTitle or first part of description
    name = item.get("name", "") or item.get("seoTitle", "")
    if not name and item.get("description"):
        name = item["description"][:80]

    # Host info
    host_data = item.get("host", {})
    host_name = ""
    superhost = False
    if isinstance(host_data, dict):
        host_name = host_data.get("name", "")
        superhost = host_data.get("isSuperHost", False)

    # Cancellation
    cancel_policies = item.get("cancellationPolicies", [])
    cancellation = ""
    if isinstance(cancel_policies, list) and cancel_policies:
        cancellation = cancel_policies[0].get("policyName", "") if isinstance(cancel_policies[0], dict) else ""

    # Location subtitle for address
    address = item.get("locationSubtitle", "") or item.get("location", "")

    return {
        "name": name,
        "url": url,
        "platform": "airbnb",
        "price_nightly": price_nightly,
        "price_total": round(price_total, 2),
        "currency": args.currency,
        "rating": overall_rating,
        "review_count": review_count,
        "type": item.get("propertyType", "") or item.get("roomType", ""),
        "stars": None,
        "bedrooms": item.get("bedrooms"),
        "room_type": item.get("roomType", ""),
        "person_capacity": item.get("personCapacity"),
        "amenities": [],
        "address": address,
        "location": {"lat": lat, "lng": lng},
        "distance_km": None,
        "description": item.get("description", ""),
        "photo_urls": photo_urls,
        "cancellation": cancellation,
        "checkin_time": "",
        "checkout_time": "",
        "nights": nights,
        "host": {
            "name": host_name,
            "superhost": superhost,
        },
        "review_texts": review_texts,
    }


# ---------------------------------------------------------------------------
# Shared filtering
# ---------------------------------------------------------------------------

def passes_filters(listing, args):
    """Apply hard filters to a normalized listing. Returns True if it passes."""
    # Budget filter
    if args.budget and listing.get("price_nightly"):
        if listing["price_nightly"] > args.budget:
            return False

    # Minimum rating filter (Booking uses 1-10, Airbnb uses 1-5)
    if args.min_rating and listing.get("rating"):
        threshold = args.min_rating
        if listing.get("platform") == "airbnb" and threshold > 5:
            # Convert 10-scale to 5-scale: 8.0 -> 4.0, 9.0 -> 4.5
            threshold = threshold / 2
        if listing["rating"] < threshold:
            return False

    # Minimum bedrooms filter
    if args.beds and listing.get("bedrooms"):
        if listing["bedrooms"] < args.beds:
            return False

    # Radius filter (requires center coords and listing coords)
    if args.radius and listing.get("location"):
        lat = listing["location"].get("lat")
        lng = listing["location"].get("lng")
        if lat and lng and args._center_lat and args._center_lng:
            dist = haversine_km(args._center_lat, args._center_lng, lat, lng)
            listing["distance_km"] = round(dist, 1)
            if dist > args.radius:
                return False

    return True


# ---------------------------------------------------------------------------
# Center point geocoding (simple approach)
# ---------------------------------------------------------------------------

def estimate_center(listings):
    """Estimate center point from listing coordinates."""
    lats = []
    lngs = []
    for l in listings:
        loc = l.get("location", {})
        if loc.get("lat") and loc.get("lng"):
            lats.append(loc["lat"])
            lngs.append(loc["lng"])
    if lats and lngs:
        return sum(lats) / len(lats), sum(lngs) / len(lngs)
    return None, None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Search Booking.com and Airbnb for accommodation listings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Booking.com search:
  python .scripts/accommodation-search.py --platform booking --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21

  # Airbnb search:
  python .scripts/accommodation-search.py --platform airbnb --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21 --budget 100

  # Both platforms:
  python .scripts/accommodation-search.py --platform both --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21
        """,
    )
    parser.add_argument("--platform", choices=["booking", "airbnb", "both"], required=True)
    parser.add_argument("--location", required=True, help="City or area to search")
    parser.add_argument("--checkin", required=True, help="Check-in date (YYYY-MM-DD)")
    parser.add_argument("--checkout", required=True, help="Check-out date (YYYY-MM-DD)")
    parser.add_argument("--guests", type=int, default=2, help="Number of guests (default: 2)")
    parser.add_argument("--budget", type=float, help="Max nightly price")
    parser.add_argument("--min-price", type=float, help="Min nightly price")
    parser.add_argument("--min-rating", type=float, help="Minimum rating (e.g. 8.0 for Booking, 4.5 for Airbnb)")
    parser.add_argument("--beds", type=int, help="Minimum bedrooms")
    parser.add_argument("--type", choices=["entire", "hotel", "hostel", "guesthouse", "all"], default="entire",
                        help="Property type (default: entire)")
    parser.add_argument("--radius", type=float, help="Max km from city center")
    parser.add_argument("--currency", default="EUR", help="Currency code (default: EUR)")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, force fresh fetch")

    args = parser.parse_args()

    # Initialize center point placeholders for radius filtering
    args._center_lat = None
    args._center_lng = None

    all_listings = []

    # Booking.com
    if args.platform in ("booking", "both"):
        if not args.no_cache:
            cached = load_cache("booking", args.location, args.checkin, args.checkout)
            if cached:
                log(f"Using cached Booking.com data from {cached.get('fetched_at', 'unknown')}")
                all_listings.extend(cached.get("listings", []))
            else:
                listings = fetch_booking(args)
                booking_data = build_output("booking", args, listings)
                save_cache("booking", args.location, args.checkin, args.checkout, booking_data)
                all_listings.extend(listings)
        else:
            listings = fetch_booking(args)
            booking_data = build_output("booking", args, listings)
            save_cache("booking", args.location, args.checkin, args.checkout, booking_data)
            all_listings.extend(listings)

    # Airbnb
    if args.platform in ("airbnb", "both"):
        if not args.no_cache:
            cached = load_cache("airbnb", args.location, args.checkin, args.checkout)
            if cached:
                log(f"Using cached Airbnb data from {cached.get('fetched_at', 'unknown')}")
                all_listings.extend(cached.get("listings", []))
            else:
                listings = fetch_airbnb(args)
                airbnb_data = build_output("airbnb", args, listings)
                save_cache("airbnb", args.location, args.checkin, args.checkout, airbnb_data)
                all_listings.extend(listings)
        else:
            listings = fetch_airbnb(args)
            airbnb_data = build_output("airbnb", args, listings)
            save_cache("airbnb", args.location, args.checkin, args.checkout, airbnb_data)
            all_listings.extend(listings)

    # Apply radius filter if requested (needs center from all listings)
    if args.radius and not args._center_lat:
        center_lat, center_lng = estimate_center(all_listings)
        if center_lat and center_lng:
            args._center_lat = center_lat
            args._center_lng = center_lng
            # Re-filter with radius
            filtered = []
            for l in all_listings:
                loc = l.get("location", {})
                lat = loc.get("lat")
                lng = loc.get("lng")
                if lat and lng:
                    dist = haversine_km(center_lat, center_lng, lat, lng)
                    l["distance_km"] = round(dist, 1)
                    if dist <= args.radius:
                        filtered.append(l)
                else:
                    filtered.append(l)
            all_listings = filtered
            log(f"After radius filter ({args.radius}km): {len(all_listings)} listings")

    # Build final output
    output = build_output(args.platform, args, all_listings)
    print(json.dumps(output, indent=2, ensure_ascii=False))


def build_output(platform, args, listings):
    """Build the output JSON structure."""
    filters = {}
    if args.budget:
        filters["budget"] = args.budget
    if args.min_rating:
        filters["min_rating"] = args.min_rating
    if args.beds:
        filters["beds"] = args.beds
    if args.type:
        filters["type"] = args.type
    if args.radius:
        filters["radius_km"] = args.radius

    return {
        "platform": platform,
        "location": args.location,
        "checkin": args.checkin,
        "checkout": args.checkout,
        "guests": args.guests,
        "currency": args.currency,
        "fetched_at": datetime.now().isoformat(),
        "filters_applied": filters,
        "listing_count": len(listings),
        "listings": listings,
    }


if __name__ == "__main__":
    main()
