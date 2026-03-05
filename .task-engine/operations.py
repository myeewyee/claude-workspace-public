"""Core task operations: create, start, complete, pause, log, read, update."""

from datetime import datetime
from pathlib import Path

import frontmatter as fm_lib

from fileops import (
    acquire_lock,
    atomic_write,
    find_task_file,
    get_task_by_status,
    list_task_files,
    patch_frontmatter_field,
    read_task_file,
    safe_move,
    write_task_file,
)
from progress_log import add_entry as add_progress_entry
from progress_log import format_status_change, get_last_progress_time, get_timestamp
from schema import (
    PRIORITY_SORT_ORDER,
    TERMINAL_STATUSES,
    default_frontmatter,
    render_frontmatter,
    validate_field_value,
    validate_frontmatter,
    validate_transition,
)
# Default workspace path
DEFAULT_WORKSPACE = Path(r"<your-workspace-path>")


def to_filename(name: str) -> str:
    """Sanitize a task name for use as a filename. Replaces path-unsafe chars with '-'."""
    unsafe = r"/\:*?\"<>|"
    result = name
    for ch in unsafe:
        result = result.replace(ch, "-")
    return result

# Task file template body (without frontmatter)
TASK_TEMPLATE = """# {title}
## Context
## Links
### Related
### Subtasks
```base
filters:
  and:
    - type == "task"
    - parent == "[[{title}]]"
properties:
  file.name:
    displayName: Subtask
  status:
    displayName: Status
  description:
    displayName: Description
views:
  - type: table
    name: Subtasks
    order:
      - file.mtime
      - status
      - file.name
    sort:
      - property: file.mtime
        direction: DESC
    indentProperties: false
    markers: none
    columnSize:
      file.mtime: 175

```
### Outputs
```base
filters:
  and:
    - type == "artifact"
    - parent == "[[{title}]]"
properties:
  file.name:
    displayName: Output
  description:
    displayName: Description
  created:
    displayName: Created
views:
  - type: table
    name: Outputs
    order:
      - file.mtime
      - file.name
    sort:
      - property: file.mtime
        direction: DESC
      - property: created
        direction: ASC
    indentProperties: false
    markers: none
    columnSize:
      file.mtime: 175

```
## Success Criteria
## Approach
## Work Done
## Progress Log
{date_heading}
{timestamp} {status_entry}
"""


def _result(action: str, ok: bool, message: str = "", error: str = "",
            task: dict = None, warnings: list = None, **extra) -> dict:
    """Build a standard result envelope."""
    r = {"ok": ok, "action": action}
    if ok:
        r["message"] = message
    else:
        r["error"] = error
    if task:
        r["task"] = task
    r["warnings"] = warnings or []
    r.update(extra)
    return r


def create_task(
    workspace: Path,
    name: str,
    description: str = "",
    status: str = "3-idea",
    parent: str = "",
    cadence: str = "",
    focus: str = "",
    category: str = "",
    pillar: str = "",
    session: str = None,
) -> dict:
    """Create a new task file."""
    # Determine target folder
    if status == "3-idea":
        target_dir = workspace / "tasks" / "ideas"
    else:
        target_dir = workspace / "tasks"

    target_path = target_dir / f"{to_filename(name)}.md"

    if target_path.exists():
        return _result("create", False, error=f"Task file already exists: {target_path.relative_to(workspace)}")

    # Build frontmatter
    fm = default_frontmatter(name, description, status=status, parent=parent, cadence=cadence, focus=focus, category=category, pillar=pillar)
    errors = validate_frontmatter(fm)
    if errors:
        return _result("create", False, error=f"Validation errors: {'; '.join(errors)}")

    # Generate timestamps
    now = datetime.now()
    date_heading = now.strftime("### %Y-%m-%d")
    timestamp = _format_12h(now)
    status_display = status.replace("-", " ").title()
    status_entry = f"*Status \u2192 {status_display} (task created)*"
    if session:
        status_entry += f" <!-- session: {session} -->"

    # Build file content
    fm_str = render_frontmatter(fm)
    body = TASK_TEMPLATE.format(
        title=name,
        description=description or "[Description]",
        date_heading=date_heading,
        timestamp=timestamp,
        status_entry=status_entry,
    )

    # Lock and write file
    lock = acquire_lock(workspace)
    try:
        with lock:
            target_dir.mkdir(parents=True, exist_ok=True)
            write_task_file(target_path, fm_str, body)
    except Exception as e:
        return _result("create", False, error=str(e))

    return _result("create", True,
                    message=f"Task created: {name}",
                    task={"name": name, "status": status, "path": str(target_path.relative_to(workspace))})


def start_task(workspace: Path, task_name: str = None) -> dict:
    """Start a task (set status to 1-active)."""
    # Resolve task
    if task_name:
        path = find_task_file(workspace, task_name)
        if not path:
            return _result("start", False, error=f"Task not found: {task_name}")
    else:
        # Find first paused task
        paused = get_task_by_status(workspace, "2-paused")
        if not paused:
            return _result("start", False, error="No paused tasks to start")
        path, _ = paused[0]

    fm, body = read_task_file(path)
    current_status = fm.get("status", "3-idea")
    name = path.stem

    # Validate transition
    valid, reason = validate_transition(current_status, "1-active")
    if not valid:
        return _result("start", False, error=f"Cannot start '{name}': {reason}")

    # Add progress log entry
    timestamp = _format_12h(datetime.now())
    body = add_progress_entry(body, format_status_change("1-active"), timestamp)

    # Update frontmatter
    fm["status"] = "1-active"

    # Clear paused priority values when resuming (next/someday/blocked don't apply to active tasks)
    from schema import VALID_PRIORITY_PAUSED
    if fm.get("priority") in VALID_PRIORITY_PAUSED:
        fm["priority"] = ""

    # If idea, move file from ideas/ to tasks/
    is_idea = current_status == "3-idea"
    new_path = workspace / "tasks" / f"{name}.md" if is_idea else path

    lock = acquire_lock(workspace)
    warnings = []
    try:
        with lock:
            # Write updated content
            fm_str = render_frontmatter(fm)
            if is_idea:
                write_task_file(new_path, fm_str, body)
                if path.exists() and path != new_path:
                    path.unlink()
            else:
                write_task_file(path, fm_str, body)
    except Exception as e:
        return _result("start", False, error=str(e))

    return _result("start", True,
                    message=f"Task started: {name}",
                    task={"name": name, "status": "1-active", "path": str(new_path.relative_to(workspace))})


def complete_task(workspace: Path, task_name: str = None) -> dict:
    """Complete a task (set status to 5-done, move to archive)."""
    # Resolve task
    if task_name:
        path = find_task_file(workspace, task_name)
        if not path:
            return _result("complete", False, error=f"Task not found: {task_name}")
    else:
        in_progress = get_task_by_status(workspace, "1-active")
        if not in_progress:
            return _result("complete", False, error="No active tasks to complete")
        if len(in_progress) > 1:
            names = [p.stem for p, _ in in_progress]
            return _result("complete", False,
                           error=f"Multiple active tasks. Specify one: {names}")
        path, _ = in_progress[0]

    fm, body = read_task_file(path)
    current_status = fm.get("status", "3-idea")
    name = path.stem

    # Validate transition
    valid, reason = validate_transition(current_status, "5-done")
    if not valid:
        return _result("complete", False, error=f"Cannot complete '{name}': {reason}")

    # Update frontmatter
    now = datetime.now()
    fm["status"] = "5-done"
    fm["completed"] = now.strftime("%Y-%m-%d %H:%M")

    # Add progress log entry
    timestamp = _format_12h(now)
    body = add_progress_entry(body, format_status_change("5-done"), timestamp)

    # Check for active children (warn but allow)
    active_children = []
    for child_path in list_task_files(workspace):
        try:
            child_fm, _ = read_task_file(child_path)
            if _match_parent(child_fm.get("parent"), name):
                child_status = child_fm.get("status", "3-idea")
                if child_status not in TERMINAL_STATUSES:
                    active_children.append(f"{child_path.stem} ({child_status})")
        except Exception:
            continue

    # Archive paths
    archive_path = workspace / "tasks" / "archive" / f"{name}.md"

    # Find and archive output files by scanning for matching parent: field
    moved_outputs = []
    output_warnings = []

    lock = acquire_lock(workspace)
    try:
        with lock:
            # Write updated task to archive
            fm_str = render_frontmatter(fm)
            write_task_file(archive_path, fm_str, body)

            # Remove original
            if path.exists() and path != archive_path:
                path.unlink()

            # Archive output files with matching parent
            for output_dir in [workspace / "outputs", workspace / "outputs" / "temp"]:
                for out_path in _scan_md_files(output_dir):
                    try:
                        out_fm, _ = read_task_file(out_path)
                        if _match_parent(out_fm.get("parent"), name):
                            out_archive = workspace / "outputs" / "archive" / out_path.name
                            safe_move(out_path, out_archive)
                            moved_outputs.append(out_path.stem)
                    except Exception as e:
                        output_warnings.append(f"Failed to archive output '{out_path.stem}': {e}")
    except Exception as e:
        return _result("complete", False, error=str(e))

    # Combine warnings
    all_warnings = output_warnings
    if active_children:
        all_warnings.insert(0, f"Active children: {', '.join(active_children)}")

    return _result("complete", True,
                    message=f"Task complete: {name}",
                    task={"name": name, "status": "5-done", "path": str(archive_path.relative_to(workspace))},
                    warnings=all_warnings,
                    moved_outputs=moved_outputs,
                    active_children=active_children)


def pause_task(workspace: Path, task_name: str = None, priority: str = "") -> dict:
    """Pause a task (set status to 2-paused). Optional priority: 1-next/2-blocked/3-later/4-someday."""
    from schema import VALID_PRIORITY_PAUSED

    # Validate priority value if provided
    if priority and priority not in VALID_PRIORITY_PAUSED:
        return _result("pause", False,
                        error=f"Invalid pause priority '{priority}'. Valid: {sorted(VALID_PRIORITY_PAUSED)}")

    # Resolve task
    if task_name:
        path = find_task_file(workspace, task_name)
        if not path:
            return _result("pause", False, error=f"Task not found: {task_name}")
    else:
        in_progress = get_task_by_status(workspace, "1-active")
        if not in_progress:
            return _result("pause", False, error="No active tasks to pause")
        if len(in_progress) > 1:
            names = [p.stem for p, _ in in_progress]
            return _result("pause", False,
                           error=f"Multiple active tasks. Specify one: {names}")
        path, _ = in_progress[0]

    fm, body = read_task_file(path)
    current_status = fm.get("status", "3-idea")
    name = path.stem

    # Validate transition
    valid, reason = validate_transition(current_status, "2-paused")
    if not valid:
        return _result("pause", False, error=f"Cannot pause '{name}': {reason}")

    # Update
    fm["status"] = "2-paused"
    if priority:
        fm["priority"] = priority
    timestamp = _format_12h(datetime.now())
    body = add_progress_entry(body, format_status_change("2-paused"), timestamp)

    lock = acquire_lock(workspace)
    warnings = []
    try:
        with lock:
            fm_str = render_frontmatter(fm)
            write_task_file(path, fm_str, body)
    except Exception as e:
        return _result("pause", False, error=str(e))

    return _result("pause", True,
                    message=f"Task paused: {name}",
                    task={"name": name, "status": "2-paused", "priority": priority,
                          "path": str(path.relative_to(workspace))})


def cancel_task(workspace: Path, task_name: str = None, reason: str = "") -> dict:
    """Cancel a task (set status to 6-cancelled, move to archive)."""
    # Resolve task
    if task_name:
        path = find_task_file(workspace, task_name)
        if not path:
            return _result("cancel", False, error=f"Task not found: {task_name}")
    else:
        in_progress = get_task_by_status(workspace, "1-active")
        if not in_progress:
            return _result("cancel", False, error="No active tasks to cancel")
        if len(in_progress) > 1:
            names = [p.stem for p, _ in in_progress]
            return _result("cancel", False,
                           error=f"Multiple active tasks. Specify one: {names}")
        path, _ = in_progress[0]

    fm, body = read_task_file(path)
    current_status = fm.get("status", "3-idea")
    name = path.stem

    # Validate transition
    valid, reason_msg = validate_transition(current_status, "6-cancelled")
    if not valid:
        return _result("cancel", False, error=f"Cannot cancel '{name}': {reason_msg}")

    # Update
    now = datetime.now()
    fm["status"] = "6-cancelled"
    fm["completed"] = now.strftime("%Y-%m-%d %H:%M")
    timestamp = _format_12h(now)
    body = add_progress_entry(body, format_status_change("6-cancelled", reason), timestamp)

    archive_path = workspace / "tasks" / "archive" / f"{name}.md"

    lock = acquire_lock(workspace)
    warnings = []
    try:
        with lock:
            fm_str = render_frontmatter(fm)
            write_task_file(archive_path, fm_str, body)
            if path.exists() and path != archive_path:
                path.unlink()
    except Exception as e:
        return _result("cancel", False, error=str(e))

    return _result("cancel", True,
                    message=f"Task cancelled: {name}",
                    task={"name": name, "status": "6-cancelled", "path": str(archive_path.relative_to(workspace))})


def reopen_task(workspace: Path, task_name: str) -> dict:
    """Reopen a done or cancelled task (move from archive back to active)."""
    if not task_name:
        return _result("reopen", False, error="Task name is required for reopen")

    # Find the task file
    path = find_task_file(workspace, task_name)
    if not path:
        return _result("reopen", False, error=f"Task not found: {task_name}")

    # Verify it's in the archive directory
    archive_dir = workspace / "tasks" / "archive"
    try:
        path.relative_to(archive_dir)
    except ValueError:
        return _result("reopen", False,
                        error=f"Task '{path.stem}' is not archived (status: {_get_status(path)}). Use 'start' for active tasks.")

    fm, body = read_task_file(path)
    current_status = fm.get("status", "unknown")
    name = path.stem

    # Validate it's in a terminal status
    if current_status not in TERMINAL_STATUSES:
        return _result("reopen", False,
                        error=f"Task '{name}' has status '{current_status}', expected 5-done or 6-cancelled")

    # Update frontmatter
    fm["status"] = "1-active"
    fm["completed"] = ""

    # Add progress log entry
    timestamp = _format_12h(datetime.now())
    body = add_progress_entry(body, format_status_change("1-active", "reopened"), timestamp)

    # Move from archive to tasks/
    new_path = workspace / "tasks" / f"{name}.md"

    lock = acquire_lock(workspace)
    try:
        with lock:
            fm_str = render_frontmatter(fm)
            write_task_file(new_path, fm_str, body)
            if path.exists() and path != new_path:
                path.unlink()
    except Exception as e:
        return _result("reopen", False, error=str(e))

    return _result("reopen", True,
                    message=f"Task reopened: {name}",
                    task={"name": name, "status": "1-active",
                          "path": str(new_path.relative_to(workspace)),
                          "previous_status": current_status})


def _get_status(path: Path) -> str:
    """Quick status read for error messages."""
    try:
        fm, _ = read_task_file(path)
        return fm.get("status", "unknown")
    except Exception:
        return "unknown"


def log_entry(workspace: Path, task_name: str = None, entry: str = "", session: str = None) -> dict:
    """Add a timestamped entry to a task's progress log."""
    if not entry:
        return _result("log", False, error="No entry text provided")

    # Resolve task
    if task_name:
        path = find_task_file(workspace, task_name)
        if not path:
            return _result("log", False, error=f"Task not found: {task_name}")
    else:
        in_progress = get_task_by_status(workspace, "1-active")
        if not in_progress:
            return _result("log", False, error="No active tasks to log to")
        if len(in_progress) > 1:
            names = [p.stem for p, _ in in_progress]
            return _result("log", False,
                           error=f"Multiple active tasks. Specify one: {names}")
        path, _ = in_progress[0]

    fm, body = read_task_file(path)
    name = path.stem
    timestamp = _format_12h(datetime.now())

    # Append session ID comment to the first line of the entry
    entry = entry.strip()
    if session:
        lines = entry.split('\n')
        lines[0] = lines[0].rstrip() + f" <!-- session: {session} -->"
        entry = '\n'.join(lines)

    # Add entry to progress log
    body = add_progress_entry(body, entry, timestamp)

    # Write back
    lock = acquire_lock(workspace)
    try:
        with lock:
            fm_str = render_frontmatter(fm)
            write_task_file(path, fm_str, body)
    except Exception as e:
        return _result("log", False, error=str(e))

    return _result("log", True,
                    message=f"Logged to: {name}",
                    task={"name": name, "path": str(path.relative_to(workspace))})


def read_task(workspace: Path, task_name: str = None) -> dict:
    """Read task info. With name: single task detail. Without: overview of all."""
    if task_name:
        path = find_task_file(workspace, task_name)
        if not path:
            return _result("read", False, error=f"Task not found: {task_name}")

        fm, body = read_task_file(path)
        return _result("read", True,
                        message=f"Task: {path.stem}",
                        task={
                            "name": path.stem,
                            "status": fm.get("status", "unknown"),
                            "path": str(path.relative_to(workspace)),
                            "frontmatter": fm,
                        })
    else:
        # Overview: scan all active task files
        overview = {
            "active": [],
            "paused": [],
            "recurring": [],
            "ideas": [],
        }
        # Map prefixed status values to group keys
        STATUS_TO_GROUP = {
            "1-active": "active",
            "2-paused": "paused",
            "3-idea": "ideas",
            "4-recurring": "recurring",
        }
        for path in list_task_files(workspace):
            try:
                fm, _ = read_task_file(path)
                status = fm.get("status", "3-idea")
                entry = {"name": path.stem, "status": status, "description": fm.get("description", "")}
                group = STATUS_TO_GROUP.get(status)
                if group:
                    overview[group].append(entry)
            except Exception:
                continue

        total = sum(len(v) for v in overview.values())
        return _result("read", True,
                        message=f"{total} active tasks",
                        overview=overview)


def update_field(workspace: Path, task_name: str, field: str, value: str) -> dict:
    """Update a single frontmatter field on a task."""
    if not task_name:
        return _result("update", False, error="task_name is required for update")
    if not field:
        return _result("update", False, error="field is required for update")

    path = find_task_file(workspace, task_name)
    if not path:
        return _result("update", False, error=f"Task not found: {task_name}")

    # Validate field and value
    valid, reason = validate_field_value(field, value)
    if not valid:
        return _result("update", False, error=f"Invalid value for '{field}': {reason}")

    # Special handling for status changes (should use start/complete/pause instead)
    if field == "status":
        fm, _ = read_task_file(path)
        current = fm.get("status", "3-idea")
        valid, reason = validate_transition(current, value)
        if not valid:
            return _result("update", False, error=f"Invalid status transition: {reason}")

    name = path.stem

    lock = acquire_lock(workspace)
    try:
        with lock:
            new_content = patch_frontmatter_field(path, field, value)
            atomic_write(path, new_content)
    except Exception as e:
        return _result("update", False, error=str(e))

    return _result("update", True,
                    message=f"Updated {name}: {field}",
                    task={"name": name, "field": field, "value": value,
                          "path": str(path.relative_to(workspace))})



def _match_parent(parent_field, target_name: str) -> bool:
    """Check if a frontmatter parent field matches a target task name."""
    if not parent_field:
        return False
    target_lower = target_name.lower()
    values = parent_field if isinstance(parent_field, list) else [parent_field]
    for val in values:
        val_str = str(val).strip().strip('"').strip("'")
        if val_str.startswith("[[") and val_str.endswith("]]"):
            val_str = val_str[2:-2]
        if val_str.lower() == target_lower:
            return True
    return False


def _scan_md_files(directory: Path) -> list[Path]:
    """List .md files in a directory (non-recursive)."""
    if not directory.exists():
        return []
    return sorted(f for f in directory.iterdir() if f.suffix == ".md" and f.is_file())


def _list_children(workspace: Path, parent_name: str) -> dict:
    """List all children (subtasks and outputs) of a parent task."""
    subtasks = []
    outputs = []

    # Scan tasks (active + archived)
    for path in list_task_files(workspace, include_archive=True):
        try:
            fm, _ = read_task_file(path)
            if _match_parent(fm.get("parent"), parent_name):
                subtasks.append({
                    "name": path.stem,
                    "status": fm.get("status", "unknown"),
                    "description": fm.get("description", ""),
                    "created": str(fm.get("created", "")),
                })
        except Exception:
            continue

    # Scan outputs (active, temp, archived)
    output_dirs = [
        workspace / "outputs",
        workspace / "outputs" / "temp",
        workspace / "outputs" / "archive",
    ]
    for output_dir in output_dirs:
        for path in _scan_md_files(output_dir):
            try:
                fm, _ = read_task_file(path)
                if _match_parent(fm.get("parent"), parent_name):
                    outputs.append({
                        "name": path.stem,
                        "description": fm.get("description", ""),
                        "created": str(fm.get("created", "")),
                    })
            except Exception:
                continue

    total = len(subtasks) + len(outputs)
    return _result("list", True,
                    message=f"{total} children of '{parent_name}'",
                    children={"subtasks": subtasks, "outputs": outputs},
                    counts={"subtasks": len(subtasks), "outputs": len(outputs)})


def list_tasks(workspace: Path, parent: str = None, focus: str = None, category: str = None, pillar: str = None) -> dict:
    """List all active tasks grouped by status. Scans task files on demand.

    When parent is specified, returns children (subtasks + outputs) of that task instead.

    Each entry includes enriched metadata from frontmatter and progress log
    to enable triage without reading individual task files.

    Optional filters:
        focus: filter to tasks matching this focus value (internal/external)
        category: filter to tasks matching this category value
        pillar: filter to tasks matching this pillar value (memory/workflow/self-improve)
    """
    if parent:
        return _list_children(workspace, parent)

    groups = {
        "active": [],
        "paused": [],
        "recurring": [],
        "ideas": [],
    }
    # Map prefixed status values to group keys
    STATUS_TO_GROUP = {
        "1-active": "active",
        "2-paused": "paused",
        "3-idea": "ideas",
        "4-recurring": "recurring",
    }
    for path in list_task_files(workspace):
        try:
            fm, body = read_task_file(path)
            status = fm.get("status", "3-idea")

            # Apply filters
            if focus and fm.get("focus", "") != focus:
                continue
            if category and fm.get("category", "") != category:
                continue
            if pillar and fm.get("pillar", "") != pillar:
                continue

            # Build enriched entry
            entry = {
                "name": path.stem,
                "description": fm.get("description", ""),
                "created": str(fm.get("created", "")),
                "parent": fm.get("parent", ""),
                "focus": fm.get("focus", ""),
                "category": fm.get("category", ""),
                "pillar": fm.get("pillar", ""),
                "priority": fm.get("priority", ""),
                "cadence": fm.get("cadence", ""),
                "last_run": str(fm.get("last-run", "")),
                "last_progress_entry": get_last_progress_time(body),
            }

            group = STATUS_TO_GROUP.get(status)
            if group:
                groups[group].append(entry)
        except Exception:
            continue

    # Sort each group by priority (tasks with priority first, sorted by rank; then no-priority)
    for key in groups:
        groups[key].sort(key=lambda e: (
            PRIORITY_SORT_ORDER.get(e.get("priority", ""), 99),
            e.get("name", ""),
        ))

    counts = {k: len(v) for k, v in groups.items()}
    total = sum(counts.values())
    return _result("list", True,
                    message=f"{total} active tasks",
                    tasks=groups, counts=counts)


def _format_12h(dt: datetime) -> str:
    """Format datetime as 12-hour time for progress logs."""
    import platform
    if platform.system() == "Windows":
        return dt.strftime("%#I:%M %p")
    else:
        return dt.strftime("%-I:%M %p")
