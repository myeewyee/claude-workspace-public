#!/usr/bin/env python3
"""Combine batch OCR transcription files into a single raw transcription.

Reads batch_*.md files from a work directory, merges them in page order,
detects dates, guesses content type, and writes a single output file with
proper frontmatter, context block, and summary for human review.

Input:  work_dir (positional), --output (file path), --pdf-name (display name),
        --parent (parent task name)
Output: JSON to stdout with output_path, page_count, dates_found, content_type_guess
Progress messages go to stderr.
"""

import argparse
import io
import json
import os
import re
import sys
from datetime import datetime

# Date patterns commonly found in handwritten journals
DATE_PATTERNS = [
    # "Fri 1/11/24", "Sun 3/11/24", "Mon 4/11/24"
    r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+\d{1,2}/\d{1,2}/\d{2,4}\b',
    # "Thursday 25th Dec", "Monday 5th Jan"
    r'\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\w*\s+\d{1,2}(?:st|nd|rd|th)\s+\w+\b',
    # "2024-11-01", "2023-02-15"
    r'\b\d{4}-\d{2}-\d{2}\b',
    # "1 November 2024", "25 December"
    r'\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s*\d{0,4}\b',
]

BATCH_METADATA_RE = re.compile(
    r'\s*<!--\s*BATCH_METADATA\b.*?-->\s*', re.DOTALL
)


def find_dates(text):
    """Extract all date-like strings from text."""
    dates = []
    for pattern in DATE_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        dates.extend(matches)
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for d in dates:
        d_lower = d.strip().lower()
        if d_lower not in seen:
            seen.add(d_lower)
            unique.append(d.strip())
    return unique


def guess_content_type(dates_found, text, page_count):
    """Guess content type based on date frequency and text patterns."""
    date_density = len(dates_found) / max(page_count, 1)

    if date_density >= 0.3:
        return "daily journal (frequent date entries)"
    elif date_density >= 0.1:
        return "journal or dated notes (some date entries)"
    elif re.search(r'chapter|table of contents|introduction|conclusion', text, re.IGNORECASE):
        return "book notes or structured document"
    elif re.search(r'trade|position|P&L|profit|loss|entry|exit', text, re.IGNORECASE):
        return "trading journal"
    else:
        return "unknown (review needed)"


def clean_heading_spacing(text):
    """Remove blank lines around markdown headings.

    Convention: headings are visual separators, no blank lines around them.
    Preserves blank lines between non-heading content paragraphs.
    """
    lines = text.split("\n")
    result = []
    for i, line in enumerate(lines):
        is_heading = line.startswith("#")
        prev_is_heading = result and result[-1].startswith("#")
        prev_blank = result and result[-1] == ""

        if is_heading and prev_blank:
            # Remove blank line before heading
            result[-1] = line
        elif line == "" and prev_is_heading:
            # Skip blank line after heading
            continue
        else:
            result.append(line)

    # Remove trailing blank lines
    while result and result[-1] == "":
        result.pop()

    return "\n".join(result)


def combine(work_dir, output_path, pdf_name, parent):
    """Combine batch files into a single transcription."""
    # Find and sort batch files
    batch_files = sorted(
        [f for f in os.listdir(work_dir) if f.startswith("batch_") and f.endswith(".md")]
    )

    if not batch_files:
        raise FileNotFoundError(f"No batch_*.md files found in {work_dir}")

    print(f"Found {len(batch_files)} batch files", file=sys.stderr)

    # Read and combine, stripping batch metadata comments
    sections = []
    for bf in batch_files:
        path = os.path.join(work_dir, bf)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read().strip()
        # Strip BATCH_METADATA HTML comments
        content = BATCH_METADATA_RE.sub("", content).strip()
        sections.append(content)
        print(f"  Read {bf}: {len(content)} chars", file=sys.stderr)

    combined_text = "\n\n".join(sections)

    # Detect dates and guess content type
    dates_found = find_dates(combined_text)
    content_type = guess_content_type(dates_found, combined_text, len(batch_files) * 5)

    # Count approximate pages (batch files contain page markers)
    page_markers = re.findall(r'#+\s*Page\s+\d+', combined_text)
    page_count = len(page_markers) if page_markers else len(batch_files) * 5

    # Build date range string
    date_range = ""
    if dates_found:
        if len(dates_found) == 1:
            date_range = dates_found[0]
        else:
            date_range = f"{dates_found[0]} to {dates_found[-1]}"

    # Build output with proper frontmatter and context block
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    # Derive display name (strip .pdf extension for title)
    display_name = pdf_name.replace(".pdf", "")

    header = f"""---
created: {now}
description: "Raw OCR transcription of {display_name} ({page_count} pages). {f'Covers {date_range}. ' if date_range else ''}Content type: {content_type}. Pending human review before formatting into vault notes."
parent: '[[{parent}]]'
source: claude
type: artifact
---
# {display_name} - raw transcription (temp)
**Context:**
**Why:** Raw OCR output from the `/ingest` pipeline on [[{parent}]]. Review in Obsidian alongside the source PDF, fix errors, then tell Claude to proceed with formatting.
**When:** {now[:10]}. Source PDF: `{pdf_name}` ({page_count} pages{f', {date_range}' if date_range else ''}).

**Summary (auto-generated):**
- **Pages:** {page_count}
- **Dates found:** {len(dates_found)} ({date_range or 'none detected'})
- **Content type guess:** {content_type}

"""

    # Clean heading spacing in the combined transcription
    cleaned_text = clean_heading_spacing(combined_text)

    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        f.write(cleaned_text)
        f.write("\n")

    print(f"Written to {output_path}", file=sys.stderr)

    return {
        "output_path": output_path.replace("\\", "/"),
        "page_count": page_count,
        "dates_found": dates_found[:20],
        "date_range": date_range,
        "content_type_guess": content_type,
    }


def main():
    parser = argparse.ArgumentParser(description="Combine batch OCR transcriptions")
    parser.add_argument("work_dir", help="Directory containing batch_*.md files")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--pdf-name", default="Unknown PDF", help="PDF filename for summary header")
    parser.add_argument("--parent", default="Ingest scanned journals into vault",
                        help="Parent task name for frontmatter")
    args = parser.parse_args()

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    try:
        if not os.path.isdir(args.work_dir):
            raise FileNotFoundError(f"Work directory not found: {args.work_dir}")

        result = combine(args.work_dir, args.output, args.pdf_name, args.parent)
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
