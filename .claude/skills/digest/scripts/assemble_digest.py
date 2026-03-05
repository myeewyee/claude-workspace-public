#!/usr/bin/env python3
"""
Assemble final digest file from agent-written Key Takeaways + content.

Content-type-agnostic: works for any digest path (YouTube, blog, X/Twitter,
or future content types). Each caller provides a content file and an optional
pre-built ToC file. The assembler just appends them.

Outputs a summary line to stdout (heading count, content size).
"""

import argparse
import io
import re
import sys


def read_file(path):
    """Read file with UTF-8, falling back to latin-1 for Windows encoding issues."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except UnicodeDecodeError:
        with open(path, "r", encoding="latin-1") as f:
            return f.read()


def assemble(
    digest_path, content_text, toc_text=None, heading="Transcript",
    provenance=None,
):
    """Assemble the final digest file.

    Args:
        digest_path: Path to agent-written digest (frontmatter + Key Takeaways).
        content_text: Full content to append (transcript, article, etc.).
        toc_text: Pre-built ToC string, or None/empty to skip ToC.
        heading: H2 heading name for the content section.
        provenance: Multi-line provenance string, or None to skip.

    Returns:
        Number of headings found in content.
    """
    digest = read_file(digest_path)

    toc_text = toc_text.strip() if toc_text else ""

    # Build provenance callout if provided
    provenance_block = ""
    if provenance and provenance.strip():
        lines = ["> [!info]- Digest provenance"]
        for line in provenance.strip().splitlines():
            lines.append(f"> {line}")
        provenance_block = "\n".join(lines)

    # Count headings in content for summary
    heading_count = len(re.findall(r"^#{2,4}\s+", content_text, re.MULTILINE))

    # Assemble: digest + ToC + content
    parts = [digest.rstrip()]
    if toc_text:
        parts.append("")
        parts.append("## Table of Contents")
        parts.append(toc_text)
    parts.append("")
    parts.append(f"## {heading}")
    if provenance_block:
        parts.append(provenance_block)
    parts.append(content_text)

    result = "\n".join(parts) + "\n"

    with open(digest_path, "w", encoding="utf-8") as f:
        f.write(result)

    return heading_count


def main():
    parser = argparse.ArgumentParser(
        description="Assemble digest file from Key Takeaways + content"
    )
    parser.add_argument("digest_path", help="Agent-written digest file (frontmatter + Key Takeaways)")
    parser.add_argument("content_path", help="Content file to append (transcript, article, etc.)")
    parser.add_argument(
        "--toc",
        default=None,
        help="Pre-built ToC file. If omitted, no Table of Contents is added.",
    )
    parser.add_argument(
        "--heading",
        default="Transcript",
        help="H2 heading name for the content section (default: Transcript)",
    )
    parser.add_argument(
        "--provenance",
        default=None,
        help="Provenance metadata string (rendered as collapsed callout under heading)",
    )
    args = parser.parse_args()

    content_text = read_file(args.content_path)

    toc_text = None
    if args.toc:
        toc_text = read_file(args.toc).strip()

    # Force UTF-8 stdout on Windows
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    heading_count = assemble(
        args.digest_path, content_text, toc_text=toc_text, heading=args.heading,
        provenance=args.provenance,
    )

    # Summary for calling agent
    content_words = len(content_text.split())
    print(f"Assembled: {heading_count} headings, {content_words} words under ## {args.heading}")


if __name__ == "__main__":
    main()
