#!/bin/bash
# Detect current Claude Code session ID.
#
# Usage: detect-session-id.sh <probe_string>
#
# The probe string must have been echoed in a previous Bash tool call
# so it appears in the current session's JSONL file. Two-step process:
#   1. Claude runs: echo "SESSION_PROBE_$(date +%s%N)"
#   2. Claude runs: bash .scripts/detect-session-id.sh "SESSION_PROBE_<from step 1>"
#
# Returns the session UUID (JSONL filename without extension).

PROBE="$1"

if [ -z "$PROBE" ]; then
    echo "ERROR: No probe string provided"
    exit 1
fi

SESSION_DIR="$HOME/.claude/projects/<your-project-hash>"

if [ ! -d "$SESSION_DIR" ]; then
    echo "ERROR: Session directory not found"
    exit 1
fi

SESSION_FILE=$(grep -Fl "$PROBE" "$SESSION_DIR"/*.jsonl 2>/dev/null | head -1)

if [ -n "$SESSION_FILE" ]; then
    basename "$SESSION_FILE" .jsonl
else
    echo "DETECTION_FAILED"
    exit 1
fi
