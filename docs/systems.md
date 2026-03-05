---
created: 2026-02-12 15:00
parent: "[[$AI \U0001F916]]"
source: claude
type: artifact
updated: 2026-02-25
---

# systems

What Claude can do in this workspace, where things live, and where to find detailed docs. 

---

## Architecture

The workspace follows a **two-zone vault** structure:
- **`1. Vault/`** — the user's content (READ ONLY for Claude)
- **`2. Claude/`** — Claude's workspace (writable)

Dot-prefixed directories (`.claude/`, `.mcp-server/`, `.scripts/`) are invisible to Obsidian but contain the systems that power this workspace.

---

## Context Architecture

Three tiers of context, from most persistent to most raw:

| Tier | Location | Written by | Loaded | Purpose |
|------|----------|-----------|--------|---------|
| **CLAUDE.md** | Workspace root | Claude (gated) | Every request (system-reminder) | Operational rules, strict constraints, conventions, environment |
| **context/** | Workspace root | Claude | On demand (Read tool) | Detailed reference files: profile, personal context, improvement log, preferences, captain's log |
| **Vault** | `<your-vault-path>\1. Vault` | the user | On demand (Vault Intuition MCP) | Raw source material (READ ONLY for Claude) |

MEMORY.md (`~/.claude/projects/<hash>/memory/`) is deprecated. It contains a redirect stub. All persistent knowledge lives in CLAUDE.md (version-controlled).

**What goes where:**
- **CLAUDE.md**: Rules where violation causes immediate, visible mistakes, plus workspace conventions, environment info, and operational lessons. Sections ordered by cost-of-failure (severity x frequency). Test: "Would removing this cause Claude to make mistakes?" Changes go through the improvement log processing pipeline. Target: under 150 lines.
- **context/**: Personal reference material about the user, too large for CLAUDE.md. Loaded on demand when relevant (personal context, improvement processing). Test: "Is this about the user as a person?"
- **docs/**: System documentation and technical reference. How tools, integrations, and conventions work. Files are `type: artifact` with standard frontmatter. Permanent reference that outlives any single task. Test: "Is this about how a system/tool/integration works?"
- **Vault**: the user's knowledge base. Search with Vault Intuition tools. Never write to it.

**Context files inventory:**
- `context/<your-profile>.md` — Life arc, relationships, patterns, philosophy
- `context/<your-context-files>.md` — Personal context file
- `context/improvement-log.md` — Observations captured during work sessions: machine improvements and personal preferences. Inbox-only: entries arrive, get triaged during improvement mode, then are deleted. Processed state lives in `inbox-state.json`.
- `context/<your-preferences>.md` — Refined personal preferences, organised by topic. Populated from improvement log triage.
- `context/captains-log.md` — Curated timeline of significant design decisions

**CLAUDE.md update discipline:** Changes to CLAUDE.md go through the improvement log processing pipeline: observations are captured in the improvement log during work sessions, then triaged during improvement mode. Direct edits require a dedicated task. No ad-hoc updates.

---

## MCP Server: Vault Intuition

**Location:** `.mcp-server/`
**Docs:** `.mcp-server/README.md`

Custom MCP server giving Claude deep access to the full Obsidian vault (3,100+ notes). 4 tools (consolidated from 10):

| Tool | Purpose |
|------|---------|
| `vault_search` | BM25 keyword search with relevance ranking |
| `vault_semantic` | Semantic search by meaning (e5-small-v2 embeddings + LanceDB) |
| `vault_sessions` | Search past Claude Code conversations by keyword |
| `vault_util` | Multi-action utility: note retrieval, graph traversal, browse, recent, stats, rebuild, session detail |

Incremental index updates built into `vault_util(action="rebuild")`. Atlas uses mtime comparison, embeddings use content hashing.

### Session Storage

Claude Code stores every conversation as a JSONL file in `~/.claude/projects/[encoded-path]/[session-uuid].jsonl`. Each line is a JSON event (user message, assistant message, tool call, timestamp, token usage). Events are appended immediately (crash-safe).

**Key files:**

| File | Purpose |
|------|---------|
| `~/.claude/projects/*/[uuid].jsonl` | Full conversation transcripts |
| `~/.claude/projects/*/sessions-index.json` | Metadata index for the /resume picker |
| `~/.claude/history.jsonl` | Global prompt index across all projects |

**Retention:** Default is 30-day auto-delete at startup. Overridden by `cleanupPeriodDays` in `~/.claude/settings.json` (set to 100000 as of 2026-02-27 to preserve all history). Setting to 0 deletes everything immediately. There is no true "disable cleanup" option, only large values.

**VS Code extension notes:** Known bugs exist where the extension may not write to `history.jsonl` (breaking cross-environment resumption) and may not persist main conversation transcripts to disk in some configurations. As of Feb 2026, our sessions appear to persist correctly. Monitor after extension updates.

**Scaling projections (based on Feb 2026 run rate of ~15.9 MB/active day):**

| Timeframe | Sessions | Raw JSONL | VI Index | Total |
|---|---|---|---|---|
| 6 months | ~1,730 | ~1.9 GB | ~70 MB | ~2 GB |
| 1 year | ~3,460 | ~3.8 GB | ~140 MB | ~4 GB |
| 2 years | ~6,900 | ~7.6 GB | ~280 MB | ~8 GB |
| 3 years | ~10,400 | ~11.4 GB | ~420 MB | ~12 GB |

Current Vault Intuition BM25 search architecture handles 1 year comfortably. At 2-3 years, consider: incremental indexing, date-range partitioning, or SQLite backend for the sessions cache.

**Search pipeline:** Session IDs recorded in improvement log entries and task progress logs enable tracing: task file -> session UUID -> `vault_util(action="session_detail")` for full transcript. `vault_sessions` provides keyword search across all indexed sessions.

---

## MCP Server: Context7

**Type:** Remote HTTP (third-party, by Upstash)
**Config:** `~/.claude.json` under project MCP servers
**Endpoint:** `https://mcp.context7.com/mcp`
**Auth:** API key via `${CONTEXT7_API_KEY}` Windows environment variable

Documentation lookup server. Indexes thousands of library docs from GitHub repos and serves structured snippets directly into context. Faster and more targeted than web searches.

| Tool | Purpose |
|------|---------|
| `resolve-library-id` | Find a library's Context7 ID from its name |
| `query-docs` | Fetch documentation snippets for a specific library |

**Usage pattern:** Call `resolve-library-id` first to get the library ID (e.g., `/anthropics/claude-code`), then `query-docs` with that ID and a topic query.

**Free tier:** 1,000 requests/month, 60/hour. Each call uses 4,000-10,000 tokens of context window.

**Confirmed indexed:** Claude Code (780 snippets), React, Next.js, FastAPI, Tailwind, and thousands more. Browse at context7.com/libraries.

---

## Task Engine

**Location:** `.task-engine/`
**Docs:** `.task-engine/README.md`
**Dependencies:** python-frontmatter, filelock (own venv at `.task-engine/.venv/`)

Deterministic Python CLI for task management operations. Replaces manual LLM-generated file edits with validated, atomic operations. Called by Claude via Bash.

**Actions:** `create`, `start`, `complete`, `cancel`, `pause`, `log`, `read`, `link`, `update`, `audit`

**Key properties:**
- Atomic writes (write to .tmp, then replace)
- File locking via `filelock` for concurrent session safety
- Frontmatter schema validation with typed status transitions
- Real timestamps from system clock (never LLM-generated)
- Structured JSON output for every call
- Multi-line content via stdin + heredoc (no Bash escaping issues)
- `task.py list` scans files on demand (no static TASKS.md file to maintain)

**Modules:** task.py (CLI), schema.py (validation), operations.py (core actions), tasks_md.py (export-only TASKS.md snapshots), progress_log.py (log entries), fileops.py (atomic I/O), audit.py (output orphan checks)

**Status:** Stage 1 (script) complete. Stage 2 (measurement) pending.

---

## Skills

Skills are invoked with `/skill-name` and define Claude's specialized behaviors.

### /task

**Location:** `.claude/skills/task/SKILL.md` (slim router) + `.claude/skills/task/references/` (6 reference files)

Task management system. Modes: `new <name>`, `start`, `complete`, `cancel`, `status`, `review`.
- SKILL.md is a slim router (~130 lines) that loads mode-specific files on demand via Read. Each mode's process lives in `references/<mode>.md`. This reduces per-invocation context from ~6K to ~1.5-3K tokens depending on mode.
- Defines conventions, judgment calls, and workflows; file operations delegated to `.task-engine/task.py`
- Uses `task.py list` for dynamic task state (no TASKS.md to maintain)
- `/task review` runs daily hygiene (automated checks via `task.py audit` plus manual judgment steps: docs audit, ideas review, systems health)
- Supports `status: 4-recurring` for process-type tasks (daily review, weekly systems review)

### /brainstorm (brainstorming)

**Location:** `.claude/skills/brainstorming/SKILL.md`

Collaborative design process for creative/design work. Must run before implementing new features, components, or behavior changes. Starts with a mandatory context alignment step (vault search + workspace search for related work, deep reading, persists findings to task file). Then asks questions one at a time, proposes approaches, presents design in sections for validation.

### /research

**Location:** `.claude/skills/research/SKILL.md`

Methodology guardrails for subagent research. Two modes (no default, explicit selection required): **quick** (`--quick`, 1 agent, 2-3 search angles, inline verification, chat output) and **deep** (`--deep`, 2-3 agents, full guardrails, file output). Deep mode has three guardrails: discovery breadth (multi-angle search queries, incumbent names, fallback categories, recency filters), cross-verification (independent source verification, hallucination documentation), and gap documentation (what was missed and why). Mode selected from criteria in SKILL.md; if ambiguous, ask. Supports future domain-specific profiles as subsections. Does not fire for quick lookups or code exploration.

### /digest

**Location:** `.claude/skills/digest/SKILL.md` + `.claude/skills/digest/scripts/` (Python pipeline scripts) + `.claude/skills/digest/references/` (per-pipeline agent prompts)

Content triage across platforms. `/digest [--quick] <URL> [URL2] [URL3]` detects URL types and routes to the correct pipeline. Multiple URLs processed in parallel.

**Full mode** (default):
- **YouTube:** Downloads audio via yt-dlp, transcribes via Groq Whisper, diarizes if multi-speaker, launches Sonnet subagent for timestamped key takeaways + full transcript.
- **X/Twitter:** Fetches via fxtwitter API (free, no auth), converts Draft.js article content to markdown. Articles get Sonnet subagent. Single posts displayed inline.
- **Blog/article:** Extracts via trafilatura (fetch_blog.py), assembles ToC + full content via assemble_digest.py.
- **Podcast:** Searches for YouTube version first (preferred), falls back to RSS/embedded audio discovery + Groq Whisper transcription.

**Quick mode** (`--quick`): Faster triage (~5-15s vs ~30-90s). YouTube uses auto-captions (youtube-transcript-api) instead of Whisper. Podcasts use show notes with Whisper fallback if thin (<200 words). Output: frontmatter + Key Takeaways only, no transcript. Includes promotion hint to run full `/digest` later.

**Channel browsing:** Passing a channel URL (`youtube.com/@handle`) to `/digest` triggers `youtube-browse.py` (YouTube Data API v3) to list recent videos. User picks numbers, selected videos enter the normal digest pipeline. Also works as a standalone general-purpose tool via `.scripts/youtube-browse.py`.

**Dependencies:** YouTube: `GROQ_API_KEY` env var, yt-dlp, ffmpeg, groq, youtube-transcript-api. Channel browsing: `YOUTUBE_API_KEY` env var. X: Python stdlib only. Blog: trafilatura. Podcast: same as YouTube + fetch_podcast.py.

### /process

**Location:** `.claude/skills/process/SKILL.md`

Vault inbox triage. `/process <note name>` reads a vault note, identifies unprocessed items, classifies each into one of 8 destination buckets (new idea task, existing task context, decision/convention, reflection, already captured, etc.), and presents a triage batch for review. Auto-processable items (reflections, already captured) execute without individual approval; escalated items (new tasks, conventions) require the user's sign-off. State tracked in `context/inbox-state.json` to prevent re-processing. Works on any vault note, not just date-headed logs.

### /autonomous

**Location:** `.claude/skills/autonomous/SKILL.md`

On-demand autonomous work mode. Scans all tasks (1-active, 2-paused, 4-recurring, 3-idea) for work items Claude can handle without the user's input. Four criteria (objective/verifiable, demonstrated pattern, no subjective judgment, bounded scope) with brainstorm gate as absolute veto. Mandatory argue-against step for each candidate (adversarial self-check before presenting). Concurrent session collision detection skips tasks with recent progress log activity. Presents plan for approval, executes sequentially, self-verifies completions, reports results. Decision audit trail logged to `context/autonomy-log.md`. Not automatic: fires only on explicit request.

### /ingest

**Location:** `.claude/skills/ingest/SKILL.md`

Scanned PDF transcription pipeline. `/ingest <pdf path>` OCRs handwritten pages via parallel Sonnet agents, combines into a raw transcription, then formats into vault-ready notes. Also: `/ingest scan` (check for new PDFs in scan folder), `/ingest status` (show tracking index). Tracking index at `outputs/Journal ingestion index.md` prevents duplicate work across sessions.

### /skill-creator

**Location:** `.claude/skills/skill-creator/SKILL.md`

Build, test, and maintain Claude skills for this workspace. Fires via brainstorm gate when skill creation work begins. Guides: placement decision (skill vs. CLAUDE.md rule vs. hook), skill structure, testing protocol, and line count discipline. Also used for auditing existing skills for bloat.

### /travel

**Location:** `.claude/skills/travel/SKILL.md` + `.claude/skills/travel/references/` (4 reference files)

Travel search and recommendation skill. Router pattern: SKILL.md is a thin router (~70 lines) with module registry, trigger matching, disruption checking, preference confirmation loop, and hierarchy convention. Each domain module has its own reference file loaded on demand. Modular: flights, accommodation, car rental, and air quality are mature modules; visas, itinerary, activities are future placeholders.
- `references/flights.md`: Source selection (Google Flights primary, Kiwi for LCC only), 7-step workflow, google-flights-search.py CLI reference
- `references/accommodation.md`: 6-step workflow (search → qualitative filter → review deep-dive → recommend), accommodation-search.py + review_scraper.py CLI reference
- `references/car-rental.md`: 3-step workflow, car-rental-search.py CLI reference
- `references/air-quality.md`: Dual-source (WAQI current + OpenAQ historical), comparison + deep-dive workflows, air-quality-search.py CLI reference

### /shop

**Location:** `.claude/skills/shop/SKILL.md` + `.claude/skills/shop/references/lazada.md`

Product search on Thai e-commerce platforms. Currently wraps `lazada-search.py` for Lazada Thailand product search via Apify actor (`fatihtahta/lazada-scraper`). Pay-per-result pricing ($0.005/result, no monthly rental). Triggers on shopping requests, product comparisons, and "find me X" queries. Shopee planned as future module (blocked by $30-40/mo actor rental costs).

### using-skills (meta-skill)

**Location:** `.claude/skills/using-skills/SKILL.md`

Auto-injected via SessionStart hook. Establishes skill enforcement, session orientation (3 cases: directed task, work status, or just respond), post-compaction protocol, vault tool decision table, and improvement logging trigger. Full improvement logging procedure in `references/improvement-logging.md`. Not user-invocable.

---

## Scripts

**Location:** `.scripts/` | **Catalog:** `.scripts/README.md`
**Convention:** Update README when creating or archiving scripts. Spent scripts go in `.scripts/archive/`.

### rename-links.ps1

Vault-wide wiki-link rename tool. Renames files and propagates `[[wiki-link]]` changes across all `.md` and `.base` files in both vault zones. Handles all link variations: plain, aliased, heading refs, block refs, embeds, and YAML frontmatter.

```powershell
# Single rename (dry-run preview):
.\.scripts\rename-links.ps1 "Old Name" "New Name"

# Batch rename from manifest:
.\.scripts\rename-links.ps1 -Manifest .scripts\renames.json -Execute

# Links only (files already renamed):
.\.scripts\rename-links.ps1 "Old Name" "New Name" -LinksOnly -Execute
```

Dry-run by default. Add `-Execute` to apply. Run by the user from VS Code PowerShell terminal (not Claude, due to vault write permissions). Claude generates the manifest when doing batch renames.

**When Claude tells you to run this**, open a PowerShell terminal in VS Code and paste:
```powershell
cd "<your-workspace-path>"
powershell -ExecutionPolicy Bypass -File .\.scripts\rename-links.ps1 -Manifest .scripts\renames.json -Execute
```

That handles all batch renames. For single renames Claude will give you the exact command with the old/new names filled in.

### flight-search.py

Flight search via Kiwi.com MCP endpoint. Calls `mcp.kiwi.com` using the MCP Streamable HTTP protocol (JSON-RPC). Returns structured flight results as JSON.

```bash
# One-way search:
python .scripts/flight-search.py --from LHR --to MAD --date 01/06/2026

# Round trip, 2 passengers:
python .scripts/flight-search.py --from LHR --to LIS --date 01/06/2026 --return-date 21/06/2026 --passengers 2

# Business class, sorted by price, in USD:
python .scripts/flight-search.py --from LHR --to MAD --date 01/06/2026 --cabin C --sort price --currency USD
```

**Options:** `--from`, `--to`, `--date` (required). `--return-date`, `--passengers` (default 1), `--cabin` (M/W/C/F), `--sort` (price/duration/quality/date), `--currency` (default EUR), `--locale` (default en), `--flex` (0-3 days).

**Dependencies:** `httpx` (available in system Python).

**Output:** JSON to stdout. Claude parses and formats results conversationally with tables, recommendations, and booking links.

### lazada-search.py

Lazada Thailand product search via Apify actor (`fatihtahta/lazada-scraper`). Requires `APIFY_API_TOKEN`.

```bash
python .scripts/lazada-search.py "100W GaN charger"
python .scripts/lazada-search.py "mechanical keyboard" --sort priceasc --max-price 2000
python .scripts/lazada-search.py "robot vacuum" --min-rating 4 --limit 30
```

**Options:** `keyword` (required positional). `--sort` (best/priceasc/pricedesc), `--min-price`, `--max-price` (THB), `--min-rating` (1-5), `--limit` (default 20), `--no-cache`.

**Output:** JSON to stdout. Products with: name, url, price, original_price, discount, sold count, rating, review_count, seller, seller_location, brand, image.

**Caching:** Day-based cache in `.scripts/lazada_data/`. Cached results re-filter instantly.

### detect-session-id.sh

Detects the current Claude Code session UUID using a probe technique. Requires a two-step process: Claude first echoes a unique probe string (which gets logged to the session JSONL), then runs this script with the probe as an argument. The script greps across all project session JSONLs and returns the filename (UUID) of the matching one.

```bash
# Step 1 (Bash tool call): echo a probe string
echo "SESSION_PROBE_$(date +%s%N)"

# Step 2 (separate Bash tool call): detect session from probe
bash .scripts/detect-session-id.sh "SESSION_PROBE_<from step 1>"
```

**Usage:** Runs automatically during session orientation (SKILL.md "Both paths" section). Also available on demand after compaction or when session ID is needed.

**Dependencies:** None (bash, grep, basename).

**Output:** Session UUID to stdout (e.g., `a8ac5317-db8a-4eba-9287-4fae4a3d7b81`). Exits 1 on failure.

### Launch-Obsidian.ps1

Obsidian startup wrapper. Empties `lastOpenFiles` from `.obsidian/workspace.json` before launching Obsidian. Prevents the startup slowdown caused by Obsidian resolving nonexistent/binary/temp file paths accumulated by Claude Code editing operations.

```powershell
powershell -ExecutionPolicy Bypass -WindowStyle Hidden -File ".scripts\Launch-Obsidian.ps1"
```

**Usage:** Pin to taskbar/desktop shortcut as the primary way to launch Obsidian. Sub-second overhead. Only matters on cold starts (Tray plugin keeps Obsidian running between uses).

**Dependencies:** None (PowerShell built-in JSON handling).

**Output:** Launches Obsidian via `obsidian://open` URI. No console output.

### review_scraper.py

Hotel/resort review scraper. Pulls reviews from Google Maps, Booking.com, and Airbnb via Apify actors, caches locally as JSON, outputs structured data for Claude to query conversationally.

```bash
# Google Maps reviews:
python .scripts/review_scraper.py --platform google --url "<GOOGLE_MAPS_URL>" --max-reviews 50

# Booking.com reviews:
python .scripts/review_scraper.py --platform booking --url "<BOOKING_URL>" --max-reviews 50

# Airbnb reviews:
python .scripts/review_scraper.py --platform airbnb --url "<AIRBNB_URL>" --max-reviews 50
```

**Env var:** `APIFY_API_TOKEN` (Windows environment variable, used for all platforms).

**Actors:** `automation-lab/google-maps-reviews-scraper` (Google Maps), `voyager/booking-reviews-scraper` (Booking.com), `tri_angle/airbnb-scraper` (Airbnb).

**Cache:** `.scripts/review_data/{sanitized_url}_{platform}_{date}.json`. No auto-expiry. Use `--no-cache` to force re-fetch.

**Output:** JSON to stdout with `place` metadata + `reviews` array. Status messages to stderr. Claude reads the JSON and answers natural language questions about the property.

### accommodation-search.py

Accommodation search across Booking.com and Airbnb. Uses Apify actors to fetch listings, applies hard filters (budget, rating, beds, radius, type), outputs structured JSON. Part of the hybrid search pipeline where Claude handles qualitative filtering against preference notes.

```bash
# Booking.com only:
python .scripts/accommodation-search.py --platform booking --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21

# Airbnb only:
python .scripts/accommodation-search.py --platform airbnb --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21 --budget 150

# Both platforms:
python .scripts/accommodation-search.py --platform both --location "Barcelona, Spain" --checkin 2026-06-01 --checkout 2026-06-21 --min-rating 8.0 --type entire
```

**Hard filters:** `--location`, `--checkin`, `--checkout`, `--guests` (default 2), `--budget` (max nightly), `--min-rating` (auto-scales between Booking 1-10 and Airbnb 1-5), `--beds`, `--type` (entire/hotel/hostel/guesthouse/all), `--radius` (km from center), `--currency` (default EUR).

**Actors:** `voyager/booking-scraper` (Booking.com), `tri_angle/airbnb-scraper` (Airbnb). Uses async polling (actors can take 2-5 min).

**Cache:** `.scripts/accommodation_data/{location}_{platform}_{date}.json`. Use `--no-cache` to force re-fetch.

**Output:** JSON to stdout with `listings` array. Each listing: name, URL (direct platform link), price (nightly + total), rating, review count, type, address, coordinates, description, photo URLs, cancellation policy.

**Workflow:** Search (script) → Qualitative filter (Claude + preference notes) → Review deep-dive (review_scraper.py) → Recommend (output file + chat). See [[Build accommodation search capability]] for full design.

**Note:** The full search + review pipeline can exceed Apify free tier in one session. Plan accordingly.

### youtube-browse.py

Browse YouTube channel videos via Data API v3. Accepts channel handles (`@Name`), URLs, channel IDs, or name search. Returns JSON with channel metadata + video list (title, URL, date, views, likes, duration).

```bash
python .scripts/youtube-browse.py @LiamOttley --max 5 --sort views
python .scripts/youtube-browse.py "https://www.youtube.com/@LiamOttley" --months 3
python .scripts/youtube-browse.py @LiamOttley --all
```

**Auth:** `YOUTUBE_API_KEY` env var. Free tier: 10K API units/day (~3 units per browse).

**No cache.** Channel data changes frequently and API calls are cheap.

**Integration:** Wired into `/digest` Step 1.5 as channel URL detection. Also usable as a standalone general-purpose tool.

### Other utilities

- `vault-count.ps1` — Count vault notes (superseded by `vault_util(action="stats")`)
- `extract-timestamps.ps1` — Timestamp extraction from session logs
- `check-session.ps1` — Session log verification

### Archived utilities (`.scripts/archive/`)

- `add-descriptions.ps1` / `add-descriptions.py` — Bulk add description frontmatter to task files
- `extract_messages*.ps1` — Session log extraction utilities (4 iterations)
- `rename-tasks.ps1` — One-off bulk task rename (superseded by `rename-links.ps1`)

---

## Hooks

**Config:** `.claude/settings.json`
**Content files:** `.claude/hooks/`

Two hooks wire the workspace together:

| Hook | Trigger | What it does |
|------|---------|--------------|
| SessionStart | startup, resume, clear, compact | Injects `using-skills/SKILL.md` into context |
| UserPromptSubmit | every user message | Injects `.claude/hooks/per-prompt-rules.md` (behavioral rules that must stay fresh) |

The SessionStart hook is what makes skill enforcement automatic. The UserPromptSubmit hook ensures critical rules stay active throughout the session. Both use `type: command` with `cat` to read markdown files into context.

**Why per-prompt rules matter (do not remove or weaken):**
The UserPromptSubmit hook adds ~4,505 chars (~1,126 est tokens) per prompt. This is intentional. Before it existed, Claude would drift mid-session: forgetting the pre-implementation gate, editing task files directly, skipping task file updates. The per-prompt repetition fixed this. It looks redundant with SKILL.md (which has the same rules), but SKILL.md is injected once at session start and fades from attention as context grows. The per-prompt rules keep critical behaviors fresh on every turn. The cost is justified by the compliance improvement. Do not optimize it away.

**What currently lives in per-prompt-rules.md:**
1. Pre-implementation gate (task tracking must be current before any Edit/Write/Bash)
2. Brainstorm gate (any work involving choices about approach)
3. Task management 10-question check (observable triggers, not subjective assessment)
4. Vault tool selection gate (search before guessing)
5. Critical infrastructure protection (per-prompt-rules.md itself cannot be modified autonomously)
6. Improvement logging (system gaps + personal preferences) with per-prompt rule candidate proposal pathway

**per-prompt-rules.md is critical infrastructure.** It cannot be modified during task reviews, cleanup, or optimization. Changes require a dedicated task with explicit user approval. This protection is enforced in three places: the file itself (PROTECTED FILE clause), using-skills/SKILL.md (red flags table), and this documentation.

**Admission criteria (for adding new per-prompt rules):**
A behavioral pattern earns a place in per-prompt-rules.md only if it meets ALL four criteria:
1. **Trigger-shaped**: Expressible as "when X, do Y". Not reference material.
2. **Proven drift**: Claude demonstrably forgets this mid-session. Not theoretical.
3. **Visible harm**: Forgetting causes real problems (missed searches, untracked work, orphaned files).
4. **Compressible**: Expressible in under 10 lines. Full detail belongs in using-skills/SKILL.md.

When a new candidate is identified, it gets logged in `context/improvement-log.md` under the current task and proposed to the user at the end of the current response.

### Hook debugging reference
- Hook commands run in **bash** (Git Bash), not cmd.exe. Use `cat` with forward-slash paths for file reading.
- `$CLAUDE_PROJECT_DIR` is **not set** in hook context (as of v2.1.39).
- Hooks must be in `.claude/settings.json` (not `settings.local.json`).
- VSCode must fully restart for hook changes to take effect.

## Permissions

**Settings:** `~/.claude/settings.json` (global), `.claude/settings.local.json` (project)

- Allow: `Bash(*)` — broad access, deny list is the safety net
- Deny: `*1. Vault*` (21 rules) + `.obsidian` (4 rules) + 12 destructive operation blocks
- Vault path matching uses `*1. Vault*` substring for Bash rules
- Edit/Write rules use full path: `<your-vault-name>\\1. Vault\\**`

## Environment

- Python 3.14.3 installed (added to PATH). Used by MCP server venv at `.mcp-server/.venv/`.
- Node.js not on Git Bash PATH. Use `powershell -NoProfile -Command` for scripts, or call node via full path.

---

## Backup and Recovery

Two independent backup layers protect the workspace. Use whichever fits the situation.

### Layer 1: Git + GitHub

**Repo:** Private, `<your-github-username>/claude-workspace` on GitHub
**Branch:** `main`
**Config:** `.gitignore` at workspace root

The `2. Claude/` workspace is version-controlled with git and pushed to a private GitHub repository.

**What's backed up:** Everything in `2. Claude/` including dot-prefixed folders (`.claude/`, `.mcp-server/`, `.scripts/`). Commits now sweep for untracked files (e.g., `.base` files created by Obsidian) so they get tracked automatically.

**What's excluded** (via `.gitignore`): Python artifacts (`.venv/`, `__pycache__/`), MCP server runtime data (`.mcp-server/data/`), Windows artifacts.

**When commits happen:**
- Automatically on `/task complete` (Step 4 in the completion flow)
- Manually on request ("back it up")

**Recovery:** `git restore .` restores all tracked files to the last commit. For older versions: `git log` to find the commit, `git show <commit>:<path>` to view, `git restore --source <commit> <path>` to recover.

**Git identity:** Repo-level config. Name: `the user`, email: `<your-email>`.

### Layer 2: Obsidian File Recovery (core plugin)

Obsidian's built-in **File Recovery** core plugin (Settings > Core Plugins > File Recovery) saves snapshots of notes independently of git. Can restore deleted or overwritten files even if they were never committed to git. Snapshots are stored outside the vault in the global settings directory.

**Defaults:** Snapshots every 5 minutes, 7-day retention. Both configurable. To recover: Settings > Core Plugins > File Recovery > View snapshots, search by filename.

**When to use:** Recovery of files that git doesn't track (Obsidian-created `.base` files, config changes, anything created between commits). Also useful when git history doesn't have the version you need.

### Which to use when

| Scenario | Use |
|---|---|
| Mass file deletion (working tree wiped) | `git restore .` |
| Single file needs older version | `git show <commit>:<path>` |
| File was never committed to git | Obsidian File Recovery |
| File overwritten, need yesterday's version | Git log or File Recovery |
| Verify nothing is missing | `git status` (tracked) + check untracked |

---

## Content Types

The workspace uses three content types, each with its own frontmatter `type:` field:

| Type | Location | What it is |
|------|----------|------------|
| `task` | `tasks/`, `tasks/ideas/`, `tasks/archive/` | Any unit of work or recurring process. Status: `3-idea` → `1-active` → `2-paused` → `5-done` or `6-cancelled`, or `4-recurring` for processes that run on a cadence (daily, weekly, monthly, quarterly, on-demand). Numeric prefixes enable Obsidian Bases sorting. Recurring tasks add `cadence:` and `last-run:` frontmatter. Ideas live in `tasks/ideas/`, active work in `tasks/`, done/cancelled in `tasks/archive/`. |
| `artifact` | `outputs/` | Deliverables produced by tasks. Archived with parent task on completion. |
| `context` | `context/` | Living reference files (profile, assessment). Never archived. |

All types share: `source: claude`, `created:` timestamp, `parent:` wiki-link to MOC or parent task.

---

## Context Files

**Location:** `context/`

Persistent reference files that Claude reads for personal context and decision-making:
- `<your-profile>.md` — Life arc, relationships, patterns, philosophy 
- `<your-context-files>.md` — Personal context and behavioral patterns
- `improvement-log.md` — Observations captured during work sessions. Two types: machine improvements (system gaps, drift, capabilities) and personal preferences (things learned about the user). Inbox-only: entries arrive during work sessions, get triaged during [[Run improvement mode]], then are deleted from the inbox. Processed state lives in `inbox-state.json` (JSON) and triage output files in `outputs/` (human-readable audit trail). Grouped by date then by task (wiki-link header). Each entry includes a session ID for traceability via `vault_util(action="session_detail")`.
- `<your-preferences>.md` — Refined personal preferences, organised by topic (Travel, Food, Environment, Social, Work, Health). Populated from improvement log preference triage. Each preference includes source line for traceability.
- `inbox-state.json` — Unified inbox processing state for both `/process` and improvement mode. Registry of monitored sources (vault notes + improvement log), processed items with full original text, exit type, action outcome with wiki-links, cluster assignment, and triage run reference. Prevents re-processing and serves as machine-readable audit trail alongside triage output files.
- `captains-log.md` — Curated timeline of significant design decisions. Records what was decided (or deliberately confirmed), why, and links to the task and research. Updated during `/task complete` reconciliation when a task changed or deliberately confirmed how the system is built. Most tasks don't generate entries here.
- `autonomy-log.md` — Decision audit trail for `/autonomous` mode. Logs what was proposed, what was approved, and what was executed during autonomous work sessions.

---

## Recurring Processes

Five recurring tasks track workspace health. Their `last-run:` frontmatter field tracks when each process last ran.

| Process | Cadence | Task File | What it does |
|---------|---------|-----------|--------------|
| Task review | Daily | `tasks/Run task review.md` | 9-step task hygiene audit (date buckets, links, status sync, docs, metrics, hook smoke test, systems review, improvement mode) |
| Systems health review | Weekly | `tasks/Run systems health review.md` | Full critical review: two Opus agents assess enforcement reliability and architecture scaling. Produces a report in `outputs/` and feeds findings to `context/improvement-log.md` |
| Improvement mode | Weekly | `tasks/Run improvement mode.md` | Processes the improvement log inbox: clusters entries by theme, interactive triage with the user (machine improvements: 4 exits; preferences: 4 exits), executes fixes, refines preferences, writes processed state to JSON, deletes entries from inbox. Runs after health review. |
| Security posture audit | Quarterly | `tasks/Run security posture audit.md` | 6-domain security audit: secrets inventory, exposure prevention, access scope, third-party/MCP risk, personal data exposure through AI, account health. Policy baseline: `docs/security-conventions.md`. Absorbed the former AI privacy audit. |
| Best practices audit | Monthly | `tasks/Run best practices audit.md` | External audit comparing workspace against community best practices, new Claude Code features, and AI agent patterns. Includes monthly secrets hygiene check (new keys, overdue rotations). Produces prioritized findings in `outputs/` |

The daily review's step 6 runs lightweight metrics checks (MEMORY.md lines, CLAUDE.md lines, SKILL.md chars, per-prompt-rules.md chars, done entries, review age, improvement log inbox size). Thresholds and resolution procedures defined in [[Context management placement framework]]. Step 7 runs a hook smoke test (executes each hook command from settings.json, verifies non-empty output). Step 8 triggers the weekly full systems review when due (7+ days since last run). Step 9 triggers improvement mode when due (7+ days since last run, always after step 8). All defined in `.claude/skills/task/references/review.md`.

---

## External Integrations

### Toggl (time tracking)

**Docs:** `docs/toggl-integration.md`

the user's time tracking data, queryable via REST API. The vault captures what the user is thinking; Toggl captures what he's doing. Claude queries the API inline (no script) when questions touch time, productivity, or "what did I do." Auth via `TOGGL_API_KEY` env var. See the integration doc for endpoints, data shape, and project map.

### Asana (project management)

**Script:** `.scripts/asana.py`

the user's business task management, shared with collaborators. Two workspaces: <workspace-1> (content/media, default) and <workspace-2> (e-commerce). Claude queries via the script when questions touch work done with the assistant, business tasks, or past projects. Auth via `ASANA_PAT` env var. Free plan (no server-side search; `find` command does client-side keyword search across all projects). Commands: `me`, `projects`, `project`, `task`, `comments`, `recent`, `find`, `search`. Set `ASANA_WORKSPACE_GID` to switch workspaces.

---

## Security

**Docs:** `docs/security-conventions.md`

Security policy for the workspace: secrets management rules, API key inventory, exposure prevention (Gitleaks pre-commit hook), MCP server security guidelines. The quarterly security posture audit checks compliance against this document. Consult when adding new API keys, integrations, or MCP servers.

---

## Decision Frameworks

- **[[MCP vs scripts decision framework]]** (`docs/MCP vs scripts decision framework.md`): When to build an MCP server vs a script, and when to install a third-party MCP. Consult when adding new capabilities or evaluating existing MCP servers.
- **Multi-document synthesis patterns** (`docs/multi-document-synthesis.md`): When to stuff documents in one context vs chunk across agents. Evidence-based decision framework with token thresholds and pattern descriptions. Consult before any multi-document analysis (digest synthesis, cross-referencing, landscape research). **FILE LOST IN GIT REVERT, NEEDS RECREATION.**

## Reference Docs
- **`docs/agent-output-convention.md`**: Relay spec for agent prompts (frontmatter, context block, vault boundary, parent, date, temp vs permanent). Read before launching agents that create files.
- **`docs/markdown-formatting.md`**: Heading spacing, progress log format, line breaks, table rendering, horizontal rule conventions. Applies to all workspace files.
- **`docs/multi-document-synthesis.md`**: Decision framework for multi-document analysis. Token thresholds, four patterns (stuff, map-reduce, hybrid, iterative), evidence from published research. Living document with empirical findings section. **FILE LOST IN GIT REVERT, NEEDS RECREATION.**
- **`docs/toggl-integration.md`**: Toggl REST API endpoints, data shape, project map.
- **`docs/security-conventions.md`**: Secrets management, exposure prevention, MCP security.

---

## Documentation convention

Every component directory gets a reference doc:
- **Skills** → `SKILL.md` (established)
- **Agents** → `.md` in `.claude/agents/` (established)
- **MCP servers** → `README.md` (established)
- **Scripts** → `README.md` if they grow into a proper system (future)

This index (`docs/systems.md`) is the entry point. Component docs have the detail. The `/task review` docs audit checks that this index stays in sync with reality.