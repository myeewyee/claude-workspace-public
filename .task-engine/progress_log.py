"""Progress log parsing and entry insertion for task files."""

import platform
import re
from datetime import datetime

# Pre-compiled patterns for progress log parsing
_DATE_HEADING_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2})", re.MULTILINE)
_TIME_ENTRY_RE = re.compile(r"^(\d{1,2}:\d{2}\s*[AaPp][Mm])", re.MULTILINE)


def get_last_progress_time(body: str) -> str:
    """Extract the most recent progress log timestamp from a task file body.

    Finds the newest date heading (### YYYY-MM-DD) and the first time entry
    under it (HH:MM AM/PM). Returns ISO-ish string like '2026-02-24T14:46'
    or empty string if no progress entries found.
    """
    # Find the Progress Log section
    log_idx = body.find("## Progress Log")
    if log_idx == -1:
        return ""

    log_section = body[log_idx:]

    # Find the first (most recent) date heading
    date_match = _DATE_HEADING_RE.search(log_section)
    if not date_match:
        return ""

    date_str = date_match.group(1)

    # Find the first time entry after this date heading
    after_heading = log_section[date_match.end():]
    time_match = _TIME_ENTRY_RE.search(after_heading)
    if not time_match:
        return ""

    # Parse the time string (e.g., "2:46 PM") into 24h format
    time_str = time_match.group(1).strip()
    try:
        t = datetime.strptime(time_str, "%I:%M %p")
        return f"{date_str}T{t.strftime('%H:%M')}"
    except ValueError:
        return ""


def get_timestamp() -> str:
    """Get current time in 12-hour format for progress logs.

    Returns format like '10:29 PM' (no leading zero on hour).
    """
    now = datetime.now()
    if platform.system() == "Windows":
        return now.strftime("%#I:%M %p")
    else:
        return now.strftime("%-I:%M %p")


def get_date_heading() -> str:
    """Get today's date as a progress log heading: ### YYYY-MM-DD"""
    return datetime.now().strftime("### %Y-%m-%d")


def format_status_change(new_status: str, note: str = "") -> str:
    """Format a status change entry.

    Returns like: *Status -> In Progress* or *Status -> Cancelled (superseded)*
    """
    # Capitalize status for display
    display = new_status.replace("-", " ").title()
    if display == "In Progress":
        display = "In Progress"  # preserve exact casing

    if note:
        return f"*Status \u2192 {display} ({note})*"
    return f"*Status \u2192 {display}*"


def add_entry(content: str, entry_text: str, timestamp: str = None) -> str:
    """Insert a timestamped entry into the progress log section.

    Args:
        content: Full file body content (after frontmatter)
        entry_text: The entry to add (may be multi-line)
        timestamp: Override timestamp (default: current time)

    Returns:
        Modified content with entry inserted.
    """
    if timestamp is None:
        timestamp = get_timestamp()

    today_heading = get_date_heading()
    today_date = datetime.now().strftime("%Y-%m-%d")

    # Find the Progress Log section
    log_marker = "## Progress Log"
    log_idx = content.find(log_marker)
    if log_idx == -1:
        # No progress log section: append one
        content = content.rstrip() + "\n\n" + log_marker + "\n"
        log_idx = content.find(log_marker)

    # Get the text after "## Progress Log"
    after_marker = log_idx + len(log_marker)
    before_log = content[:after_marker]
    log_section = content[after_marker:]

    # Strip any leading timestamp the caller may have included (avoid doubling)
    entry_text = re.sub(r"^\d{1,2}:\d{2}\s*[AaPp][Mm]\s*", "", entry_text)

    # Format the entry with timestamp
    entry_line = f"{timestamp} {entry_text}"

    # Check if today's date heading exists
    heading_pattern = re.compile(r"^### (\d{4}-\d{2}-\d{2})", re.MULTILINE)
    headings = list(heading_pattern.finditer(log_section))

    if headings and headings[0].group(1) == today_date:
        # Today's heading exists: insert entry right after it
        heading_end = headings[0].end()
        # Find the end of the heading line
        newline_after = log_section.find("\n", heading_end)
        if newline_after == -1:
            newline_after = len(log_section)

        # Insert right after the heading line (no blank line between heading and entry)
        heading_line_end = newline_after + 1
        # Skip any blank lines after the heading (consume, don't preserve)
        content_start = heading_line_end
        while content_start < len(log_section) and log_section[content_start] == "\n":
            content_start += 1

        # Blank line between entries, but not between heading and first entry
        remaining = log_section[content_start:]
        if remaining.strip():
            new_log = log_section[:heading_line_end] + entry_line + "\n\n" + remaining
        else:
            new_log = log_section[:heading_line_end] + entry_line + "\n" + remaining
    else:
        # Need to add today's heading (newest first: goes right after ## Progress Log)
        # No blank line between ## Progress Log and ### date, or between ### date and entry
        # Preserve one blank line between date groups as separator
        remaining = log_section.lstrip("\n")
        if remaining:
            new_log = "\n" + today_heading + "\n" + entry_line + "\n\n" + remaining
        else:
            new_log = "\n" + today_heading + "\n" + entry_line + "\n"

    return before_log + new_log
