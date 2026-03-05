# Car Rental Reference

## Workflow

Car rental is a commodity product. Simpler 3-step workflow (no qualitative filtering or review deep-dive needed).

### 1. Search
Run `car-rental-search.py` with location and dates.

```bash
python .scripts/car-rental-search.py \
  --pickup "Lisbon Airport, Portugal" \
  --pickup-date 2026-06-03 \
  --dropoff-date 2026-06-22
```

Or pass a Kayak URL directly (useful for precise location matching):
```bash
python .scripts/car-rental-search.py \
  --url "https://www.kayak.com/cars/Lisbon-Airport,Portugal-c31508/2026-06-03/2026-06-22?sort=price_a"
```

### 2. Filter and rank
Apply hard filters via CLI flags, then sort by price. Prefer well-known rental companies.

### 3. Recommend
Present top 3-5 options with: supplier, car model/class, price (total + daily), Kayak search URL. No output file needed for car rental unless it's part of a larger trip planning output.

## Script CLI Reference

### car-rental-search.py
Searches Kayak car rentals via Apify actor (`shahidirfan~Kayak-Car-Rental-Scraper`). Requires `APIFY_API_TOKEN`. Cost: ~$0.06/run.

| Flag | Description | Default |
|------|-------------|---------|
| `--pickup` | Pickup location (e.g. "Lisbon Airport, Portugal") | (required*) |
| `--pickup-date` | Pickup date (YYYY-MM-DD) | (required*) |
| `--dropoff-date` | Dropoff date (YYYY-MM-DD) | (required*) |
| `--url` | Direct Kayak search URL (overrides above three) | |
| `--max-price` | Max daily price in USD | |
| `--class` | Vehicle class whitelist (comma-separated: economy,compact,mini) | |
| `--no-cache` | Force fresh fetch | false |
| `--no-dedup` | Keep duplicate offers from different providers | false |

*Either `--url` or all three of `--pickup`, `--pickup-date`, `--dropoff-date` are required.

**Output:** JSON to stdout. Prices in USD. Offers sorted by daily price. Includes: vehicle name, class, supplier, daily/total price, Kayak search URL.

**Caching:** Day-based cache in `.scripts/car_rental_data/`. Re-filtering cached data is instant (no API call). Use `--no-cache` to force fresh fetch.

**Deduplication:** Removes same-car-same-price duplicates across meta-providers (Priceline, Booking.com often list the same offer on Kayak). Prefers well-known suppliers.

**Limitations:** Kayak data lacks transmission type, door/seat counts, fuel type, individual booking URLs, and insurance details. These are visible on Kayak when clicking through to book.
