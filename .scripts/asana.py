#!/usr/bin/env python3
"""
Asana workspace query tool: read-only access to tasks, projects, and comments.

Usage:
    python .scripts/asana.py me                         # show authenticated user + workspaces
    python .scripts/asana.py projects                   # list all projects in default workspace
    python .scripts/asana.py project <project-gid>      # list tasks in a project
    python .scripts/asana.py task <task-gid>             # get full task details
    python .scripts/asana.py comments <task-gid>         # get comments/activity on a task
    python .scripts/asana.py recent [days]                # tasks modified in last N days (default: 7)
    python .scripts/asana.py find <keyword>              # client-side search (works on free plan)
    python .scripts/asana.py search <keyword>            # server-side search (paid; falls back to find)

Environment variables:
    ASANA_PAT            - Personal Access Token (required)
    ASANA_WORKSPACE_GID  - Default workspace GID (optional; auto-detects first workspace if unset)
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

# Force UTF-8 output on Windows
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

BASE_URL = "https://app.asana.com/api/1.0"


class AsanaPaymentRequired(Exception):
    """Raised when an endpoint requires a paid Asana plan (402)."""
    pass


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def _read_windows_env(name):
    """Read a user environment variable from the Windows registry (fallback)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except (ImportError, OSError, FileNotFoundError):
        return ""


def get_token():
    token = os.environ.get("ASANA_PAT", "")
    if not token:
        # Fallback: read directly from Windows registry (avoids bash stdout exposure)
        token = _read_windows_env("ASANA_PAT")
    if not token:
        print("Error: ASANA_PAT environment variable not set.", file=sys.stderr)
        print("Generate a token at https://app.asana.com/0/my-apps", file=sys.stderr)
        sys.exit(1)
    return token


def api_get(path, *, params=None, token=None):
    """GET request to Asana API. Returns parsed JSON response."""
    if token is None:
        token = get_token()

    url = f"{BASE_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    })

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        if e.code == 402:
            raise AsanaPaymentRequired("This endpoint requires a paid Asana plan.")
        elif e.code == 401:
            print("Error 401: Invalid or expired PAT. Check ASANA_PAT.", file=sys.stderr)
        elif e.code == 429:
            print("Error 429: Rate limited. Try again shortly.", file=sys.stderr)
        else:
            print(f"Error {e.code}: {body[:500]}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"Network error: {e.reason}", file=sys.stderr)
        sys.exit(1)


def paginated_get(path, *, params=None, token=None, limit=100):
    """Fetch all pages from a paginated Asana endpoint."""
    if params is None:
        params = {}
    params["limit"] = limit
    all_items = []

    while True:
        result = api_get(path, params=params, token=token)
        data = result.get("data", [])
        all_items.extend(data)

        next_page = result.get("next_page")
        if not next_page or not next_page.get("offset"):
            break
        params["offset"] = next_page["offset"]

    return all_items


DEFAULT_WORKSPACE_GID = ""  # <workspace-1>


def get_workspace_gid(token=None):
    """Get the default workspace GID from env var or fall back to <workspace-1>."""
    gid = os.environ.get("ASANA_WORKSPACE_GID", "") or _read_windows_env("ASANA_WORKSPACE_GID")
    if gid:
        return gid
    return DEFAULT_WORKSPACE_GID


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def fmt_date(date_str):
    """Format an ISO date string for display."""
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except (ValueError, AttributeError):
        return date_str


def fmt_user(user_obj):
    """Format a user object to name string."""
    if not user_obj:
        return "(unassigned)"
    return user_obj.get("name", "(unknown)")


def print_json(data):
    """Pretty-print JSON to stdout."""
    print(json.dumps(data, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_me(args):
    """Show authenticated user info and workspaces."""
    result = api_get("/users/me")
    user = result.get("data", {})
    print(f"User: {user.get('name', '?')} ({user.get('email', '?')})")
    print(f"GID:  {user.get('gid', '?')}")
    print()
    workspaces = user.get("workspaces", [])
    if workspaces:
        print("Workspaces:")
        for ws in workspaces:
            print(f"  {ws['gid']}  {ws['name']}")
    else:
        print("No workspaces found.")


def cmd_projects(args):
    """List all projects in the default workspace."""
    ws_gid = get_workspace_gid()
    projects = paginated_get(f"/workspaces/{ws_gid}/projects", params={
        "opt_fields": "name,archived,created_at,modified_at,current_status_update.title",
    })

    if not projects:
        print("No projects found.")
        return

    # Separate active and archived
    active = [p for p in projects if not p.get("archived")]
    archived = [p for p in projects if p.get("archived")]

    print(f"Active projects ({len(active)}):")
    for p in active:
        status = ""
        cs = p.get("current_status_update")
        if cs:
            status = f" [{cs.get('title', '')}]"
        print(f"  {p['gid']}  {p['name']}{status}")

    if archived:
        print(f"\nArchived projects ({len(archived)}):")
        for p in archived:
            print(f"  {p['gid']}  {p['name']}")


def cmd_project(args):
    """List tasks in a project."""
    project_gid = args.project_gid

    # Get project info first
    result = api_get(f"/projects/{project_gid}", params={
        "opt_fields": "name,notes,created_at,modified_at",
    })
    proj = result.get("data", {})
    print(f"Project: {proj.get('name', '?')}")
    if proj.get("notes"):
        print(f"Notes: {proj['notes'][:200]}")
    print()

    # Get tasks
    tasks = paginated_get(f"/projects/{project_gid}/tasks", params={
        "opt_fields": "name,completed,assignee.name,due_on,modified_at",
    })

    if not tasks:
        print("No tasks in this project.")
        return

    incomplete = [t for t in tasks if not t.get("completed")]
    complete = [t for t in tasks if t.get("completed")]

    print(f"Incomplete tasks ({len(incomplete)}):")
    for t in incomplete:
        assignee = fmt_user(t.get("assignee"))
        due = t.get("due_on", "")
        due_str = f" due:{due}" if due else ""
        print(f"  {t['gid']}  {t['name']}  ({assignee}{due_str})")

    if complete:
        max_show = 20
        print(f"\nCompleted tasks ({len(complete)}):")
        for t in complete[:max_show]:
            print(f"  {t['gid']}  {t['name']}")
        if len(complete) > max_show:
            print(f"\n  ... and {len(complete) - max_show} more (use 'task <gid>' for details)")


def cmd_task(args):
    """Get full details for a single task."""
    task_gid = args.task_gid
    result = api_get(f"/tasks/{task_gid}", params={
        "opt_fields": ",".join([
            "name", "notes", "completed", "completed_at", "completed_by.name",
            "created_at", "modified_at", "created_by.name",
            "assignee.name", "due_on", "due_at", "start_on",
            "parent.name", "parent.gid",
            "memberships.project.name", "memberships.section.name",
            "tags.name", "num_subtasks",
            "custom_fields.name", "custom_fields.display_value",
            "followers.name",
        ]),
    })
    task = result.get("data", {})

    print(f"Task: {task.get('name', '?')}")
    print(f"GID:  {task_gid}")
    print(f"Status: {'Completed' if task.get('completed') else 'Incomplete'}")

    if task.get("assignee"):
        print(f"Assignee: {fmt_user(task['assignee'])}")
    if task.get("created_by"):
        print(f"Created by: {fmt_user(task['created_by'])}")
    if task.get("due_on"):
        print(f"Due: {task['due_on']}")
    if task.get("start_on"):
        print(f"Start: {task['start_on']}")
    if task.get("completed_at"):
        print(f"Completed: {fmt_date(task['completed_at'])}")
        if task.get("completed_by"):
            print(f"Completed by: {fmt_user(task['completed_by'])}")
    print(f"Created: {fmt_date(task.get('created_at', ''))}")
    print(f"Modified: {fmt_date(task.get('modified_at', ''))}")

    # Parent task
    parent = task.get("parent")
    if parent:
        print(f"Parent task: {parent.get('name', '?')} ({parent.get('gid', '?')})")

    # Project memberships
    memberships = task.get("memberships", [])
    if memberships:
        print("Projects:")
        for m in memberships:
            proj = m.get("project", {})
            section = m.get("section", {})
            sec_str = f" > {section.get('name', '')}" if section.get("name") else ""
            print(f"  {proj.get('name', '?')}{sec_str}")

    # Tags
    tags = task.get("tags", [])
    if tags:
        print(f"Tags: {', '.join(t.get('name', '?') for t in tags)}")

    # Custom fields
    custom_fields = task.get("custom_fields", [])
    if custom_fields:
        non_empty = [cf for cf in custom_fields if cf.get("display_value")]
        if non_empty:
            print("Custom fields:")
            for cf in non_empty:
                print(f"  {cf.get('name', '?')}: {cf.get('display_value', '')}")

    # Subtasks
    num_subtasks = task.get("num_subtasks", 0)
    if num_subtasks:
        print(f"Subtasks: {num_subtasks}")

    # Followers
    followers = task.get("followers", [])
    if followers:
        print(f"Followers: {', '.join(f.get('name', '?') for f in followers)}")

    # Notes (description)
    notes = task.get("notes", "")
    if notes:
        print(f"\nDescription:\n{notes}")


def cmd_comments(args):
    """Get comments and activity on a task."""
    task_gid = args.task_gid
    stories = paginated_get(f"/tasks/{task_gid}/stories", params={
        "opt_fields": "created_at,created_by.name,type,text,resource_subtype",
    })

    if not stories:
        print("No activity on this task.")
        return

    # Filter to comments only by default, show all with --all
    if not args.all:
        stories = [s for s in stories if s.get("resource_subtype") == "comment_added"
                   or s.get("type") == "comment"]

    if not stories:
        print("No comments on this task. Use --all to see system activity.")
        return

    print(f"{'Activity' if args.all else 'Comments'} ({len(stories)}):\n")
    for s in stories:
        author = fmt_user(s.get("created_by"))
        date = fmt_date(s.get("created_at", ""))
        text = s.get("text", "(no text)")
        subtype = s.get("resource_subtype", "")

        if args.all and subtype != "comment_added":
            print(f"  [{date}] {author} -- {subtype}: {text[:200]}")
        else:
            print(f"  [{date}] {author}:")
            # Indent comment text
            for line in text.split("\n"):
                print(f"    {line}")
        print()


def cmd_recent(args):
    """Show tasks modified in the last N days across all projects."""
    ws_gid = get_workspace_gid()
    days = args.days

    since = datetime.now(tz=None)
    since = since.replace(hour=0, minute=0, second=0, microsecond=0)
    since -= timedelta(days=days)
    since_iso = since.strftime("%Y-%m-%dT%H:%M:%S.000Z")

    # Get all active projects
    projects = paginated_get(f"/workspaces/{ws_gid}/projects", params={
        "opt_fields": "name,archived",
    })
    projects = [p for p in projects if not p.get("archived")]

    all_tasks = []
    for proj in projects:
        tasks = paginated_get(f"/projects/{proj['gid']}/tasks", params={
            "opt_fields": "name,completed,completed_at,assignee.name,due_on,modified_at,created_at",
            "modified_since": since_iso,
        })
        for t in tasks:
            t["_project_name"] = proj.get("name", "?")
            all_tasks.append(t)

    # Deduplicate (task can be in multiple projects)
    seen = set()
    unique = []
    for t in all_tasks:
        if t["gid"] not in seen:
            seen.add(t["gid"])
            unique.append(t)

    # Sort by modified_at descending
    unique.sort(key=lambda t: t.get("modified_at", ""), reverse=True)

    if not unique:
        print(f"No tasks modified in the last {days} days.")
        return

    # Separate by status
    completed = [t for t in unique if t.get("completed")]
    active = [t for t in unique if not t.get("completed")]

    print(f"Activity in the last {days} days: {len(unique)} tasks ({len(active)} active, {len(completed)} completed)\n")

    if active:
        print(f"Active ({len(active)}):")
        for t in active:
            assignee = fmt_user(t.get("assignee"))
            due = t.get("due_on", "")
            due_str = f" due:{due}" if due else ""
            modified = fmt_date(t.get("modified_at", ""))
            proj = t.get("_project_name", "")
            print(f"  {t['gid']}  {t['name']}")
            print(f"           {assignee}{due_str}  modified:{modified}  in [{proj}]")
            print()

    if completed:
        print(f"Completed ({len(completed)}):")
        for t in completed:
            assignee = fmt_user(t.get("assignee"))
            completed_at = fmt_date(t.get("completed_at", ""))
            modified = fmt_date(t.get("modified_at", ""))
            proj = t.get("_project_name", "")
            print(f"  {t['gid']}  {t['name']}")
            print(f"           {assignee}  completed:{completed_at}  in [{proj}]")
            print()


def cmd_find(args):
    """Client-side keyword search across all projects (works on free plan)."""
    ws_gid = get_workspace_gid()
    keyword = " ".join(args.keyword).lower()

    # Get all projects
    print(f"Searching all projects for '{keyword}'...", file=sys.stderr)
    projects = paginated_get(f"/workspaces/{ws_gid}/projects", params={
        "opt_fields": "name,archived",
    })

    # Filter to active projects unless --archived
    if not args.archived:
        projects = [p for p in projects if not p.get("archived")]

    matches = []
    for proj in projects:
        tasks = paginated_get(f"/projects/{proj['gid']}/tasks", params={
            "opt_fields": "name,completed,assignee.name,due_on,modified_at,notes",
        })
        for t in tasks:
            name = (t.get("name") or "").lower()
            notes = (t.get("notes") or "").lower()
            if keyword in name or keyword in notes:
                t["_project_name"] = proj.get("name", "?")
                matches.append(t)

    if not matches:
        print(f"No tasks found matching '{keyword}'.")
        return

    # Deduplicate (task can be in multiple projects)
    seen = set()
    unique = []
    for t in matches:
        if t["gid"] not in seen:
            seen.add(t["gid"])
            unique.append(t)

    # Sort by modified_at descending
    unique.sort(key=lambda t: t.get("modified_at", ""), reverse=True)

    print(f"Found {len(unique)} tasks matching '{keyword}':\n")
    for t in unique:
        status = "done" if t.get("completed") else "open"
        assignee = fmt_user(t.get("assignee"))
        due = t.get("due_on", "")
        due_str = f" due:{due}" if due else ""
        modified = fmt_date(t.get("modified_at", ""))
        proj = t.get("_project_name", "")

        print(f"  {t['gid']}  [{status}] {t['name']}")
        print(f"           {assignee}{due_str}  modified:{modified}  in [{proj}]")
        print()


def cmd_search(args):
    """Search tasks by keyword (paid plan: server-side, free: falls back to find)."""
    ws_gid = get_workspace_gid()
    keyword = " ".join(args.keyword)

    params = {
        "text": keyword,
        "opt_fields": "name,completed,assignee.name,due_on,modified_at,memberships.project.name",
        "sort_by": "modified_at",
        "sort_ascending": "false",
    }

    if args.completed is not None:
        params["completed"] = str(args.completed).lower()
    if args.project:
        params["projects.any"] = args.project

    try:
        result = api_get(f"/workspaces/{ws_gid}/tasks/search", params=params)
    except AsanaPaymentRequired:
        print("Paid search unavailable. Falling back to client-side search...", file=sys.stderr)
        args.archived = False
        cmd_find(args)
        return

    tasks = result.get("data", [])

    if not tasks:
        print(f"No tasks found matching '{keyword}'.")
        return

    print(f"Search results for '{keyword}' ({len(tasks)} tasks):\n")
    for t in tasks:
        status = "done" if t.get("completed") else "open"
        assignee = fmt_user(t.get("assignee"))
        due = t.get("due_on", "")
        due_str = f" due:{due}" if due else ""
        modified = fmt_date(t.get("modified_at", ""))

        projects = t.get("memberships", [])
        proj_str = ""
        if projects:
            proj_names = [m.get("project", {}).get("name", "") for m in projects if m.get("project")]
            if proj_names:
                proj_str = f" in [{', '.join(proj_names)}]"

        print(f"  {t['gid']}  [{status}] {t['name']}")
        print(f"           {assignee}{due_str}  modified:{modified}{proj_str}")
        print()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Asana workspace query tool (read-only)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # me
    subparsers.add_parser("me", help="Show authenticated user and workspaces")

    # projects
    subparsers.add_parser("projects", help="List all projects in workspace")

    # project <gid>
    p_project = subparsers.add_parser("project", help="List tasks in a project")
    p_project.add_argument("project_gid", help="Project GID")

    # task <gid>
    p_task = subparsers.add_parser("task", help="Get full task details")
    p_task.add_argument("task_gid", help="Task GID")

    # comments <gid>
    p_comments = subparsers.add_parser("comments", help="Get comments on a task")
    p_comments.add_argument("task_gid", help="Task GID")
    p_comments.add_argument("--all", action="store_true", help="Show all activity, not just comments")

    # recent [days]
    p_recent = subparsers.add_parser("recent", help="Show tasks modified in last N days")
    p_recent.add_argument("days", nargs="?", type=int, default=7, help="Number of days to look back (default: 7)")

    # find <keyword> (client-side, works on free plan)
    p_find = subparsers.add_parser("find", help="Search tasks by keyword (client-side, works on free plan)")
    p_find.add_argument("keyword", nargs="+", help="Search terms")
    p_find.add_argument("--archived", action="store_true", help="Include archived projects")

    # search <keyword> (server-side, paid plan; falls back to find on free)
    p_search = subparsers.add_parser("search", help="Search tasks (paid plan; falls back to find on free)")
    p_search.add_argument("keyword", nargs="+", help="Search terms")
    p_search.add_argument("--completed", type=bool, default=None, help="Filter: true/false")
    p_search.add_argument("--project", help="Filter by project GID")

    args = parser.parse_args()

    commands = {
        "me": cmd_me,
        "projects": cmd_projects,
        "project": cmd_project,
        "task": cmd_task,
        "comments": cmd_comments,
        "recent": cmd_recent,
        "find": cmd_find,
        "search": cmd_search,
    }

    commands[args.command](args)


if __name__ == "__main__":
    main()
