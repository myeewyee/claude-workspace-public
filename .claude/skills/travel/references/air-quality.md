# Air Quality Module

Real-time AQI comparison and historical monthly PM2.5/AQI trends. Dual-source: WAQI for current, OpenAQ for historical.

Triggers on: air quality, AQI, pollution queries (both within trip planning and standalone).

## Script CLI

```bash
# Current AQI for multiple cities (WAQI API):
python .scripts/air-quality-search.py current "City 1" "City 2" "City 3"

# Historical monthly data (OpenAQ API):
python .scripts/air-quality-search.py history --city "City Name" --from YYYY-MM --to YYYY-MM
python .scripts/air-quality-search.py history --city "City Name" --from 2024-01 --to 2025-12 --no-cache
```

**Environment:** `WAQI_TOKEN` and `OPENAQ_API_KEY` (set as Windows User environment variables). Script reads from Windows registry as fallback if shell env vars aren't set.

**Output:** JSON to stdout, status messages to stderr. History mode caches to `.scripts/aqi_data/`.

## Comparison Workflow (trip planning)

Use when comparing air quality across destination candidates.

1. Run `current` with all candidate cities.
2. Present comparison table: city, AQI, PM2.5 (ug/m3), category.
3. Flag any city with AQI > 100 (Unhealthy for Sensitive Groups).
4. If seasonal timing matters (e.g., "should I go in March or June?"), run `history` for relevant cities.
5. Summarize: which destinations have clean air for the travel dates?

## Deep-Dive Workflow (single city)

Use for "what's the air quality like in X?" questions.

1. Run `current` for real-time snapshot.
2. Run `history` for 2+ years to show seasonal pattern.
3. Summarize: best/worst months, burning season window (if applicable), WHO guideline (15 ug/m3 annual) exceedance.
4. Reference the user's vault note [[Air quality]] for health protocols and monitoring equipment context (do not reproduce health advice, just link).

## AQI Interpretation

| AQI Range | Category | PM2.5 (ug/m3) | Guidance |
|-----------|----------|---------------|----------|
| 0-50 | Good | 0-12.0 | No concern |
| 51-100 | Moderate | 12.1-35.4 | Sensitive individuals may notice |
| 101-150 | USG | 35.5-55.4 | Sensitive groups reduce outdoor activity |
| 151-200 | Unhealthy | 55.5-150.4 | Everyone reduce prolonged outdoor exertion |
| 201-300 | Very Unhealthy | 150.5-250.4 | Everyone avoid outdoor exertion |
| 301-500 | Hazardous | 250.5-500.4 | Emergency conditions |

**WHO daily guideline:** 15 ug/m3 PM2.5 (24-hour average).

**PM2.5 to AQI formula:** The script computes this automatically. For manual checks: AQI 100 = 35.4 ug/m3, AQI 150 = 55.4 ug/m3, AQI 200 = 150.4 ug/m3.

## Notes

- **WAQI** returns AQI sub-indices per pollutant, not raw concentrations. The script converts PM2.5 sub-index back to ug/m3.
- **OpenAQ** doesn't support city name search. The script chains: WAQI city lookup → coordinates → OpenAQ nearby station search → PM2.5 sensor → monthly aggregation.
- **Station selection:** OpenAQ picks the station with the longest operational history near the target coordinates. For London, this resolves to a local monitoring station.
- **Data availability varies by city.** Some cities have sparse OpenAQ coverage. Current mode (WAQI) has broader coverage than history mode (OpenAQ).
