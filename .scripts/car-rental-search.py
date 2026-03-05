#!/usr/bin/env python3
"""
Car rental search: searches Kayak for car rental offers via Apify actor.
Outputs structured JSON to stdout.

Usage:
    python .scripts/car-rental-search.py --pickup "Lisbon Airport, Portugal" --pickup-date 2026-06-03 --dropoff-date 2026-06-22
    python .scripts/car-rental-search.py --pickup "Lisbon Airport, Portugal" --pickup-date 2026-06-03 --dropoff-date 2026-06-22 --max-price 30 --class economy,compact
    python .scripts/car-rental-search.py --url "https://www.kayak.com/cars/Lisbon-Airport,Portugal-c31508/2026-06-03/2026-06-22?sort=price_a"

Environment variables:
    APIFY_API_TOKEN - Apify API token
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

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

CACHE_DIR = Path(__file__).parent / "car_rental_data"

APIFY_ACTOR = "shahidirfan~Kayak-Car-Rental-Scraper"


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
    print(f"[car-rental-search] {msg}", file=sys.stderr)


def get_token():
    """Get Apify API token from environment."""
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Get one at https://console.apify.com/account#/integrations"
        )
    return token


def run_actor(actor_id, actor_input, token, poll_interval=10, max_wait=300):
    """Start an Apify actor run asynchronously, poll until done, return dataset items."""

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
# Kayak URL construction
# ---------------------------------------------------------------------------

def build_kayak_url(pickup, pickup_date, dropoff_date, sort="price_a"):
    """Build a Kayak car rental search URL from location and dates.

    Location format for Kayak: "City,Country" or "City-Airport,Country-cXXXXX".
    We normalize the pickup string into Kayak's expected format.
    """
    # Normalize location for Kayak URL: replace spaces with hyphens, ensure comma separation
    location = pickup.strip()

    # If it looks like "City, Country" or "City Airport, Country", convert for URL
    # Kayak format: City-Airport,Country (no spaces, hyphen-separated words)
    parts = [p.strip() for p in location.split(",")]
    kayak_parts = [p.replace(" ", "-") for p in parts]
    kayak_location = ",".join(kayak_parts)

    return f"https://www.kayak.com/cars/{kayak_location}/{pickup_date}/{dropoff_date}?sort={sort}"


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def cache_path(pickup, pickup_date, dropoff_date):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = sanitize_filename(f"{pickup}_{pickup_date}_{dropoff_date}")
    today = datetime.now().strftime("%Y-%m-%d")
    return CACHE_DIR / f"{slug}_{today}.json"


def load_cache(pickup, pickup_date, dropoff_date):
    path = cache_path(pickup, pickup_date, dropoff_date)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(pickup, pickup_date, dropoff_date, data):
    path = cache_path(pickup, pickup_date, dropoff_date)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Cached to {path}")


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def fetch_car_rentals(kayak_url):
    """Search car rentals via Kayak Apify actor."""
    token = get_token()

    actor_input = {
        "startUrl": kayak_url,
    }

    log(f"Searching: {kayak_url}")
    log("This typically takes 30-60 seconds.")

    items = run_actor(APIFY_ACTOR, actor_input, token)
    log(f"Received {len(items)} raw offers")
    return items


def parse_price(price_str):
    """Parse a price string like '$27' or '€35' into a float."""
    if not price_str:
        return None
    # Remove currency symbols and commas, extract number
    nums = re.findall(r"[\d,]+\.?\d*", str(price_str).replace(",", ""))
    if nums:
        return float(nums[0])
    return None


def extract_car_class(car_type):
    """Extract vehicle class from Kayak car_type string like 'Hyundai i10 (Mini)'."""
    match = re.search(r"\(([^)]+)\)", car_type or "")
    if match:
        return match.group(1).lower()
    return ""


def normalize_offer(item, args):
    """Normalize a Kayak car rental offer to our standard format."""
    price_daily = parse_price(item.get("price_per_day"))
    price_total = parse_price(item.get("total_price"))

    # Calculate rental days
    try:
        pickup_dt = datetime.strptime(args.pickup_date, "%Y-%m-%d")
        dropoff_dt = datetime.strptime(args.dropoff_date, "%Y-%m-%d")
        rental_days = (dropoff_dt - pickup_dt).days
    except ValueError:
        rental_days = 1

    # If we have total but not daily, calculate
    if price_total and not price_daily and rental_days > 0:
        price_daily = round(price_total / rental_days, 2)
    # If we have daily but not total
    if price_daily and not price_total:
        price_total = round(price_daily * rental_days, 2)

    car_type_full = item.get("car_type", "")
    car_class = extract_car_class(car_type_full)

    # Extract car name (everything before the parentheses)
    car_name = re.sub(r"\s*\([^)]*\)\s*$", "", car_type_full).strip()

    return {
        "vehicle_name": car_name,
        "vehicle_class": car_class,
        "car_type_full": car_type_full,
        "price_total": price_total,
        "price_daily": price_daily,
        "currency": "USD",
        "supplier": item.get("company", ""),
        "rental_days": rental_days,
        "search_url": item.get("url", ""),
        "raw_id": item.get("raw_id", ""),
        "rating": item.get("rating"),
    }


def deduplicate_offers(offers):
    """Remove duplicate offers (same car at same price from different meta-providers).

    Kayak often shows the same offer from Priceline, IPRICELINECARWHISKY, and Booking.com.
    Keep the one with the most recognizable supplier name.
    """
    # Group by (car_type_full, price_daily)
    groups = {}
    for offer in offers:
        key = (offer["car_type_full"], offer["price_daily"])
        if key not in groups:
            groups[key] = []
        groups[key].append(offer)

    # Pick best from each group (prefer well-known suppliers)
    preferred_suppliers = ["europcar", "hertz", "avis", "sixt", "enterprise", "budget",
                           "alamo", "national", "thrifty", "dollar", "goldcar",
                           "booking.com", "rentalcars"]
    deduped = []
    for key, group in groups.items():
        if len(group) == 1:
            deduped.append(group[0])
        else:
            # Sort: preferred suppliers first, then alphabetically
            def supplier_rank(o):
                s = o["supplier"].lower()
                for i, pref in enumerate(preferred_suppliers):
                    if pref in s:
                        return i
                return 100
            group.sort(key=supplier_rank)
            deduped.append(group[0])

    return deduped


def passes_filters(offer, args):
    """Apply hard filters to a normalized offer. Returns True if it passes."""
    # Price filter (daily)
    if args.max_price and offer.get("price_daily"):
        if offer["price_daily"] > args.max_price:
            return False

    # Vehicle class filter
    if args.car_class:
        allowed = [c.strip().lower() for c in args.car_class.split(",")]
        offer_class = offer.get("vehicle_class", "").lower()
        if offer_class and not any(a in offer_class for a in allowed):
            return False

    return True


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Search car rentals via Kayak (Apify actor)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search:
  python .scripts/car-rental-search.py --pickup "Lisbon Airport, Portugal" --pickup-date 2026-06-03 --dropoff-date 2026-06-22

  # With filters:
  python .scripts/car-rental-search.py --pickup "Lisbon Airport, Portugal" --pickup-date 2026-06-03 --dropoff-date 2026-06-22 --max-price 40 --class economy,compact

  # Direct Kayak URL (for precise location matching):
  python .scripts/car-rental-search.py --url "https://www.kayak.com/cars/Lisbon-Airport,Portugal-c31508/2026-06-03/2026-06-22?sort=price_a"
        """,
    )
    parser.add_argument("--pickup", help="Pickup location (e.g. 'Lisbon Airport, Portugal')")
    parser.add_argument("--pickup-date", help="Pickup date (YYYY-MM-DD)")
    parser.add_argument("--dropoff-date", help="Dropoff date (YYYY-MM-DD)")
    parser.add_argument("--url", help="Direct Kayak search URL (overrides --pickup and dates)")
    parser.add_argument("--max-price", type=float, help="Max daily price (USD)")
    parser.add_argument("--class", dest="car_class", help="Vehicle class whitelist (comma-separated, e.g. economy,compact,mini)")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, force fresh fetch")
    parser.add_argument("--no-dedup", action="store_true", help="Keep duplicate offers from different providers")

    args = parser.parse_args()

    # Determine Kayak URL
    if args.url:
        kayak_url = args.url
        # Extract dates from URL for caching
        date_match = re.search(r"/(\d{4}-\d{2}-\d{2})/(\d{4}-\d{2}-\d{2})", kayak_url)
        if date_match:
            args.pickup_date = date_match.group(1)
            args.dropoff_date = date_match.group(2)
        else:
            args.pickup_date = "unknown"
            args.dropoff_date = "unknown"
        # Extract location from URL
        loc_match = re.search(r"/cars/([^/]+)/", kayak_url)
        args.pickup = loc_match.group(1) if loc_match else "unknown"
    elif args.pickup and args.pickup_date and args.dropoff_date:
        kayak_url = build_kayak_url(args.pickup, args.pickup_date, args.dropoff_date)
    else:
        parser.error("Either --url or (--pickup, --pickup-date, --dropoff-date) are required")

    # Check cache
    if not args.no_cache:
        cached = load_cache(args.pickup, args.pickup_date, args.dropoff_date)
        if cached:
            log(f"Using cached data from {cached.get('fetched_at', 'unknown')}")
            # Re-apply filters to cached data
            offers = cached.get("offers", [])
            filtered = [o for o in offers if passes_filters(o, args)]
            cached["offers"] = filtered
            cached["offer_count"] = len(filtered)
            cached["filters_applied"] = build_filters_summary(args)
            print(json.dumps(cached, indent=2, ensure_ascii=False))
            return

    # Fetch
    try:
        items = fetch_car_rentals(kayak_url)
    except RuntimeError as e:
        log(f"ERROR: {e}")
        sys.exit(1)
    except urllib.error.URLError as e:
        log(f"Network error: {e}")
        sys.exit(1)

    # Normalize
    offers = [normalize_offer(item, args) for item in items]

    # Deduplicate
    if not args.no_dedup:
        before = len(offers)
        offers = deduplicate_offers(offers)
        if before != len(offers):
            log(f"Deduplicated: {before} -> {len(offers)} offers")

    # Filter
    filtered = [o for o in offers if passes_filters(o, args)]
    log(f"After filtering: {len(filtered)} offers (from {len(offers)} unique)")

    # Sort by daily price
    filtered.sort(key=lambda o: o.get("price_daily") or float("inf"))

    # Build output
    try:
        pickup_dt = datetime.strptime(args.pickup_date, "%Y-%m-%d")
        dropoff_dt = datetime.strptime(args.dropoff_date, "%Y-%m-%d")
        rental_days = (dropoff_dt - pickup_dt).days
    except ValueError:
        rental_days = 0

    output = {
        "pickup": args.pickup,
        "pickup_date": args.pickup_date,
        "dropoff_date": args.dropoff_date,
        "rental_days": rental_days,
        "source": "kayak",
        "kayak_url": kayak_url,
        "currency": "USD",
        "fetched_at": datetime.now().isoformat(),
        "filters_applied": build_filters_summary(args),
        "offer_count": len(filtered),
        "offers": filtered,
    }

    # Cache the full unfiltered results for re-filtering
    cache_output = dict(output)
    cache_output["offers"] = [normalize_offer(item, args) for item in items]
    if not args.no_dedup:
        cache_output["offers"] = deduplicate_offers(cache_output["offers"])
    cache_output["offer_count"] = len(cache_output["offers"])
    cache_output["filters_applied"] = {}
    save_cache(args.pickup, args.pickup_date, args.dropoff_date, cache_output)

    # Output filtered results
    print(json.dumps(output, indent=2, ensure_ascii=False))


def build_filters_summary(args):
    """Build a summary of applied filters."""
    filters = {}
    if args.max_price:
        filters["max_daily_price"] = args.max_price
    if args.car_class:
        filters["vehicle_class"] = args.car_class
    return filters


if __name__ == "__main__":
    main()
