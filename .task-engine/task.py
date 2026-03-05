#!/usr/bin/env python3
"""Task engine CLI: deterministic task management operations.

Usage:
    python task.py create --name "Task name" [--description "..."] [--status 3-idea] [--parent "..."] [--cadence "..."] [--focus "..."] [--category "..."] [--pillar "..."] [--session "UUID"]
    python task.py start [--task "Task name"]
    python task.py complete [--task "Task name"]
    python task.py pause [--task "Task name"] [--priority "1-next|2-blocked|3-later|4-someday"]
    python task.py cancel [--task "Task name"] [--reason "..."]
    python task.py reopen --task "Task name"
    python task.py log [--task "Task name"] [--session "UUID"] <<'EOF'
    Entry text from stdin
    EOF
    python task.py read [--task "Task name"]
    python task.py list [--parent "Parent task name"] [--focus "internal|external"] [--category "feature|bug|..."] [--pillar "memory|workflow|self-improve"]
    python task.py update --task "Task name" --field "field" --value "value"
    python task.py audit [--regenerate]
"""

import argparse
import json
import sys
from pathlib import Path

# Force UTF-8 stdin on Windows (default is CP1252, which corrupts → and other Unicode)
if hasattr(sys.stdin, 'reconfigure'):
    sys.stdin.reconfigure(encoding='utf-8')

# Add this directory to path for module imports
sys.path.insert(0, str(Path(__file__).parent))

from operations import (
    cancel_task,
    complete_task,
    create_task,
    list_tasks,
    log_entry,
    pause_task,
    read_task,
    reopen_task,
    start_task,
    update_field,
)

DEFAULT_WORKSPACE = Path(r"<your-workspace-path>")


def main():
    parser = argparse.ArgumentParser(description="Task engine CLI")
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE,
                        help="Workspace root directory")

    subparsers = parser.add_subparsers(dest="action", required=True)

    # create
    p_create = subparsers.add_parser("create", help="Create a new task")
    p_create.add_argument("--name", required=True, help="Task name")
    p_create.add_argument("--description", default="", help="Task description (or pass via stdin with --stdin)")
    p_create.add_argument("--status", default="3-idea", help="Initial status (default: 3-idea)")
    p_create.add_argument("--parent", default="", help="Parent wiki-link (MOC or task)")
    p_create.add_argument("--cadence", default="", help="Cadence for recurring tasks (daily, weekly, monthly, quarterly, on-demand)")
    p_create.add_argument("--focus", default="", help="Focus classification (internal, external)")
    p_create.add_argument("--category", default="", help="Work-type category (feature, bug, improvement, research, maintenance)")
    p_create.add_argument("--pillar", default="", help="Internal pillar (memory, workflow, self-improve). Only for internal tasks.")
    p_create.add_argument("--stdin", action="store_true", help="Read description from stdin")
    p_create.add_argument("--session", default=None, help="Session UUID to append as HTML comment to creation log entry")

    # start
    p_start = subparsers.add_parser("start", help="Start a task")
    p_start.add_argument("--task", default=None, help="Task name (default: first paused)")

    # complete
    p_complete = subparsers.add_parser("complete", help="Complete a task")
    p_complete.add_argument("--task", default=None, help="Task name (default: current active)")

    # pause
    p_pause = subparsers.add_parser("pause", help="Pause a task")
    p_pause.add_argument("--task", default=None, help="Task name (default: current active)")
    p_pause.add_argument("--priority", default="", help="Pause priority: 1-next, 2-blocked, 3-later, or 4-someday")

    # cancel
    p_cancel = subparsers.add_parser("cancel", help="Cancel a task")
    p_cancel.add_argument("--task", default=None, help="Task name (default: current active)")
    p_cancel.add_argument("--reason", default="", help="Cancellation reason")

    # reopen
    p_reopen = subparsers.add_parser("reopen", help="Reopen a done/cancelled task from archive")
    p_reopen.add_argument("--task", required=True, help="Task name (must be in archive)")

    # log
    p_log = subparsers.add_parser("log", help="Add progress log entry (entry via stdin)")
    p_log.add_argument("--task", default=None, help="Task name (default: current active)")
    p_log.add_argument("--session", default=None, help="Session UUID to append as HTML comment")

    # read
    p_read = subparsers.add_parser("read", help="Read task info")
    p_read.add_argument("--task", default=None, help="Task name (omit for overview)")

    # update
    p_update = subparsers.add_parser("update", help="Update a frontmatter field")
    p_update.add_argument("--task", required=True, help="Task name")
    p_update.add_argument("--field", required=True, help="Field name")
    p_update.add_argument("--value", required=True, help="New value")

    # list
    p_list = subparsers.add_parser("list", help="List all active tasks grouped by status")
    p_list.add_argument("--parent", default=None, help="Filter to children of a specific parent task")
    p_list.add_argument("--focus", default=None, help="Filter by focus (internal, external)")
    p_list.add_argument("--category", default=None, help="Filter by category (feature, bug, improvement, research, maintenance)")
    p_list.add_argument("--pillar", default=None, help="Filter by pillar (memory, workflow, self-improve)")

    # audit
    p_audit = subparsers.add_parser("audit", help="Run audit checks")
    p_audit.add_argument("--regenerate", action="store_true", help="Export TASKS.md snapshot from task files")

    args = parser.parse_args()
    workspace = args.workspace

    try:
        if args.action == "create":
            desc = args.description
            if args.stdin:
                desc = sys.stdin.read().strip()
            result = create_task(workspace, args.name, desc, args.status, args.parent, args.cadence, args.focus, args.category, args.pillar, session=args.session)

        elif args.action == "start":
            result = start_task(workspace, args.task)

        elif args.action == "complete":
            result = complete_task(workspace, args.task)

        elif args.action == "pause":
            result = pause_task(workspace, args.task, priority=args.priority)

        elif args.action == "cancel":
            result = cancel_task(workspace, args.task, args.reason)

        elif args.action == "reopen":
            result = reopen_task(workspace, args.task)

        elif args.action == "log":
            entry = sys.stdin.read().strip()
            if not entry:
                result = {"ok": False, "action": "log", "error": "No entry provided via stdin", "warnings": []}
            else:
                result = log_entry(workspace, args.task, entry, session=args.session)

        elif args.action == "read":
            result = read_task(workspace, args.task)

        elif args.action == "list":
            result = list_tasks(workspace, parent=args.parent, focus=args.focus, category=args.category, pillar=args.pillar)

        elif args.action == "update":
            result = update_field(workspace, args.task, args.field, args.value)

        elif args.action == "audit":
            from audit import run_audit
            result = run_audit(workspace, regenerate_flag=args.regenerate)

        else:
            result = {"ok": False, "action": args.action, "error": f"Unknown action: {args.action}", "warnings": []}

    except Exception as e:
        result = {
            "ok": False,
            "action": args.action if hasattr(args, "action") else "unknown",
            "error": f"Unexpected error: {type(e).__name__}: {e}",
            "warnings": [],
        }

    # Output JSON (ensure_ascii=True to avoid cp1252 encoding issues on Windows)
    print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
    sys.exit(0 if result.get("ok") else 1)


if __name__ == "__main__":
    main()
