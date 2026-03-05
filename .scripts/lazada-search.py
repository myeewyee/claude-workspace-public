#!/usr/bin/env python3
"""
Lazada Thailand product search via Apify actor.
Outputs structured JSON to stdout.

Usage:
    python .scripts/lazada-search.py "100W GaN charger"
    python .scripts/lazada-search.py "mechanical keyboard" --sort priceasc --max-price 2000
    python .scripts/lazada-search.py "robot vacuum" --min-rating 4 --limit 20

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
import urllib.request
from datetime import datetime
from pathlib import Path

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

CACHE_DIR = Path(__file__).parent / "lazada_data"

APIFY_ACTOR = "fatihtahta~lazada-scraper"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MAX_LIMIT = 100  # Hard cap to prevent accidental credit burn
MIN_ACTOR_LIMIT = 10  # Actor requires limit >= 10


def api_request(url, *, data=None, headers=None, timeout=30, retries=3):
    """Make an HTTP request and return parsed JSON. Retries on transient errors."""
    headers = headers or {}
    if data is not None and isinstance(data, (dict, list)):
        data = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")

    last_error = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read().decode("utf-8")
                try:
                    return json.loads(body)
                except json.JSONDecodeError:
                    return body
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                # Rate limited: back off and retry
                wait = 2 ** attempt * 5
                log(f"Rate limited (429), waiting {wait}s before retry {attempt + 1}/{retries}...")
                time.sleep(wait)
                last_error = e
                continue
            elif e.code == 402:
                raise RuntimeError(
                    f"Apify credits exhausted (HTTP 402). Check usage at https://console.apify.com/billing"
                ) from e
            elif e.code == 403:
                # Check for actor rental issues
                if "actor-is-not-rented" in body:
                    raise RuntimeError(
                        f"Actor requires rental. Check https://console.apify.com/actors"
                    ) from e
                raise RuntimeError(f"HTTP 403: {body[:500]}") from e
            else:
                raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries - 1:
                wait = 2 ** attempt * 2
                log(f"Network error, retrying in {wait}s ({attempt + 1}/{retries}): {e}")
                time.sleep(wait)
                last_error = e
                continue
            raise

    raise RuntimeError(f"Failed after {retries} retries: {last_error}")


def sanitize_filename(text, max_len=80):
    """Turn arbitrary text into a safe filename fragment."""
    text = re.sub(r"[^a-zA-Z0-9_-]", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:max_len]


def log(msg):
    """Print a status message to stderr."""
    print(f"[lazada-search] {msg}", file=sys.stderr)


def get_token():
    """Get Apify API token from environment."""
    token = os.environ.get("APIFY_API_TOKEN")
    if not token:
        raise RuntimeError(
            "APIFY_API_TOKEN not set. Get one at https://console.apify.com/account#/integrations"
        )
    return token


def run_actor(actor_id, actor_input, token, poll_interval=5, max_wait=180):
    """Start an Apify actor run, poll until done, return dataset items."""

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
# Data normalization
# ---------------------------------------------------------------------------

def parse_sold_count(sold_str):
    """Parse '16.0K sold' or '413 sold' into a numeric value."""
    if not sold_str:
        return 0
    text = str(sold_str).lower().replace(",", "")
    match = re.search(r"([\d.]+)\s*(k|m)?\s*sold", text)
    if not match:
        # Try just a number
        nums = re.findall(r"[\d.]+", text)
        return int(float(nums[0])) if nums else 0
    num = float(match.group(1))
    suffix = match.group(2)
    if suffix == "k":
        num *= 1000
    elif suffix == "m":
        num *= 1000000
    return int(num)


def normalize_product(item):
    """Flatten the nested actor output into a consistent product record."""
    pricing = item.get("pricing", {})
    inventory = item.get("inventory", {})
    ratings = item.get("ratings", {})
    vendor = item.get("vendor", {})
    brand = item.get("brand", {})
    media = item.get("media", {})

    current_price = pricing.get("current_price")
    original_price = pricing.get("original_price")

    # Parse prices to float
    try:
        current_price = float(current_price) if current_price else None
    except (ValueError, TypeError):
        current_price = None
    try:
        original_price = float(original_price) if original_price else None
    except (ValueError, TypeError):
        original_price = None

    # Parse rating
    rating_score = ratings.get("rating_score")
    try:
        rating_score = round(float(rating_score), 2) if rating_score else None
    except (ValueError, TypeError):
        rating_score = None

    # Parse review count
    review_count = ratings.get("review_count")
    try:
        review_count = int(review_count) if review_count else 0
    except (ValueError, TypeError):
        review_count = 0

    return {
        "product_id": item.get("product_id"),
        "name": item.get("product_name", ""),
        "url": item.get("product_url", ""),
        "price": current_price,
        "original_price": original_price,
        "discount": pricing.get("discount"),
        "currency": "THB",
        "in_stock": inventory.get("in_stock", True),
        "sold": parse_sold_count(inventory.get("item_sold", "")),
        "sold_display": inventory.get("item_sold", ""),
        "rating": rating_score,
        "review_count": review_count,
        "seller": vendor.get("seller_name", ""),
        "seller_location": vendor.get("location", ""),
        "brand": brand.get("brand_name", ""),
        "image": media.get("primary_image", ""),
    }


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def cache_path(keyword, sort):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = sanitize_filename(f"{keyword}_{sort}")
    today = datetime.now().strftime("%Y-%m-%d")
    return CACHE_DIR / f"{slug}_{today}.json"


def load_cache(keyword, sort):
    path = cache_path(keyword, sort)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_cache(keyword, sort, data):
    path = cache_path(keyword, sort)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Cached to {path}")


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def passes_filters(product, args):
    """Apply hard filters to a normalized product. Returns True if it passes."""
    if args.min_price and product.get("price"):
        if product["price"] < args.min_price:
            return False
    if args.max_price and product.get("price"):
        if product["price"] > args.max_price:
            return False
    if args.min_rating and product.get("rating"):
        if product["rating"] < args.min_rating:
            return False
    return True


def build_filters_summary(args):
    """Build a summary of applied filters."""
    filters = {}
    if args.min_price:
        filters["min_price"] = args.min_price
    if args.max_price:
        filters["max_price"] = args.max_price
    if args.min_rating:
        filters["min_rating"] = args.min_rating
    return filters


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Search Lazada Thailand products via Apify actor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic search:
  python .scripts/lazada-search.py "100W GaN charger"

  # Sort by price (ascending):
  python .scripts/lazada-search.py "mechanical keyboard" --sort priceasc

  # With price range and rating filter:
  python .scripts/lazada-search.py "robot vacuum" --min-price 5000 --max-price 15000 --min-rating 4

  # More results:
  python .scripts/lazada-search.py "wireless earbuds" --limit 30
        """,
    )
    parser.add_argument("keyword", help="Search keyword")
    parser.add_argument("--sort", choices=["best", "priceasc", "pricedesc"], default="best",
                        help="Sort order (default: best match)")
    parser.add_argument("--min-price", type=float, help="Minimum price (THB)")
    parser.add_argument("--max-price", type=float, help="Maximum price (THB)")
    parser.add_argument("--min-rating", type=float, help="Minimum rating (1-5)")
    parser.add_argument("--limit", type=int, default=20, help="Max products to fetch (default: 20)")
    parser.add_argument("--no-cache", action="store_true", help="Skip cache, force fresh fetch")

    args = parser.parse_args()

    # Cost guard: cap limit to prevent accidental credit burn
    if args.limit > MAX_LIMIT:
        log(f"WARNING: --limit {args.limit} exceeds cap of {MAX_LIMIT}. Clamping.")
        args.limit = MAX_LIMIT

    # Check cache
    if not args.no_cache:
        cached = load_cache(args.keyword, args.sort)
        if cached:
            log(f"Using cached data from {cached.get('fetched_at', 'unknown')}")
            products = cached.get("products", [])
            filtered = [p for p in products if passes_filters(p, args)]
            # Apply limit after filtering
            filtered = filtered[:args.limit]
            cached["products"] = filtered
            cached["product_count"] = len(filtered)
            cached["filters_applied"] = build_filters_summary(args)
            print(json.dumps(cached, indent=2, ensure_ascii=False))
            return

    # Build actor input (actor requires limit >= 10, we truncate output later)
    actor_limit = max(args.limit, MIN_ACTOR_LIMIT)
    actor_input = {
        "queries": [args.keyword],
        "country": "th",
        "sort": args.sort,
        "limit": actor_limit,
        "getReviews": False,
        "proxyConfiguration": {"useApifyProxy": True},
    }

    # Pass price filters to the actor if set (reduces result volume)
    if args.min_price:
        actor_input["minPrice"] = int(args.min_price)
    if args.max_price:
        actor_input["maxPrice"] = int(args.max_price)

    # Fetch
    log(f"Searching Lazada Thailand for '{args.keyword}'...")
    log("This typically takes 15-30 seconds.")

    try:
        items = run_actor(APIFY_ACTOR, actor_input, get_token())
    except RuntimeError as e:
        log(f"ERROR: {e}")
        sys.exit(1)
    except urllib.error.URLError as e:
        log(f"Network error: {e}")
        sys.exit(1)

    log(f"Received {len(items)} raw items")

    if not items:
        log("WARNING: Actor returned zero items. Possible causes: keyword too specific, actor issue, or Lazada blocking.")
        log("Try a broader keyword or --no-cache to retry.")

    # Filter out metadata records, normalize products
    products = []
    for item in items:
        if item.get("record_type") != "product":
            continue
        products.append(normalize_product(item))

    log(f"Extracted {len(products)} products")

    if not products and items:
        log("WARNING: Items returned but no products found. The actor may have returned only metadata.")

    # Apply local filters (in case actor didn't filter precisely)
    filtered = [p for p in products if passes_filters(p, args)]
    log(f"After filtering: {len(filtered)} products")

    # Sort
    if args.sort == "priceasc":
        filtered.sort(key=lambda p: p.get("price") or float("inf"))
    elif args.sort == "pricedesc":
        filtered.sort(key=lambda p: -(p.get("price") or 0))
    else:
        # Best match: keep actor's order but push 0-sold items down
        pass

    # Truncate to user's requested limit
    filtered = filtered[:args.limit]

    # Build output
    output = {
        "keyword": args.keyword,
        "country": "Thailand",
        "platform": "Lazada",
        "sort": args.sort,
        "currency": "THB",
        "fetched_at": datetime.now().isoformat(),
        "filters_applied": build_filters_summary(args),
        "product_count": len(filtered),
        "products": filtered,
    }

    # Cache the full unfiltered results for re-filtering
    cache_output = dict(output)
    cache_output["products"] = [normalize_product(item) for item in items if item.get("record_type") == "product"]
    cache_output["product_count"] = len(cache_output["products"])
    cache_output["filters_applied"] = {}
    save_cache(args.keyword, args.sort, cache_output)

    # Output filtered results
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
