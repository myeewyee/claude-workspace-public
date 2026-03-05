#!/usr/bin/env python3
"""
Air quality search: real-time AQI comparison and historical monthly trends.

Dual-source:
  - WAQI (aqicn.org) for real-time current AQI by city name
  - OpenAQ for historical monthly PM2.5/AQI data

Usage:
    # Current AQI for multiple cities:
    python .scripts/air-quality-search.py current "London" "Paris" "Lisbon"

    # Historical monthly data for a city:
    python .scripts/air-quality-search.py history --city "London" --from 2024-01 --to 2025-12

Environment variables:
    WAQI_TOKEN    - WAQI API token (https://aqicn.org/data-platform/token/)
    OPENAQ_API_KEY - OpenAQ API key (https://explore.openaq.org/register)

    On Windows, if env vars aren't in the current shell, the script reads them
    from Windows User environment variables automatically.
"""

import argparse
import json
import math
import os
import platform
import re
import subprocess
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

CACHE_DIR = Path(__file__).parent / "aqi_data"

WAQI_BASE = "https://api.waqi.info"
OPENAQ_BASE = "https://api.openaq.org/v3"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_env(name):
    """Get an environment variable, falling back to Windows registry on Windows."""
    val = os.environ.get(name)
    if val:
        return val

    # Windows fallback: read from User environment variables
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


def api_request(url, *, headers=None, timeout=30):
    """Make an HTTP GET request and return parsed JSON."""
    headers = headers or {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:500]}") from e


def log(msg):
    """Print a status message to stderr."""
    print(f"[air-quality] {msg}", file=sys.stderr)


def pm25_to_aqi(pm25):
    """Convert PM2.5 concentration (ug/m3) to US EPA AQI.

    Uses the EPA breakpoint table for PM2.5 (24-hour average).
    """
    if pm25 is None or pm25 < 0:
        return None

    breakpoints = [
        (0.0, 12.0, 0, 50),
        (12.1, 35.4, 51, 100),
        (35.5, 55.4, 101, 150),
        (55.5, 150.4, 151, 200),
        (150.5, 250.4, 201, 300),
        (250.5, 350.4, 301, 400),
        (350.5, 500.4, 401, 500),
    ]

    for bp_lo, bp_hi, aqi_lo, aqi_hi in breakpoints:
        if bp_lo <= pm25 <= bp_hi:
            aqi = ((aqi_hi - aqi_lo) / (bp_hi - bp_lo)) * (pm25 - bp_lo) + aqi_lo
            return round(aqi)

    # Above 500.4: cap at 500+
    if pm25 > 500.4:
        return 500

    return None


def aqi_to_pm25(aqi):
    """Reverse-convert US EPA AQI to PM2.5 concentration (ug/m3).

    WAQI's iaqi.pm25.v returns the AQI sub-index, not raw concentration.
    This converts back to approximate PM2.5 ug/m3.
    """
    if aqi is None or aqi < 0:
        return None

    breakpoints = [
        (0, 50, 0.0, 12.0),
        (51, 100, 12.1, 35.4),
        (101, 150, 35.5, 55.4),
        (151, 200, 55.5, 150.4),
        (201, 300, 150.5, 250.4),
        (301, 400, 250.5, 350.4),
        (401, 500, 350.5, 500.4),
    ]

    for aqi_lo, aqi_hi, bp_lo, bp_hi in breakpoints:
        if aqi_lo <= aqi <= aqi_hi:
            pm25 = ((aqi - aqi_lo) / (aqi_hi - aqi_lo)) * (bp_hi - bp_lo) + bp_lo
            return round(pm25, 1)

    if aqi > 500:
        return round(500.4 + (aqi - 500) * 1.0, 1)

    return None


def aqi_category(aqi):
    """Return the US EPA AQI category label."""
    if aqi is None:
        return "Unknown"
    if aqi <= 50:
        return "Good"
    if aqi <= 100:
        return "Moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups"
    if aqi <= 200:
        return "Unhealthy"
    if aqi <= 300:
        return "Very Unhealthy"
    return "Hazardous"


# ---------------------------------------------------------------------------
# WAQI: Real-time current AQI
# ---------------------------------------------------------------------------

def get_waqi_token():
    """Get WAQI API token."""
    token = get_env("WAQI_TOKEN")
    if not token:
        raise RuntimeError(
            "WAQI_TOKEN not set. Get one free at https://aqicn.org/data-platform/token/"
        )
    return token


def waqi_search(keyword, token):
    """Search WAQI for stations matching a keyword. Returns list of stations."""
    encoded = urllib.parse.quote(keyword)
    url = f"{WAQI_BASE}/search/?keyword={encoded}&token={token}"
    resp = api_request(url)

    if resp.get("status") != "ok":
        raise RuntimeError(f"WAQI search failed: {resp}")

    return resp.get("data", [])


def waqi_feed(city, token):
    """Get current AQI feed for a city name."""
    encoded = urllib.parse.quote(city)
    url = f"{WAQI_BASE}/feed/{encoded}/?token={token}"
    resp = api_request(url)

    if resp.get("status") != "ok":
        # Try search as fallback
        log(f"Direct feed failed for '{city}', trying search...")
        stations = waqi_search(city, token)
        if not stations:
            return None

        # Pick the station with highest AQI relevance (first result)
        best = stations[0]
        station_uid = best.get("uid")
        if station_uid:
            url = f"{WAQI_BASE}/feed/@{station_uid}/?token={token}"
            resp = api_request(url)
            if resp.get("status") != "ok":
                return None

    data = resp.get("data", {})

    # Extract PM2.5 AQI sub-index and convert to concentration
    # WAQI's iaqi.pm25.v is the AQI sub-index, not raw ug/m3
    iaqi = data.get("iaqi", {})
    pm25_reading = iaqi.get("pm25", {})
    pm25_aqi = pm25_reading.get("v") if isinstance(pm25_reading, dict) else None
    pm25_value = aqi_to_pm25(pm25_aqi) if pm25_aqi is not None else None

    city_info = data.get("city", {})
    geo = city_info.get("geo", [])

    return {
        "city": city,
        "station": city_info.get("name", "Unknown"),
        "aqi": data.get("aqi"),
        "pm25": pm25_value,
        "dominant_pollutant": data.get("dominentpol", "Unknown"),
        "category": aqi_category(data.get("aqi")),
        "timestamp": data.get("time", {}).get("iso", ""),
        "latitude": float(geo[0]) if len(geo) > 0 else None,
        "longitude": float(geo[1]) if len(geo) > 1 else None,
        "source": "waqi",
        "attribution": data.get("attributions", []),
    }


def cmd_current(args):
    """Handle the 'current' subcommand: real-time AQI for multiple cities."""
    token = get_waqi_token()
    results = []

    for city in args.cities:
        log(f"Fetching current AQI for: {city}")
        try:
            result = waqi_feed(city, token)
            if result:
                results.append(result)
                log(f"  {city}: AQI {result['aqi']} ({result['category']}), "
                    f"PM2.5: {result['pm25']} ug/m3")
            else:
                log(f"  {city}: No data found")
                results.append({
                    "city": city,
                    "error": "No data found",
                    "source": "waqi",
                })
        except Exception as e:
            log(f"  {city}: Error - {e}")
            results.append({
                "city": city,
                "error": str(e),
                "source": "waqi",
            })

    output = {
        "mode": "current",
        "fetched_at": datetime.now().isoformat(),
        "city_count": len(results),
        "results": results,
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# OpenAQ: Historical monthly data
# ---------------------------------------------------------------------------

def get_openaq_key():
    """Get OpenAQ API key."""
    key = get_env("OPENAQ_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAQ_API_KEY not set. Get one free at https://explore.openaq.org/register"
        )
    return key


def openaq_request(path, params=None, api_key=None):
    """Make an OpenAQ API v3 request."""
    if params:
        query = urllib.parse.urlencode(params)
        url = f"{OPENAQ_BASE}{path}?{query}"
    else:
        url = f"{OPENAQ_BASE}{path}"

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    return api_request(url, headers=headers, timeout=60)


def openaq_find_locations(lat, lon, radius_m, api_key):
    """Find OpenAQ monitoring locations near coordinates.

    Returns list of locations with their sensors.
    """
    params = {
        "coordinates": f"{lat},{lon}",
        "radius": radius_m,
        "limit": 20,
    }
    resp = openaq_request("/locations", params=params, api_key=api_key)
    return resp.get("results", [])


def openaq_find_pm25_sensor(location):
    """Find the PM2.5 sensor ID from a location record."""
    sensors = location.get("sensors", [])
    for sensor in sensors:
        param = sensor.get("parameter", {})
        param_name = param.get("name", "").lower()
        if param_name in ("pm25", "pm2.5"):
            return sensor.get("id"), param.get("units", "")
    return None, None


def openaq_get_monthly(sensor_id, date_from, date_to, api_key):
    """Get monthly aggregated data for a sensor.

    Uses /v3/sensors/{id}/days/monthly endpoint.
    """
    params = {
        "datetime_from": f"{date_from}-01T00:00:00Z",
        "datetime_to": f"{date_to}-28T23:59:59Z",  # safe end-of-month
        "limit": 100,
    }

    resp = openaq_request(
        f"/sensors/{sensor_id}/days/monthly",
        params=params,
        api_key=api_key,
    )

    return resp.get("results", [])


def resolve_city_coordinates(city, waqi_token):
    """Use WAQI to resolve a city name to coordinates.

    OpenAQ doesn't support city name search, so we use WAQI's search
    to get coordinates, then query OpenAQ by coordinates.
    """
    log(f"Resolving coordinates for '{city}' via WAQI...")
    result = waqi_feed(city, waqi_token)
    if result and result.get("latitude") and result.get("longitude"):
        log(f"  Found: {result['station']} ({result['latitude']}, {result['longitude']})")
        return result["latitude"], result["longitude"]

    raise RuntimeError(f"Could not resolve coordinates for '{city}'")


def cmd_history(args):
    """Handle the 'history' subcommand: monthly PM2.5/AQI trends."""
    waqi_token = get_waqi_token()
    openaq_key = get_openaq_key()

    city = args.city
    date_from = args.date_from  # YYYY-MM
    date_to = args.date_to      # YYYY-MM

    # Check cache
    cache_file = get_cache_path(city, date_from, date_to)
    if not args.no_cache and cache_file.exists():
        log(f"Using cached data from {cache_file}")
        with open(cache_file, "r", encoding="utf-8") as f:
            cached = json.load(f)
        print(json.dumps(cached, indent=2, ensure_ascii=False))
        return

    # Step 1: resolve city to coordinates via WAQI
    lat, lon = resolve_city_coordinates(city, waqi_token)

    # Step 2: find nearby OpenAQ stations
    log(f"Searching OpenAQ for stations near ({lat}, {lon})...")
    locations = openaq_find_locations(lat, lon, radius_m=25000, api_key=openaq_key)

    if not locations:
        log("No OpenAQ stations found within 25km. Trying 50km...")
        locations = openaq_find_locations(lat, lon, radius_m=50000, api_key=openaq_key)

    if not locations:
        raise RuntimeError(f"No OpenAQ monitoring stations found near {city}")

    log(f"Found {len(locations)} stations")

    # Step 3: find best station with PM2.5 sensor
    best_location = None
    best_sensor_id = None
    best_units = None

    for loc in locations:
        sensor_id, units = openaq_find_pm25_sensor(loc)
        if sensor_id:
            # Prefer station with more data (longer operational period)
            if best_location is None:
                best_location = loc
                best_sensor_id = sensor_id
                best_units = units
            else:
                # Compare by datetime range (longer = more data)
                loc_first = loc.get("datetimeFirst", {}).get("utc", "")
                best_first = best_location.get("datetimeFirst", {}).get("utc", "")
                if loc_first < best_first:
                    best_location = loc
                    best_sensor_id = sensor_id
                    best_units = units

    if not best_sensor_id:
        raise RuntimeError(f"No PM2.5 sensor found at any station near {city}")

    station_name = best_location.get("name", "Unknown")
    log(f"Using station: {station_name} (sensor {best_sensor_id})")

    # Step 4: get monthly aggregated data
    log(f"Fetching monthly data from {date_from} to {date_to}...")
    monthly_data = openaq_get_monthly(best_sensor_id, date_from, date_to, openaq_key)

    # Step 5: format results
    months = []
    for entry in monthly_data:
        period = entry.get("period", {})
        summary = entry.get("value", entry.get("summary", {}))

        # Handle different response structures
        if isinstance(summary, dict):
            avg_pm25 = summary.get("avg")
            min_pm25 = summary.get("min")
            max_pm25 = summary.get("max")
        else:
            avg_pm25 = summary
            min_pm25 = None
            max_pm25 = None

        # Extract month label
        date_from_str = period.get("datetimeFrom", {}).get("utc", "")
        if date_from_str:
            month_label = date_from_str[:7]  # YYYY-MM
        else:
            month_label = "unknown"

        computed_aqi = pm25_to_aqi(avg_pm25)

        months.append({
            "month": month_label,
            "avg_pm25": round(avg_pm25, 1) if avg_pm25 is not None else None,
            "min_pm25": round(min_pm25, 1) if min_pm25 is not None else None,
            "max_pm25": round(max_pm25, 1) if max_pm25 is not None else None,
            "aqi": computed_aqi,
            "category": aqi_category(computed_aqi),
            "measurement_count": entry.get("parameter", {}).get("measurandsCount",
                                entry.get("count")),
        })

    # Sort by month
    months.sort(key=lambda m: m["month"])

    # Summary stats
    valid_aqi = [m["aqi"] for m in months if m["aqi"] is not None]
    valid_pm25 = [m["avg_pm25"] for m in months if m["avg_pm25"] is not None]

    output = {
        "mode": "history",
        "city": city,
        "station": station_name,
        "sensor_id": best_sensor_id,
        "units": best_units,
        "date_range": f"{date_from} to {date_to}",
        "fetched_at": datetime.now().isoformat(),
        "month_count": len(months),
        "summary": {
            "avg_aqi": round(sum(valid_aqi) / len(valid_aqi)) if valid_aqi else None,
            "worst_month": max(months, key=lambda m: m["aqi"] or 0)["month"] if months else None,
            "best_month": min(months, key=lambda m: m["aqi"] or 999)["month"] if months else None,
            "avg_pm25": round(sum(valid_pm25) / len(valid_pm25), 1) if valid_pm25 else None,
            "who_guideline_exceedance_months": len([m for m in months
                                                     if m["avg_pm25"] and m["avg_pm25"] > 15]),
        },
        "months": months,
        "source": "openaq",
        "coordinates": {"latitude": lat, "longitude": lon},
    }

    # Log summary to stderr
    if months:
        log(f"Results: {len(months)} months of data")
        if output["summary"]["avg_aqi"]:
            log(f"  Average AQI: {output['summary']['avg_aqi']}")
        if output["summary"]["worst_month"]:
            worst = next(m for m in months if m["month"] == output["summary"]["worst_month"])
            log(f"  Worst month: {worst['month']} (AQI {worst['aqi']})")
        if output["summary"]["best_month"]:
            best = next(m for m in months if m["month"] == output["summary"]["best_month"])
            log(f"  Best month: {best['month']} (AQI {best['aqi']})")

    # Cache
    save_cache(cache_file, output)

    print(json.dumps(output, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Caching
# ---------------------------------------------------------------------------

def get_cache_path(city, date_from, date_to):
    """Build cache file path for historical data."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", city).lower()
    return CACHE_DIR / f"{slug}_{date_from}_{date_to}.json"


def save_cache(path, data):
    """Save data to cache file."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    log(f"Cached to {path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Air quality search: real-time AQI and historical trends",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Current AQI for multiple cities:
  python .scripts/air-quality-search.py current "London" "Paris" "Lisbon"

  # Historical monthly data:
  python .scripts/air-quality-search.py history --city "London" --from 2024-01 --to 2025-12

  # Historical with fresh data (skip cache):
  python .scripts/air-quality-search.py history --city "Paris" --from 2023-01 --to 2025-12 --no-cache
        """,
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # current subcommand
    current_parser = subparsers.add_parser(
        "current", help="Get current AQI for one or more cities (WAQI API)"
    )
    current_parser.add_argument(
        "cities", nargs="+", help="City names to check (e.g. 'London' 'Paris')"
    )

    # history subcommand
    history_parser = subparsers.add_parser(
        "history", help="Get historical monthly PM2.5/AQI data (OpenAQ API)"
    )
    history_parser.add_argument(
        "--city", required=True, help="City name"
    )
    history_parser.add_argument(
        "--from", dest="date_from", required=True,
        help="Start month (YYYY-MM)"
    )
    history_parser.add_argument(
        "--to", dest="date_to", required=True,
        help="End month (YYYY-MM)"
    )
    history_parser.add_argument(
        "--no-cache", action="store_true", help="Skip cache, force fresh fetch"
    )

    args = parser.parse_args()

    try:
        if args.command == "current":
            cmd_current(args)
        elif args.command == "history":
            cmd_history(args)
    except RuntimeError as e:
        log(f"ERROR: {e}")
        sys.exit(1)
    except urllib.error.URLError as e:
        log(f"Network error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
