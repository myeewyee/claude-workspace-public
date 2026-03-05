"""
Vault Intuition MCP Server.

FastMCP server providing 4 tools for deep vault understanding:
- vault_search: BM25 keyword search
- vault_semantic: embedding-based semantic search
- vault_sessions: past Claude conversation search
- vault_util: consolidated utility (note, graph, browse, recent, stats, rebuild, session_detail)

Runs as a stdio MCP server launched by Claude Code.
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from pathlib import Path

from fastmcp import FastMCP
from rapidfuzz import fuzz, process as rfprocess

# Ensure src/ is on the path for imports
sys.path.insert(0, str(Path(__file__).parent))

from atlas import get_atlas, NoteMetadata, VAULT_ROOT, DATA_DIR
from search import SearchEngine
from graph import GraphEngine
from embeddings import EmbeddingEngine
from sessions import SessionEngine

# ── Logging setup ─────────────────────────────────────────────────

DATA_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        RotatingFileHandler(
            DATA_DIR / "server.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=2,
        ),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger("vault-intuition")

# ── Server setup ───────────────────────────────────────────────────

mcp = FastMCP(
    "vault-intuition",
    instructions=(
        "MCP server for deep Obsidian vault understanding. "
        "Indexes 3,000+ notes and provides keyword search, "
        "semantic search, link graph traversal, browsing, analytics, "
        "and session history search across past Claude conversations."
    ),
)

# ── Global state (initialized on first tool call) ─────────────────

_atlas: list[NoteMetadata] | None = None
_search_engine: SearchEngine | None = None
_graph_engine: GraphEngine | None = None
_embedding_engine: EmbeddingEngine | None = None
_session_engine: SessionEngine | None = None
_last_freshness_check: float = 0.0  # time.time() of last mtime walk

FRESHNESS_INTERVAL_SECONDS = 30  # How often to check for file changes


def _ensure_initialized():
    """Lazy initialization — load atlas and build indexes on first use."""
    global _atlas, _search_engine, _graph_engine, _last_freshness_check
    if _atlas is None:
        _atlas = get_atlas()
        _search_engine = SearchEngine(_atlas)
        _graph_engine = GraphEngine(_atlas)
        _last_freshness_check = time.time()


def _ensure_fresh():
    """Check if any vault files changed since last check. Refresh if needed.

    Compares file mtimes against the cached atlas. Only re-scans files that
    actually changed. Runs at most once every FRESHNESS_INTERVAL_SECONDS.
    """
    global _atlas, _search_engine, _graph_engine, _last_freshness_check
    _ensure_initialized()

    now = time.time()
    if now - _last_freshness_check < FRESHNESS_INTERVAL_SECONDS:
        return  # Checked recently, skip

    _last_freshness_check = now

    from atlas import incremental_update, save_atlas
    updated_notes, stats = incremental_update()

    if stats["added"] or stats["changed"] or stats["deleted"]:
        _atlas = updated_notes
        _search_engine = SearchEngine(_atlas)
        _graph_engine = GraphEngine(_atlas)
        save_atlas(_atlas)
        logger.info(
            "Freshness check: +%d added, ~%d changed, -%d deleted",
            stats["added"], stats["changed"], stats["deleted"],
        )


def _rebuild(scope: str = "atlas", force: bool = False):
    """Rebuild indexes. Uses incremental updates by default, full rebuild if force=True."""
    global _atlas, _search_engine, _graph_engine, _embedding_engine, _session_engine
    if scope in ("atlas", "all"):
        _atlas = get_atlas(force_rebuild=True)
        _search_engine = SearchEngine(_atlas)
        _graph_engine = GraphEngine(_atlas)
    if scope in ("embeddings", "all"):
        _ensure_initialized()
        if _embedding_engine is None:
            _embedding_engine = EmbeddingEngine()
        if force:
            _embedding_engine.build(_atlas)
        else:
            _embedding_engine.incremental_build(_atlas)
    if scope in ("sessions", "all"):
        _session_engine = SessionEngine()
        _session_engine.build(force=True)


def _fuzzy_find_note(name: str) -> NoteMetadata | None:
    """Find a note by name using fuzzy matching."""
    _ensure_initialized()
    assert _atlas is not None

    # Exact match first
    for note in _atlas:
        if note.name.lower() == name.lower():
            return note

    # Fuzzy match
    all_names = [n.name for n in _atlas]
    matches = rfprocess.extract(name, all_names, scorer=fuzz.WRatio, limit=1)
    if matches and matches[0][1] >= 60:  # Minimum 60% similarity
        matched_name = matches[0][0]
        for note in _atlas:
            if note.name == matched_name:
                return note

    return None


def _ensure_sessions():
    """Initialize session engine on first use."""
    global _session_engine
    if _session_engine is None:
        _session_engine = SessionEngine()
    if not _session_engine.is_built:
        _session_engine.build()


# ── Tool 1: vault_search ──────────────────────────────────────────

@mcp.tool()
def vault_search(
    query: str,
    limit: int = 10,
    zone: str = "",
    folder: str = "",
) -> str:
    """
    Search vault notes by keyword using BM25 ranking.

    Args:
        query: Search terms (e.g. "margin loan", "morning routine")
        limit: Maximum results to return (default 10)
        zone: Filter by zone - "vault" or "claude" (empty = all)
        folder: Filter to specific folder name (empty = all)

    Returns:
        Ranked search results with relevance scores and text snippets.
    """
    _ensure_fresh()
    assert _search_engine is not None

    results = _search_engine.search(
        query=query,
        limit=limit,
        zone=zone or None,
        folder=folder or None,
    )

    if not results:
        return f"No results found for '{query}'."

    lines = [f"Found {len(results)} results for '{query}':\n"]
    for r in results:
        lines.append(f"**{r.name}** (score: {r.score})")
        lines.append(f"  Path: {r.path}")
        lines.append(f"  Zone: {r.zone} | Folder: {r.folder} | {r.word_count} words")
        lines.append(f"  Snippet: {r.snippet[:200]}")
        lines.append("")

    return "\n".join(lines)


# ── Tool 2: vault_semantic ────────────────────────────────────────

@mcp.tool()
def vault_semantic(
    query: str,
    limit: int = 10,
    zone: str = "",
    folder: str = "",
) -> str:
    """
    Semantic search — find notes by meaning, not just keywords.

    Use this when the user's query is conceptual or emotional rather than
    a specific keyword. For example: "notes about feeling stuck",
    "thoughts on minimalism", "entries about relationship patterns".

    The embedding model loads at server startup. Queries are fast (~50-150ms).

    If embeddings haven't been built yet, call vault_util(action="rebuild", scope="embeddings") first.

    Args:
        query: Natural language query describing what you're looking for
        limit: Maximum results to return (default 10)
        zone: Filter by zone - "vault" or "claude" (empty = all)
        folder: Filter to specific folder name (empty = all)

    Returns:
        Ranked search results with similarity scores and text snippets.
    """
    _ensure_fresh()

    if _embedding_engine is None:
        return (
            "Semantic search is unavailable — the embedding model failed to load at startup. "
            "Check .mcp-server/data/server.log for details and restart the MCP server."
        )

    if not _embedding_engine.is_built:
        return (
            "Embeddings have not been built yet. "
            "Run vault_util(action='rebuild', scope='embeddings') first — this takes ~2 minutes "
            "on first run (embeds all 3,000+ notes) but only needs to happen once."
        )

    try:
        results = _embedding_engine.search(
            query=query,
            limit=limit,
            zone=zone or None,
            folder=folder or None,
        )
    except Exception as e:
        logger.exception("Semantic search failed")
        return f"Semantic search failed: {e}"

    if not results:
        return f"No semantic matches found for '{query}'."

    lines = [f"Found {len(results)} semantic matches for '{query}':\n"]
    for r in results:
        lines.append(f"**{r.name}** (similarity: {r.score})")
        lines.append(f"  Path: {r.path}")
        lines.append(f"  Zone: {r.zone} | Folder: {r.folder} | {r.word_count} words")
        if r.total_chunks > 1:
            lines.append(f"  Best match: chunk {r.chunk_index + 1}/{r.total_chunks}")
        lines.append(f"  Snippet: {r.snippet[:200]}")
        lines.append("")

    return "\n".join(lines)


# ── Tool 3: vault_sessions ────────────────────────────────────────

@mcp.tool()
def vault_sessions(
    query: str,
    limit: int = 10,
    days: int = 0,
) -> str:
    """
    Search past Claude Code conversations by keyword.

    Use this to find sessions where a topic was discussed, a decision was
    made, or specific work was done. Searches across all conversation text
    (both user messages and Claude responses).

    Args:
        query: Search terms (e.g. "permissions", "brainstorm feature", "investment tracker")
        limit: Maximum results to return (default 10)
        days: Only search sessions from the last N days (0 = all time)

    Returns:
        Ranked list of sessions matching the query, with snippets.
    """
    try:
        _ensure_sessions()
    except Exception as e:
        logger.exception("Session engine initialization failed")
        return f"Session search unavailable: {e}"

    assert _session_engine is not None

    results = _session_engine.search(query=query, limit=limit, days=days)

    if not results:
        return f"No sessions found matching '{query}'."

    lines = [f"Found {len(results)} sessions matching '{query}':\n"]
    for r in results:
        start = r.start_time[:16].replace("T", " ") if r.start_time else "?"
        lines.append(f"**{r.title[:100]}** (score: {r.score})")
        lines.append(f"  Session: {r.session_id}")
        lines.append(f"  Date: {start} | Messages: {r.message_count}")
        lines.append(f"  Snippet: {r.snippet[:250]}")
        lines.append("")

    lines.append("Use vault_util(action='session_detail', session_id=ID) to read a full conversation.")
    return "\n".join(lines)


# ── Tool 4: vault_util ────────────────────────────────────────────

@mcp.tool()
def vault_util(
    action: str,
    name: str = "",
    max_lines: int = 0,
    depth: int = 1,
    direction: str = "both",
    path: str = "",
    topic: str = "",
    sort: str = "modified",
    limit: int = 0,
    days: int = 7,
    zone: str = "",
    note_type: str = "",
    detail: str = "summary",
    scope: str = "atlas",
    force: bool = False,
    session_id: str = "",
    max_messages: int = 0,
) -> str:
    """
    Multi-action vault utility for note retrieval, graph traversal,
    browsing, recent notes, analytics, index rebuild, and session detail.

    Args:
        action: Operation to perform (required). One of:
            "note" - Retrieve a note's full content (requires name)
            "graph" - Explore wiki-link connections (requires name)
            "browse" - List notes in a folder or topic area
            "recent" - Show recently modified notes
            "stats" - Vault-wide analytics
            "rebuild" - Refresh vault indexes
            "session_detail" - Full conversation from a past session (requires session_id)
        name: Note name, fuzzy matched (required for note, graph)
        max_lines: Truncate note to first N lines, 0=full (note)
        depth: Hops to follow 1-3 (graph, default 1)
        direction: "outlinks", "backlinks", or "both" (graph)
        path: Folder path relative to vault (browse)
        topic: Topic name matching $-prefixed folders (browse)
        sort: "name", "modified", or "created" (browse, default "modified")
        limit: Max results (browse default 50, recent default 20)
        days: Look back N days (recent, default 7)
        zone: Filter by "vault" or "claude" (recent)
        note_type: "topic", "content", "journal", or "moc" (recent)
        detail: "summary", "folders", "topics", or "links" (stats)
        scope: "atlas", "embeddings", "sessions", or "all" (rebuild)
        force: Full rebuild instead of incremental (rebuild, default false)
        session_id: Session UUID from vault_sessions results (session_detail)
        max_messages: Limit messages shown, 0=all (session_detail)

    Returns:
        Action-specific results.
    """
    # ── action: note ──────────────────────────────────────────────
    if action == "note":
        if not name:
            return "Error: action 'note' requires 'name' parameter."

        _ensure_initialized()
        assert _graph_engine is not None

        note = _fuzzy_find_note(name)
        if note is None:
            return f"Note '{name}' not found. Try a different name or use vault_search to find it."

        graph_node = _graph_engine.get_node(note.name)
        backlinks = graph_node.backlinks if graph_node else []

        lines = [
            f"# {note.name}",
            f"**Path:** {note.path}",
            f"**Zone:** {note.zone} | **Folder:** {note.folder}",
            f"**Created:** {note.created or 'unknown'} | **Modified:** {note.modified}",
            f"**Words:** {note.word_count} | **Links out:** {len(note.outlinks)} | **Links in:** {len(backlinks)}",
        ]

        if note.is_moc:
            lines.append("**Type:** MOC Hub")
        if note.is_journal:
            lines.append("**Type:** Journal/Review")
        if note.is_content:
            lines.append("**Type:** Content (external source)")

        if note.frontmatter:
            fm_items = [f"{k}: {v}" for k, v in note.frontmatter.items() if v]
            if fm_items:
                lines.append(f"\n**Frontmatter:** {', '.join(fm_items[:10])}")

        if note.outlinks:
            lines.append(f"\n**Outlinks:** {', '.join(note.outlinks[:20])}")
        if backlinks:
            lines.append(f"**Backlinks:** {', '.join(backlinks[:20])}")

        # Content — always read fresh from disk (atlas content may be stale)
        try:
            content = Path(note.full_path).read_text(encoding="utf-8")
            if content.startswith("---"):
                end = content.find("---", 3)
                if end != -1:
                    content = content[end + 3:].lstrip("\n")
        except OSError:
            content = note.content

        if max_lines > 0:
            content_lines = content.split("\n")
            content = "\n".join(content_lines[:max_lines])
            if len(content_lines) > max_lines:
                content += f"\n\n... (truncated, {len(content_lines) - max_lines} more lines)"

        lines.append(f"\n---\n{content}")
        return "\n".join(lines)

    # ── action: graph ─────────────────────────────────────────────
    elif action == "graph":
        if not name:
            return "Error: action 'graph' requires 'name' parameter."

        _ensure_initialized()
        assert _graph_engine is not None

        note = _fuzzy_find_note(name)
        if note is None:
            return f"Note '{name}' not found. Try vault_search to find the correct name."

        result = _graph_engine.get_connections(note.name, depth=depth, direction=direction)
        if result is None:
            return f"No graph data for '{name}'."

        lines = [f"# Graph: {result.center} (depth {depth}, {direction})\n"]

        lines.append(f"**Outlinks ({len(result.outlinks)}):**")
        if result.outlinks:
            for link in result.outlinks:
                lines.append(f"  - {link}")
        else:
            lines.append("  (none)")

        lines.append(f"\n**Backlinks ({len(result.backlinks)}):**")
        if result.backlinks:
            for link in result.backlinks:
                lines.append(f"  - {link}")
        else:
            lines.append("  (none)")

        if result.mocs:
            lines.append(f"\n**Connected MOC hubs:** {', '.join(result.mocs)}")

        if depth > 1:
            other_nodes = [n for n in result.graph if n != result.center]
            lines.append(f"\n**Subgraph:** {len(result.graph)} notes within {depth} hops")
            for node_name in other_nodes[:20]:
                node_data = result.graph[node_name]
                tag = " [MOC]" if node_data.get("is_moc") else ""
                lines.append(f"  - {node_name}{tag} ({len(node_data['outlinks'])} out, {len(node_data['backlinks'])} back)")
            if len(other_nodes) > 20:
                lines.append(f"  ... and {len(other_nodes) - 20} more")

        return "\n".join(lines)

    # ── action: browse ────────────────────────────────────────────
    elif action == "browse":
        _ensure_fresh()
        assert _atlas is not None

        effective_limit = limit if limit > 0 else 50

        filtered = _atlas

        if topic:
            topic_clean = topic.lstrip("$").lower()
            filtered = [
                n for n in filtered
                if n.topic_folder and topic_clean in n.topic_folder.lstrip("$").lower()
            ]
        elif path:
            path_lower = path.lower()
            filtered = [
                n for n in filtered
                if path_lower in n.path.lower() or path_lower in n.folder.lower()
            ]
        else:
            folders: dict[str, int] = {}
            for n in _atlas:
                folders[n.folder] = folders.get(n.folder, 0) + 1
            lines = ["# Vault Folders\n"]
            for f, c in sorted(folders.items(), key=lambda x: -x[1]):
                lines.append(f"  {f}: {c} notes")
            return "\n".join(lines)

        if sort == "name":
            filtered.sort(key=lambda n: n.name.lower())
        elif sort == "created":
            filtered.sort(key=lambda n: n.created or "", reverse=True)
        else:
            filtered.sort(key=lambda n: n.modified, reverse=True)

        filtered = filtered[:effective_limit]

        if not filtered:
            return f"No notes found for path='{path}', topic='{topic}'."

        lines = [f"Found {len(filtered)} notes:\n"]
        for n in filtered:
            created = n.created[:10] if n.created else "?"
            modified = n.modified[:10] if n.modified else "?"
            tags = []
            if n.is_moc:
                tags.append("MOC")
            if n.is_journal:
                tags.append("Journal")
            if n.is_content:
                tags.append("Content")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"- **{n.name}**{tag_str} ({n.word_count}w, modified {modified})")

        return "\n".join(lines)

    # ── action: recent ────────────────────────────────────────────
    elif action == "recent":
        _ensure_fresh()
        assert _atlas is not None

        effective_limit = limit if limit > 0 else 20

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        filtered = [n for n in _atlas if n.modified >= cutoff]

        if zone:
            filtered = [n for n in filtered if n.zone == zone]
        if note_type:
            if note_type == "content":
                filtered = [n for n in filtered if n.is_content]
            elif note_type == "journal":
                filtered = [n for n in filtered if n.is_journal]
            elif note_type == "moc":
                filtered = [n for n in filtered if n.is_moc]
            elif note_type == "topic":
                filtered = [n for n in filtered if not n.is_content and not n.is_journal]

        filtered.sort(key=lambda n: n.modified, reverse=True)
        filtered = filtered[:effective_limit]

        if not filtered:
            return f"No notes modified in the last {days} days matching filters."

        lines = [f"**{len(filtered)} notes modified in the last {days} days:**\n"]
        for n in filtered:
            modified = n.modified[:16].replace("T", " ")
            tags = []
            if n.is_moc:
                tags.append("MOC")
            if n.is_journal:
                tags.append("Journal")
            if n.is_content:
                tags.append("Content")
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            lines.append(f"- {modified} — **{n.name}**{tag_str} ({n.zone}/{n.folder})")

        return "\n".join(lines)

    # ── action: stats ─────────────────────────────────────────────
    elif action == "stats":
        _ensure_fresh()
        assert _atlas is not None and _graph_engine is not None

        graph_stats = _graph_engine.stats()

        if detail == "summary":
            zones = {}
            for n in _atlas:
                zones[n.zone] = zones.get(n.zone, 0) + 1

            content_count = sum(1 for n in _atlas if n.is_content)
            journal_count = sum(1 for n in _atlas if n.is_journal)
            moc_count = sum(1 for n in _atlas if n.is_moc)
            avg_words = round(sum(n.word_count for n in _atlas) / max(len(_atlas), 1))

            embedding_status = (
                "loaded" if _embedding_engine and _embedding_engine._model
                else "unavailable"
            )

            session_status = "not loaded"
            session_count = 0
            if _session_engine and _session_engine.is_built:
                session_count = len(_session_engine._sessions)
                session_status = f"{session_count} sessions indexed"

            lines = [
                "# Vault Statistics\n",
                f"**Total notes:** {len(_atlas)}",
                f"**By zone:** " + ", ".join(f"{z}: {c}" for z, c in sorted(zones.items())),
                f"**Content notes:** {content_count}",
                f"**Journal entries:** {journal_count}",
                f"**MOC hubs:** {moc_count}",
                f"**Average word count:** {avg_words}",
                f"**Semantic search:** {embedding_status}",
                f"**Session history:** {session_status}",
                f"\n**Link graph:**",
                f"  Total links: {graph_stats['total_links']}",
                f"  Linked notes: {graph_stats['linked_notes']}",
                f"  Orphaned notes: {graph_stats['orphaned_notes']}",
                f"  Avg outlinks per note: {graph_stats['avg_outlinks']}",
            ]
            return "\n".join(lines)

        elif detail == "folders":
            folders: dict[str, int] = {}
            for n in _atlas:
                folders[n.folder] = folders.get(n.folder, 0) + 1
            lines = ["# Notes by Folder\n"]
            for f, c in sorted(folders.items(), key=lambda x: -x[1]):
                lines.append(f"  {f}: {c}")
            return "\n".join(lines)

        elif detail == "topics":
            topics: dict[str, int] = {}
            for n in _atlas:
                if n.topic_folder:
                    topics[n.topic_folder] = topics.get(n.topic_folder, 0) + 1
            lines = ["# Notes by Topic ($-prefixed folders)\n"]
            for t, c in sorted(topics.items(), key=lambda x: -x[1]):
                lines.append(f"  {t}: {c}")
            return "\n".join(lines)

        elif detail == "links":
            mocs = _graph_engine.get_mocs()
            lines = [
                "# Link Statistics\n",
                f"**Total links:** {graph_stats['total_links']}",
                f"**Linked notes:** {graph_stats['linked_notes']} / {graph_stats['total_notes']}",
                f"**Orphaned notes:** {graph_stats['orphaned_notes']}",
                f"**Max outlinks:** {graph_stats['max_outlinks']}",
                f"**Max backlinks:** {graph_stats['max_backlinks']}",
                f"\n**Top MOC hubs:**",
            ]
            for m in mocs[:15]:
                lines.append(f"  {m['name']}: {m['total_connections']} connections")
            return "\n".join(lines)

        return f"Unknown detail level: '{detail}'. Use 'summary', 'folders', 'topics', or 'links'."

    # ── action: rebuild ───────────────────────────────────────────
    elif action == "rebuild":
        start = time.time()

        try:
            _rebuild(scope, force=force)
        except Exception as e:
            logger.exception(f"Rebuild failed (scope={scope})")
            return f"Rebuild failed ({scope}): {e}"

        elapsed = round(time.time() - start, 1)
        note_count = len(_atlas) if _atlas else 0

        parts = [
            f"Rebuilt: {scope}",
            f"Notes indexed: {note_count}",
        ]
        if scope in ("sessions", "all") and _session_engine:
            parts.append(f"Sessions indexed: {len(_session_engine._sessions)}")
        parts.append(f"Duration: {elapsed}s")

        return "\n".join(parts)

    # ── action: session_detail ────────────────────────────────────
    elif action == "session_detail":
        if not session_id:
            return "Error: action 'session_detail' requires 'session_id' parameter."

        try:
            _ensure_sessions()
        except Exception as e:
            logger.exception("Session engine initialization failed")
            return f"Session detail unavailable: {e}"

        assert _session_engine is not None

        result = _session_engine.get_detail(session_id)

        if result is None:
            return f"Session '{session_id}' not found."

        metadata, messages = result

        lines = [
            f"# Session: {metadata.title[:100]}",
            f"**ID:** {metadata.session_id}",
            f"**Time:** {metadata.start_time[:16]} to {metadata.end_time[:16]}",
            f"**Messages:** {metadata.message_count} ({metadata.user_message_count} user, {metadata.assistant_message_count} assistant)",
            f"**Words:** {metadata.total_words}",
            "",
            "---",
            "",
        ]

        display_messages = messages
        if max_messages > 0:
            display_messages = messages[:max_messages]

        for msg in display_messages:
            role = "USER" if msg.role == "user" else "ASSISTANT"
            ts = msg.timestamp[:19].replace("T", " ") if msg.timestamp else ""
            lines.append(f"**[{ts}] {role}**")

            if msg.tool_names:
                lines.append(f"*Tools: {', '.join(msg.tool_names)}*")

            if msg.text:
                text = msg.text
                if len(text) > 2000:
                    text = text[:2000] + f"\n\n... (truncated, {len(msg.text)} chars total)"
                lines.append(text)

            lines.append("")

        if max_messages > 0 and len(messages) > max_messages:
            lines.append(f"... ({len(messages) - max_messages} more messages not shown)")

        return "\n".join(lines)

    # ── unknown action ────────────────────────────────────────────
    else:
        return (
            f"Unknown action: '{action}'. "
            "Valid actions: note, graph, browse, recent, stats, rebuild, session_detail"
        )


# ── Startup initialization ────────────────────────────────────────

def _init_embedding_engine():
    """Load embedding model at startup so first tool call is fast."""
    global _embedding_engine
    try:
        _embedding_engine = EmbeddingEngine()
        _embedding_engine._ensure_model()
        logger.info("Embedding engine ready")
    except Exception:
        logger.exception("Failed to load embedding model — semantic search disabled")
        _embedding_engine = None


def _init_session_engine():
    """Pre-build session index at startup so first tool call is fast."""
    global _session_engine
    try:
        _session_engine = SessionEngine()
        stats = _session_engine.build()
        logger.info(
            "Session engine ready: %d sessions indexed",
            stats.get("session_count", 0),
        )
    except Exception:
        logger.exception("Failed to initialize session engine")
        _session_engine = None


# ── Entry point ───────────────────────────────────────────────────

if __name__ == "__main__":
    # Pre-initialize on startup so first tool call is fast
    _ensure_initialized()
    _init_embedding_engine()
    _init_session_engine()
    mcp.run(transport="stdio")
