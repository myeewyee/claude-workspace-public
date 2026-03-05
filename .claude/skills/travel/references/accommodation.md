# Accommodation Reference

## Workflow

### 1. Search
Run `accommodation-search.py` with location, dates, and filters.

```bash
# Both platforms
python .scripts/accommodation-search.py \
  --platform both \
  --location "Barcelona, Spain" \
  --checkin 2026-06-01 \
  --checkout 2026-06-21 \
  --min-rating 8.0 \
  --type entire \
  --currency EUR

# Single platform
python .scripts/accommodation-search.py \
  --platform airbnb \
  --location "Barcelona, Spain" \
  --checkin 2026-06-01 \
  --checkout 2026-06-21 \
  --budget 100
```

Default: `--platform both` unless user specifies. Output: JSON to stdout, cached in `.scripts/accommodation_data/`.

### 2. Hard filter
Script-side filters (passed as CLI flags):
- Budget (max nightly price). No hard universal cap: destination cost-of-living varies.
- Min rating: 8.0 for Booking.com (10-point scale), 4.5 for Airbnb (5-point scale)
- Property type: entire (default), hotel, hostel, guesthouse
- Bedrooms minimum
- Radius from center (km)

### 3. Qualitative filter
Run preference confirmation (see SKILL.md). Key signals from the user's preferences:
- **Noise isolation / privacy** (top priority): standalone unit over shared building, isolated position on property, natural ambient sound is positive
- **Deep-dive before booking**: cross-reference reviews vs property website, analyze layout, verify room type
- **Greenery/views**: descriptions mentioning gardens, nature, scenic views
- **Walkability**: proximity to town center, restaurants, groceries
- **Workspace**: desk, reliable WiFi, quiet environment for work
- **Balcony/outdoor space**: private outdoor area

Narrow from ~10-15 filtered listings to 3-5 candidates.

### 4. Shortlist
Write shortlist to output file with per-property: name, platform, URL, nightly/total price, rating, review count, key amenities, description highlights, photo links.

### 5. Review deep-dive
Run `review_scraper.py` for each shortlisted property. Only for shortlisted properties (Apify quota).

```bash
# Booking.com reviews
python .scripts/review_scraper.py --platform booking --url "https://www.booking.com/hotel/..." --max-reviews 50

# Airbnb reviews (uses dedicated reviews actor, NOT search actor)
python .scripts/review_scraper.py --platform airbnb --url "https://www.airbnb.com/rooms/..." --max-reviews 50

# Google Maps reviews (third source, if available)
python .scripts/review_scraper.py --platform google --url "https://maps.google.com/..." --max-reviews 100
```

Mine reviews for preference signals: noise mentions, workspace quality, views/light/greenery, kitchen quality, walkability notes, long-stay viability, host responsiveness.

### 6. Recommend
Update output file with review analysis. Include:
- Per-property: review highlights (positive + negative), preference alignment score
- Top pick with reasoning
- Backup option
- Action items (things to verify before booking, e.g., WiFi speed)
- Clickable booking URLs

**Photo limitation:** Claude cannot evaluate listing images. Include clickable photo URLs in output file. Mine reviews for visual/spatial quality mentions as proxy. the user does a quick visual scan of shortlisted listing links.

## Script CLI Reference

### accommodation-search.py
Searches Booking.com and Airbnb via Apify actors. Requires `APIFY_API_TOKEN`.

| Flag | Description | Default |
|------|-------------|---------|
| `--platform` | booking / airbnb / both | (required) |
| `--location` | City or area | (required) |
| `--checkin` | Check-in date (YYYY-MM-DD) | (required) |
| `--checkout` | Check-out date (YYYY-MM-DD) | (required) |
| `--guests` | Number of guests | 2 |
| `--budget` | Max nightly price | (none) |
| `--min-price` | Min nightly price | (none) |
| `--min-rating` | Minimum rating | (none) |
| `--beds` | Minimum bedrooms | (none) |
| `--type` | entire / hotel / hostel / guesthouse / all | entire |
| `--radius` | Max km from center | (none) |
| `--currency` | Currency code | EUR |
| `--no-cache` | Force fresh fetch | false |

Apify actors: `voyager~booking-scraper` (Booking.com), `tri_angle~airbnb-scraper` (Airbnb). Cache: `.scripts/accommodation_data/`.

**Apify quota awareness:** Accommodation search actors use significant compute (~5 min for Booking, ~90 sec for Airbnb). the user has Apify Starter plan ($29/month). Run searches judiciously. Review scraping adds more compute, so only scrape reviews for shortlisted properties.

### review_scraper.py
Pulls reviews from Google Maps, Booking.com, and Airbnb via Apify. Requires `APIFY_API_TOKEN`.

| Flag | Description | Default |
|------|-------------|---------|
| `--platform` | google / booking / airbnb | (required) |
| `--url` | Property URL | (required) |
| `--max-reviews` | Maximum reviews to fetch | 50 |
| `--no-cache` | Force fresh fetch | false |

Apify actors:
- Google Maps: `automation-lab~google-maps-reviews-scraper`
- Booking.com: `voyager~booking-reviews-scraper`
- Airbnb: `tri_angle~airbnb-reviews-scraper` (dedicated reviews actor, NOT the search actor `tri_angle~airbnb-scraper` which rejects listing detail URLs)

Cache: `.scripts/review_data/`.
