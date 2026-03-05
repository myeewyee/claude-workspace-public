# Lazada Reference

## Script CLI Reference

### lazada-search.py
Searches Lazada Thailand products via Apify actor (`fatihtahta/lazada-scraper`). Requires `APIFY_API_TOKEN`. Cost: ~$0.005/result (pay-per-result, no monthly rental).

```bash
python .scripts/lazada-search.py "100W GaN charger"
python .scripts/lazada-search.py "mechanical keyboard" --sort priceasc --max-price 2000
python .scripts/lazada-search.py "robot vacuum" --min-price 5000 --max-price 15000 --min-rating 4 --limit 30
```

| Flag | Description | Default |
|------|-------------|---------|
| `keyword` (positional) | Search keyword | (required) |
| `--sort` | Sort order: `best`, `priceasc`, `pricedesc` | `best` |
| `--min-price` | Minimum price in THB | |
| `--max-price` | Maximum price in THB | |
| `--min-rating` | Minimum rating (1-5) | |
| `--limit` | Max products to fetch | 20 |
| `--no-cache` | Force fresh fetch | false |

**Output:** JSON to stdout with product array. Each product has: `product_id`, `name`, `url`, `price`, `original_price`, `discount`, `currency` (THB), `in_stock`, `sold` (numeric), `sold_display` (string), `rating`, `review_count`, `seller`, `seller_location`, `brand`, `image`.

**Caching:** Day-based cache in `.scripts/lazada_data/`. Re-filtering cached data is instant (no API call). Use `--no-cache` for fresh results.

**Typical timing:** 15-60 seconds for a fresh search (Apify actor startup + crawl). Cached results are instant.

## Data Quality Notes

- `sold` is parsed from display strings ("16.0K sold" → 16000). Use for sorting/comparison.
- `rating` is a float (e.g., 4.95). Most products cluster 4.8-5.0, so small differences matter.
- `original_price` and `discount` may be null (not all products show discounts).
- `seller_location`: "Paris" = domestic fast shipping. "China"/"Hong Kong" = cross-border, slower.
- `brand`: "No Brand" means the actor couldn't identify a brand. May be generic/unbranded product.

## Seller Trust Signals

| Signal | Interpretation |
|--------|---------------|
| Official Store (e.g., "UGREEN Official Store") | Authorized, genuine products |
| LazMall badge (visible on Lazada site, not in API data) | Verified seller with return guarantee |
| Paris location + high sales + high rating | Reliable domestic seller |
| China/HK location + low sales + no brand | Higher risk, longer shipping |
| Very high original price with 60-70% "discount" | Common marketing tactic, compare actual prices |

## Limitations

- Search results are Lazada only (no Shopee). For cross-platform comparison, manual Shopee checking is needed until Shopee module is added.
- No individual product detail scraping (specifications, full descriptions). Only search result data.
- No review text (the actor supports it via `--getReviews` but we disable it to keep costs down).
- Category browsing is supported via URL but not yet exposed in the CLI (future enhancement).
