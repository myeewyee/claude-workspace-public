---
type: task
source: claude
created: 2026-02-28 12:50
status: 5-done
description: "Build a skill-creator skill for this workspace, informed by Anthropic's official skill-creator. Establishes: documented folder structure convention (SKILL.md + scripts/ + references/ + assets/), quality criteria (behavior per token, 500-line threshold, progressive disclosure), and an iterative test/eval loop for validating new skills before shipping."
decision:
parent:
focus: internal
category: feature
pillar: workflow
completed: 2026-03-03 21:00
---
# Build skill-creator skill
## Context
Surfaced during [[Add instruction file refactoring habit and audit]] while reviewing the digest SKILL.md efficiency gains (736 to 149 lines) and researching Anthropic's official skill-creator at `https://github.com/anthropics/skills/blob/main/skills/skill-creator/SKILL.md`.

Two gaps identified: (1) no documented folder structure convention for skills in this workspace, `task/` uses `modes/`, `digest/` uses `prompts/`, scripts sit at skill root rather than in `scripts/` subfolder; (2) no quality criteria or creation guide, so skills accumulate bloat without an efficiency baseline.

Anthropic's skill-creator covers both: progressive disclosure model (metadata/body/bundled resources), 500-line SKILL.md threshold, test/eval loop with grader subagents, description optimization for trigger reliability.
## Links
### Related
- [[Add instruction file refactoring habit and audit]] : child task, established refactoring habit and audited existing skills
- [[Split digest SKILL.md into routing file and per-pipeline agent prompts]] : triggering event, showed 80% reduction was possible
- [[Build travel skill]] : exposed the brainstorm competition gap that triggered this reopen
### Subtasks
```base
filters:
  and:
    - type == "task"
    - parent == "[[Build skill-creator skill]]"
properties:
  file.name:
    displayName: Subtask
  status:
    displayName: Status
  description:
    displayName: Description
views:
  - type: table
    name: Subtasks
    order:
      - file.mtime
      - status
      - file.name
    sort:
      - property: file.mtime
        direction: DESC
    indentProperties: false
    markers: none
    columnSize:
      file.mtime: 175

```
### Outputs
```base
filters:
  and:
    - type == "artifact"
    - parent == "[[Build skill-creator skill]]"
properties:
  file.name:
    displayName: Output
  description:
    displayName: Description
  created:
    displayName: Created
views:
  - type: table
    name: Outputs
    order:
      - file.mtime
      - file.name
    sort:
      - property: file.mtime
        direction: DESC
      - property: created
        direction: ASC
    indentProperties: false
    markers: none
    columnSize:
      file.mtime: 175

```
## Success Criteria
- Canonical folder structure convention documented and enforced at creation time
- Quality criteria defined with principle (minimum tokens that produce intended behavior) and hard limit (500 lines)
- Creation process is a mandatory 5-step workflow: intent, draft, test, refactor, ship
- Ongoing audit integrated into `/task review` cadence
- Workspace-specific rules covered: placement decision tree, output file conventions, vault path rule
- Existing skills (digest, ingest, task) brought into conformance with new convention
## Design
### Architecture
Reference skill with lightweight interactive mode. Passive: fires when creating a new skill (via brainstorm gate or explicit invocation). Active (`/skill-creator <name>`): interactive creation wizard.

Single file: `.claude/skills/skill-creator/SKILL.md` (~150 lines). No scripts needed, creation process is conversational.

Not adopted from Anthropic's version: browser-based review viewer, grader subagent pipeline, Cowork/Claude.ai platform sections, automated description optimization loop.
### Folder structure convention
```
.claude/skills/skill-name/
  SKILL.md              # Required. Frontmatter + instructions.
  scripts/              # Executable code Claude runs via Bash
  references/           # All on-demand docs: agent prompts, mode files, reference docs
  assets/               # Templates, static files used in output
```

Rules:
- Scripts always in `scripts/`, never at skill root
- All on-demand markdown docs go in `references/` (replaces `prompts/`, `modes/`)
- No nesting within subfolders (one level deep only)
- SKILL.md must have `name:` and `description:` frontmatter

Complexity tiers:
- **Simple:** SKILL.md only (autonomous, brainstorming, research, using-skills)
- **Medium:** SKILL.md + `scripts/` or `references/` (ingest)
- **Complex:** SKILL.md + both (digest)
### Quality criteria
**Principle:** Minimum tokens that produce the intended behavior. Every line should change what Claude does. If removing it doesn't change behavior, remove it.

**Hard limit:** 500 lines. Approaching this forces structural intervention: move content to `references/`, add progressive disclosure.
### Creation process
1. **Capture intent** : what does it do, when does it trigger, what does success look like? Also: does this belong as a skill, CLAUDE.md rule, or per-prompt-rules gate?
2. **Set up structure** : pick tier, create folder, add frontmatter stub
3. **Draft SKILL.md** : imperative form, explain the why, reference supporting files
4. **Test** : define 5-10 prompts (should-trigger + should-not-trigger), run fresh session, evaluate qualitatively
5. **Refactor and ship** : cut everything that doesn't change behavior, move on-demand content to `references/`, verify under 500 lines
## Approach
1. Write `skill-creator/SKILL.md` using the design above
2. Migrate existing skills to conform: move digest scripts to `scripts/`, rename `prompts/` and `modes/` to `references/`, add frontmatter to `task/SKILL.md`
3. Add skill audit to `/task review` checklist
## Work Done
- Created `.claude/skills/skill-creator/SKILL.md` (121 lines): placement decision tree, folder structure convention with tier table, quality criteria, 5-step creation process, ongoing audit section, workspace-specific rules
- Migrated digest skill: created `scripts/` subfolder and moved all 7 Python scripts; renamed `prompts/` to `references/`; moved `batch.md` and `reference.md` into `references/`; updated all path references in SKILL.md
- Migrated ingest skill: created `scripts/` subfolder and moved `extract_pages.py` and `combine_transcriptions.py`; updated both path references in SKILL.md
- Migrated task skill: added YAML frontmatter to SKILL.md; renamed `modes/` to `references/`; updated 2 path references
- Added step 4 "Skill line count audit" to `task/references/review.md`
- **Convention alignment audit (reopened 2026-03-03):**
  - Step 1: replaced standalone "Capture intent" with explicit delegation to `/brainstorm`, establishing clear lane boundaries (brainstorm owns design, skill-creator owns structure/quality)
  - Added task gate prerequisite before Step 1
  - Replaced inline workspace rule summaries with cross-references to source docs
  - Step 5: added documentation registration (`docs/systems.md`) and captain's log check
  - Enriched audit section with description-drift, reference-validity, and systems-index checks
## Progress Log
### 2026-03-03
9:00 PM *Status -> Done*

8:54 PM **Convention alignment fixes applied** (7 gaps from audit)
- Step 1: replaced "Capture intent" with delegation to /brainstorm
- Added task gate prerequisite before creation process
- Replaced inline workspace rules with cross-references to source docs
- Step 5: added docs registration (systems.md) and captain's log check
- SKILL.md: 122 -> 125 lines (net +3 lines, replaced inline summaries with pointers)

8:52 PM **Reopened for convention alignment audit**
- Triggered by improvement log flag: skill-creator Step 1 competes with /brainstorm

8:52 PM *Status -> Active (reopened)*
### 2026-02-28
2:36 PM *Status -> Done*

2:36 PM **Implementation complete**
- Created skill-creator/SKILL.md (121 lines)
- Migrated digest, ingest, and task skills to new convention
- Added skill line count audit to task/references/review.md

2:08 PM **Brainstorm complete, design validated**
- Researched Anthropic's skill-creator (fork-and-adapt verdict)
- Ran workspace audit
- Designed 5 sections: architecture, folder convention, quality criteria, creation process, workspace-specific rules

1:03 PM *Status -> In Progress*

12:53 PM Promoted from idea to pending.

12:50 PM *Status -> Idea (task created)*
