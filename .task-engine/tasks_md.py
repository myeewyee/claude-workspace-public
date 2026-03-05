"""TASKS.md export: on-demand snapshot generation from task files.

Used only by audit --regenerate. Not part of normal task operations.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path


@dataclass
class TaskEntry:
    """An entry in an active section (Active, Paused, Recurring, Ideas)."""
    name: str
    description: str = ""
    checked: bool = False


@dataclass
class DoneEntry:
    """An entry in the Done section."""
    name: str
    timestamp: str = ""  # Time for today/yesterday, date for older
    cancelled: bool = False
    raw_line: str = ""   # Original line for legacy entries without wiki-links


@dataclass
class DoneSection:
    """The Done section with date-based buckets."""
    today: list[DoneEntry] = field(default_factory=list)
    today_date: str = ""  # e.g., "2026-02-19"
    yesterday: list[DoneEntry] = field(default_factory=list)
    yesterday_date: str = ""
    last_7_days: list[DoneEntry] = field(default_factory=list)
    earlier: list[DoneEntry] = field(default_factory=list)


@dataclass
class TasksIndex:
    """Structured representation of TASKS.md."""
    active: list[TaskEntry] = field(default_factory=list)
    paused: list[TaskEntry] = field(default_factory=list)
    recurring: list[TaskEntry] = field(default_factory=list)
    ideas: list[TaskEntry] = field(default_factory=list)
    done: DoneSection = field(default_factory=DoneSection)


# Section heading to attribute name mapping
SECTION_MAP = {
    "Active": "active",
    "Paused": "paused",
    "Recurring": "recurring",
    "Ideas": "ideas",
}

# Regex for parsing entries
ENTRY_RE = re.compile(
    r"^- \[([ x])\] "               # checkbox
    r"(?:\[\[([^\]]+)\]\])?"         # optional wiki-link
    r"(.*?)$",                       # rest of line
    re.MULTILINE,
)

# Regex for done entries with timestamp
DONE_ENTRY_RE = re.compile(
    r"^- \[x\] "
    r"(?:\[\[([^\]]+)\]\])?"         # optional wiki-link
    r"\s*"
    r"(?:\(([^)]*)\))?"              # optional (timestamp/date)
    r"(.*?)$",
    re.MULTILINE,
)


def parse_tasks_md(path: Path) -> TasksIndex:
    """Parse TASKS.md into a structured TasksIndex."""
    content = path.read_text(encoding="utf-8")
    index = TasksIndex()

    # Split into sections by ## headings
    sections = re.split(r"^## ", content, flags=re.MULTILINE)

    for section in sections[1:]:  # Skip content before first ##
        lines = section.strip().split("\n")
        heading = lines[0].strip()

        if heading in SECTION_MAP:
            attr = SECTION_MAP[heading]
            entries = _parse_active_entries("\n".join(lines[1:]))
            setattr(index, attr, entries)
        elif heading == "Done":
            index.done = _parse_done_section("\n".join(lines[1:]))

    return index


def _parse_active_entries(text: str) -> list[TaskEntry]:
    """Parse entries from an active section."""
    entries = []
    for match in ENTRY_RE.finditer(text):
        checked = match.group(1) == "x"
        name = match.group(2) or ""
        rest = match.group(3).strip()
        description = rest[2:].strip() if rest.startswith("- ") else rest.strip()
        if not name and rest:
            # Legacy entry without wiki-link: treat whole text as name
            name = rest.strip()
            description = ""
        entries.append(TaskEntry(name=name, description=description, checked=checked))
    return entries


def _parse_done_section(text: str) -> DoneSection:
    """Parse the Done section with date buckets."""
    done = DoneSection()

    # Split by ### subheadings
    subsections = re.split(r"^### ", text, flags=re.MULTILINE)
    current_bucket = None

    for subsection in subsections:
        if not subsection.strip():
            continue

        lines = subsection.strip().split("\n")
        heading = lines[0].strip()

        if heading.startswith("Today"):
            current_bucket = done.today
            # Extract date from "Today (2026-02-19)"
            date_match = re.search(r"\((\d{4}-\d{2}-\d{2})\)", heading)
            if date_match:
                done.today_date = date_match.group(1)
        elif heading.startswith("Yesterday"):
            current_bucket = done.yesterday
            date_match = re.search(r"\((\d{4}-\d{2}-\d{2})\)", heading)
            if date_match:
                done.yesterday_date = date_match.group(1)
        elif heading.startswith("Last 7 Days"):
            current_bucket = done.last_7_days
        elif heading.startswith("Earlier"):
            current_bucket = done.earlier
        else:
            continue

        if current_bucket is not None:
            entries_text = "\n".join(lines[1:])
            for match in DONE_ENTRY_RE.finditer(entries_text):
                name = match.group(1) or ""
                ts = match.group(2) or ""
                rest = match.group(3).strip()
                cancelled = "cancelled" in ts.lower() if ts else False
                if cancelled:
                    ts = re.sub(r",?\s*cancelled", "", ts, flags=re.IGNORECASE).strip()
                if not name and rest:
                    name = rest.strip()
                current_bucket.append(DoneEntry(
                    name=name,
                    timestamp=ts,
                    cancelled=cancelled,
                    raw_line=match.group(0),
                ))

    return done


def render_tasks_md(index: TasksIndex, today: date = None) -> str:
    """Render a full TASKS.md from the structured index."""
    if today is None:
        today = date.today()

    lines = ["# TASKS", ""]

    # Active sections
    for heading, attr in SECTION_MAP.items():
        entries = getattr(index, attr)
        lines.append(f"## {heading}")
        for entry in entries:
            check = "x" if entry.checked else " "
            if entry.description:
                lines.append(f"- [{check}] [[{entry.name}]] - {entry.description}")
            else:
                lines.append(f"- [{check}] [[{entry.name}]]")
        lines.append("")

    # Done section
    lines.append("## Done")
    lines.append("")
    done = index.done

    buckets = [
        ("Today", today.strftime("%Y-%m-%d"), done.today),
        ("Yesterday", (today - timedelta(days=1)).strftime("%Y-%m-%d"), done.yesterday),
        ("Last 7 Days", None, done.last_7_days),
        ("Earlier", None, done.earlier),
    ]

    for label, bucket_date, entries in buckets:
        if not entries:
            continue
        if bucket_date:
            lines.append(f"### {label} ({bucket_date})")
        else:
            lines.append(f"### {label}")
        for entry in entries:
            suffix = ""
            if entry.cancelled:
                suffix = ", cancelled"
            if entry.timestamp:
                ts_display = f"({entry.timestamp}{suffix})"
            else:
                ts_display = ""
            if entry.name:
                line = f"- [x] [[{entry.name}]]"
            else:
                line = f"- [x] {entry.raw_line}" if entry.raw_line else "- [x] (unknown)"
            if ts_display:
                line += f" {ts_display}"
            lines.append(line)
        lines.append("")

    return "\n".join(lines)


def regenerate(workspace: Path) -> TasksIndex:
    """Full rebuild of TASKS.md from task files.

    Scans all task files, reads frontmatter, builds index, writes TASKS.md.
    """
    import frontmatter as fm_lib
    from fileops import list_task_files

    index = TasksIndex()
    tasks_md_path = workspace / "TASKS.md"

    # Scan active task files
    for path in list_task_files(workspace):
        try:
            post = fm_lib.load(str(path))
            meta = post.metadata
        except Exception:
            continue

        name = path.stem
        status = meta.get("status", "3-idea")
        desc = meta.get("description", "")

        entry = TaskEntry(name=name, description=desc)

        if status == "3-idea":
            index.ideas.append(entry)
        elif status == "1-active":
            index.active.append(entry)
        elif status == "2-paused":
            index.paused.append(entry)
        elif status == "4-recurring":
            index.recurring.append(entry)

    # Scan archive for done section (read existing TASKS.md done entries)
    if tasks_md_path.exists():
        existing = parse_tasks_md(tasks_md_path)
        index.done = existing.done

    # Re-sort done buckets and trim to limit
    index.done = resort_done_buckets(index.done, date.today())
    index.done = trim_done_entries(index.done, max_done=50)

    # Write
    content = render_tasks_md(index, date.today())
    from fileops import atomic_write
    atomic_write(tasks_md_path, content)

    return index


def resort_done_buckets(done: DoneSection, today: date) -> DoneSection:
    """Re-sort done entries into correct date buckets."""
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    # Collect all entries with their dates
    all_entries = []
    for entry in done.today + done.yesterday + done.last_7_days + done.earlier:
        entry_date = _parse_entry_date(entry, done)
        all_entries.append((entry, entry_date))

    # Re-bucket
    new_done = DoneSection(
        today_date=today.strftime("%Y-%m-%d"),
        yesterday_date=yesterday.strftime("%Y-%m-%d"),
    )

    for entry, entry_date in all_entries:
        if entry_date is None:
            # Can't determine date, keep in earlier
            new_done.earlier.append(entry)
        elif entry_date == today:
            new_done.today.append(entry)
        elif entry_date == yesterday:
            new_done.yesterday.append(entry)
        elif entry_date >= week_ago:
            # Convert time-based timestamp to date-based
            if entry.timestamp and ("AM" in entry.timestamp or "PM" in entry.timestamp):
                entry = DoneEntry(
                    name=entry.name,
                    timestamp=entry_date.strftime("%Y-%m-%d"),
                    cancelled=entry.cancelled,
                    raw_line=entry.raw_line,
                )
            new_done.last_7_days.append(entry)
        else:
            if entry.timestamp and ("AM" in entry.timestamp or "PM" in entry.timestamp):
                entry = DoneEntry(
                    name=entry.name,
                    timestamp=entry_date.strftime("%Y-%m-%d"),
                    cancelled=entry.cancelled,
                    raw_line=entry.raw_line,
                )
            new_done.earlier.append(entry)

    return new_done


def trim_done_entries(done: DoneSection, max_done: int = 50) -> DoneSection:
    """Trim done entries to a maximum count, removing oldest first."""
    total = len(done.today) + len(done.yesterday) + len(done.last_7_days) + len(done.earlier)
    if total <= max_done:
        return done

    excess = total - max_done
    # Trim from earliest bucket first
    if excess <= len(done.earlier):
        done.earlier = done.earlier[:-excess] if excess < len(done.earlier) else []
    else:
        excess -= len(done.earlier)
        done.earlier = []
        if excess <= len(done.last_7_days):
            done.last_7_days = done.last_7_days[:-excess] if excess < len(done.last_7_days) else []
        else:
            excess -= len(done.last_7_days)
            done.last_7_days = []
            if excess <= len(done.yesterday):
                done.yesterday = done.yesterday[:-excess] if excess < len(done.yesterday) else []

    return done


def _parse_entry_date(entry: DoneEntry, done: DoneSection) -> date | None:
    """Try to determine the completion date of a done entry."""
    ts = entry.timestamp.strip()
    if not ts:
        return None

    # Try full date format: YYYY-MM-DD
    try:
        return datetime.strptime(ts, "%Y-%m-%d").date()
    except ValueError:
        pass

    # If it's a time (AM/PM), it was in Today or Yesterday bucket
    if "AM" in ts or "PM" in ts:
        # Check which bucket it came from
        if entry in done.today and done.today_date:
            try:
                return datetime.strptime(done.today_date, "%Y-%m-%d").date()
            except ValueError:
                pass
        if entry in done.yesterday and done.yesterday_date:
            try:
                return datetime.strptime(done.yesterday_date, "%Y-%m-%d").date()
            except ValueError:
                pass

    return None


if __name__ == "__main__":
    import sys
    print("Error: tasks_md.py is a library module, not a CLI entry point.", file=sys.stderr)
    print("Use task.py instead: python task.py <command> [args]", file=sys.stderr)
    sys.exit(1)
