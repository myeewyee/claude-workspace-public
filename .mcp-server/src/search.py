"""
Search: BM25 keyword search engine.

Indexes full content of every note and provides ranked keyword search
using the BM25 algorithm (same as Elasticsearch uses). Title matches
are boosted 3x over content matches.
"""

import re
from dataclasses import dataclass
from rank_bm25 import BM25Okapi

from atlas import NoteMetadata


@dataclass
class SearchResult:
    name: str
    path: str
    zone: str
    folder: str
    score: float
    snippet: str
    word_count: int


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, filter short tokens."""
    return [t for t in re.split(r"[^\w]+", text.lower()) if len(t) > 1]


class SearchEngine:
    """BM25-based keyword search over vault notes."""

    def __init__(self, notes: list[NoteMetadata]):
        self._notes = notes
        self._name_lookup = {n.name.lower(): i for i, n in enumerate(notes)}

        # Build two corpora: one for titles (boosted), one for content
        # We combine them by repeating title tokens to simulate a 3x boost
        corpus = []
        for note in notes:
            title_tokens = _tokenize(note.name) * 3  # 3x title boost
            content_tokens = _tokenize(note.content)
            corpus.append(title_tokens + content_tokens)

        self._bm25 = BM25Okapi(corpus)

    def search(
        self,
        query: str,
        limit: int = 10,
        zone: str | None = None,
        folder: str | None = None,
    ) -> list[SearchResult]:
        """
        Search notes by keyword query.

        Args:
            query: Search terms
            limit: Maximum results to return
            zone: Filter by "vault" or "claude" (None = all)
            folder: Filter to specific folder name (None = all)

        Returns:
            List of SearchResult sorted by relevance score (descending)
        """
        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)

        # Build (index, score) pairs, apply filters
        candidates = []
        for i, score in enumerate(scores):
            if score <= 0:
                continue
            note = self._notes[i]
            if zone and note.zone != zone:
                continue
            if folder and note.folder != folder:
                continue
            candidates.append((i, score))

        # Sort by score descending, take top N
        candidates.sort(key=lambda x: -x[1])
        candidates = candidates[:limit]

        # Build results with snippets
        results = []
        for idx, score in candidates:
            note = self._notes[idx]
            snippet = _extract_snippet(note.content, query_tokens)
            results.append(SearchResult(
                name=note.name,
                path=note.path,
                zone=note.zone,
                folder=note.folder,
                score=round(score, 3),
                snippet=snippet,
                word_count=note.word_count,
            ))

        return results


def _extract_snippet(content: str, query_tokens: list[str], context_chars: int = 150) -> str:
    """Extract a text snippet around the first occurrence of any query term."""
    if not content:
        return ""

    content_lower = content.lower()

    # Find the earliest match position
    best_pos = len(content)
    for token in query_tokens:
        pos = content_lower.find(token)
        if pos != -1 and pos < best_pos:
            best_pos = pos

    if best_pos == len(content):
        # No exact match found — return start of content
        return content[:context_chars * 2].strip() + "..."

    # Extract surrounding context
    start = max(0, best_pos - context_chars)
    end = min(len(content), best_pos + context_chars)

    snippet = content[start:end].strip()

    # Clean up: collapse whitespace, add ellipsis
    snippet = re.sub(r"\s+", " ", snippet)
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."

    return snippet


# ── CLI test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

    from atlas import get_atlas

    notes = get_atlas()
    engine = SearchEngine(notes)

    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "margin loan"
    print(f"Searching for: '{query}'\n")

    results = engine.search(query, limit=5)
    for r in results:
        print(f"  [{r.score:>6.1f}]  {r.name}")
        print(f"           {r.zone}/{r.folder} ({r.word_count} words)")
        # Truncate snippet for display
        snip = r.snippet[:120] + "..." if len(r.snippet) > 120 else r.snippet
        print(f"           {snip}")
        print()
