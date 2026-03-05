# Task Engine

Deterministic Python CLI for task management operations. Replaces manual LLM-generated file edits with validated, atomic operations over markdown task files with YAML frontmatter.

## Architecture

```
.task-engine/
  task.py           # CLI entry point (argparse dispatch, JSON output)
  schema.py         # Frontmatter schema, validation, status transitions
  operations.py     # Core operations (create, start, complete, pause, reopen, log, read, list, update, cancel)
  tasks_md.py       # TASKS.md export (on-demand snapshot only, not used in normal operations)
  progress_log.py   # Progress log entry insertion with real timestamps
  fileops.py        # Atomic writes, file moves, locking
  audit.py          # Audit checks (output orphans)
  requirements.txt  # python-frontmatter, filelock
```

## Usage

All commands output structured JSON with `ok`, `action`, `message`/`error`, and `warnings` fields.

```bash
# Create a task (--session embeds birth session in creation log entry)
python .task-engine/task.py create --name "Task name" --description "What and why" --parent '[[$AI 🤖]]' --session "UUID"

# Create a recurring task
python .task-engine/task.py create --name "Run something" --description "What and why" --status 4-recurring --cadence weekly --parent '[[$AI 🤖]]'

# Start (default: first paused)
python .task-engine/task.py start --task "Task name"

# Log progress (multi-line via heredoc, --session appends session ID comment)
python .task-engine/task.py log --task "Task name" --session "UUID" <<'EOF'
**What changed**
- Detail with 'apostrophes' and $variables safe
EOF

# Complete (moves to archive)
python .task-engine/task.py complete --task "Task name"

# Cancel
python .task-engine/task.py cancel --task "Task name" --reason "Superseded"

# Pause (with optional priority: 1-next, 2-blocked, 3-later, 4-someday)
python .task-engine/task.py pause --task "Task name" --priority "1-next"

# Reopen (move from archive back to active, set 1-active)
python .task-engine/task.py reopen --task "Task name"

# Read single task detail
python .task-engine/task.py read --task "Task name"

# List all active tasks grouped by status (enriched metadata per entry)
# Returns: name, description, created, parent, priority, cadence, last_run, last_progress_entry
# Each group sorted by priority (1-high/1-next first, then 2-medium/2-blocked, then 3-low/3-later, then 4-someday, then unset)
python .task-engine/task.py list

# List children (subtasks + outputs) of a parent task
python .task-engine/task.py list --parent "Parent task name"

# Update a frontmatter field
python .task-engine/task.py update --task "Task name" --field "field" --value "value"

# Run audit (output orphan check)
python .task-engine/task.py audit

# Export TASKS.md snapshot from task files (on-demand)
python .task-engine/task.py audit --regenerate
```

## Key Design Decisions

- **python-frontmatter for reading, manual string construction for writing.** PyYAML roundtrip breaks key order, quoting, and empty field formatting. The script uses `frontmatter.load()` for parsing and `schema.render_frontmatter()` for serialized output.
- **Heredoc + stdin for multi-line content.** Single-quoted `<<'EOF'` prevents all Bash interpretation. Eliminates string escaping bugs for markdown content with apostrophes, bold, backticks, etc.
- **File locking via `filelock` library.** Single lock file (`.task-engine.lock`) in workspace root. Coarse lock on any write operation. 10-second timeout with structured error.
- **Atomic writes.** Write to `.tmp`, then `Path.replace()`. No partial file writes.
- **No TASKS.md sync.** Task files are the sole source of truth. `task.py list` scans files on demand. `audit --regenerate` can export a TASKS.md snapshot if needed.

## Status Transitions

```
3-idea -> 1-active, 2-paused, 6-cancelled
1-active -> 5-done, 2-paused, 6-cancelled
2-paused -> 1-active, 6-cancelled
5-done -> 1-active (via reopen only)
6-cancelled -> 1-active (via reopen only)
```

## JSON Output

Success:
```json
{
  "ok": true,
  "action": "create",
  "message": "Task created: Build new feature",
  "task": { "name": "...", "status": "...", "path": "..." },
  "warnings": []
}
```

Error:
```json
{
  "ok": false,
  "action": "create",
  "error": "Task file already exists",
  "warnings": []
}
```

## Dependencies

- `python-frontmatter>=1.1.0`
- `filelock>=3.0`
- Python 3.14.3

## Related

- Parent task: [[Develop agent-friendly task management system]]
- Research: [[Agent-friendly task management format research]]
- Decision context: Codex reviewer synthesis in parent task file (script-first, MCP conditional)
