"""File operations: atomic writes, moves, locking, task file I/O."""

import re
import shutil
from pathlib import Path

import frontmatter
from filelock import FileLock, Timeout

# Lock file location (in workspace root, visible for debugging)
LOCK_FILENAME = ".task-engine.lock"
LOCK_TIMEOUT = 10  # seconds


def atomic_write(path: Path, content: str) -> None:
    """Write content to path atomically. Writes to .tmp then replaces."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp_path.write_text(content, encoding="utf-8")
        tmp_path.replace(path)
    except Exception:
        # Clean up tmp file on failure
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def safe_move(src: Path, dst: Path) -> None:
    """Move a file, creating destination directory if needed."""
    if not src.exists():
        raise FileNotFoundError(f"Source file not found: {src}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def acquire_lock(workspace: Path) -> FileLock:
    """Return a FileLock for the workspace. Caller must use as context manager.

    Usage:
        lock = acquire_lock(workspace)
        with lock:
            # do work under lock
    """
    lock_path = workspace / LOCK_FILENAME
    return FileLock(str(lock_path), timeout=LOCK_TIMEOUT)


def read_task_file(path: Path) -> tuple[dict, str]:
    """Read a task file. Returns (frontmatter_dict, body_content).

    Uses python-frontmatter for parsing (reliable reading).
    """
    if not path.exists():
        raise FileNotFoundError(f"Task file not found: {path}")
    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


def write_task_file(path: Path, fm_str: str, body: str) -> None:
    """Write a task file from pre-rendered frontmatter string and body.

    fm_str should include the --- delimiters (from schema.render_frontmatter).
    """
    content = fm_str + "\n" + body
    atomic_write(path, content)


def patch_frontmatter_field(path: Path, field: str, value) -> str:
    """Update a single frontmatter field in-place using regex.

    Preserves all other formatting. Returns the updated file content.
    For list fields (output), this replaces the entire field.
    """
    content = path.read_text(encoding="utf-8")

    # Split into frontmatter and body
    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"File does not have valid frontmatter: {path}")

    fm_text = parts[1]

    if isinstance(value, list):
        # Replace the entire field block (field: + indented list items)
        # First remove existing field and its list items
        pattern = rf"^{re.escape(field)}:.*(?:\n  - .*)*"
        if value:
            replacement = f"{field}:\n" + "\n".join(f'  - "{item}"' for item in value)
        else:
            replacement = f"{field}:"
        new_fm, count = re.subn(pattern, replacement, fm_text, count=1, flags=re.MULTILINE)
        if count == 0:
            # Field doesn't exist, append it
            new_fm = fm_text.rstrip() + "\n" + replacement + "\n"
    else:
        # Simple key: value replacement
        # Strip outer quotes if already present to avoid double-wrapping
        if isinstance(value, str):
            stripped = value.strip()
            if (stripped.startswith('"') and stripped.endswith('"')) or \
               (stripped.startswith("'") and stripped.endswith("'")):
                value = stripped[1:-1]

        if value is None or value == "":
            replacement = f"{field}:"
        elif isinstance(value, str) and ("[[" in value or ":" in value or len(value) > 80):
            replacement = f'{field}: "{value}"'
        else:
            replacement = f"{field}: {value}"

        pattern = rf"^{re.escape(field)}:.*$"
        new_fm, count = re.subn(pattern, replacement, fm_text, count=1, flags=re.MULTILINE)
        if count == 0:
            # Field doesn't exist, append it
            new_fm = fm_text.rstrip() + "\n" + replacement + "\n"

    new_content = "---" + new_fm + "---" + parts[2]
    return new_content


def find_task_file(workspace: Path, name: str) -> Path | None:
    """Search for a task file by name. Case-insensitive stem match.

    Searches tasks/, tasks/ideas/, then tasks/archive/.
    Returns the first match or None.
    """
    search_dirs = [
        workspace / "tasks",
        workspace / "tasks" / "ideas",
        workspace / "tasks" / "archive",
    ]
    name_lower = name.lower()

    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.suffix == ".md" and f.stem.lower() == name_lower:
                return f

    # Fuzzy fallback: check if name is contained in stem
    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.iterdir():
            if f.suffix == ".md" and name_lower in f.stem.lower():
                return f

    return None


def list_task_files(workspace: Path, include_archive: bool = False) -> list[Path]:
    """List all task .md files in tasks/ and tasks/ideas/.

    Optionally includes tasks/archive/.
    """
    files = []
    search_dirs = [
        workspace / "tasks",
        workspace / "tasks" / "ideas",
    ]
    if include_archive:
        search_dirs.append(workspace / "tasks" / "archive")

    for d in search_dirs:
        if not d.exists():
            continue
        for f in sorted(d.iterdir()):
            if f.suffix == ".md" and f.name != ".md":
                files.append(f)

    return files


def get_task_by_status(workspace: Path, status: str) -> list[tuple[Path, dict]]:
    """Find all task files with a given status. Returns list of (path, frontmatter)."""
    results = []
    for path in list_task_files(workspace):
        try:
            fm, _ = read_task_file(path)
            if fm.get("status") == status:
                results.append((path, fm))
        except Exception:
            continue
    return results
