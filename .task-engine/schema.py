"""Task frontmatter schema, validation, and status transitions."""

from datetime import datetime

# Valid status values (numeric prefixes enable Obsidian Bases sorting)
VALID_STATUSES = {"1-active", "2-paused", "3-idea", "4-recurring", "5-done", "6-cancelled"}
TERMINAL_STATUSES = {"5-done", "6-cancelled"}
ACTIVE_STATUSES = {"1-active", "2-paused"}

# Valid status transitions (from -> set of allowed targets)
TRANSITIONS = {
    "3-idea": {"1-active", "2-paused", "6-cancelled"},
    "1-active": {"5-done", "2-paused", "6-cancelled"},
    "2-paused": {"1-active", "6-cancelled"},
    # 5-done and 6-cancelled are terminal: no transitions out
    # 4-recurring: special, only last-run updates
}

REQUIRED_FIELDS = {"type", "source", "created", "status", "description"}
OPTIONAL_FIELDS = {"decision", "parent", "completed", "cadence", "last-run", "focus", "category", "pillar", "priority", "context-aligned"}
ALL_FIELDS = REQUIRED_FIELDS | OPTIONAL_FIELDS

# Fields that must be wiki-links (quoted in YAML)
WIKILINK_FIELDS = {"parent"}

# Valid cadence values for recurring tasks
VALID_CADENCES = {"daily", "weekly", "monthly", "quarterly", "on-demand"}

# Valid focus values (internal vs external effort classification)
VALID_FOCUS_VALUES = {"internal", "external"}

# Valid category values (work-type classification)
VALID_CATEGORIES = {"feature", "bug", "improvement", "research", "maintenance"}

# Valid pillar values (internal-only: which part of the machine)
VALID_PILLARS = {"memory", "workflow", "self-improve"}

# Valid priority values (context-dependent on status)
# Numeric prefixes enable natural sorting in Obsidian Bases
VALID_PRIORITY_ACTIVE = {"1-high", "2-medium", "3-low"}  # for 1-active
VALID_PRIORITY_PAUSED = {"1-next", "2-blocked", "3-later", "4-someday"}  # for 2-paused
VALID_PRIORITY_ALL = VALID_PRIORITY_ACTIVE | VALID_PRIORITY_PAUSED

# Priority sort order (lower number = higher priority in list output)
PRIORITY_SORT_ORDER = {
    "1-high": 0, "2-medium": 1, "3-low": 2,
    "1-next": 0, "2-blocked": 1, "3-later": 2, "4-someday": 3,
}

# Frontmatter key order (matches our convention)
FIELD_ORDER = [
    "type", "source", "created", "status", "priority", "description",
    "decision", "parent", "focus", "category", "pillar", "context-aligned", "completed", "cadence", "last-run",
]


def validate_frontmatter(fm: dict) -> list[str]:
    """Validate a frontmatter dict. Returns list of error strings (empty = valid)."""
    errors = []

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in fm or fm[field] is None or fm[field] == "":
            errors.append(f"Missing required field: {field}")

    # Check type is 'task'
    if fm.get("type") and fm["type"] != "task":
        errors.append(f"type must be 'task', got '{fm['type']}'")

    # Check source is 'claude'
    if fm.get("source") and fm["source"] != "claude":
        errors.append(f"source must be 'claude', got '{fm['source']}'")

    # Check status is valid
    status = fm.get("status")
    if status and status not in VALID_STATUSES:
        errors.append(f"Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}")

    # Check date formats
    for date_field in ("created", "completed", "last-run", "context-aligned"):
        val = fm.get(date_field)
        if val and val is not None:
            val_str = str(val)
            try:
                datetime.strptime(val_str, "%Y-%m-%d %H:%M")
            except ValueError:
                errors.append(f"{date_field} must be YYYY-MM-DD HH:mm format, got '{val_str}'")

    # Check cadence
    cadence = fm.get("cadence")
    if cadence and cadence not in VALID_CADENCES:
        errors.append(f"Invalid cadence '{cadence}'. Valid: {sorted(VALID_CADENCES)}")

    # Check focus
    focus = fm.get("focus")
    if focus and focus not in VALID_FOCUS_VALUES:
        errors.append(f"Invalid focus '{focus}'. Valid: {sorted(VALID_FOCUS_VALUES)}")

    # Check category
    category = fm.get("category")
    if category and category not in VALID_CATEGORIES:
        errors.append(f"Invalid category '{category}'. Valid: {sorted(VALID_CATEGORIES)}")

    # Check pillar
    pillar = fm.get("pillar")
    if pillar and pillar not in VALID_PILLARS:
        errors.append(f"Invalid pillar '{pillar}'. Valid: {sorted(VALID_PILLARS)}")

    # Check priority (context-dependent on status)
    priority = fm.get("priority")
    if priority:
        if status == "1-active":
            if priority not in VALID_PRIORITY_ACTIVE:
                errors.append(f"Invalid priority '{priority}' for {status} task. Valid: {sorted(VALID_PRIORITY_ACTIVE)}")
        elif status == "2-paused":
            if priority not in VALID_PRIORITY_PAUSED:
                errors.append(f"Invalid priority '{priority}' for 2-paused task. Valid: {sorted(VALID_PRIORITY_PAUSED)}")
        elif priority not in VALID_PRIORITY_ALL:
            errors.append(f"Invalid priority '{priority}'. Valid: {sorted(VALID_PRIORITY_ALL)}")

    # Terminal states should have completed date
    if status in TERMINAL_STATUSES and not fm.get("completed"):
        errors.append(f"Status '{status}' requires a completed timestamp")

    # Recurring tasks must have a cadence
    if status == "4-recurring" and not cadence:
        errors.append("Recurring tasks require a cadence value")

    return errors


def validate_transition(current: str, target: str) -> tuple[bool, str]:
    """Check if a status transition is allowed. Returns (valid, reason)."""
    if current in TERMINAL_STATUSES:
        return False, f"Cannot transition from terminal status '{current}'"

    if current == "4-recurring":
        return False, "Recurring tasks don't change status (only last-run updates)"

    allowed = TRANSITIONS.get(current, set())
    if target not in allowed:
        return False, f"Cannot transition from '{current}' to '{target}'. Allowed: {sorted(allowed)}"

    return True, ""


def validate_field_value(field: str, value: str) -> tuple[bool, str]:
    """Validate a value for a specific field. Returns (valid, reason)."""
    if field == "status":
        if value not in VALID_STATUSES:
            return False, f"Invalid status '{value}'. Valid: {sorted(VALID_STATUSES)}"
    elif field == "cadence":
        if value not in VALID_CADENCES:
            return False, f"Invalid cadence '{value}'. Valid: {sorted(VALID_CADENCES)}"
    elif field == "focus":
        if value not in VALID_FOCUS_VALUES:
            return False, f"Invalid focus '{value}'. Valid: {sorted(VALID_FOCUS_VALUES)}"
    elif field == "category":
        if value not in VALID_CATEGORIES:
            return False, f"Invalid category '{value}'. Valid: {sorted(VALID_CATEGORIES)}"
    elif field == "pillar":
        if value not in VALID_PILLARS:
            return False, f"Invalid pillar '{value}'. Valid: {sorted(VALID_PILLARS)}"
    elif field == "priority":
        if value not in VALID_PRIORITY_ALL:
            return False, f"Invalid priority '{value}'. Valid: {sorted(VALID_PRIORITY_ALL)}"
    elif field in ("created", "completed", "last-run", "context-aligned"):
        try:
            datetime.strptime(value, "%Y-%m-%d %H:%M")
        except ValueError:
            return False, f"{field} must be YYYY-MM-DD HH:mm format, got '{value}'"
    elif field not in ALL_FIELDS:
        return False, f"Unknown field '{field}'. Valid: {sorted(ALL_FIELDS)}"

    return True, ""


def default_frontmatter(
    name: str,
    description: str,
    status: str = "3-idea",
    parent: str = "",
    cadence: str = "",
    focus: str = "",
    category: str = "",
    pillar: str = "",
) -> dict:
    """Create a complete frontmatter dict with defaults."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    fm = {
        "type": "task",
        "source": "claude",
        "created": now,
        "status": status,
        "priority": "",
        "description": description,
        "decision": "",
        "parent": parent,
        "focus": focus,
        "category": category,
        "pillar": pillar,
        "context-aligned": "",
        "completed": "",
    }
    if status == "4-recurring":
        fm["cadence"] = cadence
        fm["last-run"] = now
    return fm


def render_frontmatter(fm: dict) -> str:
    """Render a frontmatter dict as a YAML string with controlled formatting.

    Preserves our conventions: key order, empty strings for blanks (not null),
    quoted wiki-links, block-style lists.
    """
    lines = ["---"]

    for key in FIELD_ORDER:
        if key not in fm:
            continue

        value = fm[key]

        # Skip recurring-only fields if not present
        if key in ("cadence", "last-run") and not value:
            continue

        if isinstance(value, list):
            if not value:
                lines.append(f"{key}:")
            else:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f'  - "{_escape_yaml_quotes(item)}"')
        elif value is None or value == "":
            lines.append(f"{key}:")
        elif isinstance(value, str) and _needs_quoting(value):
            lines.append(f'{key}: "{_escape_yaml_quotes(value)}"')
        else:
            lines.append(f"{key}: {value}")

    lines.append("---")
    return "\n".join(lines)


def _escape_yaml_quotes(value: str) -> str:
    """Escape characters that break double-quoted YAML strings."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _needs_quoting(value: str) -> bool:
    """Check if a YAML value needs double-quoting."""
    if not value:
        return False
    # Wiki-links always quoted
    if "[[" in value:
        return True
    # Multi-line
    if "\n" in value:
        return True
    # Long values (prevent wrapping)
    if len(value) > 80:
        return True
    # YAML special first characters
    if value[0] in "{[>|*&!#%@`'\"":
        return True
    # YAML booleans and null
    if value.lower() in ("true", "false", "null", "yes", "no", "on", "off"):
        return True
    # Trailing/leading whitespace
    if value != value.strip():
        return True
    return False
