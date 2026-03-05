"""
Atlas: Vault scanner and metadata extraction.

Scans every .md file in the Obsidian vault, extracts frontmatter,
wiki-links, and classifies each note by zone, topic, and type.
This is the foundation module — every other module depends on it.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import frontmatter

# ── Constants ──────────────────────────────────────────────────────────

VAULT_ROOT = Path(r"<your-vault-path>")
DATA_DIR = Path(__file__).parent.parent / "data"
ATLAS_CACHE = DATA_DIR / "atlas.json"
ATLAS_MAX_AGE_HOURS = 24

# Directories to skip entirely during scanning
SKIP_DIRS = {
    ".obsidian", ".trash", ".git", ".claude", ".scripts",
    ".vscode", ".mcp-server", "node_modules",
}

# ── Content classification (ported from vault-indexer.ps1) ─────────

# Folders whose contents are definitely "content" (external sources)
CONTENT_FOLDER_PREFIXES = ("Clippings", "2. Reference")
CONTENT_SUBFOLDERS = ("books-temp",)

# Frontmatter fields that indicate content notes
CONTENT_FM_FIELDS = {"source", "author"}
CONTENT_FM_TYPE_VALUES = {"content"}

# URL patterns that suggest content (consumed media)
CONTENT_URL_PATTERN = re.compile(
    r"https?://(www\.)?(youtube|youtu\.be|medium|substack|twitter|x\.com)",
    re.IGNORECASE,
)

# ── Wiki-link extraction ───────────────────────────────────────────

# Matches [[Target]] or [[Target|Display Text]]
# Excludes image embeds ![[...]]
WIKILINK_PATTERN = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#[^\]|]*)?\s*(?:\|[^\]]+)?\]\]")


# ── Data classes ───────────────────────────────────────────────────

@dataclass
class NoteMetadata:
    name: str                        # Filename without extension
    path: str                        # Relative path from vault root
    full_path: str                   # Absolute path on disk
    zone: str                        # "vault" or "claude"
    folder: str                      # Top-level folder
    topic_folder: Optional[str]      # $-prefixed topic folder, if any
    frontmatter: dict                # Parsed YAML frontmatter
    created: Optional[str]           # ISO date string from frontmatter or filesystem
    modified: str                    # ISO date string from filesystem mtime
    size: int                        # File size in bytes
    outlinks: list[str] = field(default_factory=list)   # Wiki-link targets
    is_moc: bool = False             # Is this a Map of Content hub?
    is_content: bool = False         # Is this external content (not user-authored)?
    is_journal: bool = False         # Is this a journal/review entry?
    word_count: int = 0              # Approximate word count
    content: str = ""                # Full text content (frontmatter stripped)


def _classify_zone(rel_path: str) -> str:
    """Determine which zone a file belongs to."""
    # CONFIGURE: change "1. Vault" to your vault content folder name
    if rel_path.startswith("1. Vault"):
        return "vault"
    # CONFIGURE: change "2. Claude" to your workspace folder name
    if rel_path.startswith("2. Claude"):
        return "claude"
    # Files at vault root or in other folders
    return "vault"


def _extract_topic_folder(rel_path: str) -> Optional[str]:
    """Extract $-prefixed topic folder from path, if present."""
    parts = Path(rel_path).parts
    for part in parts:
        if part.startswith("$"):
            return part
    return None


def _is_moc(name: str, rel_path: str) -> bool:
    """Detect Map of Content hub notes."""
    if "0. Topics-MOCs" in rel_path:
        return True
    if name.startswith("$"):
        return True
    return False


def _is_content_note(rel_path: str, folder: str, fm: dict, text: str) -> bool:
    """
    Classify whether a note is 'content' (external sources like books,
    articles, videos) vs. user-authored notes.
    Ported from vault-indexer.ps1 logic.
    """
    # Definite content folders
    for prefix in CONTENT_FOLDER_PREFIXES:
        if folder.startswith(prefix):
            return True

    # Content subfolders anywhere in path
    for subfolder in CONTENT_SUBFOLDERS:
        if subfolder in rel_path:
            return True

    # Frontmatter signals
    for key in CONTENT_FM_FIELDS:
        if key in fm and fm[key]:
            return True
    fm_type = str(fm.get("type", "")).lower().strip("'\"")
    if fm_type in CONTENT_FM_TYPE_VALUES:
        return True

    # URL patterns in first ~500 chars
    if CONTENT_URL_PATTERN.search(text[:500]):
        return True

    return False


def _is_journal(name: str, rel_path: str) -> bool:
    """Detect journal and review entries."""
    if "$Journal" in rel_path or "Reflection & Reviews" in rel_path:
        return True
    # Date-prefixed names like "2026-01 Journal" or "Daily Journal 2026 01"
    if re.match(r"^\d{4}[-\s]\d{2}\b", name):
        return True
    if name.lower().startswith("daily journal"):
        return True
    return False


def _parse_created_date(fm: dict, file_path: Path) -> Optional[str]:
    """Extract created date from frontmatter, falling back to filesystem."""
    raw = fm.get("created")
    if raw:
        # Handle various formats: "2023-06-27", "2023-06-27 08:18:53", datetime objects
        if isinstance(raw, datetime):
            return raw.isoformat()
        s = str(raw).strip().strip("'\"")
        # Try parsing as date or datetime
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt).isoformat()
            except ValueError:
                continue
        # Return raw string if we can't parse it
        return s
    # Fallback to filesystem creation time
    try:
        ctime = file_path.stat().st_ctime
        return datetime.fromtimestamp(ctime).isoformat()
    except OSError:
        return None


def scan_note(file_path: Path, vault_root: Path) -> Optional[NoteMetadata]:
    """Scan a single .md file and extract all metadata."""
    try:
        rel_path = str(file_path.relative_to(vault_root))
        name = file_path.stem
        parts = Path(rel_path).parts
        # folder = second-level folder (inside the zone), e.g. "1. Projects & Areas"
        # If file is directly in zone root, folder = zone name
        folder = parts[1] if len(parts) > 2 else parts[0] if parts else ""

        # Read and parse file
        post = frontmatter.load(str(file_path), encoding="utf-8")
        fm = dict(post.metadata) if post.metadata else {}
        text = post.content  # Content without frontmatter

        # Extract wiki-links from full content
        outlinks = list(set(WIKILINK_PATTERN.findall(text)))

        # File stats
        stat = file_path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).isoformat()
        size = stat.st_size

        # Classifications
        zone = _classify_zone(rel_path)
        topic_folder = _extract_topic_folder(rel_path)
        is_moc = _is_moc(name, rel_path)
        is_content = _is_content_note(rel_path, folder, fm, text)
        is_journal = _is_journal(name, rel_path)

        # Word count (split on whitespace)
        word_count = len(text.split()) if text else 0

        return NoteMetadata(
            name=name,
            path=rel_path,
            full_path=str(file_path),
            zone=zone,
            folder=folder,
            topic_folder=topic_folder,
            frontmatter=fm,
            created=_parse_created_date(fm, file_path),
            modified=modified,
            size=size,
            outlinks=outlinks,
            is_moc=is_moc,
            is_content=is_content,
            is_journal=is_journal,
            word_count=word_count,
            content=text,
        )
    except Exception as e:
        # Log to stderr (MCP uses stdout for protocol)
        import sys
        print(f"[atlas] Error scanning {file_path}: {e}", file=sys.stderr)
        return None


def scan_vault(vault_root: Path = VAULT_ROOT) -> list[NoteMetadata]:
    """Scan the entire vault and return metadata for all .md files."""
    notes = []
    for root, dirs, files in os.walk(vault_root):
        # Skip excluded directories (modifies dirs in-place to prevent descent)
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for filename in files:
            if not filename.endswith(".md"):
                continue
            file_path = Path(root) / filename
            note = scan_note(file_path, vault_root)
            if note is not None:
                notes.append(note)

    return notes


# ── Caching ────────────────────────────────────────────────────────

def _note_to_dict(note: NoteMetadata) -> dict:
    """Convert NoteMetadata to a JSON-serializable dict."""
    d = asdict(note)
    # Frontmatter may contain date/datetime objects — convert them
    from datetime import date as date_type

    def _serialize(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date_type):
            return obj.isoformat()
        if isinstance(obj, (set, frozenset)):
            return list(obj)
        if isinstance(obj, list):
            return [_serialize(item) for item in obj]
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        return obj

    d["frontmatter"] = _serialize(d.get("frontmatter", {}))
    return d


def _dict_to_note(d: dict) -> NoteMetadata:
    """Reconstruct NoteMetadata from a dict (loaded from JSON cache)."""
    return NoteMetadata(**d)


def save_atlas(notes: list[NoteMetadata]) -> None:
    """Save atlas to JSON cache, including per-file mtimes for incremental updates."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Build mtime index: rel_path -> mtime (for incremental change detection)
    mtimes = {n.path: n.modified for n in notes}

    data = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "note_count": len(notes),
        "mtimes": mtimes,
        "notes": [_note_to_dict(n) for n in notes],
    }
    # Write atomically (write to temp, then rename)
    tmp = ATLAS_CACHE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(ATLAS_CACHE)


def _load_cache_raw() -> Optional[dict]:
    """Load raw cache data if it exists and is fresh."""
    if not ATLAS_CACHE.exists():
        return None

    try:
        with open(ATLAS_CACHE, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Check freshness
        generated = datetime.fromisoformat(data["generated"])
        now = datetime.now(timezone.utc)
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age_hours = (now - generated).total_seconds() / 3600
        if age_hours > ATLAS_MAX_AGE_HOURS:
            return None  # Stale cache

        return data
    except Exception:
        return None  # Corrupt cache


def load_atlas() -> Optional[list[NoteMetadata]]:
    """Load atlas from JSON cache if it exists and is fresh."""
    data = _load_cache_raw()
    if data is None:
        return None
    return [_dict_to_note(d) for d in data["notes"]]


def _collect_mtimes(vault_root: Path = VAULT_ROOT) -> dict[str, str]:
    """
    Fast walk: collect just file paths and mtimes (no content reading).
    Returns {rel_path: mtime_iso} for all .md files.
    """
    mtimes = {}
    for root, dirs, files in os.walk(vault_root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            if not filename.endswith(".md"):
                continue
            file_path = Path(root) / filename
            rel_path = str(file_path.relative_to(vault_root))
            try:
                mtime = datetime.fromtimestamp(file_path.stat().st_mtime).isoformat()
                mtimes[rel_path] = mtime
            except OSError:
                continue
    return mtimes


def incremental_update(vault_root: Path = VAULT_ROOT) -> tuple[list[NoteMetadata], dict]:
    """
    Incremental atlas update: compare current file mtimes with cached values.
    Only re-scans files that changed, were added, or were deleted.

    Returns:
        (updated_notes, stats) where stats has added/changed/deleted/unchanged counts.
    """
    import sys

    cache_data = _load_cache_raw()
    if cache_data is None:
        # No usable cache, fall back to full scan
        notes = scan_vault(vault_root)
        return notes, {"added": len(notes), "changed": 0, "deleted": 0, "unchanged": 0, "full_scan": True}

    cached_mtimes = cache_data.get("mtimes", {})
    cached_notes = {d["path"]: _dict_to_note(d) for d in cache_data["notes"]}

    # Collect current mtimes (fast, no content reading)
    current_mtimes = _collect_mtimes(vault_root)

    # Diff: find added, changed, deleted
    current_paths = set(current_mtimes.keys())
    cached_paths = set(cached_mtimes.keys())

    added_paths = current_paths - cached_paths
    deleted_paths = cached_paths - current_paths
    common_paths = current_paths & cached_paths
    changed_paths = {p for p in common_paths if current_mtimes[p] != cached_mtimes.get(p)}
    unchanged_paths = common_paths - changed_paths

    rescan_paths = added_paths | changed_paths

    if not rescan_paths and not deleted_paths:
        # Nothing changed, return cached atlas as-is
        notes = list(cached_notes.values())
        return notes, {"added": 0, "changed": 0, "deleted": 0, "unchanged": len(notes), "full_scan": False}

    # Start with unchanged notes from cache
    updated_notes = [cached_notes[p] for p in unchanged_paths if p in cached_notes]

    # Re-scan changed and new files
    for rel_path in rescan_paths:
        file_path = vault_root / rel_path
        if file_path.exists():
            note = scan_note(file_path, vault_root)
            if note is not None:
                updated_notes.append(note)

    stats = {
        "added": len(added_paths),
        "changed": len(changed_paths),
        "deleted": len(deleted_paths),
        "unchanged": len(unchanged_paths),
        "full_scan": False,
    }

    print(
        f"[atlas] Incremental: +{stats['added']} added, ~{stats['changed']} changed, "
        f"-{stats['deleted']} deleted, ={stats['unchanged']} unchanged",
        file=sys.stderr,
    )

    return updated_notes, stats


def get_atlas(force_rebuild: bool = False) -> list[NoteMetadata]:
    """
    Get the atlas, loading from cache if fresh or scanning if needed.
    This is the main entry point other modules should use.

    Uses incremental update when cache exists but force_rebuild is True:
    compares mtimes and only re-scans changed files.
    """
    if not force_rebuild:
        cached = load_atlas()
        if cached is not None:
            return cached

    # Try incremental update first (unless no cache at all)
    import sys
    start = time.time()

    notes, stats = incremental_update()
    elapsed = time.time() - start

    if stats.get("full_scan"):
        print(f"[atlas] Full scan: {len(notes)} notes in {elapsed:.1f}s", file=sys.stderr)
    else:
        print(f"[atlas] Incremental update in {elapsed:.1f}s", file=sys.stderr)

    save_atlas(notes)
    return notes


# ── CLI test ───────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    force = "--force" in sys.argv
    notes = get_atlas(force_rebuild=force)

    # Print summary
    zones = {}
    folders = {}
    moc_count = 0
    content_count = 0
    journal_count = 0
    total_links = 0

    for n in notes:
        zones[n.zone] = zones.get(n.zone, 0) + 1
        folders[n.folder] = folders.get(n.folder, 0) + 1
        if n.is_moc:
            moc_count += 1
        if n.is_content:
            content_count += 1
        if n.is_journal:
            journal_count += 1
        total_links += len(n.outlinks)

    print(f"\n=== Atlas Summary ===")
    print(f"Total notes: {len(notes)}")
    print(f"\nBy zone:")
    for z, c in sorted(zones.items()):
        print(f"  {z}: {c}")
    print(f"\nBy folder (top 10):")
    for f, c in sorted(folders.items(), key=lambda x: -x[1])[:10]:
        print(f"  {f}: {c}")
    print(f"\nClassification:")
    print(f"  MOC hubs: {moc_count}")
    print(f"  Content notes: {content_count}")
    print(f"  Journal entries: {journal_count}")
    print(f"  Total wiki-links: {total_links}")
    print(f"  Notes with links: {sum(1 for n in notes if n.outlinks)}")
