"""
Sessions: Claude Code session log parser and search engine.

Parses JSONL session logs from ~/.claude/projects/*/,
extracts conversation text, and provides BM25 keyword search
across all past sessions.

Session logs contain:
  - type: "user" / "assistant" / "progress" / "queue-operation" / etc.
  - message.content: array of {type: "text", text: "..."} blocks
  - Timestamps, session IDs, tool use records

We only index human-readable text (user + assistant), stripping
system reminders, tool parameters, and hook output.
"""

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rank_bm25 import BM25Okapi

from atlas import DATA_DIR

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
SESSIONS_CACHE = DATA_DIR / "sessions-index.json"
SESSIONS_MAX_AGE_HOURS = 1  # Re-check for new sessions frequently

# Regex to strip system tags and their content
SYSTEM_TAG_PATTERN = re.compile(
    r"<(?:system-reminder|task-tracking-reminder|ide_selection|"
    r"EXTREMELY-IMPORTANT|antml_thinking|command-name|user-prompt-submit-hook)"
    r"[^>]*>.*?</(?:system-reminder|task-tracking-reminder|ide_selection|"
    r"EXTREMELY-IMPORTANT|antml_thinking|command-name|user-prompt-submit-hook)>",
    re.DOTALL,
)

# Also strip standalone XML-like tags that wrap system content
STANDALONE_TAG_PATTERN = re.compile(r"<[a-z_-]+>.*?</[a-z_-]+>", re.DOTALL)


# ── Data classes ───────────────────────────────────────────────────

@dataclass
class SessionMetadata:
    session_id: str
    file_path: str
    start_time: str          # ISO timestamp of first message
    end_time: str            # ISO timestamp of last message
    message_count: int       # Total user + assistant messages
    user_message_count: int
    assistant_message_count: int
    title: str               # First meaningful user message (truncated)
    total_words: int         # Word count of all extracted text
    file_size: int           # File size in bytes


@dataclass
class SessionSearchResult:
    session_id: str
    title: str
    start_time: str
    end_time: str
    message_count: int
    score: float
    snippet: str


@dataclass
class SessionMessage:
    role: str                # "user" or "assistant"
    text: str                # Cleaned text content
    timestamp: str           # ISO timestamp
    tool_names: list[str] = field(default_factory=list)  # Tools used (assistant only)


# ── Text extraction ───────────────────────────────────────────────

def _clean_text(text: str) -> str:
    """Strip system tags, XML wrappers, and excessive whitespace from message text."""
    # Remove known system tag blocks
    text = SYSTEM_TAG_PATTERN.sub("", text)
    # Collapse excessive whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    return text.strip()


def _extract_title(text: str, max_length: int = 120) -> str:
    """Extract a clean title from the first user message text."""
    # Remove IDE selection and opened file context
    text = re.sub(r"<ide_selection>.*?</ide_selection>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ide_opened_file>.*?</ide_opened_file>", "", text, flags=re.DOTALL)
    # Remove any remaining XML-like tags
    text = re.sub(r"<[^>]+>.*?</[^>]+>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+/?>", "", text)
    text = _clean_text(text)
    # Take first non-empty line
    for line in text.split("\n"):
        line = line.strip()
        if line and len(line) > 5:
            if len(line) > max_length:
                return line[:max_length] + "..."
            return line
    return "(no text)"


def _extract_message_text(content_blocks: list) -> tuple[str, list[str]]:
    """
    Extract readable text and tool names from message content blocks.

    Returns:
        (text, tool_names) tuple
    """
    texts = []
    tool_names = []

    for block in content_blocks:
        if not isinstance(block, dict):
            continue

        block_type = block.get("type", "")

        if block_type == "text":
            text = block.get("text", "")
            cleaned = _clean_text(text)
            if cleaned:
                texts.append(cleaned)

        elif block_type == "tool_use":
            name = block.get("name", "")
            if name:
                tool_names.append(name)
            # Don't index tool input parameters (just JSON blobs)

        # Skip tool_result blocks entirely (they contain raw file contents, etc.)

    return "\n".join(texts), tool_names


# ── Session parsing ───────────────────────────────────────────────

def parse_session(file_path: Path) -> tuple[SessionMetadata, list[SessionMessage], str]:
    """
    Parse a single JSONL session file.

    Returns:
        (metadata, messages, combined_text) tuple.
        combined_text is all message text joined, for BM25 indexing.
    """
    messages: list[SessionMessage] = []
    timestamps: list[str] = []
    title = ""
    first_user_text = ""

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = obj.get("type", "")
            if msg_type not in ("user", "assistant"):
                continue

            timestamp = obj.get("timestamp", "")
            if timestamp:
                timestamps.append(timestamp)

            msg_data = obj.get("message", {})
            if not isinstance(msg_data, dict):
                continue

            content = msg_data.get("content", [])
            if isinstance(content, str):
                # Some messages have string content directly
                content = [{"type": "text", "text": content}]

            text, tool_names = _extract_message_text(content)

            if text or tool_names:
                messages.append(SessionMessage(
                    role=msg_type,
                    text=text,
                    timestamp=timestamp,
                    tool_names=tool_names,
                ))

            # Capture title from first user message with text
            if msg_type == "user" and text and not first_user_text:
                first_user_text = text
                title = _extract_title(text)

    # Build combined text for search indexing
    combined_text = "\n\n".join(m.text for m in messages if m.text)
    total_words = len(combined_text.split()) if combined_text else 0

    user_count = sum(1 for m in messages if m.role == "user")
    assistant_count = sum(1 for m in messages if m.role == "assistant")

    session_id = file_path.stem  # UUID filename without .jsonl

    metadata = SessionMetadata(
        session_id=session_id,
        file_path=str(file_path),
        start_time=min(timestamps) if timestamps else "",
        end_time=max(timestamps) if timestamps else "",
        message_count=user_count + assistant_count,
        user_message_count=user_count,
        assistant_message_count=assistant_count,
        title=title or "(empty session)",
        total_words=total_words,
        file_size=file_path.stat().st_size,
    )

    return metadata, messages, combined_text


# ── Session engine ────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, filter short tokens."""
    return [t for t in re.split(r"[^\w]+", text.lower()) if len(t) > 1]


class SessionEngine:
    """
    Indexes and searches Claude Code session logs.

    Scans all JSONL files under ~/.claude/projects/*/,
    extracts conversation text, and builds a BM25 index.
    """

    def __init__(self):
        self._sessions: list[SessionMetadata] = []
        self._combined_texts: list[str] = []  # One per session, for BM25
        self._bm25: Optional[BM25Okapi] = None
        self._session_lookup: dict[str, int] = {}  # session_id -> index

    def build(self, force: bool = False) -> dict:
        """
        Scan all session files and build the search index.

        Returns:
            Stats dict with session_count, total_messages, elapsed time.
        """
        start = time.time()

        # Find all JSONL files across all project directories
        jsonl_files = []
        if CLAUDE_PROJECTS_DIR.exists():
            for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
                if project_dir.is_dir():
                    for f in project_dir.glob("*.jsonl"):
                        jsonl_files.append(f)

        if not jsonl_files:
            logger.warning("No session JSONL files found in %s", CLAUDE_PROJECTS_DIR)
            return {"session_count": 0, "total_messages": 0, "elapsed": 0}

        logger.info("Found %d session files to parse", len(jsonl_files))

        # Try loading from cache (unless forced)
        if not force:
            cached = self._load_cache(jsonl_files)
            if cached:
                elapsed = round(time.time() - start, 2)
                logger.info(
                    "Loaded %d sessions from cache in %ss",
                    len(self._sessions), elapsed,
                )
                return {
                    "session_count": len(self._sessions),
                    "total_messages": sum(s.message_count for s in self._sessions),
                    "elapsed": elapsed,
                }

        # Parse all sessions
        sessions = []
        combined_texts = []
        skipped = 0

        for f in sorted(jsonl_files, key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                metadata, messages, combined_text = parse_session(f)
                if metadata.message_count > 0:
                    sessions.append(metadata)
                    combined_texts.append(combined_text)
                else:
                    skipped += 1
            except Exception as e:
                logger.warning("Failed to parse %s: %s", f.name, e)
                skipped += 1

        self._sessions = sessions
        self._combined_texts = combined_texts
        self._session_lookup = {s.session_id: i for i, s in enumerate(sessions)}

        # Build BM25 index
        if sessions:
            # Include title tokens (boosted 3x) + combined text tokens
            corpus = []
            for i, session in enumerate(sessions):
                title_tokens = _tokenize(session.title) * 3
                content_tokens = _tokenize(combined_texts[i])
                corpus.append(title_tokens + content_tokens)
            self._bm25 = BM25Okapi(corpus)

        # Save cache
        self._save_cache()

        elapsed = round(time.time() - start, 2)
        total_messages = sum(s.message_count for s in sessions)

        logger.info(
            "Indexed %d sessions (%d messages, %d skipped) in %ss",
            len(sessions), total_messages, skipped, elapsed,
        )

        return {
            "session_count": len(sessions),
            "total_messages": total_messages,
            "skipped": skipped,
            "elapsed": elapsed,
        }

    def search(
        self,
        query: str,
        limit: int = 10,
        days: int = 0,
    ) -> list[SessionSearchResult]:
        """
        Search sessions by keyword query using BM25.

        Args:
            query: Search terms
            limit: Maximum results
            days: Only search sessions from the last N days (0 = all)

        Returns:
            List of SessionSearchResult sorted by relevance.
        """
        if not self._bm25 or not self._sessions:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Build candidates with optional time filter
        cutoff = ""
        if days > 0:
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        candidates = []
        for i, score in enumerate(scores):
            if score <= 0:
                continue
            session = self._sessions[i]
            if cutoff and session.start_time < cutoff:
                continue
            candidates.append((i, score))

        # Sort by score descending
        candidates.sort(key=lambda x: -x[1])
        candidates = candidates[:limit]

        results = []
        for idx, score in candidates:
            session = self._sessions[idx]
            snippet = _extract_snippet(self._combined_texts[idx], query_tokens)
            results.append(SessionSearchResult(
                session_id=session.session_id,
                title=session.title,
                start_time=session.start_time,
                end_time=session.end_time,
                message_count=session.message_count,
                score=round(score, 3),
                snippet=snippet,
            ))

        return results

    def get_detail(self, session_id: str) -> Optional[tuple[SessionMetadata, list[SessionMessage]]]:
        """
        Get full conversation detail for a specific session.

        Args:
            session_id: The UUID session ID (filename without .jsonl)

        Returns:
            (metadata, messages) tuple, or None if not found.
        """
        idx = self._session_lookup.get(session_id)
        if idx is None:
            # Session not in index, try parsing the file directly
            return self._parse_by_id(session_id)

        session = self._sessions[idx]
        # Re-parse to get full messages (we don't cache message content)
        file_path = Path(session.file_path)
        if not file_path.exists():
            return None

        metadata, messages, _ = parse_session(file_path)
        return metadata, messages

    def list_sessions(
        self,
        limit: int = 20,
        days: int = 0,
    ) -> list[SessionMetadata]:
        """
        List sessions sorted by most recent first.

        Args:
            limit: Maximum sessions to return
            days: Only list sessions from the last N days (0 = all)

        Returns:
            List of SessionMetadata sorted by end_time descending.
        """
        sessions = self._sessions

        if days > 0:
            from datetime import timedelta
            cutoff = (datetime.now() - timedelta(days=days)).isoformat()
            sessions = [s for s in sessions if s.start_time >= cutoff]

        # Already sorted by mtime (most recent first from build)
        return sessions[:limit]

    # ── Cache management ──────────────────────────────────────────

    def _save_cache(self):
        """Save session metadata and texts to JSON cache."""
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        data = {
            "generated": datetime.now(tz=timezone.utc).isoformat(),
            "session_count": len(self._sessions),
            "sessions": [asdict(s) for s in self._sessions],
            "texts": self._combined_texts,
        }

        tmp = SESSIONS_CACHE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        tmp.replace(SESSIONS_CACHE)

    def _load_cache(self, current_files: list[Path]) -> bool:
        """
        Load from cache if it's fresh and the file count matches.
        Returns True if cache was loaded successfully.
        """
        if not SESSIONS_CACHE.exists():
            return False

        try:
            with open(SESSIONS_CACHE, encoding="utf-8") as f:
                data = json.load(f)

            # Check freshness (handle both naive and aware timestamps)
            generated = datetime.fromisoformat(data["generated"])
            now = datetime.now(tz=timezone.utc)
            if generated.tzinfo is None:
                generated = generated.replace(tzinfo=timezone.utc)
            age_hours = (now - generated).total_seconds() / 3600
            if age_hours > SESSIONS_MAX_AGE_HOURS:
                return False

            # Check if new sessions have appeared
            cached_count = data.get("session_count", 0)
            if len(current_files) > cached_count + 5:
                # Many new sessions since cache, rebuild
                return False

            sessions = [SessionMetadata(**s) for s in data["sessions"]]
            texts = data.get("texts", [])

            if len(sessions) != len(texts):
                return False

            self._sessions = sessions
            self._combined_texts = texts
            self._session_lookup = {s.session_id: i for i, s in enumerate(sessions)}

            # Rebuild BM25 from cached texts
            if sessions:
                corpus = []
                for i, session in enumerate(sessions):
                    title_tokens = _tokenize(session.title) * 3
                    content_tokens = _tokenize(texts[i])
                    corpus.append(title_tokens + content_tokens)
                self._bm25 = BM25Okapi(corpus)

            return True

        except Exception as e:
            logger.warning("Failed to load session cache: %s", e)
            return False

    def _parse_by_id(self, session_id: str) -> Optional[tuple[SessionMetadata, list[SessionMessage]]]:
        """Try to find and parse a session file by ID across all project dirs."""
        if not CLAUDE_PROJECTS_DIR.exists():
            return None

        filename = f"{session_id}.jsonl"
        for project_dir in CLAUDE_PROJECTS_DIR.iterdir():
            if project_dir.is_dir():
                candidate = project_dir / filename
                if candidate.exists():
                    metadata, messages, _ = parse_session(candidate)
                    return metadata, messages

        return None

    @property
    def is_built(self) -> bool:
        return len(self._sessions) > 0


# ── Snippet extraction ────────────────────────────────────────────

def _extract_snippet(text: str, query_tokens: list[str], context_chars: int = 200) -> str:
    """Extract a text snippet around the first occurrence of any query term."""
    if not text:
        return ""

    text_lower = text.lower()

    # Find the earliest match position
    best_pos = len(text)
    for token in query_tokens:
        pos = text_lower.find(token)
        if pos != -1 and pos < best_pos:
            best_pos = pos

    if best_pos == len(text):
        return text[:context_chars].strip() + "..."

    start = max(0, best_pos - context_chars // 2)
    end = min(len(text), best_pos + context_chars)

    snippet = text[start:end].strip()
    snippet = re.sub(r"\s+", " ", snippet)

    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


# ── CLI test ──────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    logging.basicConfig(level=logging.INFO)

    engine = SessionEngine()

    if "--build" in sys.argv:
        stats = engine.build(force=True)
        print(f"\nBuild complete: {stats}")

        print("\nRecent sessions:")
        for s in engine.list_sessions(limit=5):
            print(f"  [{s.start_time[:16]}] {s.title[:80]} ({s.message_count} msgs)")

    elif "--search" in sys.argv:
        # Build first (uses cache if available)
        engine.build()

        query = " ".join(a for a in sys.argv[1:] if a != "--search") or "permissions"
        print(f"Session search: '{query}'\n")

        results = engine.search(query, limit=5)
        for r in results:
            print(f"  [{r.score:>6.1f}]  {r.title[:80]}")
            print(f"           {r.start_time[:16]} | {r.message_count} messages")
            snip = r.snippet[:150] + "..." if len(r.snippet) > 150 else r.snippet
            print(f"           {snip}")
            print()

    elif "--detail" in sys.argv:
        engine.build()
        sid = sys.argv[sys.argv.index("--detail") + 1] if len(sys.argv) > sys.argv.index("--detail") + 1 else ""
        if not sid:
            print("Usage: python sessions.py --detail <session-id>")
            sys.exit(1)

        result = engine.get_detail(sid)
        if result:
            meta, messages = result
            print(f"Session: {meta.session_id}")
            print(f"Title: {meta.title}")
            print(f"Time: {meta.start_time} -> {meta.end_time}")
            print(f"Messages: {meta.message_count}")
            print(f"\n{'='*60}\n")
            for msg in messages:
                role = "USER" if msg.role == "user" else "ASSISTANT"
                print(f"[{msg.timestamp[:19]}] {role}")
                if msg.tool_names:
                    print(f"  Tools: {', '.join(msg.tool_names)}")
                if msg.text:
                    print(f"  {msg.text[:300]}")
                print()
        else:
            print(f"Session '{sid}' not found")

    else:
        print("Usage:")
        print("  python sessions.py --build           Build/rebuild session index")
        print("  python sessions.py --search <query>  Search sessions by keyword")
        print("  python sessions.py --detail <id>     Show session conversation")
