---
name: task
description: Manage the full task lifecycle in this workspace. Use for creating, starting, updating, completing, or cancelling tasks, and for running periodic task reviews. Fires when any task operation is requested, when work emerges that should be tracked, or when reviewing workspace state.
---
# Task Management

Manage the full task lifecycle: from idea capture through completion. File operations use the task engine CLI (`.task-engine/task.py`). This skill defines conventions, judgment calls, and workflows that wrap those operations.

## What Is a Task?

A task is any unit of work worth tracking: 3-idea → 1-active/2-paused → 5-done/6-cancelled. Recurring tasks (4-recurring) run on a cadence and never complete.

**IS a task:** Business idea, system improvement, building something, implementing a feature.
**NOT a task:** Learning something (informational), minor setup, coaching conversation with no file output.
**Rule of thumb:** If it's worth capturing, it's a task. If the only outcome is "understood something," it's not.
**Every task MUST have a task file.**

## Modes

```
/task new <name> [description]   -> Create new task
/task start [task-name]          -> Move a task to Active
/task complete [task-name]       -> Mark as done and archive
/task cancel [task-name]         -> Mark as cancelled and archive
/task status                     -> Show current task state
/task review                     -> Deep audit of all files, links, consistency
```

**IMPORTANT: After reading this file, Read the mode-specific file before executing:**
`.claude/skills/task/references/<mode>.md` (e.g., `references/new.md`, `references/complete.md`)

## Files

| File | Purpose |
|------|---------|
| `tasks/` | Active task documents (1-active, 2-paused) |
| `tasks/ideas/` | Idea-stage tasks |
| `tasks/archive/` | Done and cancelled task documents |
| `outputs/` | Active output files |
| `outputs/archive/` | Archived output files |
| `.task-engine/` | Task engine CLI (see `.task-engine/README.md`) |

## Task Document Structure

Body sections: Context (mandatory, first), Links, Success Criteria, Approach, Work Done, Progress Log. Frontmatter schema and file conventions are in CLAUDE.md (Frontmatter, File Naming sections under Conventions).

The **Links** section appears after Context, grouping all situational awareness material together. It contains three subsections:
- `### Related` — Manual links to related tasks, docs, and context (hand-curated, most useful for reading)
- `### Subtasks` — Bases query showing child tasks (where `parent:` points to this task)
- `### Outputs` — Bases query showing output artifacts (where `parent:` points to this task)

All three subsections are always present (empty tables auto-populate when children are created). The task engine's `create` command generates the Links section with the correct Bases queries. See [[Vault frontmatter conventions]] "Inline Bases query patterns" for the canonical query templates.

## Updating a Task File

When you do work related to a task, update the task file **before** reporting it:

1. **Work Done section** (manual Edit): Add or extend the relevant item
2. **Progress Log** (via task engine): Log what changed
3. **Then** output the standard message (see Standard Output Messages)

The output message is a receipt, not an intention. Never say "Task updated" without having written to the file first.

### Progress logging
```bash
python .task-engine/task.py log --task "Task name" --session "UUID" <<'EOF'
**What changed (bold heading for major entries)**
- Sub-bullet detail
- Sub-bullet detail
EOF
```
The engine handles timestamps and date heading management. Do not include timestamps in entry text; the engine prepends them automatically. For one-liners, the entry text can be a single line. The `--session` arg appends `<!-- session: UUID -->` to the entry (use the session UUID detected during orientation).

**Entry text formatting:**
- **Major entries:** Bold heading + sub-bullets: `**What changed**\n- Detail\n- Detail`
- **One-liners:** Plain text, single line.
- **Status changes:** The engine formats these automatically on start/complete/cancel/pause.
- Entries within a date are reverse chronological (engine handles insertion order).
- Date headings are also newest-first (most recent date right after `## Progress Log`).

### Querying children (subtasks and outputs)
```bash
python .task-engine/task.py list --parent "Task name"
```
Returns all tasks and output files where `parent:` matches the given task name. Scans active, temp, and archived files.

### Field updates
```bash
python .task-engine/task.py update --task "Task name" --field "field" --value "value"
```

### Body sections
Work Done, Approach, Success Criteria, and other body sections are still edited manually via the Edit tool. The task engine handles progress log entries and frontmatter fields, not body content. No blank lines around headings (see `docs/markdown-formatting.md`). If you ever need to write a timestamp manually, get it from `date` first. Never fabricate.

## Priority Field

Tasks have a `priority:` frontmatter field with numeric prefixes for Obsidian Bases sorting:
- **Active tasks** (1-active): `1-high`, `2-medium`, `3-low`
- **Paused tasks**: `1-next`, `2-blocked`, `3-later`, `4-someday`

**When pausing:** Always include `--priority` with the pause command. Ask the user if not obvious from context.
```bash
python .task-engine/task.py pause --task "Task name" --priority "1-next"
```

**When starting:** The engine auto-clears paused priority values. If the user wants to set an active priority, update it after starting.

## Output File Convention

Output files link to their parent task via the `parent:` frontmatter field. No separate linking step is needed. The task engine finds outputs by scanning for matching `parent:` when archiving.

When you create a file in `outputs/`:
1. Set `parent: '[[Task Name]]'` in the file's frontmatter (standard output file format)
2. Reference in Work Done where relevant
3. Report to the user immediately: "Here's the output: filename."

**Subagent outputs:**
1. **Agent side:** Include active task name in prompt so agent adds `parent:` in frontmatter
2. **Parent side:** After agent returns, verify `parent:` is set correctly on new files
3. **Report immediately:** Tell the user as soon as the agent returns. Don't wait until later in the conversation.

## Summary Communication

**Always lead with the task name** when reporting progress. the user juggles multiple sessions.

- Good: "**Standardize task management metadata**: Part 1 done. Here's what changed: ..."
- Bad: "Part 1 is done. Here's what was implemented: ..."

## Standard Output Messages

**Always tell the user what you did.** Short, consistent formats:

- **Task created:** `Task created: [Task Name] -> tasks/Task Name.md`
- **Task started:** `Task started: [Task Name]`
- **Task updated:** `Task updated: [Task Name] -- [what changed]`
- **Task complete:** `Task complete: [Task Name] -> archived`
- **Task cancelled:** `Task cancelled: [Task Name] -> archived`
- **Status changed:** `Task status: [Task Name] -> [Status]`

## Reference

Schemas and conventions that apply to task management are defined in CLAUDE.md:
- **Frontmatter schemas** (task, output, context files): CLAUDE.md "Frontmatter" under Conventions
- **Naming and titles**: CLAUDE.md "File Naming" under Conventions
- **Wiki links**: CLAUDE.md "Frontmatter" under Conventions (wiki-links in YAML)
- **Parent inference**: See mode file `references/new.md` for common parent (MOC) list
