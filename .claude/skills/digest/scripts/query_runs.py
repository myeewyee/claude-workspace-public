#!/usr/bin/env python3
"""Query the digest run log.

Usage:
    python query_runs.py                    # Last 10 runs
    python query_runs.py --last 20          # Last 20 runs
    python query_runs.py --url "youtube"    # Runs matching URL substring
    python query_runs.py --mode quick       # Filter by mode
    python query_runs.py --pipeline youtube # Filter by pipeline
    python query_runs.py --id d20260305    # Filter by run ID prefix
    python query_runs.py --stats            # Summary statistics
    python query_runs.py --json             # Raw JSON output
"""

import argparse
import json
import os
import sys
from collections import defaultdict

LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "run-log.jsonl")


def load_runs():
    """Load all runs from the JSONL log."""
    if not os.path.exists(LOG_FILE):
        return []
    runs = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                runs.append(json.loads(line))
    return runs


def filter_runs(runs, args):
    """Apply filters to runs."""
    if args.url:
        runs = [r for r in runs if args.url.lower() in r.get("url", "").lower()]
    if args.mode:
        runs = [r for r in runs if r.get("mode") == args.mode]
    if args.pipeline:
        runs = [r for r in runs if r.get("pipeline") == args.pipeline]
    if args.id:
        runs = [r for r in runs if r.get("run_id", "").startswith(args.id)]
    if args.title:
        runs = [r for r in runs
                if args.title.lower() in r.get("title", "").lower()]
    return runs


def truncate(s, width):
    """Truncate string to width with ellipsis."""
    if len(s) <= width:
        return s
    return s[: width - 3] + "..."


def format_table(runs):
    """Format runs as a readable table."""
    if not runs:
        print("No runs found.")
        return

    # Collect all step names across runs
    all_steps = []
    for r in runs:
        for step in r.get("steps", {}):
            if step not in all_steps:
                all_steps.append(step)

    # Header
    cols = ["Run ID", "Date", "Mode", "Pipeline", "Total"]
    cols.extend(s.capitalize() for s in all_steps)
    cols.append("Title")

    # Rows
    rows = []
    for r in runs:
        row = [
            r.get("run_id", "?"),
            r.get("date", "?"),
            r.get("mode", "?"),
            r.get("pipeline", "?"),
            f"{r.get('duration_s', 0):.1f}s",
        ]
        for step in all_steps:
            val = r.get("steps", {}).get(step)
            row.append(f"{val:.1f}s" if val is not None else "-")
        row.append(truncate(r.get("title", "?"), 40))
        rows.append(row)

    # Calculate column widths
    widths = [len(c) for c in cols]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    # Print
    header = " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
    separator = "-+-".join("-" * widths[i] for i in range(len(cols)))
    print(header)
    print(separator)
    for row in rows:
        print(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)))


def format_stats(runs):
    """Print summary statistics."""
    if not runs:
        print("No runs found.")
        return

    by_mode = defaultdict(list)
    by_pipeline = defaultdict(list)
    for r in runs:
        d = r.get("duration_s", 0)
        by_mode[r.get("mode", "?")].append(d)
        by_pipeline[r.get("pipeline", "?")].append(d)

    def stats_line(label, durations):
        durations.sort()
        n = len(durations)
        avg = sum(durations) / n
        median = durations[n // 2]
        return (f"  {label}: {n} runs, avg {avg:.1f}s, "
                f"median {median:.1f}s, "
                f"min {min(durations):.1f}s, max {max(durations):.1f}s")

    print(f"Total runs: {len(runs)}")
    print()
    print("By mode:")
    for mode in sorted(by_mode):
        print(stats_line(mode, by_mode[mode]))
    print()
    print("By pipeline:")
    for pipeline in sorted(by_pipeline):
        print(stats_line(pipeline, by_pipeline[pipeline]))

    # Step-level stats
    step_times = defaultdict(list)
    for r in runs:
        for step, val in r.get("steps", {}).items():
            step_times[step].append(val)

    if step_times:
        print()
        print("By step:")
        for step in sorted(step_times):
            print(stats_line(step, step_times[step]))


def main():
    parser = argparse.ArgumentParser(description="Query digest run log")
    parser.add_argument("--last", type=int, default=10,
                        help="Show last N runs (default: 10)")
    parser.add_argument("--url", default="", help="Filter by URL substring")
    parser.add_argument("--mode", default="", help="Filter by mode")
    parser.add_argument("--pipeline", default="", help="Filter by pipeline")
    parser.add_argument("--id", default="", help="Filter by run ID prefix")
    parser.add_argument("--title", default="", help="Filter by title substring")
    parser.add_argument("--stats", action="store_true",
                        help="Show summary statistics")
    parser.add_argument("--json", action="store_true",
                        help="Output raw JSON")
    parser.add_argument("--all", action="store_true",
                        help="Show all runs (no --last limit)")
    args = parser.parse_args()

    runs = load_runs()
    runs = filter_runs(runs, args)

    if args.stats:
        format_stats(runs)
        return

    if not args.all:
        runs = runs[-args.last:]

    if args.json:
        for r in runs:
            print(json.dumps(r))
    else:
        format_table(runs)


if __name__ == "__main__":
    main()
