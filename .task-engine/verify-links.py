#!/usr/bin/env python3
"""
Verify ## Links template migration integrity.

Two modes:
  --capture    Capture before-state metrics to a JSON file
  --verify     Compare current state against captured metrics

Checks:
1. YAML frontmatter still valid (parseable)
2. No content loss (line count only increased)
3. Structure intact (## Links, ### Subtasks, ### Outputs, ### Related present)
4. Task names correct (Bases query name matches H1 heading)
5. Related wiki-links preserved (count matches before/after)
6. No duplicate ## Links sections
7. ## Progress Log still present (not eaten by insertion)
"""

import argparse
import json
import os
import re
import sys

TASK_DIRS = ["tasks", "tasks/archive", "tasks/ideas"]
METRICS_FILE = ".task-engine/links-migration-metrics.json"


def find_task_files(base_dir):
    """Find all task markdown files."""
    files = []
    for task_dir in TASK_DIRS:
        full_dir = os.path.join(base_dir, task_dir)
        if os.path.isdir(full_dir):
            for fname in os.listdir(full_dir):
                if fname.endswith('.md'):
                    files.append(os.path.join(full_dir, fname))
    return sorted(files)


def count_wiki_links_in_related(content):
    """Count [[wiki-links]] in the Related section (## or ###)."""
    # Find ## Related or ### Related
    match = re.search(r'^#{2,3} Related\s*$', content, re.MULTILINE)
    if not match:
        return 0

    # Get content from Related heading to next heading
    start = match.end()
    next_heading = re.search(r'^#{1,3} [^#]', content[start:], re.MULTILINE)
    if next_heading:
        section = content[start:start + next_heading.start()]
    else:
        section = content[start:]

    return len(re.findall(r'\[\[([^\]]+)\]\]', section))


def get_h1_title(content):
    """Extract H1 title from content."""
    match = re.search(r'^# (.+)$', content, re.MULTILINE)
    return match.group(1).strip() if match else None


def has_valid_frontmatter(content):
    """Check if YAML frontmatter is parseable (basic check)."""
    if not content.startswith('---'):
        return False
    end = content.find('---', 3)
    return end > 3


def get_all_headings(content):
    """Get all markdown headings with their levels."""
    return re.findall(r'^(#{1,6}) (.+)$', content, re.MULTILINE)


def capture_metrics(base_dir):
    """Capture before-state metrics for all task files."""
    files = find_task_files(base_dir)
    metrics = {}

    for filepath in files:
        relpath = os.path.relpath(filepath, base_dir)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            metrics[relpath] = {
                "line_count": content.count('\n') + 1,
                "related_wiki_links": count_wiki_links_in_related(content),
                "has_related": bool(re.search(r'^## Related\s*$', content, re.MULTILINE)),
                "has_links": bool(re.search(r'^## Links\s*$', content, re.MULTILINE)),
                "has_progress_log": bool(re.search(r'^## Progress Log\s*$', content, re.MULTILINE)),
                "h1_title": get_h1_title(content),
                "valid_frontmatter": has_valid_frontmatter(content),
                "heading_count": len(get_all_headings(content)),
            }
        except Exception as e:
            metrics[relpath] = {"error": str(e)}

    metrics_path = os.path.join(base_dir, METRICS_FILE)
    with open(metrics_path, 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)

    print(f"Captured metrics for {len(metrics)} files -> {METRICS_FILE}")
    return metrics


def verify_migration(base_dir):
    """Verify migration integrity against captured metrics."""
    metrics_path = os.path.join(base_dir, METRICS_FILE)
    if not os.path.exists(metrics_path):
        print("ERROR: No before-metrics found. Run --capture first.")
        sys.exit(1)

    with open(metrics_path, 'r', encoding='utf-8') as f:
        before = json.load(f)

    files = find_task_files(base_dir)
    issues = []
    stats = {"checked": 0, "passed": 0, "skipped_stubs": 0, "issues": 0}

    for filepath in files:
        relpath = os.path.relpath(filepath, base_dir)
        before_data = before.get(relpath, {})

        if "error" in before_data:
            continue

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception as e:
            issues.append(f"  CANT_READ: {relpath}: {e}")
            stats["issues"] += 1
            continue

        stats["checked"] += 1

        # Skip stub files (no H1, minimal content)
        if before_data.get("h1_title") is None:
            stats["skipped_stubs"] += 1
            continue

        file_issues = []

        # Check 1: Valid frontmatter
        if not has_valid_frontmatter(content):
            file_issues.append("Broken frontmatter")

        # Check 2: No content loss (line count should increase or stay same)
        current_lines = content.count('\n') + 1
        before_lines = before_data.get("line_count", 0)
        if current_lines < before_lines:
            file_issues.append(f"Lost lines: {before_lines} -> {current_lines} (lost {before_lines - current_lines})")

        # Check 3: Structure - if file was updated (had no ## Links before), check new sections
        had_links_before = before_data.get("has_links", False)
        has_links_now = bool(re.search(r'^## Links\s*$', content, re.MULTILINE))

        if not had_links_before and has_links_now:
            # Was updated - verify full structure
            if not re.search(r'^### Subtasks\s*$', content, re.MULTILINE):
                file_issues.append("Missing ### Subtasks")
            if not re.search(r'^### Outputs\s*$', content, re.MULTILINE):
                file_issues.append("Missing ### Outputs")
            if not re.search(r'^### Related\s*$', content, re.MULTILINE):
                file_issues.append("Missing ### Related")

            # Check 4: Task name in Bases query matches H1
            h1 = get_h1_title(content)
            if h1:
                expected_pattern = f'parent == "[[{re.escape(h1)}]]"'
                bases_matches = re.findall(r'parent == "\[\[(.+?)\]\]"', content)
                for match in bases_matches:
                    if match != h1:
                        file_issues.append(f"Query name mismatch: H1='{h1}' but query has '{match}'")
                        break

            # Check 5: Related wiki-links preserved
            current_related_links = count_wiki_links_in_related(content)
            before_related_links = before_data.get("related_wiki_links", 0)
            if current_related_links < before_related_links:
                file_issues.append(f"Lost Related links: {before_related_links} -> {current_related_links}")

            # Check 6: No duplicate ## Links
            links_count = len(re.findall(r'^## Links\s*$', content, re.MULTILINE))
            if links_count > 1:
                file_issues.append(f"Duplicate ## Links sections: {links_count}")

        # Check 7: Progress Log still present (if it was before)
        if before_data.get("has_progress_log"):
            if not re.search(r'^## Progress Log\s*$', content, re.MULTILINE):
                file_issues.append("Lost ## Progress Log")

        if file_issues:
            stats["issues"] += 1
            for issue in file_issues:
                issues.append(f"  FAIL: {relpath}: {issue}")
        else:
            stats["passed"] += 1

    # Report
    print("=== Links Migration Verification ===\n")

    if issues:
        print("ISSUES FOUND:\n")
        for issue in issues:
            print(issue)
        print()

    print(f"Files checked: {stats['checked']}")
    print(f"  Passed: {stats['passed']}")
    print(f"  Skipped (stubs): {stats['skipped_stubs']}")
    print(f"  Issues: {stats['issues']}")

    if stats["issues"] == 0:
        print("\nVERIFICATION PASSED. All files intact.")
        return True
    else:
        print(f"\nVERIFICATION FAILED. {stats['issues']} file(s) have issues.")
        print("Run: git checkout -- tasks/ to revert all changes.")
        return False


def main():
    parser = argparse.ArgumentParser(description="Verify Links migration integrity")
    parser.add_argument('--capture', action='store_true', help='Capture before-state metrics')
    parser.add_argument('--verify', action='store_true', help='Verify against captured metrics')
    args = parser.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.dirname(script_dir)

    if args.capture:
        capture_metrics(base_dir)
    elif args.verify:
        success = verify_migration(base_dir)
        sys.exit(0 if success else 1)
    else:
        print("Usage: --capture (before migration) or --verify (after migration)")
        sys.exit(1)


if __name__ == "__main__":
    main()
