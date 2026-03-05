# Mode: complete

## Input
```
/task complete              -> Complete the current active task
/task complete <task-name>  -> Complete a specific task
```

## Process

1. **Self-verification sweep** -- Before declaring ready to complete, run the verification appropriate to the task type. Do this BEFORE presenting the confirmation to the user.

   | Task type | Verification action |
   |-----------|-------------------|
   | Rename/reference updates | Grep for the old term across active files. Confirm zero hits outside archives. |
   | Convention/process changes | Re-read files that should reflect the change. Report inconsistencies. If the convention affects runtime behavior (e.g., agent prompting, hook wiring, skill triggers), also do a functional test: trigger the workflow and verify the output matches expectations. File inspection alone is insufficient for behavioral changes. |
   | Feature/component builds | Trigger the feature, confirm it works. Check the output. |
   | Documentation-only | Re-read changed docs. Confirm cross-references are consistent. |
   | Config/wiring | Run the thing, check the output, confirm the behavior. |

   Report findings to user (including "sweep clean, no issues found" if nothing turns up). Fix any issues found before proceeding.

2. **Self-verify and complete** (no confirmation needed in most cases):
   - **First pass:** Check each success criterion against Work Done. Are they met?
   - **Deliberate second pass:** "Am I sure? What am I missing? What would the user flag?" Actively look for: unfinished edges, untested paths, stale sections, missing doc updates. This pass exists because Claude has a pattern of finding more work when pushed.
   - If both passes clean AND Claude is confident → proceed to step 3 without asking.
   - If uncertain (ambiguous criteria, edge cases, scope questions) → pause and confirm:
     ```
     Ready to complete: [Task Name]
     Uncertainty: [what specifically is unclear]
     Proceed? [yes/no]
     ```
   - If issues found → fix them, then re-run both passes.
3. **Reconciliation check** -- Before archiving, re-read the full task doc and verify:
   - Do the Approach sections reflect what was actually built?
   - Does Success Criteria match reality?
   - Does Work Done cover everything, including late changes?
   - **Metadata reconciliation:** Review key frontmatter fields against the actual work done. These fields are set at creation and can drift as scope evolves:
     - **Title/filename:** Does the task name still describe what was actually done? Rename if the scope pivoted (e.g., "via MCP" when the decision was to build a script). Renaming requires: file rename, H1 update, grep for all `[[Old Name]]` references across tasks/, outputs/, context/, and docs/.
     - `description`: Does it still accurately summarize what the task became? Rewrite if the scope shifted materially from the original one-liner.
     - `focus`: Does internal/external still match the primary intent of the work done?
     - `category`: A task that started as `research` may have become `feature`. Match to actual outcome.
     - `pillar`: For internal tasks, does memory/workflow/self-improve still match? Blank for external.
     - `parent`: Still the right parent, or did the task's place in the hierarchy shift?
     If any field needs updating, fix it now (via `task.py update`) and note the change in the progress log. This is the last chance before archive.
   - **Documentation check.** If this task changed any documented component:
     1. `docs/systems.md`: Did a component change?
     2. Component docs (README.md, SKILL.md): Still accurate?
     3. `CLAUDE.md`: Did workflow rules or patterns change?
     4. `CLAUDE.md`: Did a new convention or lesson emerge? (Changes go through improvement log pipeline, not direct edits.)
     5. `context/` data files: Do any context files need structural updates? (`improvement-log.md`, `captains-log.md`, `<your-preferences>.md`, profile files)
   - Fix stale sections now. This is the last chance before archive.
   - **Captain's log check.** Did this task introduce a new capability, establish a new convention, change how the system's architecture works, or deliberately evaluate and confirm an existing convention? (Not: "did you make a tradeoff while implementing a fix." Implementation details belong in the task file's progress log.) If yes: fill `decision:` via `task.py update --field decision --value "..."` (ensures YAML quoting), append to `context/captains-log.md`, and add a `## Rollback` section to the task file. The rollback section must be specific enough that a future session with no context can execute it:
     - **Find the commit:** Include the exact `git log --grep="..."` command to locate the relevant commit(s).
     - **List what to restore:** Name the specific files that were changed/deleted, not just "revert changes."
     - **List what to delete:** Name files that were created and would need removal.
     - **Ordered steps:** Write numbered steps, not prose. A future session should be able to follow them mechanically.
     - **Test:** "Don't just say 'test it works.' Say what command to run and what output to expect."
   - **Unblock check.** Grep `tasks/` for files containing a `## Blocked By` section that references the completing task name. For each match:
     1. Read the blocked task's `## Blocked By` section
     2. Check if the completing task is the only blocker or one of several
     3. Report to user:
        - **Sole blocker:** "Completing [[This Task]] unblocks [[Blocked Task]] (currently paused). No remaining blockers."
        - **One of multiple:** "Completing [[This Task]] resolves one blocker for [[Blocked Task]], but it's still blocked by [[Other Task]]."
     4. Report only. Do not auto-resume the unblocked task.
4. **Complete via task engine:**
   ```bash
   python .task-engine/task.py complete --task "Task name"
   ```
5. **Git backup:**
   ```bash
   git add tasks/ outputs/ context/ docs/ .claude/ .task-engine/ .scripts/ CLAUDE.md .gitignore && git add $(git ls-files --others --exclude-standard) 2>/dev/null; git commit -m "Complete: [Task Name]" && git push
   ```
   The second `git add` sweeps any untracked files not in `.gitignore` (e.g., `.base` files Obsidian created). If commit/push fails, warn but don't block completion.
6. **Confirm:** Report what was archived (task file + any output files)

## Important
- **Self-verify and complete without asking** unless uncertain. Always run two verification passes (criteria check + "what am I missing?") before completing.
- The task engine automatically archives output files by scanning for files where `parent:` matches the completing task. No manual output linking needed.
- Only archive outputs in `outputs/`. Files in `context/` are living references and stay put.
