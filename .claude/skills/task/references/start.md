# Mode: start

## Input
```
/task start              -> Start a paused or idea task (set to 1-active)
/task start <task-name>  -> Start a specific task
```

## Process

1. **Start via task engine:**
   ```bash
   python .task-engine/task.py start --task "Task name"
   ```
   Omit `--task` to start the first 2-paused task. The engine handles: status change, progress log entry, and file move (ideas/ to tasks/) if promoting an idea.
2. **Readiness assessment:** Read the full task file. Check the **Approach** and **Success Criteria** sections:
   - **Absent or empty** (heading missing, or no content below it): Invoke `/brainstorm` before any implementation. This is automatic, not a judgment call.
   - **Present with content:** State a brief readiness assessment to the user:
     > **Readiness: [Task Name]**
     > - Approach: [1-sentence summary of what it says]
     > - Success Criteria: [1-sentence summary of what it says]
     > - Metadata: description=[first ~10 words...], focus=[value], category=[value], pillar=[value or blank], parent=[value or none]
     > - Assessment: [Ready / Concerns — with reasoning]
     The user can override ("that's stale, brainstorm first") or confirm. If you have concerns (vague criteria, outdated context, approach that doesn't match current system state), say so. Show your reasoning. Never silently decide "this is fine."
   - **Metadata check:** Review key frontmatter fields before proceeding. Flag any that are blank or stale:
     - **Task name (filename + H1):** Does the name still match the task's actual scope? Names written at creation can be as stale as descriptions — especially if brainstorming shifted the framing. If stale: `mv "tasks/Old Name.md" "tasks/New Name.md"` + update the H1 heading.
     - `description`: Does it still match the task's actual scope? Descriptions written at creation often drift as scope clarifies.
     - `focus`: internal/external. Blank → ask user to set. Populated → verify still accurate.
     - `category`: feature/bug/improvement/research/maintenance. Same as focus.
     - `pillar`: memory/workflow/self-improve. Only for internal tasks. Blank for external. Populated → verify still accurate.
     - `parent`: Still the right parent, or has the task's home in the hierarchy shifted?
     - **Key links (Context + Related):** Spot-check wiki links in the Context section and `### Related`. Do the referenced tasks still exist? Renamed or archived tasks leave dead links. Fix broken links before proceeding.
     If any field needs updating, fix it now (via `task.py update`) before proceeding.
   - **Blocked By (paused tasks only):** If the task has a `## Blocked By` section, verify the blocker is still active. Check the blocking task's status via `task.py list` or read its file. If resolved, clear the `## Blocked By` section before proceeding. If still blocked, warn the user before starting.
3. **Context alignment gate:** Run the context alignment procedure. Read `references/context-alignment.md` for the full procedure. Check the `context-aligned:` frontmatter field: empty → full alignment (agent-based), populated → light refresh. This ensures prior work is discovered before implementation begins, even if brainstorming is skipped.
4. **Confirm:** `Task started: [Task Name]`

## Important
- Multiple tasks can be 1-active simultaneously. No need to ask before starting a second.
- Any non-terminal status can move to 1-active (2-paused, 3-idea).
- The readiness assessment in step 2 serves two purposes: (1) auto-redirect to brainstorm when sections are absent/empty, and (2) force Claude to visibly engage with existing content rather than rationalizing past it. The user sees the assessment and can override.
- **When no task is specified and user asks "what should I work on?":** Show paused tasks sorted by priority (1-next > 2-blocked > 3-later > 4-someday). This helps the user pick from the full queue.
