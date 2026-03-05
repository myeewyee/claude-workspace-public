---
name: autonomous
description: On-demand autonomous work mode. Scans all tasks (1-active, 2-paused, 4-recurring, 3-idea) for work items Claude can handle without the user's input, presents a plan for approval, then executes. Invoked explicitly, not automatic.
---

# Autonomous Work Mode

## Overview

Scan all tasks for work items that can be completed without the user's input. Present the plan, get approval, execute sequentially, report results.

This skill is **on-demand only**. It fires when the user explicitly requests autonomous work ("go work autonomously", "autonomous session", "find things you can do", or similar). It does NOT fire automatically at session start or after completing work.

## The Flow

### 1. Scan (two-phase triage)

Uses the enriched `task.py list` output to eliminate most tasks without reading any files.

**Step 1a: Triage from list metadata (zero file reads)**

Run `task.py list`. From the output, apply these elimination rules in order:

- [ ] **Paused tasks** → skip all (no unblock detectable from metadata)
- [ ] **Ideas** → skip all (brainstorm veto: ideas have unresolved design by definition)
- [ ] **Recurring: not due** → skip if `last_run` + `cadence` = not yet due. Cadence math: daily = 1 day, weekly = 7 days, monthly = 30 days, quarterly = 90 days.
- [ ] **In-progress: recent activity** → skip if `last_progress_entry` is within 2 hours of current time. Likely another active session. Log under "Skipped (recent session activity)."
- [ ] **Paused: blocked priority** → skip if `priority` is `2-blocked`. Heuristic; non-blocked paused tasks survive for full read.

Everything not eliminated is a **candidate**. Typically 2-5 tasks out of 15-20.

**Step 1b: Read candidate files and evaluate (file reads only for candidates)**

For each candidate:
- [ ] Read the full task file
- [ ] Identify specific outstanding work items (from Approach, Success Criteria, or Work Done gaps)
- [ ] Evaluate each work item against the autonomy criteria below
- [ ] Proceed to Step 2 (Argue Against) for any items tentatively classified autonomous

### 2. Argue Against (mandatory)

For every item tentatively classified as autonomous-safe in step 1, run an adversarial pass. This is not optional. It is a required step that produces explicit output.

**For each autonomous-safe item:**
1. Write the strongest argument for why it should NOT be autonomous. Target specific criteria: "Criterion 2 fails because..." or "Criterion 3 fails because..."
2. The argument must be genuine, not a strawman you can easily dismiss. Imagine the user reading the counter-argument. Would he say "yeah, that's a fair point"?
3. If the counter-argument is plausible, reclassify the item to "Needs the user." Do not proceed.
4. If you believe the counter-argument doesn't hold, write an explicit override explaining why. The override must be more convincing than the counter-argument.

**If you cannot write a convincing override, the item fails.** Move it to "Needs the user."

The counter-argument and override (if any) are recorded in the audit trail. This creates a reviewable record of the adversarial check.

### 3. Log

Write the scan results to `context/autonomy-log.md`. Every scan gets logged, whether or not autonomous work is found. See § Decision Audit Trail below for format requirements.

### 4. Present

Show the user the plan:

> **Autonomous work scan.** Evaluated [N] tasks across [categories].
>
> Can work autonomously on:
> - [[Task Name]] (1-active): [specific work item]. Basis: [brief reasoning]
> - [[Task Name]] (2-paused): [specific work item]. Basis: [brief reasoning]
>
> Skipped (recent session activity):
> - [[Task Name]]: last entry [TIME] (~[N] min ago)
>
> Needs your input:
> - [[Task Name]] (1-active): [what's blocking]. Needs: [what decision]
>
> Starting with [first item]. Anything to skip or reprioritize?

### 5. Approval

Wait for the user's green light. He can reprioritize, skip items, or redirect. One approval covers the whole batch.

### 6. Execute

Work through approved items sequentially:
- Standard task file updates for each item (Work Done via Edit, Progress Log via task engine)
- If something unexpected comes up on an item: stop on that item, log what happened, move to the next
- Do not try to resolve unexpected issues alone. That's exactly the kind of judgment call that needs the user.

### 7. Complete

When a task's success criteria are fully met by the autonomous work:
- Self-verify using the two-pass process in `modes/complete.md` step 2
- If confident: complete the task (archive, commit)
- If uncertain: flag it in the report and move on

### 8. Commit

Git commit per task completion during autonomous work.

### 9. Report

When the autonomous queue is empty:

> **Autonomous pass complete.** Worked on [N] items across [M] tasks.
> - [[Task Name]]: [what was done]. [Completed and archived / Partially done]
> - [[Task Name]]: [what was done]. [Completed and archived / Partially done]
>
> Blocked / needs you:
> - [[Task Name]]: [what's blocking, what decision needed]

## Autonomy Criteria

Evaluated per work item, not per task. A single task may have autonomous and non-autonomous items.

### Gate Order

**Step 1 — Brainstorm veto (prerequisite):**
Would this work item trigger the brainstorm gate? (Modifying behavior, adding features, changing conventions, design work?) If yes → **NOT autonomous-safe. Full stop.** The brainstorm gate has absolute veto over autonomy classification. This cannot be overridden by the criteria below.

**Step 2 — All four criteria must pass:**

1. **Objective/verifiable:** Success criteria can be checked by Claude against a concrete standard. Not "make it better" but "match field X to template Y."
2. **Demonstrated pattern:** The approach has been used at least once before in this workspace. Not just documented — actually done. First-time application of a new convention is not autonomous-safe, even if the convention is documented, because edge cases always emerge on first application.
3. **No subjective judgment:** No taste, quality, or priority calls required. If reasonable people could disagree on the right answer, it's not autonomous-safe.
4. **Bounded scope:** Work can be defined in advance with clear boundaries. Claude can recognize when it's exceeding those boundaries. "Fix frontmatter on these 3 files" is bounded. "Improve the task system" is not.

**Safety net:** All changes are in git, so classification errors are recoverable. This doesn't loosen the criteria but means mistakes aren't catastrophic.

## Decision Audit Trail

Every scan is logged to `context/autonomy-log.md`. Read `references/audit-log-format.md` for the entry format, detail requirements, and the distinction between candidate entries (full detail) and triage-eliminated entries (abbreviated).

## Red Flags

These thoughts mean STOP — you're rationalizing autonomous classification:

| Thought | Reality |
|---------|---------|
| "This is autonomous, I don't need to brainstorm" | Brainstorm gate vetoes autonomy. If brainstorm would fire, the work is not autonomous. No exceptions. |
| "The criteria basically pass" | All four must clearly pass. "Basically" means it doesn't. |
| "This is similar enough to work I've done before" | Similar is not the same. If you can't point to a specific prior instance, it's not demonstrated. |
| "The scope is probably bounded" | Define the boundary explicitly. If you can't, it's not bounded. |
| "I'll just do this one small thing" | Small things that fail criteria are still not autonomous. Size doesn't override the gate. |
| "the user would probably be fine with this" | That's a subjective judgment about the user's preferences. Ask him. |
