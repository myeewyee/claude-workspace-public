# Flights Reference

## Source Selection

### Google Flights (primary, all searches)
Real-time data from GDS (Amadeus, Sabre, Travelport) + direct airline APIs + ATPCO fare database. Shows actual bookable fares. Use for all flight searches.

### Kiwi (secondary, LCC discovery only)
Covers 800+ airlines including LCCs not in GDS. Constructs virtual interline (multi-carrier itineraries that don't exist as single tickets). Use only for:
- Discovering budget carriers not on Google Flights
- Price floor benchmarking in stable conditions (no active disruptions)

Do not use Kiwi for booking recommendations. Virtual interline routes become unbookable during disruptions (the route through Iran that "exists" on Kiwi may route through closed airspace). Always verify any Kiwi-sourced route on Google Flights before recommending.

### Direct carrier checks
Budget carriers sometimes not in either source. When a carrier is missing from search results, check their website directly. Known carriers on Google Flights that may not appear in default searches:
- **Norse Atlantic Airways**: IATA N0 (Norwegian entity), Z0 (UK entity). LHR direct to LGW (4x weekly), OSL (4x weekly), ARN (4x weekly), MAN (weekly). 787-9 Dreamliner. Economy + premium economy only, no business. Include LGW/OSL/ARN/MAN in destination list to see Norse results.

## Workflow

### 1. Disruption check
See SKILL.md "Before Any Flight Search" section. This runs before every search, no exceptions.

### 2. Search
Run `flight-search.py` (Kiwi) with appropriate parameters.

```bash
python .scripts/flight-search.py \
  --origins LHR,LHR \
  --destinations LIS,FAO,BCN,MAD,FCO \
  --dates 2026-03-07,2026-03-08,2026-03-09 \
  --cabin economy \
  --delay 1.5
```

Output: JSON to stdout. Each record has: origin, destination, dest_city, depart_date, cabin, airline, departure_time, arrival_time, duration_h, stops, via (layover cities), price_eur, google_flights_url.

### 2b. Validate search coverage (multi-leg only)
For multi-leg itineraries, verify completeness before filtering:
- Cross-check all arrival airports from leg N as departure airports for leg N+1
- Verify all intended destinations are included in the search grid
- Check that no logical origin/destination combinations were missed
Note: another session is exploring improved approaches to this via the AI learning log. Check for updates before implementing.

### 3. Hard filter
Apply after search results are loaded:
- Remove routes through closed airspace (from disruption check)
- Price caps (user-specified or reasonable defaults)
- Maximum stops (typically 2)
- Time constraints (e.g., evening departures only)

### 4. Qualitative filter
Run preference confirmation (see SKILL.md). Then filter on:
- Airline reputation and service quality
- Connection quality (layover duration, airport, overnight vs daytime)
- Route directness (prefer fewer stops at similar price)
- Arrival time at destination

### 5. Shortlist
Build Pareto frontier: price vs duration vs stops. No single metric dominates. Present as comparison table in output file with columns: rank, airline, route, departure, arrival, duration, stops, via, price, booking link.

### 6. Review
For shortlisted options, check:
- Recent carrier disruption reports
- Airport connection quality (tight connections, terminal changes)
- Baggage policies if relevant

### 7. Recommend
Write output file to `outputs/` (or `outputs/temp/` for active trip searches) with:
- Comparison table (all shortlisted options)
- Per-option assessment (pros/cons)
- Booking links (Google Flights URLs)
- Top pick with reasoning

Summarize in chat: top pick, price, key trade-off. Link to the output file.

## Output Table Convention

Flight recommendation tables follow a specific format. This is a living document: update as preferences evolve.

### Economy tables (grouped by date)

Header pattern: `**Mar 9:** 3 flights, cheapest €1,151pp` (or `**Mar 6:** 1 flight` for single results).

Columns in order:

| Column | Format | Example |
|--------|--------|---------|
| ID | Bold, sequential per cabin | **E1**, **E23** |
| Price | € symbol, comma-separated, per person | €1,268 |
| Duration | Hours + minutes | 23h 10m |
| Route | Airport codes with → arrow | LHR→FRA |
| Stops | Integer | 0, 1, 2 |
| Via | Layover airport codes, or "Direct" | ALA, NQZ |
| Airline | As reported by Google Flights | Air Astana |
| Link | GF link with tfs protobuf param | [GF](https://...) |

### Business class table (single table, all dates)

Same columns as economy plus a **Date** column after Route:

`| ID | Price | Duration | Route | Date | Stops | Via | Airline | Link |`

Date format: `Mar 11`

### Formatting rules

- **Price is per person.** Google Flights returns total for all passengers. Divide by passenger count (usually 2).
- **€ symbol, not "EUR".** `€1,738` not `EUR 1,738` or `€ 1738`.
- **Duration as Xh YYm.** `23h 10m` not `23.1h` or `23 hr 10 min`.
- **Airport codes only in Route.** `LHR→FRA` not `Paris (LHR) → Frankfurt (FRA)`.
- **No departure/arrival times** in the main table. These add clutter. The GF link shows exact timing.
- **IDs are sequential per cabin.** Economy: E1, E2, ... Business: B1, B2, ...
- **Sort by price within each date** (economy) or globally (business).
- **Max ~10 rows per date.** Show top options by price. State total count in header.
- **Blank line above tables.** Markdown tables don't render without a space above them in Obsidian.
- **Airport code glossary.** Every output file includes a glossary of all airport codes used. Place near the top (after the context block). List codes alphabetically. Skip universally obvious ones only if the audience is a frequent flyer; when in doubt, include it. Format: `**CODE** City Name (Airport Name)` on a single line, or as a compact table.

### GF link format

Links use the protobuf `tfs` parameter for direct search page navigation:
```
https://www.google.com/travel/flights?tfs={base64_protobuf}&hl=en&tfu=EgQIABABIgA&curr=EUR
```

This takes users directly to the specific route/date/cabin results. The `tfs` param is generated by `fast-flights` during search. Generic `?q=Flights+from+X+to+Y` links are deprecated: they trigger a natural language search that surfaces irrelevant results.


## Script CLI Reference

### flight-search.py (Kiwi)
Single-route search via Kiwi MCP endpoint. Full argparse CLI.

| Flag | Description |
|------|-------------|
| `--origin` | Origin airport code |
| `--destination` | Destination airport code |
| `--date` | Departure date (DD/MM/YYYY) |
| `--return-date` | Return date (DD/MM/YYYY) |
| `--max-stops` | Maximum stopovers |
| `--cabin` | Cabin class (M/W/C/F) |
