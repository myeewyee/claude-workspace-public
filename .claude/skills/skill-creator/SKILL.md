---
name: skill-creator
description: Build, test, and maintain Claude skills for this workspace. Use when creating a new skill, auditing an existing skill for bloat, or deciding where behavior belongs (skill vs. CLAUDE.md rule vs. hook). Fires automatically via brainstorm gate when skill creation work begins.
---

# Skill Creator

Guide for building, testing, and maintaining skills in this workspace. Adapted from Anthropic's official skill-creator with platform-specific sections removed and workspace conventions added.

## Before You Build: Placement Decision

Ask first — does this behavior belong as a skill?

| Where | Use when |
|-------|----------|
| **Skill** | On-demand, scoped behavior. User-facing action or methodology invoked by name or triggered by context. |
| **CLAUDE.md rule** | Always-on knowledge or constraint that applies to everything (vault read-only, output file format, workspace patterns). |
| **per-prompt-rules gate** | Mandatory cross-cutting enforcement that must fire on every turn regardless of context (implementation gate, brainstorm gate). |
| **Hook injection** | Content that must always load at session start or per-prompt, independent of skill triggering. |

If you find yourself putting mandatory enforcement language in a skill description, it belongs in a hook. If you're putting always-on knowledge in a skill body, it belongs in CLAUDE.md.

## Folder Structure

```
.claude/skills/skill-name/
├── SKILL.md              # Required. Frontmatter + instructions.
├── scripts/              # Executable code Claude runs via Bash
├── references/           # All on-demand docs: agent prompts, mode files, reference docs
└── assets/               # Templates, static files used in output
```

**Rules:**
- Scripts always go in `scripts/`. Never at skill root.
- All on-demand markdown docs go in `references/` — agent prompts, mode-specific files, reference docs. One concept, one folder.
- No nesting within subfolders. One level deep only.
- SKILL.md must have `name:` and `description:` frontmatter. No exceptions.
- Every supporting file must be explicitly referenced in SKILL.md with what it contains and when to load it. Unreferenced files are invisible to Claude.

**Complexity tiers — pick before building:**

| Tier | When | Structure |
|------|------|-----------|
| Simple | Conversational skill, no scripts or reference docs | SKILL.md only |
| Medium | Scripts or reference docs, not both | SKILL.md + `scripts/` or `references/` |
| Complex | Scripts and reference docs, or many agent prompts | Full structure |

## Quality Criteria

**Principle:** Minimum tokens that produce the intended behavior. Every line should change what Claude does. If removing it doesn't change behavior, remove it.

**Hard limit:** 500 lines. Approaching this forces a structural intervention — move content to `references/`, add progressive disclosure. 500 is the ceiling, not the target.

**Description:**
- Third person ("Processes X" not "I help you with X")
- States both what it does AND when to use it
- Specific enough to discriminate from adjacent skills
- Slightly pushy: list the contexts where it applies rather than understating them
- Descriptions from all skills share a ~16,000-character context budget — verbose descriptions crowd out others

**Writing:**
- Imperative form: "Run X", "Check Y" — not "You should run X"
- Explain the why behind rules, not just the rule. Claude needs intent to generalize correctly.
- No ALL-CAPS constraints. If you're writing ALWAYS or NEVER, rewrite the rule with reasoning instead.
- Don't overfit: instructions should work across varied inputs, not just the case you tested.

**Structure:**
- Every supporting file referenced in SKILL.md with a note on what it contains and when to load it
- Large reference files (>100 lines) get a table of contents

## Creation Process

**Prerequisite:** A task must be 1-active before starting. If no task exists, invoke `/task new` + `/task start`. The implementation gate applies to skill creation just like any other work.

### Step 1: Design via brainstorm
Invoke `/brainstorm`. The brainstorming skill handles intent capture, context alignment (vault search for related work), design exploration (2-3 approaches with trade-offs), and incremental design validation. Skill-creator picks up at Step 2 once the design is settled.

During brainstorm, also answer: does this belong as a skill, CLAUDE.md rule, per-prompt-rules gate, or hook? (See placement table above.) If the answer is "not a skill," stop here.

### Step 2: Set up structure
Pick a tier (simple/medium/complex). Create the folder. Add a frontmatter stub with `name:` and `description:` placeholder.

### Step 3: Draft SKILL.md
Write instructions in imperative form. Explain the why. Reference any supporting files explicitly with their path and purpose.

### Step 4: Test
Define 5-10 test prompts in two groups:
- **Should trigger:** varied phrasings of the intended use case, not just the obvious invocation
- **Should NOT trigger:** adjacent requests that might accidentally match

Open a fresh session. Check: does it trigger on the right things? Does the behavior match intent? Fix and re-test until both groups pass. Qualitative review is sufficient at this scale.

### Step 5: Refactor, register, and ship
Run the refactor pass before shipping:
- Cut everything that doesn't change behavior
- Move on-demand content to `references/`
- Verify under 500 lines
- Verify every supporting file is referenced

Then register:
- Add the skill to `docs/systems.md` (the workspace's central index)
- If design decisions were made during brainstorm/build, verify a captain's log entry exists (`context/captains-log.md`)

Only after both passes is the skill done.

## Modification Process

The Creation Process above covers building new skills. This section covers modifying, refactoring, or restructuring existing skills. The brainstorm gate (per-prompt-rules) determines when brainstorming is needed. This process defines what to do during that brainstorm when the subject is an existing skill.

### Step M-1: Read the architecture principle
Check the skill's SKILL.md for a documented architecture principle (a brief statement of what belongs in the routing file vs. reference files). If one exists, it frames the brainstorm. If not, defining one becomes the first design decision.

### Step M-2: Categorize before moving
Audit every section in the current SKILL.md into buckets:
- **Always-loaded:** routing, classification logic, shared rules, reporting
- **Conditional:** only needed for specific paths or modes
- **Reference:** lookup tables, error handling, examples, step-by-step procedures
- **Duplicate:** already covered by CLAUDE.md, MEMORY.md, or other files

Move nothing until categorization is complete.

### Step M-3: State or validate the design principle
Write one sentence: what stays in SKILL.md and why. Examples from prior work: "routing for orchestration, prompts read on demand" (digest), "SKILL.md becomes a slim router" (task). The principle must be specific enough that future additions can be classified against it.

### Step M-4: Execute in passes
Don't restructure all at once. Each pass should be independently verifiable:
1. Split: move content to reference files based on the categorization
2. Deduplicate: collapse repeated patterns, remove content covered elsewhere
3. Extract conditional: move content only needed for specific paths

Not every modification needs all three passes. Stop when the principle is satisfied.

### Step M-5: Document the principle in the skill
Add or update a brief architecture note in the skill's SKILL.md. This is grow-back prevention: not a gate (the brainstorm gate handles enforcement), but visible context so the next brainstorm has a criterion to evaluate against. One to two lines, placed after the skill's introductory paragraph.

## Ongoing Audit

Skill bloat accumulates even with the creation refactor pass. The `/task review` checklist (step 4 in `task/references/review.md`) includes:
- Line count per skill: flag any over 400 lines for refactor review
- Last-modified check: if a skill has grown since last review, a refactor pass is due
- Description drift: does the description still match actual behavior? Descriptions control triggering, so drift means wrong-triggering.
- Reference validity: do all files referenced in SKILL.md still exist? Unreferenced files are invisible; missing referenced files cause silent failures.
- Systems index: is the skill registered in `docs/systems.md`?

## Workspace Conventions

Skills don't exist in isolation. These conventions apply during skill creation and to the skills you build:

- **Vault boundary:** `<your-vault-name>/1. Vault/` is read-only. `2. Claude/` is writable.
- **Output files:** See CLAUDE.md "Output Workflow" for temp vs permanent, frontmatter, and placement rules.
- **Subagent prompts:** Read `docs/agent-output-convention.md` for the relay spec (frontmatter, context block, date, parent). Subagents cannot read CLAUDE.md, so conventions must be relayed in the prompt.
- **Frontmatter:** See [[Vault frontmatter conventions]] for schemas (task, output, context files).
- **Markdown formatting:** See `docs/markdown-formatting.md` for heading spacing, table rules, and line break conventions.
- **Systems index:** `docs/systems.md` is the central registry. New skills must be registered there.
