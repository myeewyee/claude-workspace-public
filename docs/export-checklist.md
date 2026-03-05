---
created: 2026-03-05 17:30
source: claude
type: artifact
parent: "[[Package workspace for external sharing via GitHub]]"
description: "Checklist for the repeatable export-to-public-repo workflow. Run through this each time you want to publish a new version of the workspace."
---
# export-checklist
**When:** After significant workspace changes you want to share publicly.
**How:** Run the steps below. The export script handles automated checks, but the deep verification step requires human + AI review.

## Pre-export
- [ ] Decide if any new skills or integrations should be showcased
- [ ] Check if README.md needs updates (new skills, changed architecture)
- [ ] Update meta-example content if packaging task has new work to show

## Export
- [ ] Run: `bash .scripts/export-public.sh --force`
- [ ] Verify security scan shows `CLEAN` (zero findings)
- [ ] If findings exist: fix in source, re-run export

## Deep verification (before first publish and after significant changes)
The automated security scan catches pattern-based leaks (paths, emails, API keys). This step catches everything it can't: business names, personal topic categories, spent scripts containing task inventories, missing docs that break references, and other contextual leaks.

- [ ] **Launch a verification agent** against the export directory with this prompt:
  > Audit this export for (1) any personal/private information that shouldn't be public, and (2) any missing files that the system references but aren't included. Read every .md file. Grep for personal names (the owner's name should appear nowhere except CLAUDE.example.md as a placeholder), business entities, health info, relationship details, vault topic categories, investment strategy names, location data that could identify a specific person. Check all cross-file references for broken links.
- [ ] Review agent findings and fix each issue in the source workspace
- [ ] Re-run export after fixes
- [ ] **Skip this step** only for minor updates where no new files were added to the export

## Manual review
- [ ] Spot-check CLAUDE.example.md: paths redacted, uses `<your-name>` placeholder
- [ ] Spot-check 2-3 skill files: paths redacted, name shows as "the user"
- [ ] Spot-check 2-3 scripts: paths redacted
- [ ] Check meta-example tasks and outputs are present in `tasks/` and `outputs/`
- [ ] **Identity check:** `grep -rni "the user" exported-dir/` returns zero (excluding CLAUDE.example.md)
- [ ] **Possessive check:** `grep -rn "the user'" exported-dir/ | grep -v "the user's"` returns zero (no broken possessives from name substitution)
- [ ] **Cross-reference check:** no combination of location + lifestyle + activity data that narrows to one person (e.g., country-specific shopping skills + city names + topic categories)

## Publish
- [ ] `cd` to export target directory
- [ ] `git add -A && git status` (review what changed)
- [ ] Commit with version tag message: `git commit -m "v2: added X skill, updated Y"`
- [ ] Tag: `git tag v<N>`
- [ ] Push: `git push && git push --tags`

## Post-publish verify
- [ ] Clone to a temp directory
- [ ] Open in VS Code with Claude Code
- [ ] Ask Claude: "Explain how this workspace works"
- [ ] Verify Claude can navigate using CLAUDE.md, skills, and docs
- [ ] Run the external audit prompt below in a **separate, clean workspace** (not this one)

### External audit prompt
Run this in a fresh Claude Code session pointed at a clone of the public repo. Copy the block below as-is:

> Read every file in this repository. This is a public GitHub repo at github.com/<your-github-username>/claude-workspace-public. Perform two analyses and write the results to a single file called `Claude workspace public - analysis yyyy-mm-dd vX.X.md`:
>
> **1. Privacy Audit**
> - Search every file for PII patterns: names, email addresses, API keys, hardcoded paths, location data, personal references
> - Check for data that could be cross-referenced to identify a specific person (travel plans, timestamps, project names)
> - Check the export/redaction logic itself for leaking what it was trying to redact
> - Rate each finding by severity (High/Medium/Low) with specific recommendations
>
> **2. Outside Perspective**
> - What is this project, in one paragraph?
> - Who would actually benefit from this? Be honest.
> - What's genuinely novel vs what's overengineered or redundant?
> - If you cloned this and tried to set it up from scratch, how far would you get? Where would you hit walls? Be specific about which steps would fail and why.
> - What's the main gap in the documentation?
>
> Be direct. No flattery. Flag everything you find.
