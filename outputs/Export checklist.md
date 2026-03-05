---
created: 2026-03-05 17:30
source: claude
type: artifact
parent: "[[Package workspace for external sharing]]"
description: "Checklist for the repeatable export-to-public-repo workflow. Demonstrates the output file convention with frontmatter, parent linking, and context block."
---
# Export checklist
**When:** After significant workspace changes you want to share publicly.
**How:** Run the steps below. The export script handles most of the work.

## Pre-export
- [ ] Decide if any new skills or integrations should be showcased
- [ ] Check if README.md needs updates (new skills, changed architecture)
- [ ] Update meta-example content if packaging task has new work to show

## Export
- [ ] Run: `bash .scripts/export-public.sh --force`
- [ ] Verify security scan shows `CLEAN` (zero findings)
- [ ] If findings exist: fix in source, re-run export

## Review
- [ ] Spot-check CLAUDE.example.md: paths redacted, no personal references
- [ ] Spot-check 2-3 skill files: paths redacted
- [ ] Spot-check 2-3 scripts: paths redacted
- [ ] Check meta-example tasks and outputs are present

## Publish
- [ ] `cd` to export target directory
- [ ] `git add -A && git status` (review what changed)
- [ ] Commit with version tag message
- [ ] Tag: `git tag v<N>`
- [ ] Push: `git push && git push --tags`

## Verify
- [ ] Clone to a temp directory
- [ ] Open in VS Code with Claude Code
- [ ] Ask Claude: "Explain how this workspace works"
- [ ] Verify Claude can navigate using CLAUDE.md, skills, and docs
