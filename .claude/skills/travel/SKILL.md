---
name: travel
description: "Travel search and recommendation skill. Wraps flight, accommodation, car rental, air quality, and review scripts with source selection logic, disruption checking, preference confirmation, and structured workflows. Triggers on flight searches, accommodation searches, car rental, air quality/AQI queries, trip planning, and travel booking discussions. Modular: flights, accommodation, car rental, and air quality are mature; visas, itinerary, activities are future modules."
---

# Travel

Knowledge layer for travel search and recommendations. Wraps existing scripts with decision logic, source selection, and institutional memory. The skill tells Claude which tools exist, when to use them, and how to validate results.

## Module Registry

| Module | Status | Reference file | Scripts |
|--------|--------|---------------|---------|
| Flights | Mature | `references/flights.md` | `google-flights-search.py`, `flight-analysis.py` |
| Accommodation | Mature | `references/accommodation.md` | `accommodation-search.py`, `review_scraper.py` |
| Car rental | Working | `references/car-rental.md` | `car-rental-search.py` |
| Air quality | Working | `references/air-quality.md` | `air-quality-search.py` |
| Visas | Planned | (future) | |
| Itinerary | Planned | (future) | |
| Activities | Planned | (future) | |

Load the relevant reference file when a module triggers. Each file has the full workflow, script CLI reference, and domain-specific guidance.

## Trigger Contexts

- Flight search or booking requests → load `references/flights.md`
- Accommodation search requests → load `references/accommodation.md`
- Car rental requests → load `references/car-rental.md`
- Air quality, AQI, pollution queries → load `references/air-quality.md`
- Trip planning discussions → load all relevant module references
- Travel route, airline, or destination questions → load `references/flights.md`

## Before Any Flight Search: Disruption Check

Run a quick web search for airspace closures and conflict zones affecting the route corridor before every flight search. This is not optional.

1. Search: `"airspace closures [region] [current month/year]"` and `"flight disruptions [origin] [destination]"`.
2. Check: Russian airspace (closed to EU/UK/US carriers since 2022), any active conflict zones, airline groundings.
3. Filter: remove flights routing through closed airspace before presenting results. Note what was filtered and why.

Why: Kiwi constructs virtual interline routes through any airspace, including closed zones. Google Flights shows routes carriers sell, but doesn't flag geopolitical risk. The Feb 2026 Iran strikes collapsed Gulf airspace and grounded Emirates/Qatar/Etihad overnight. Without this check, recommendations can include unbookable or unsafe routes.

## Preference Confirmation

Before running qualitative filters in any workflow, pull relevant preferences and confirm them with the user. This is an active step, not a silent read.

1. Read `context/<your-preferences>.md` (Travel & Accommodation section).
2. For accommodation: also read vault notes [[Accommodation criteria]] and [[Travel notes]].
3. Present the relevant preferences in the context of the current search. Example: "For this Lagos accommodation search, I'm filtering for: noise isolation/standalone unit, workspace, greenery/views, walkability. Correct?"
4. the user confirms or corrects. Apply corrections immediately to the current search and note them for preference file updates.

Why: preference files may not be complete or current. This creates a feedback loop where each search improves the preference data.

## Task Hierarchy Convention

Travel tasks follow a two-tree structure:

**Capability tree** (building tools):
- Capability tasks → `parent: "[[Build travel skill]]"`
- Build travel skill → `parent: "[[$Travel 🌍]]"`

**Trip tree** (using tools for a specific trip):
- Trip subtasks → `parent: "[[Plan YYYY-MM destination]]"`
- Trip planning tasks → `parent: "[[YYYY-MM destination]]"` (the vault trip note, e.g., `[[YYYY-MM Trip]]`)

The $Travel MOC connects to trip notes through the vault's own hierarchy. Claude tasks parent directly to the vault trip note they serve.

## Output Convention

All travel outputs go to `outputs/` (flat, frontmatter-based discovery). Temp files for active trip searches use `(temp)` suffix in `outputs/temp/`. Structured content (comparison tables, shortlists, recommendation matrices) goes in files, not chat. Summarize in chat and link.
