# Mode: review

Deep audit of all task files, links, outputs, and cross-references.

## When to Run
- Prompted at session start if `Run task review` recurring task's `last-run:` is not today
- On demand via `/task review`

## Process

1. **Run automated audit:**
   ```bash
   python .task-engine/task.py audit
   ```
   Handles: output orphans.

2. **Task doc link verification** -- For each active task in `tasks/`, check wiki links and Related links all resolve. Use `task.py list --parent "Task Name"` to verify output files have correct `parent:` backlinks.

3. **Skill and agent references** -- Verify all skills in `using-skills` SKILL.md, agents in `.claude/agents/`, and hook scripts exist.

4. **Skill line count audit** -- For each skill in `.claude/skills/`, check line count of SKILL.md. Flag any over 400 lines for a refactor review. Also flag any skill whose line count has grown since the previous review (compare against the last logged count if available). The refactor goal is minimum tokens that produce intended behavior; 500 lines is the hard ceiling.

5. **Documentation audit** -- Check `docs/systems.md` and component docs are in sync:
   - Forward: index to reality, docs to code
   - Reverse: reality to index, code to docs
   - Scripts catalog: compare `.scripts/README.md` entries against actual files in `.scripts/`. Flag scripts not in README, and README entries for scripts that no longer exist.

6. **Priority staleness check** -- For each 2-paused task with `priority: 1-next`, check `last_progress_entry` from `task.py list`. Flag any where last progress is 14+ days ago:
   > "Stale priority: [[Task Name]] is 2-paused as `1-next` but has no progress since [date]. Still next, or should this be `3-later` or `4-someday`?"
   Also flag any 2-paused task with no priority set (missing field).

7. **Report, update, offer to fix.**

8. **Systems health check (daily, silent)** -- Only report if breached. Thresholds use character counts where applicable (see [[Context management placement framework]] for rationale):
   - CLAUDE.md length: warn 120 lines, alert 150 lines
   - SKILL.md size: warn 12,000 chars, alert 15,000 chars
   - per-prompt-rules.md size: warn 4,000 chars, alert 5,000 chars
   - Systems review age: warn 7 days, alert 14 days
   - Learning log inbox entries: warn 25, alert 40
   When a threshold is breached, apply the matching resolution procedure from [[Context management placement framework]].

9. **Hook smoke test (daily, silent)** -- Read `.claude/settings.json`, extract each hook command, run it in bash, verify non-empty output. Report immediately if any hook produces empty output. This catches silent failures like wrong shell commands (e.g. `type` vs `cat` on Windows/bash).

10. **Full systems review (weekly, if due)** -- If `Run systems health review` `last-run:` is 7+ days old: report all metrics, launch two Opus agents (Enforcement + Architecture), output to `outputs/Systems health report YYYY-MM-DD.md`, feed findings to learning log, present triage list. Agents should reference [[Context management placement framework]] for placement tiers and resolution procedures.

11. **Improvement mode (weekly, if due)** -- If `Run improvement mode` `last-run:` is 7+ days old: run the full improvement mode process defined in the task doc. Always runs AFTER the systems health review (step 8) so health review findings are in the inbox.

## Automatic fixes (no permission needed)
- Broken links where the file was clearly renamed
- Empty Related sections where siblings are obvious
- Date bucket re-sorting (always automatic via audit)

## Requires permission
- Deleting orphaned files
- Changing task status
- Moving files between directories
