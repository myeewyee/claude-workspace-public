---
completed: 2026-02-21 14:24
created: 2026-02-13 16:10
description: 'Build the full self-improvement loop: capture mechanism (improvement
  log or task-based), processing convention (improvement mode), and the pipeline that
  ensures findings get actioned.'
parent: '[[Brainstorm self-improving machine]]'
source: claude
status: 5-done
type: task
focus: internal
category: feature
pillar: self-improve
---
# Build self-improvement system
## What It Is
Build the full self-improvement loop: the capture mechanism for observations about the machine, and the processing convention (improvement mode) that turns those observations into action.

Open design decisions:
1. ~~**Capture format:**~~ **Resolved (2026-02-21).** Inbox model approved. Central improvement log with Inbox/Processed split. See [[Improvement log design recommendation]].
2. ~~**Improvement mode convention:**~~ **Resolved (2026-02-21).** Built as recurring task [[Run improvement mode]]. Weekly 5-step process: load context, cluster, interactive triage, execute, close out.
3. ~~**Decision log (captain's log):**~~ **Resolved (2026-02-16).** Built as a separate task: [[Build captain's log for design decisions]]. Captain's log lives at `context/captains-log.md`.
## Context
Phase 1, deliverables #1 and #2 from [[Brainstorm self-improving machine]]. See the design doc's "Two Modes" and "Phase 1" sections for full spec.

Merged from two originally separate tasks: Build improvement log (capture side, mostly done) and Build improvement mode convention (processing side, not started).
### Relationship to systems health review
Improvement mode consumes three input sources:
1. **Improvement log / idea tasks**: Observations flagged during work sessions
2. **Systems health review** (weekly report from [[Run systems health review]]): Metrics, drift detection, architectural findings
3. **Session history** (JSONL logs): Safety net for unflagged insights

The systems health review *detects* problems. Improvement mode *designs solutions* and implements them. One is diagnostic, the other is surgical.
## Links
### Related
- [[Brainstorm self-improving machine]] (parent design doc)
- [[Improvement flag placement recommendation]] (design: where flags get captured)
- [[Improvement log design recommendation]] (design: log structure, GTD inbox model)
- [[Add systems health review to task review]] (built the diagnostic layer that feeds into this)
- [[Run systems health review]] (recurring: produces weekly health reports consumed by improvement mode)
- [[Run improvement mode]] (recurring: the processing convention built by this task)
- [[Build captain's log for design decisions]] (resolved design decision #3: decision records)
### Subtasks
```base
filters:
  and:
    - type == "task"
    - parent == "[[Build self-improvement system]]"
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
      - status
      - file.name
    sort:
      - property: status
        direction: DESC

```
### Outputs
```base
filters:
  and:
    - type == "artifact"
    - parent == "[[Build self-improvement system]]"
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
**Capture (met):**
- Capture mechanism exists and is integrated into session workflow
- Real entries captured during normal work

**Processing (met):**
- Documented pattern for running an improvement mode session: [[Run improvement mode]] recurring task with full 5-step convention
- Clear process: read observations, read latest health report, identify patterns, propose changes, implement approved changes
- At least one real improvement mode session run: first run processed 25 entries, 8 clusters, 3 tasks spawned

**Pipeline (met):**
- Structural decision made on capture format: inbox model approved, Inbox/Processed split implemented
- Findings have a clear lifecycle: capture, triage, action/dismiss. 4 exits defined.
- Nothing falls through the cracks: inbox size thresholds (warn 10, alert 15), weekly cadence check, `[improvement-flag]` keyword for session traceability
## Design
### Improvement mode convention
**Form:** Recurring task ([[Run improvement mode]]). Convention defined in the task doc, triggered from `/task review` step 9 on weekly cadence.

**Inputs:** Improvement log Inbox + latest systems health report (if new).

**Process (5 steps):**
1. **Load context** - Read inbox, read latest health report, note entry count and date range
2. **Cluster** - Group entries by theme before triaging. Present clusters with summaries.
3. **Triage (interactive)** - For each cluster/entry, recommend an exit. User approves/overrides. Four exits: task, direct fix, accepted risk, dismissed.
4. **Execute** - Implement direct fixes, create tasks via `/task new`, move entries to Processed with exit annotations.
5. **Close out** - Update `last-run:`, write run history entry.

**Safeguards:** Inbox size thresholds in daily review (warn 10, alert 15). Weekly cadence check in step 9. `[improvement-flag]` keyword in chat responses for session traceability.
## Approach
Decide on capture structure, document the improvement mode convention, run a real session, iterate.
## Work Done
- Created `context/improvement-log.md` with frontmatter, layer definitions, and date-grouped entry format
- Added "Work Mode: Improvement Flagging" section to `using-skills/SKILL.md` with full convention
- Added one-liner flagging reminder to per-prompt hook (fires every prompt)
- Updated `docs/systems.md` Context Files section with improvement log entry
- Added task reference breadcrumb to entry format: `(during [[Task Name]])` for traceability
- Aligned improvement log format with task progress log convention: H3 date headings, timestamped entries
- Brainstormed structural redesign: researched GTD inbox model vs merging into task/idea system. Decision deferred initially, approved later.
- **Redesigned improvement log format (v2):** Task-grouped entries instead of flat list. Entries grouped under `[[Task Name]]` wiki-link headers. Added session ID capture via HTML comments (invisible in Obsidian, machine-readable).
- Reformatted all existing entries (19 entries across 4 dates) to new task-grouped structure
- **Verified hooks broken since Feb 13:** JSONL forensics confirmed `type` command (bash builtin) never produced file output. Zero `hook success` markers in any pre-fix session. CLAUDE.md fallback masked the failure for 8 days.
- **Added hook health check to CLAUDE.md:** Replaced passive fallback with active detection: model checks for marker tags, reads files directly if absent, alerts user. Every message becomes a hook health check at zero additional token cost.
- **Removed redundant enforcement from CLAUDE.md:** Stripped ~365 tokens of enforcement content that duplicated hook-injected rules. Hook failures now produce visible compliance drops rather than silent degradation.
- **Added daily hook smoke test:** New step in review.md. During daily task review, extract hook commands, run each in bash, verify non-empty output.
- **Implemented inbox/processed split:** Restructured `context/improvement-log.md` with `## Inbox` and `## Processed` sections. All existing entries placed in Inbox pending first triage.
- **Built improvement mode convention:** Created [[Run improvement mode]] as recurring task with full 5-step process. Added weekly cadence check and inbox size thresholds to review.
- **Added `[improvement-flag]` keyword:** Searchable keyword in chat responses when logging observations.
- **First improvement mode run (validation):** Processed 25 inbox entries across 4 dates. Clustered into 8 themes + 6 standalone. Exits: 3 tasks created (ideas), 4 direct fixes, 8 accepted risks, 10 dismissed. Inbox cleared to zero.
## Rollback
To revert the self-improvement system:
1. **Improvement mode convention:** Delete `tasks/Run improvement mode.md`. Remove weekly cadence step from review checklist.
2. **Inbox/Processed split:** Revert `context/improvement-log.md` to flat list format.
3. **[improvement-flag] keyword:** Remove from `using-skills/SKILL.md` and per-prompt rules.
4. **Documentation:** Revert entries in `docs/systems.md`. Revert MEMORY.md section.
5. **Spawned tasks:** The 3 idea tasks created during the first run are independent and can be kept or cancelled separately.
## Progress Log
### 2026-02-21
2:24 PM *Status -> Done*
2:24 PM **Reconciliation and completion**
- Updated success criteria, Work Done, MEMORY.md
- Added captain's log entry, decision frontmatter, Rollback section
1:53 PM **Built improvement mode convention**
- Created [[Run improvement mode]] recurring task with full 5-step process
- Added weekly cadence check and inbox size thresholds to review
- Added [improvement-flag] keyword
- Resolved all three design decisions
12:25 PM **Hook failure detection and CLAUDE.md deduplication**
- Verified via JSONL forensics that hooks were broken since Feb 13
- Replaced passive fallback with active hook health check
- Removed ~365 tokens of redundant enforcement content from CLAUDE.md
- Added daily hook smoke test to review
11:34 AM **Redesigned improvement log format (v2)**
- Task-grouped entries with session ID capture via HTML comments
- Reformatted all 19 existing entries
11:28 AM *Status -> In Progress*
### 2026-02-15
01:47 PM Added decision log (captain's log) as open design decision #3.
### 2026-02-13
06:39 PM **Merged with improvement mode convention task into single scope**
06:36 PM **Brainstormed structural redesign**
- Researched GTD inbox model vs. merging log into task/idea system
- Core tension: low-friction capture (1 tool call) vs. system coherence (one lifecycle)
- Decision deferred. Research captured in [[Improvement log design recommendation]]
06:13 PM **Aligned log format with task progress log convention**
04:44 PM *Status -> Done (first pass)*
04:33 PM **Implementation complete** (capture side)
04:30 PM *Status -> In Progress*
04:10 PM *Status -> Pending (task created)*
