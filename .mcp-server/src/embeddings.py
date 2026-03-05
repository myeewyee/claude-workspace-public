"""
Embeddings: Semantic search using e5-small-v2 + LanceDB.

The embedding model (~130MB) loads eagerly at server startup (~10-15s).
Subsequent queries are fast (~50-150ms per query).

Chunking strategy:
  - Notes <= 400 words: embed as a single chunk
  - Longer notes: split into ~400-word chunks with ~100-word overlap
  - Each chunk carries its parent note metadata for result dedup

e5-small-v2 requires prefixes:
  - "query: " for search queries
  - "passage: " for documents being indexed

Incremental updates:
  - Each chunk stores a content_hash (MD5 of the parent note's full text)
  - On incremental build, only notes with changed hashes are re-embedded
  - Deleted notes' chunks are removed, unchanged notes are kept as-is
"""

import hashlib
import logging
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from atlas import NoteMetadata, DATA_DIR

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────

LANCEDB_DIR = DATA_DIR / "lancedb"
TABLE_NAME = "vault_chunks"
MODEL_NAME = "intfloat/e5-small-v2"
EMBEDDING_DIM = 384

# Chunking parameters
CHUNK_SIZE_WORDS = 400
CHUNK_OVERLAP_WORDS = 100

# ── Data classes ───────────────────────────────────────────────────

@dataclass
class SemanticResult:
    name: str
    path: str
    zone: str
    folder: str
    score: float
    snippet: str
    word_count: int
    chunk_index: int
    total_chunks: int


# ── Chunking ───────────────────────────────────────────────────────

def _chunk_text(text: str) -> list[str]:
    """
    Split text into overlapping word-based chunks.
    Short texts (<=CHUNK_SIZE_WORDS) return as a single chunk.
    """
    words = text.split()
    if len(words) <= CHUNK_SIZE_WORDS:
        return [text]

    chunks = []
    start = 0
    while start < len(words):
        end = start + CHUNK_SIZE_WORDS
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))
        # Advance by (chunk_size - overlap)
        start += CHUNK_SIZE_WORDS - CHUNK_OVERLAP_WORDS
        # If the remaining words would make a tiny last chunk, merge with previous
        if start < len(words) and len(words) - start < CHUNK_OVERLAP_WORDS:
            chunks[-1] = " ".join(words[start - (CHUNK_SIZE_WORDS - CHUNK_OVERLAP_WORDS):])
            break

    return chunks


def _content_hash(text: str) -> str:
    """Compute MD5 hash of note content for change detection."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def _prepare_chunks(notes: list[NoteMetadata]) -> list[dict]:
    """
    Convert all notes into chunk records for embedding.
    Each record is a dict with text + metadata fields.
    Includes content_hash for incremental update tracking.
    """
    records = []
    for note in notes:
        text = note.content.strip()
        if not text:
            continue

        note_hash = _content_hash(text)
        chunks = _chunk_text(text)
        total = len(chunks)

        for i, chunk in enumerate(chunks):
            # Prepend note name to first chunk for better matching
            passage = f"{note.name}\n{chunk}" if i == 0 else chunk
            records.append({
                "text": passage,
                "note_name": note.name,
                "note_path": note.path,
                "zone": note.zone,
                "folder": note.folder,
                "word_count": note.word_count,
                "chunk_index": i,
                "total_chunks": total,
                "content_hash": note_hash,
            })

    return records


# ── Embedding Engine (lazy-loaded) ─────────────────────────────────

class EmbeddingEngine:
    """
    Manages the embedding model and LanceDB vector store.
    Everything is lazy-loaded — first call triggers model download
    and/or table creation.
    """

    def __init__(self):
        self._model = None
        self._db = None
        self._table = None

    def _ensure_model(self):
        """Load the sentence-transformers model (first call: ~10-15s)."""
        if self._model is not None:
            return

        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model %s...", MODEL_NAME)
        start = time.time()

        # Try local cache first (skips ~20 HTTP requests to Hugging Face)
        try:
            self._model = SentenceTransformer(MODEL_NAME, local_files_only=True)
        except Exception:
            # Model not cached yet — download it
            logger.info("Model not in local cache, downloading...")
            self._model = SentenceTransformer(MODEL_NAME)

        elapsed = time.time() - start
        logger.info("Embedding model loaded in %.1fs", elapsed)

    def _ensure_db(self):
        """Open or create the LanceDB database."""
        if self._db is not None:
            return

        import lancedb

        LANCEDB_DIR.mkdir(parents=True, exist_ok=True)
        self._db = lancedb.connect(str(LANCEDB_DIR))

    def _ensure_table(self):
        """Open the existing chunks table, if it exists."""
        self._ensure_db()
        if self._table is not None:
            return

        try:
            self._table = self._db.open_table(TABLE_NAME)
        except Exception:
            # Table doesn't exist yet — will be created on build
            self._table = None

    @property
    def is_built(self) -> bool:
        """Check if embeddings have been built."""
        self._ensure_db()
        try:
            self._db.open_table(TABLE_NAME)
            return True
        except Exception:
            return False

    def build(self, notes: list[NoteMetadata]) -> dict:
        """
        Build (or rebuild) the embeddings table from scratch.
        This embeds all note chunks and stores them in LanceDB.

        Returns:
            Stats dict with chunk_count, note_count, elapsed time.
        """
        self._ensure_model()
        self._ensure_db()

        start = time.time()

        # Prepare chunks
        records = _prepare_chunks(notes)
        if not records:
            return {"chunk_count": 0, "note_count": 0, "elapsed": 0}

        logger.info(
            "Embedding %d chunks from %d notes...",
            len(records),
            len(set(r["note_name"] for r in records)),
        )

        # Embed all chunks with "passage: " prefix (required by e5)
        texts = [f"passage: {r['text']}" for r in records]
        embeddings = self._model.encode(
            texts,
            batch_size=64,
            show_progress_bar=True,
            normalize_embeddings=True,
        )

        # Build LanceDB records
        for i, record in enumerate(records):
            record["vector"] = embeddings[i].tolist()

        # Drop old table if it exists, create new one
        try:
            self._db.drop_table(TABLE_NAME)
        except Exception:
            pass

        self._table = self._db.create_table(TABLE_NAME, data=records)

        elapsed = round(time.time() - start, 1)
        note_count = len(set(r["note_name"] for r in records))

        logger.info("Built %d chunks in %ss", len(records), elapsed)

        return {
            "chunk_count": len(records),
            "note_count": note_count,
            "elapsed": elapsed,
        }

    def incremental_build(self, notes: list[NoteMetadata]) -> dict:
        """
        Incremental embedding update: only re-embed notes whose content changed.

        Compares content hashes in LanceDB with current note content.
        Adds new notes, re-embeds changed notes, removes deleted notes.
        Falls back to full build if the table doesn't exist or lacks content_hash.

        Returns:
            Stats dict with added, changed, deleted, unchanged, elapsed.
        """
        self._ensure_model()
        self._ensure_db()

        start = time.time()

        # Check if table exists and has content_hash column
        try:
            table = self._db.open_table(TABLE_NAME)
            existing_df = table.to_pandas()
            if "content_hash" not in existing_df.columns:
                logger.info("No content_hash column found, falling back to full build")
                result = self.build(notes)
                result["fallback"] = "no content_hash column"
                return result
        except Exception:
            logger.info("No existing embeddings table, doing full build")
            result = self.build(notes)
            result["fallback"] = "no table"
            return result

        # Build current hash map: note_name -> content_hash
        current_hashes: dict[str, str] = {}
        for note in notes:
            text = note.content.strip()
            if text:
                current_hashes[note.name] = _content_hash(text)

        # Build existing hash map from LanceDB (one hash per note, from chunk_index=0)
        existing_hashes: dict[str, str] = {}
        for _, row in existing_df.iterrows():
            name = row["note_name"]
            if name not in existing_hashes:
                existing_hashes[name] = row.get("content_hash", "")

        # Diff
        current_names = set(current_hashes.keys())
        existing_names = set(existing_hashes.keys())

        added = current_names - existing_names
        deleted = existing_names - current_names
        common = current_names & existing_names
        changed = {n for n in common if current_hashes[n] != existing_hashes.get(n)}
        unchanged = common - changed

        needs_embedding = added | changed
        needs_removal = deleted | changed  # Changed notes: remove old, add new

        if not needs_embedding and not needs_removal:
            elapsed = round(time.time() - start, 2)
            logger.info("No embedding changes needed (%d notes unchanged)", len(unchanged))
            self._table = table
            return {
                "added": 0, "changed": 0, "deleted": 0,
                "unchanged": len(unchanged), "elapsed": elapsed,
            }

        logger.info(
            "Incremental embed: +%d added, ~%d changed, -%d deleted, =%d unchanged",
            len(added), len(changed), len(deleted), len(unchanged),
        )

        # Remove chunks for deleted/changed notes
        if needs_removal:
            removal_names = list(needs_removal)
            # Filter out removed notes from the dataframe
            keep_df = existing_df[~existing_df["note_name"].isin(removal_names)]
        else:
            keep_df = existing_df

        # Prepare and embed new/changed notes
        notes_to_embed = [n for n in notes if n.name in needs_embedding]
        new_records = _prepare_chunks(notes_to_embed)

        if new_records:
            texts = [f"passage: {r['text']}" for r in new_records]
            embeddings = self._model.encode(
                texts,
                batch_size=64,
                show_progress_bar=True,
                normalize_embeddings=True,
            )
            for i, record in enumerate(new_records):
                record["vector"] = embeddings[i].tolist()

        # Rebuild table: kept chunks + new chunks
        import pandas as pd

        if not keep_df.empty and new_records:
            new_df = pd.DataFrame(new_records)
            combined_df = pd.concat([keep_df, new_df], ignore_index=True)
        elif new_records:
            combined_df = pd.DataFrame(new_records)
        elif not keep_df.empty:
            combined_df = keep_df
        else:
            combined_df = pd.DataFrame()

        # Drop and recreate table with combined data
        try:
            self._db.drop_table(TABLE_NAME)
        except Exception:
            pass

        if not combined_df.empty:
            self._table = self._db.create_table(TABLE_NAME, data=combined_df)
        else:
            self._table = None

        elapsed = round(time.time() - start, 1)
        logger.info(
            "Incremental build: %d new chunks embedded, %d chunks kept, %ss",
            len(new_records), len(keep_df), elapsed,
        )

        return {
            "added": len(added),
            "changed": len(changed),
            "deleted": len(deleted),
            "unchanged": len(unchanged),
            "new_chunks": len(new_records),
            "kept_chunks": len(keep_df),
            "elapsed": elapsed,
        }

    def search(
        self,
        query: str,
        limit: int = 10,
        zone: str | None = None,
        folder: str | None = None,
    ) -> list[SemanticResult]:
        """
        Semantic search: find notes by meaning, not just keywords.

        Args:
            query: Natural language query
            limit: Max results (after dedup by note)
            zone: Filter by "vault" or "claude"
            folder: Filter by folder name

        Returns:
            List of SemanticResult, one per unique note, best chunk wins.
        """
        self._ensure_model()
        self._ensure_table()

        if self._table is None:
            raise RuntimeError(
                "Embeddings table not found — run vault_util(action='rebuild', scope='embeddings') to create it."
            )

        # Embed query with "query: " prefix (required by e5)
        query_vec = self._model.encode(
            f"query: {query}",
            normalize_embeddings=True,
        ).tolist()

        # Search LanceDB — fetch extra results to account for dedup + filtering
        fetch_limit = limit * 5
        results_df = (
            self._table
            .search(query_vec)
            .limit(fetch_limit)
            .to_pandas()
        )

        if results_df.empty:
            return []

        # Apply filters
        if zone:
            results_df = results_df[results_df["zone"] == zone]
        if folder:
            results_df = results_df[results_df["folder"] == folder]

        # Deduplicate: keep best-scoring chunk per note
        seen_notes: dict[str, int] = {}  # note_name -> index in results
        results: list[SemanticResult] = []

        for _, row in results_df.iterrows():
            note_name = row["note_name"]
            if note_name in seen_notes:
                continue

            seen_notes[note_name] = len(results)

            # LanceDB returns _distance (L2) — for normalized vectors,
            # cosine similarity = 1 - (distance^2 / 2)
            distance = row.get("_distance", 0.0)
            score = round(1.0 - (distance / 2.0), 4)

            # Extract snippet from the chunk text
            text = row.get("text", "")
            # Remove note name prefix if present
            if text.startswith(note_name):
                text = text[len(note_name):].strip()
            snippet = text[:300]

            results.append(SemanticResult(
                name=note_name,
                path=row["note_path"],
                zone=row["zone"],
                folder=row["folder"],
                score=score,
                snippet=snippet,
                word_count=int(row.get("word_count", 0)),
                chunk_index=int(row.get("chunk_index", 0)),
                total_chunks=int(row.get("total_chunks", 1)),
            ))

            if len(results) >= limit:
                break

        return results


# ── CLI test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent))
    from atlas import get_atlas

    engine = EmbeddingEngine()

    if "--build" in sys.argv:
        notes = get_atlas()
        stats = engine.build(notes)
        print(f"\nBuild complete: {stats}")
    elif "--incremental" in sys.argv:
        notes = get_atlas()
        stats = engine.incremental_build(notes)
        print(f"\nIncremental build: {stats}")
    elif "--search" in sys.argv:
        query = " ".join(
            a for a in sys.argv[1:] if a != "--search"
        ) or "feeling stuck in life"
        print(f"Semantic search: '{query}'\n")

        results = engine.search(query, limit=5)
        for r in results:
            print(f"  [{r.score:.4f}]  {r.name}")
            print(f"           {r.zone}/{r.folder} ({r.word_count}w, chunk {r.chunk_index+1}/{r.total_chunks})")
            snip = r.snippet[:120] + "..." if len(r.snippet) > 120 else r.snippet
            print(f"           {snip}")
            print()
    else:
        print("Usage: python embeddings.py --build  |  python embeddings.py --search <query>")
