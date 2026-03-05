---
name: brainstorming
description: You MUST use this before any creative work - designing features, building components, adding functionality, or modifying behavior. Also fires when starting a task with unclear scope (rough notes, TBD approach, inferred success criteria). Explores user intent, requirements and design before implementation.
---

# Brainstorming Ideas Into Designs

## Overview

Help turn ideas into fully formed designs and specs through natural collaborative dialogue.

Start by understanding the current project context, then ask questions one at a time to refine the idea. Once you understand what you're building, present the design in small sections (200-300 words), checking after each section whether it looks right so far.

## The Process

**Before starting (task gate):**
- **Task exists, 2-paused or 3-idea:** invoke `/task start` to move it to 1-active. Brainstorming IS working on the task.
- **Task exists, already 1-active:** proceed.
- **No task exists:** ask "This is shaping up into real work. Want me to create a task for it?" If yes, invoke `/task new` + `/task start` before continuing. If no, proceed without a task (some brainstorms are purely exploratory).

**Context alignment (before asking questions):**
Run the unified context alignment gate. Read `.claude/skills/task/references/context-alignment.md` for the full procedure. Check the task's `context-aligned:` frontmatter field: empty → full alignment (agent-based search + deep reading + Context enrichment), populated → light refresh (re-run search, diff against Related, flag new items). This is not skippable. "We already discussed the landscape" is rationalization.

**Understanding the idea:**
- Ask questions one at a time to refine the idea
- Prefer multiple choice questions when possible, but open-ended is fine too
- Only one question per message - if a topic needs more exploration, break it into multiple questions
- Focus on understanding: purpose, constraints, success criteria

**Exploring approaches:**
- Propose 2-3 different approaches with trade-offs
- Present options conversationally with your recommendation and reasoning
- Lead with your recommended option and explain why
- **Test before committing at scale:** If the decision involves significant volume (batch processing, model selection, format choices for hundreds+ items), suggest a small comparative test. Run 5-10 items through competing approaches and produce a side-by-side comparison. The initiative to test should come from Claude.

**Presenting the design:**
- Once you believe you understand what you're building, present the design
- Break it into sections of 200-300 words
- Ask after each section whether it looks right so far
- Cover: architecture, components, data flow, error handling, testing
- Be ready to go back and clarify if something doesn't make sense

## After the Design

**Documentation:**
- Add the validated design as a `## Design` section in the task document
- **Check task name:** Does the name still match the settled design? Original names are often written before the solution is understood. If the brainstorm shifted the framing (e.g., disproved the vault-lookup approach, changed the mechanism), rename the task now. Rename via: `mv "tasks/Old Name.md" "tasks/New Name.md"` + update the H1 heading in the file. Do this before implementation — after the design is settled is the best moment, not mid-build.
- If no task was created during the "Before starting" gate and the design warrants one, ask again now

**Implementation (default: continue):**
- Proceed directly to plan mode (EnterPlanMode) with the task doc as the foundation
- the user will say when he wants to stop. Don't ask for permission to continue.

## Key Principles

- **One question at a time** - Don't overwhelm with multiple questions
- **Multiple choice preferred** - Easier to answer than open-ended when possible
- **YAGNI ruthlessly** - Remove unnecessary features from all designs
- **Explore alternatives** - Always propose 2-3 approaches before settling
- **Incremental validation** - Present design in sections, validate each
- **Be flexible** - Go back and clarify when something doesn't make sense
