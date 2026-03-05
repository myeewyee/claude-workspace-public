---
type: task
source: claude
created: 2026-03-05 16:48
status: 5-done
description: "Package the Claude Code workspace for external sharing via GitHub. Separate public repo with automated export, meta-examples, dual CLAUDE.md, and guided-tour README."
decision: "Whitelist export with global redaction, meta-examples as content strategy"
parent:
focus: external
category: feature
pillar:
completed: 2026-03-05
---
# Package workspace for external sharing
## Context
**Trigger:** A friend asked for a walkthrough of the workspace, which exposed the question: is the system self-descriptive enough that someone else's Claude could explain it?

**Scope:** Two threads: (1) making the workspace understandable to an external audience, and (2) packaging it for GitHub.
## Links
### Related
- This task's own outputs serve as the meta-examples for the public repo
## Success Criteria
- A stranger's Claude can clone the public repo and explain how the system works
- No personal data leaks (profile, personal tasks/outputs, API keys, vault paths with username)
- Export script is idempotent and repeatable for future releases
- README provides a self-contained guided tour
- Real meta-example content demonstrates the system working
## Design
### Decisions
1. **Separate public repo** - clean export, private workspace untouched
2. **Small audience showcase** - not mass adoption template, not single-person only
3. **Meta-examples** - the repo's own packaging tasks serve as example content
4. **Core + showcase integrations** - task engine, skills, hooks, docs, plus interesting integrations (travel, shop, digest) with "you need API key X" notes
5. **Dual CLAUDE.md** - `CLAUDE.md` (minimal starter) + `CLAUDE.example.md` (real production config, redacted paths)
6. **Script + checklist, not a skill** - runs infrequently, mechanical process
### Export Script (`export-public.sh`)
Whitelist-based: explicitly copies what we want rather than stripping what we don't.
- Copies system infrastructure (skills, hooks, task engine, MCP server, docs, scripts)
- Generates CLAUDE.example.md with automatic path redaction
- Runs global redaction pass on all exported files
- Security scan catches any remaining personal data
- Idempotent: re-run anytime to refresh
## Approach
1. Build export script (whitelist-based, with redaction and security scan)
2. Write starter CLAUDE.md and README.md guided tour
3. Write export checklist for repeatable releases
4. Create meta-example content (this task itself)
5. Run first export, security review, push v1
## Work Done
- Built `export-public.sh`: whitelist copy, path redaction, security scan
- Wrote starter `CLAUDE.md`: minimal config pointing to CLAUDE.example.md
- Wrote `README.md`: system diagram, key concepts, showcase skills, getting started
- Wrote `docs/export-checklist.md`: repeatable release workflow
- Created meta-example task and output files
- First export: 116 files, security scan clean after redaction pass
## Progress Log
### 2026-03-05
5:30 PM **First clean export** - 116 files, security scan clean after global redaction pass

5:19 PM **Brainstorm complete: design settled** - separate repo, meta-examples, core + showcase integrations, dual CLAUDE.md, script + checklist

4:48 PM *Status: Active*
