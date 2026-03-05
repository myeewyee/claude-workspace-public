---
created: 2026-02-21 13:35
description: Context management placement framework organized by drift risk. Defines
  where content belongs, decision tree for new rules, current inventory with measurements,
  resolution procedures for reviews, and corrected metric thresholds.
parent: '[[Audit context management overhead]]'
source: claude
type: artifact
---

# Context management placement framework

**Context:**
**Why:** Core deliverable of [[Audit context management overhead]]. The workspace had no defined placement rules, leading to content landing wherever felt natural rather than where it would be most effective. Key reframe: drift risk determines placement, not token cost. The most expensive tokens in the context are the most valuable ones, because they're what make the system work.
**When:** 2026-02-21. Based on 22-session token analysis ([[Context management token analysis]]), CLAUDE.md best practices research ([[MCP ecosystem and Claude Code best practices research]]), and observed compliance patterns over 8 days.
**How:** Combined measured token costs from session logs with observed compliance patterns and official Claude Code documentation on CLAUDE.md/MEMORY.md purpose. Drift classifications are intuitive (based on observed violations), not statistically measured. Character counts are direct measurements; token estimates use chars/4 as a rough guide (actual ratio for structured markdown is likely 2.5-3, see token analysis doc).

## Placement Tiers

Content placement is determined by **drift risk**: how quickly Claude forgets or ignores a rule as context grows. Higher drift risk requires more aggressive reinforcement.

| Tier | Location | Loading | Drift Profile | Measured Size |
|------|----------|---------|---------------|---------------|
| **Per-prompt** | `per-prompt-rules.md` | Every user message (hook) | Addresses HIGH drift: rules Claude demonstrably forgets mid-session | 3,144 chars |
| **Session-start** | `using-skills/SKILL.md` | Once at start + on compaction (hook) | Addresses MEDIUM drift: process definitions that fade as context grows | 11,043 chars |
| **Always-loaded labeled** | `CLAUDE.md` | Every request (system-reminder) | LOW drift: labeled, persistent, user-written constraints | 83 lines, 7,303 chars |
| **Always-loaded silent** | `MEMORY.md` | First 200 lines, every session (no visible tag) | LOW drift: persistent but invisible to self-audit | 170 lines of 200 |
| **On-demand** | `context/`, task files, vault | When explicitly loaded via Read or MCP | N/A: not in context until loaded | Variable |

## Admission Criteria by Tier

### Per-prompt rules (highest cost per message, highest behavioral value)

Must meet ALL four criteria:
1. **Trigger-shaped**: Expressible as "when X, do Y". Not reference material.
2. **Proven drift**: Claude demonstrably forgets this mid-session. Not theoretical.
3. **Visible harm**: Forgetting causes real problems (missed searches, untracked work, orphaned files).
4. **Compressible**: Under 10 lines. Full detail belongs in SKILL.md.

When a candidate is identified: log in improvement-log.md, propose to the user at end of response. Requires dedicated task and explicit approval to add.

### Session-start (SKILL.md)

- Process definitions that need to be available but not hammered every turn
- Skill routing tables, orientation protocols, full process specs
- Overflow detail for per-prompt rules (the "full version" behind the compressed reminder)
- Gate: does this define HOW to do something Claude is already told to do? If yes, it belongs here.

### CLAUDE.md

- Test: "Would removing this cause Claude to make mistakes?"
- Written by the user, not Claude. Claude proposes changes, the user approves.
- Target under 150 lines (currently 83)
- Pointers to detail, not detail itself
- Gate: is this a constraint or rule? CLAUDE.md. Is it documentation? systems.md. Is it a convention Claude should remember? MEMORY.md.

### MEMORY.md

- Things Claude learned that should persist across sessions
- Workspace conventions, tool behavior, environment facts, lessons
- Written by Claude, auto-loaded
- 200-line limit (Claude Code feature). Currently at 170.
- Gate: will a future session need this to avoid repeating a mistake?

### On-demand (context/, vault)

- Everything else: reference material, profiles, historical analysis
- Loaded only when relevant to current work
- No drift concern (not in context until explicitly loaded)

## Decision Tree for New Content

```
New content to place:
|
+-- Is it a behavioral rule Claude must follow?
|   |
|   +-- YES: Does Claude demonstrably forget it mid-session?
|   |   |
|   |   +-- YES: Is it trigger-shaped and under 10 lines?
|   |   |   +-- YES --> per-prompt-rules.md (dedicated task + the user approval)
|   |   |   +-- NO  --> SKILL.md (full version) + compressed per-prompt reminder
|   |   |
|   |   +-- NO: Is it an operational constraint the user sets?
|   |       +-- YES --> CLAUDE.md (the user writes/approves)
|   |       +-- NO  --> MEMORY.md (Claude's working note)
|   |
|   +-- NO: Is it documentation about how something works?
|       +-- YES --> docs/systems.md
|       +-- NO: Is it reference material needed occasionally?
|           +-- YES --> context/ file (loaded on demand)
|           +-- NO  --> Vault (if the user's content) or unnecessary
```

## Current Inventory

### per-prompt-rules.md (3,144 chars)

| Rule | Drift Evidence | Placement |
|------|---------------|-----------|
| Implementation gate | Pre-gate: untracked edits observed | Correct |
| Brainstorm gate | Skipped brainstorming observed (Feb 20, improvement log) | Correct |
| Task management 10-question check | Pre-check: direct TASKS.md edits, missing updates | Correct |
| Task switching guard | File changes between messages caused false task switches (Feb 15) | Correct |
| Tool selection gate | 2 vault tool violations in single session (Feb 15) | Correct |
| Protected file clause | Protects this file from autonomous modification | Correct |
| Improvement flagging reminder | Not yet tested for drift. Placed as convenience (single reference point) | Monitor |

**Assessment:** All rules correctly placed per the user's confirmation (Feb 20). Improvement flagging is the newest addition and hasn't been tested for drift. If it proves stable without per-prompt reinforcement, consider demoting to SKILL.md-only.

### using-skills/SKILL.md (11,043 chars)

Session orientation, post-compaction protocol, skill trigger table (7 skills), vault tool selection guide (8 tools), pre-implementation gate (full version with red flags), improvement flagging (full version), work mode section, core principles.

### CLAUDE.md (83 lines, 7,303 chars)

Hook health check, context architecture pointer, primary use cases, strict rules (vault read-only, output workflow 11 rules, task tracking, idea capture), workspace patterns (6 items).

### MEMORY.md (170 of 200 lines)

Memory architecture map, task management, session start architecture, two-zone vault, permissions, hooks, per-prompt rules architecture, self-orientation rule, documentation convention, environment, formatting conventions, file rename protocol, self-improvement loop, captain's log, working patterns, WhatsApp messages, file naming, frontmatter conventions, 5 lessons.

**Capacity note:** At 170/200 lines, MEMORY.md is at the warn threshold. Next addition should trigger a triage pass: identify duplicates, outdated content, or entries that have migrated to systems.md.

## Resolution Procedures

When reviews flag a context management problem, use the matching procedure below.

### MEMORY.md near capacity (170+ lines)

1. Read the full file
2. Identify: duplicate information, outdated lessons, content that migrated to docs/systems.md or SKILL.md
3. Merge similar sections (e.g., two formatting-related sections could consolidate)
4. Remove content already covered authoritatively elsewhere
5. If still over 170 after cleanup: flag least-referenced sections for the user to decide on removal
6. After triage: verify remaining content is accurate (staleness check)

### per-prompt-rules.md growing (4,000+ chars)

1. Audit each rule against the 4 admission criteria
2. Check: has any rule become habitual? (no violations in 2+ weeks of session logs)
3. Look for compression opportunities (two rules that can merge)
4. If still over threshold: propose to the user which rules to demote to SKILL.md-only
5. **Requires dedicated task and explicit user approval.** Cannot be done during reviews.

### CLAUDE.md growing (120+ lines)

1. Apply the test: "Would removing this cause mistakes?"
2. Move detail to systems.md or SKILL.md, replace with pointer
3. Check for content that should be in MEMORY.md instead (Claude-written conventions)
4. Verify remaining content is the user-authored constraints, not Claude-authored notes

### SKILL.md growing (12,000+ chars)

1. Check for content that duplicates CLAUDE.md or MEMORY.md
2. Look for sections that could be split into mode files (like task skill's architecture)
3. Verify all content is referenced by at least one skill trigger
4. Remove orphaned process definitions

### Stale content detected

1. Identify which file(s) are stale and what changed
2. Check git log for when the change was made that caused staleness
3. Fix the stale content directly (auto-fix, no permission needed)
4. If it reveals a process gap (e.g., ad hoc changes bypassing /task complete docs check): log in improvement-log.md

### Duplicate or conflicting content across tiers

1. Determine which tier is authoritative per the placement rules
2. Keep the authoritative version, remove or pointer-ify the duplicate
3. If both contain unique detail: merge into the authoritative location
4. Document the resolution in the task's progress log

## Corrected Metric Thresholds

Previous thresholds used flawed char/4 token estimates. These corrected thresholds use **character counts** (directly measurable, no tokenizer uncertainty) with estimated token equivalents for reference only.

| Metric | Warn | Alert | Current | Rationale |
|--------|------|-------|---------|-----------|
| per-prompt-rules.md | 4,000 chars | 5,000 chars | 3,144 chars | Room for 1-2 more rules before warn. Alert triggers compression audit. |
| MEMORY.md | 170 / 200 lines | 190 / 200 lines | 170 lines | Hard 200-line limit (Claude Code feature). Warn early for triage. |
| SKILL.md | 12,000 chars | 15,000 chars | 11,043 chars | Session-start cost is one-time and cached. Generous ceiling. |
| CLAUDE.md | 120 lines | 150 lines | 83 lines | Under 150 per best practices. Warn at 120 to catch growth. |
| Done entries in TASKS.md | 50 | 75 | N/A | Performance/readability concern. Archive clears them. |
| Systems review age | 7 days | 14 days | N/A | Weekly cadence for full review. |

**Why characters, not tokens:** The old warn=700/alert=900 "tokens" for per-prompt rules was based on a char/4 estimate that put the file at ~909 tokens. Actual session data shows chars/4 underestimates for structured markdown (true ratio is closer to 2.5-3 chars/token). Character count is the one metric we can measure exactly from the file. Token estimates are directional only.

## Review Integration Points

Where these procedures connect to existing review processes:

### Daily review (`/task review`, step 6)

**Current:** Silent metrics check with thresholds.
**Change:** Use the corrected thresholds from this document. Switch per-prompt-rules metric from estimated tokens to character count. Add CLAUDE.md line count check (new metric).

### Weekly systems health review (step 8)

**Current:** Two Opus agents assess enforcement reliability and architecture scaling.
**Change:** Agents should reference this document's placement tiers and resolution procedures. When findings include "content in wrong tier" or "stale content," apply the matching resolution procedure.

### Monthly best practices audit

**Current:** External audit comparing workspace against community best practices.
**Change:** Include a check: do current placement decisions still align with the framework? Has new research changed what constitutes best practice for CLAUDE.md vs MEMORY.md content?

### Ad hoc (improvement log processing)

When improvement mode processes inbox entries that involve content placement (e.g., "X should be in MEMORY.md not CLAUDE.md"), reference this framework's decision tree rather than making intuitive placement choices.