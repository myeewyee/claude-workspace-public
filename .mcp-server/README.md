# Vault Intuition

Custom MCP server that gives Claude deep access to the Obsidian vault (3,100+ notes) and past Claude conversations. Provides keyword search, semantic search, wiki-link graph traversal, folder browsing, vault analytics, and session history search. Runs locally as a stdio server launched by Claude Code.

**All phases complete** (4 tools: keyword search, semantic search, session search, multi-action utility). Incremental updates keep all indexes fresh without full rebuilds.

---

## Tools Reference

### vault_search

**When to use:** Find notes by keyword. Good for locating specific topics, terms, or phrases across the entire vault.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Search terms (e.g. "margin loan", "morning routine") |
| `limit` | int | 10 | Maximum results to return |
| `zone` | str | "" | Filter by zone: "vault" or "claude" (empty = all) |
| `folder` | str | "" | Filter to specific folder name (empty = all) |

**Returns:** Ranked list of results, each with: note name, path, zone, folder, word count, BM25 relevance score, and a text snippet (truncated to 200 chars).

**How ranking works:** BM25 algorithm (same as Elasticsearch). Title matches are boosted 3x over content matches. Scores are relative — higher is more relevant, but the absolute numbers depend on query and corpus.

**Example:** `vault_search(query="investing policy", limit=5, zone="vault")`

---

### vault_semantic

**When to use:** Find notes by meaning, not just keywords. Use when the query is conceptual or emotional: "feeling stuck", "thoughts on minimalism", "entries about relationship patterns". Complements `vault_search` — use keyword search for specific terms, semantic search for concepts.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Natural language query describing what you're looking for |
| `limit` | int | 10 | Maximum results to return |
| `zone` | str | "" | Filter by zone: "vault" or "claude" (empty = all) |
| `folder` | str | "" | Filter to specific folder name (empty = all) |

**Returns:** Ranked list of results, each with: note name, path, zone, folder, word count, cosine similarity score (0-1), chunk info (if note was split), and a text snippet (truncated to 200 chars).

**How it works:** Uses e5-small-v2 embedding model (384-dim) to encode the query, then searches a LanceDB vector database of pre-computed note chunk embeddings. Results are deduplicated by note (best chunk wins per note).

**Chunking:** Notes over ~400 words are split into overlapping chunks (~400 words, ~100 word overlap). Short notes embed as a single chunk. The first chunk of each note is prepended with the note name for better title matching.

**Embedding model loads at server startup** (~10-15s added to startup time). All queries are fast (~50-150ms). If the model fails to load, the tool returns a descriptive error message.

**Requires embeddings to be built first.** If not built, the tool tells you to run `vault_util(action="rebuild", scope="embeddings")`. Building takes ~10 minutes on CPU (one-time).

**Example:** `vault_semantic(query="feeling stuck in life", limit=5, zone="vault")`

---

### vault_sessions

**When to use:** Search past Claude Code conversations by keyword. Use when you want to find a session where a topic was discussed, a decision was made, or specific work was done. Searches across all user messages and Claude responses.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | required | Search terms (e.g. "permissions", "brainstorm feature") |
| `limit` | int | 10 | Maximum results to return |
| `days` | int | 0 | Only search sessions from the last N days (0 = all time) |

**Returns:** Ranked list of matching sessions, each with: session title (first user message), session UUID, start date, message count, BM25 relevance score, and a text snippet (truncated to 250 chars). Includes a hint to use `vault_util(action="session_detail")` for full conversation.

**How it works:** Parses all JSONL session log files under `~/.claude/projects/*/`, extracts human-readable text (user + assistant messages, stripping system tags and tool parameters), and builds a BM25 index. Title tokens are boosted 3x. Session index is cached to `data/sessions-index.json` for 1 hour.

**Session title:** Derived from the first meaningful user message, with IDE selection/opened file context stripped. Some sessions may show `(no text)` if they contained only tool use.

**Example:** `vault_sessions(query="investment tracker", days=7)`

---

### vault_util

**Multi-action utility tool.** Consolidates 7 operations into one tool with an `action` parameter. All actions share a flat parameter set; pass only the params relevant to your action.

| Parameter | Type | Default | Actions | Description |
|-----------|------|---------|---------|-------------|
| `action` | str | required | all | Operation: "note", "graph", "browse", "recent", "stats", "rebuild", "session_detail" |
| `name` | str | "" | note, graph | Note name (fuzzy matched) |
| `max_lines` | int | 0 | note | Truncate to N lines (0 = full) |
| `depth` | int | 1 | graph | Hops to follow (1-3) |
| `direction` | str | "both" | graph | "outlinks", "backlinks", or "both" |
| `path` | str | "" | browse | Folder path relative to vault |
| `topic` | str | "" | browse | Topic name matching $-prefixed folders |
| `sort` | str | "modified" | browse | "name", "modified", or "created" |
| `limit` | int | 0 | browse, recent | Max results (browse default 50, recent default 20) |
| `days` | int | 7 | recent | Look back N days |
| `zone` | str | "" | recent | Filter by "vault" or "claude" |
| `note_type` | str | "" | recent | "topic", "content", "journal", or "moc" |
| `detail` | str | "summary" | stats | "summary", "folders", "topics", or "links" |
| `scope` | str | "atlas" | rebuild | "atlas", "embeddings", "sessions", or "all" |
| `force` | bool | false | rebuild | Full rebuild vs incremental |
| `session_id` | str | "" | session_detail | Session UUID from vault_sessions |
| `max_messages` | int | 0 | session_detail | Limit messages (0 = all) |

**Validation:** Missing required params return a clear error (e.g., "action 'note' requires 'name' parameter").

#### action="note"

Retrieve a specific note's full content and metadata. Uses rapidfuzz WRatio fuzzy matching (60% minimum). Returns metadata (path, zone, dates, word count, links, frontmatter) + full content. Outlinks/backlinks capped at 20 each.

**Example:** `vault_util(action="note", name="Investing Policy", max_lines=30)`

#### action="graph"

Explore wiki-link connections via BFS traversal. At depth 1: outlinks, backlinks, MOC hubs. At depth > 1: subgraph summary (capped at 20 nodes). Only follows links to notes that exist in the atlas.

**Example:** `vault_util(action="graph", name="$Home", depth=2, direction="outlinks")`

#### action="browse"

List notes in a folder or topic area. No path/topic: folder overview with counts. Topic matching: case-insensitive substring on $-prefixed folders (physical location, not content). Path matching: case-insensitive substring on full path or folder name.

**Example:** `vault_util(action="browse", topic="Health", sort="name", limit=20)`

#### action="recent"

Recently modified notes, sorted by date. `note_type="topic"` is a negative filter (NOT content AND NOT journal), not a topic folder filter. Use `action="browse"` with `topic=` for that.

**Example:** `vault_util(action="recent", days=3, zone="vault", note_type="journal")`

#### action="stats"

Vault analytics. `detail="summary"`: totals, zones, types, avg words, search status, link graph. `detail="folders"`: note count per folder. `detail="topics"`: note count per $-prefixed folder. `detail="links"`: link stats + top 15 MOC hubs.

**Example:** `vault_util(action="stats", detail="links")`

#### action="rebuild"

Force refresh vault indexes. Incremental by default (atlas: mtime comparison, embeddings: MD5 hash). `force=true` for full rebuild. Atlas incremental: ~0.3s. Embeddings incremental (no changes): ~0.2s. Full embedding rebuild: ~11 min.

**Example:** `vault_util(action="rebuild", scope="atlas")` or `vault_util(action="rebuild", scope="all", force=true)`

#### action="session_detail"

Full conversation transcript from a past session. Use after `vault_sessions` finds a relevant session. Shows timestamps, roles, tool usage, text content. Long messages truncated to 2,000 chars.

**Example:** `vault_util(action="session_detail", session_id="abc12345-...", max_messages=20)`

---

## How Notes Are Classified

The atlas classifies every note along four dimensions. These classifications drive filtering in `vault_util` actions: browse, recent, and stats.

**Zone** — Where the note lives:
- Path starts with `1. Vault` → `"vault"` (the user's content, read-only)
- Path starts with `2. Claude` → `"claude"` (Claude's workspace)
- Everything else → `"vault"`

**MOC (Map of Content)** — Hub notes that organize topics:
- Path contains `0. Topics-MOCs`, OR
- Note name starts with `$`

**Content** — External sources (books, articles, videos), not user-authored:
- Folder starts with `Clippings` or `2. Reference`, OR
- Path contains `books-temp`, OR
- Frontmatter has `source` or `author` field with a value, OR
- Frontmatter `type` field equals `content`, OR
- First 500 characters contain a URL from YouTube, Medium, Substack, Twitter, or X

**Journal** — Journal and review entries:
- Path contains `$Journal` or `Reflection & Reviews`, OR
- Note name matches date pattern `YYYY-MM ...` (e.g. "2026-01 Journal"), OR
- Note name starts with "daily journal" (case-insensitive)

**Topic** (as used in `vault_util(action="recent")`):
- Not a real classification — it's a negative filter meaning "not content AND not journal"

---

## Limitations and Gotchas

1. **Automatic freshness checks.** Search tools (vault_search, vault_semantic) and vault_util actions (browse, recent, stats) automatically check file mtimes every 30 seconds and incrementally update the atlas if anything changed (~95ms mtime walk). vault_util action="note" always reads file content fresh from disk (atlas is used for metadata only). The atlas JSON cache (`data/atlas.json`) persists across server restarts with a 24-hour max age. Calling `vault_util(action="rebuild")` forces an immediate refresh. Pass `force=true` for a complete rescan from scratch.

2. **Fuzzy matching can return wrong notes.** The 60% similarity threshold means ambiguous names might match the wrong note. Always verify the returned note name is what you expected. If unsure, use `vault_search` first to find the exact name.

3. **Rebuild scopes and timing.** `vault_util(action="rebuild")` supports `"atlas"`, `"embeddings"`, `"sessions"`, and `"all"`. Incremental atlas refresh: ~0.3s (vs ~2.5s full). Incremental embeddings with no changes: ~0.2s (vs ~11 min full rebuild). Session rebuild: ~1-4s. Use `force=true` only when you suspect the cache is corrupt or after major vault restructuring.

4. **No orphan listing.** `vault_util(action="stats", detail="links")` reports how many orphaned notes exist, but there is no tool to list *which* notes are orphans. The data exists in the graph engine but isn't exposed.

5. **Topic browsing is physical, not semantic.** `vault_util(action="browse", topic="Investing")` only returns notes physically located in a `$Investing` folder. Notes *about* investing that live elsewhere (e.g. journal entries mentioning trades) won't appear. Use `vault_search` for content-based discovery.

6. **`note_type="topic"` is a negative filter.** In `vault_util(action="recent")`, this means "not content AND not journal" — it's everything else, not specifically notes in topic folders.

7. **Semantic search needs pre-built embeddings.** Unlike keyword search which works immediately, `vault_semantic` requires a one-time embedding build (~10 min). If embeddings aren't built, the tool returns an error message with instructions. Embeddings persist in `data/lancedb/` across server restarts. After the initial build, incremental updates only re-embed notes whose content changed (MD5 hash comparison), so routine refreshes are fast. The embedding model loads at server startup (~10-15s) rather than on first tool call.

8. **`find_path()` and `get_mocs()` exist but aren't exposed as tools.** The graph engine has a shortest-path finder (`find_path(start, end, max_depth=6)`) and a MOC lister (`get_mocs()`), but neither is available as an MCP tool action.

9. **Outlinks and backlinks capped at 20.** `vault_util(action="note")` displays at most 20 outlinks and 20 backlinks. Notes with more links are silently truncated.

10. **Search snippets truncated to 200 characters.** The server truncates snippets in `vault_search` results to 200 chars, even though the underlying search engine may produce longer snippets.

11. **Skipped directories.** The scanner ignores: `.obsidian`, `.trash`, `.git`, `.claude`, `.scripts`, `.vscode`, `.mcp-server`, `node_modules`. Notes in these directories will never appear in any tool's results.

12. **Frontmatter display capped at 10 items.** `vault_util(action="note")` shows at most 10 frontmatter key-value pairs.

13. **Browse fails on emoji folder paths.** The `vault_util(action="browse")` `path` parameter does not match folders containing emoji characters (e.g. `Movies & TV 🎬`, `Podcast & Misc🎙️💼`). Returns "No notes found" even though the folder exists and contains notes. Root cause is likely a Unicode encoding mismatch in the path substring matching logic. Workaround: use `vault_search` or `vault_semantic` instead (these work fine regardless of emojis in paths). Or use `ls` via Bash for direct folder listing.

---

## Architecture

```
.mcp-server/
├── README.md              ← This file
├── requirements.txt       ← Python dependencies
├── pyproject.toml         ← Project metadata
├── src/
│   ├── server.py          ← MCP entry point: 4 tools, lazy init, fuzzy matching
│   ├── atlas.py           ← Vault scanner: metadata extraction, classification, 24h caching
│   ├── search.py          ← BM25 keyword search with 3x title boost
│   ├── graph.py           ← Wiki-link graph: backlinks, BFS traversal, MOC detection
│   ├── embeddings.py      ← Semantic search: e5-small-v2 + LanceDB (eager-loaded at startup)
│   └── sessions.py        ← Session log parser: JSONL parsing, BM25 search, 1h caching
└── data/                  ← Persistent cache (gitignored)
    ├── atlas.json         ← Cached vault index (~16MB, regenerated every 24h)
    ├── sessions-index.json ← Cached session index (regenerated every 1h)
    ├── server.log         ← Rotating log file (5MB max, 2 backups) for diagnostics
    └── lancedb/           ← Vector embeddings database (persists across restarts)
```

**Data flow:** On startup → `atlas.py` loads from cache (or incrementally updates if stale) → `SearchEngine`, `GraphEngine`, `EmbeddingEngine`, and `SessionEngine` are built → tools query these engines and format results. All engines load eagerly at startup so tool calls are always fast. During operation, search tools and vault_util actions call `_ensure_fresh()` which checks file mtimes every 30 seconds and incrementally updates if anything changed. The "note" action reads file content directly from disk on every call. Incremental updates compare file mtimes (atlas) and content hashes (embeddings) to avoid unnecessary work.

**Dependencies:** fastmcp (MCP framework), rank-bm25 (BM25 ranking), rapidfuzz (fuzzy matching), python-frontmatter (YAML parsing), sentence-transformers + torch (embedding model), lancedb (vector database), pandas (query results).

---

## Maintenance

**Cache location:** `.mcp-server/data/atlas.json` (~16MB). Auto-regenerates when older than 24 hours.

**Force refresh:** Call `vault_util(action="rebuild", scope="atlas")` to re-scan the vault immediately.

**Delete cache to hard reset:** Remove `data/atlas.json` and the server will rebuild on next tool call.

**MCP registration command:**
```
claude mcp add vault-intuition -- ".mcp-server\.venv\Scripts\python.exe" ".mcp-server\src\server.py"
```

**Server lifecycle:** Pre-initializes on startup (reads cache or scans vault, loads embedding model, builds session index), then enters stdio MCP loop. Startup takes ~10-15s with embedding model loading + ~1-4s for session parsing. Shuts down when Claude Code closes.

**Logging:** Server writes to `data/server.log` (rotating, 5MB max, 2 backups). Logs model loading, build operations, and errors. Useful for diagnosing issues after the fact.

---

## Roadmap

- ~~**Phase 1: Core tools**~~ — COMPLETE. Keyword search, note retrieval, graph traversal, browse, recent, stats, rebuild.
- ~~**Phase 2: Semantic search**~~ — COMPLETE. Find notes by meaning using e5-small-v2 embeddings + LanceDB. 8,497 chunks from 3,103 notes.
- ~~**Phase 3: Session awareness**~~ — COMPLETE. Search past Claude Code conversations via JSONL session log parsing. 84+ sessions, 7,600+ messages indexed.
- ~~**Phase 2b: Index freshness**~~ — COMPLETE. Atlas uses mtime comparison (0.3s incremental vs 2.5s full). Embeddings use MD5 content hashing (0.2s when unchanged vs 11 min full). Both default to incremental; `force=true` triggers full rebuild.
- ~~**Phase 4: Tool consolidation**~~ — COMPLETE. Consolidated 10 tools into 4 (vault_search, vault_semantic, vault_sessions, vault_util). Saves ~650-1,500 tokens/session in tool definitions.

See the task document ([[Build Vault Intuition system]]) for full architecture and research.
