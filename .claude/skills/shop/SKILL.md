---
name: shop
description: "Product search on Thai e-commerce platforms. Wraps lazada-search.py with product analysis, comparison tables, and purchase recommendations. Triggers on shopping requests, product searches, price comparisons, and 'find me X' queries for physical products."
---

# Shop

Product search and recommendation skill for Thai e-commerce. Currently supports Lazada Thailand via Apify actor. Shopee planned as future addition.

## Module Registry

| Module | Status | Reference file | Scripts |
|--------|--------|---------------|---------|
| Lazada | Working | `references/lazada.md` | `lazada-search.py` |
| Shopee | Planned | (future) | (blocked: $30-40/mo actor rental) |

Load the relevant reference file when a module triggers.

## Trigger Contexts

- "Find me [product]" or "search for [product]" on Lazada/Shopee/Thai e-commerce
- Product comparison requests ("compare GaN chargers", "best robot vacuum under 5000")
- Price check requests ("how much is X on Lazada")
- Shopping recommendations ("I need a [product], what should I get?")

Do NOT trigger for: travel bookings (use `/travel`), digital products/subscriptions, or general web research about products (use web search).

## Workflow

### 1. Clarify the search
Before running a search, confirm:
- **Keyword**: what to search for. Help refine if vague ("charger" → "100W GaN USB-C charger").
- **Budget**: any price range? Convert to THB if given in other currencies.
- **Sort preference**: best match (default), price low-high, or price high-low.
- **Quality floor**: minimum rating? Default to 4+ stars for recommendations.

If the user gives a clear request ("find me a 100W GaN charger under 1500 baht"), skip clarification and search immediately.

### 2. Search
Run `lazada-search.py` with appropriate parameters. Load `references/lazada.md` for full CLI reference.

### 3. Analyze and recommend
From the results, build a comparison focusing on:
- **Value leaders**: best price-to-quality ratio (high sales + high rating + reasonable price)
- **Official store picks**: prefer official brand stores (UGREEN Official, Anker Official, etc.) for authenticity
- **Budget picks**: cheapest options that still have decent ratings (4+ stars, 50+ sold)
- **Premium picks**: highest rated/most sold regardless of price

Flag concerns:
- Sellers in China/Hong Kong (longer shipping, potential customs)
- "No Brand" items (may be knockoffs)
- Very low review counts (<10) on expensive items
- Unrealistic original prices (inflated to fake discounts)

### 4. Present results
Externalize to a file when there are 10+ products to compare. Use comparison table format. For quick searches (under 5 results), present in chat.

Output format for files: standard output file in `outputs/temp/` with `(temp)` suffix.

## Platform Notes

**Lazada Thailand:** prices in THB. Official stores are reliable. "LazMall" sellers are verified. Seller location matters for shipping speed (Paris = fast, China = slow). High sold counts (1K+) with 4.9+ ratings are strong quality signals.

## Task Hierarchy

Shopping tasks parent to `[[$Purchases & Shopping]]` MOC.
