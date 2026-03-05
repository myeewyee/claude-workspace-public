---
type: task
source: claude
created: 2026-02-15 12:39
status: 5-done
description: "Research, design, and build a deterministic task management system. Includes format comparison research, delivery mechanism analysis (MCP server vs script vs other), and implementation of task operation tools."
decision: "Script-first deterministic task engine. All task file operations go through task.py CLI, SKILL.md retains only judgment and conventions."
parent:
focus: internal
category: feature
pillar: workflow
completed: 2026-02-28 16:53
---
# Develop agent-friendly task management system
## What It Is
Research, design, and build a deterministic task management system that replaces LLM-generated file edits with reliable, validated operations. Starting with format comparison research (complete), then designing operations and choosing a delivery mechanism (MCP server, Python script, or other) that handles task CRUD, progress logging, status tracking, and review operations over markdown files.
## Context
Currently using `.md` files with YAML frontmatter for all task tracking. This works well for Obsidian integration and human readability, but the question is whether it scales as agent workflows grow more complex.

**User's framing (from early brainstorming):**
- Familiar with Asana for team collaboration. Knows other tools are database-driven. Not sure if simple text documents scale.
- Forward-looking but also evaluating the current system. The vision: Claude as a business portfolio managing/creating machine. Can this task system scale from dozens to thousands of tasks with multiple collaborating agents?
- Determinism question: Is the way we write to these files scalable? Should task operations be programmatic/scripted (deterministic) rather than LLM-generated edits (probabilistic)?
## Links
### Related
- [[Overhaul task management system]] (current system was built here)
### Subtasks
```base
filters:
  and:
    - type == "task"
    - parent == "[[Develop agent-friendly task management system]]"
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
    - parent == "[[Develop agent-friendly task management system]]"
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
- Clear comparison of markdown vs API-based task management for agent use (**done**)
- Pros/cons of each approach with real examples (**done**)
- Recommendation on whether to evolve the current system or migrate (**done**: keep markdown, add deterministic writes)
- Design for task operations: actions, parameters, what stays in SKILL.md (**done**)
- Delivery mechanism decision with rigorous analysis (**done**: script-first, MCP conditional. Revised after Codex independent review.)
- Working implementation that handles core task operations (Python script `task.py`) (**done**: 7 modules, 9 actions, full integration test passed)
- `/task` SKILL.md reduced to conventions/judgment only (**done**: ~4,752 tokens from ~8,508, 44% reduction. Initial refactor hit 51% but gap analysis identified 6 lost behavioral rules that were added back.)
## Approach
### Phase 1: Research (complete)
Three-layer research comparing markdown, PM SaaS, databases, and hybrid architectures. Extended with MCP ecosystem analysis, context window research, and measured SKILL.md token breakdown. Full findings in [[Agent-friendly task management format research]].

**Key conclusion:** Keep markdown files as storage. Make operations deterministic (programmatic, not LLM-generated edits). ~50% token reduction on `/task` skill. Note: the research concluded "deterministic operations" but the "MCP server" delivery mechanism was assumed, not researched. See Phase 2 for the open question on delivery mechanism.

**Constraints from brainstorm:**
- Scale target: 10-50 concurrent in-progress tasks (near-term), 50+ (aspirational). Hundreds to thousands total over time.
- Obsidian visibility is important but not non-negotiable. Burden of proof is on the alternative.
- All four fragility concerns matter equally: correctness, speed/cost, concurrency, readability.
### Phase 2: Design (complete)
Brainstormed operations design: 8 actions, what stays in SKILL.md vs moves to deterministic code, hardcoded conventions. These decisions are stable regardless of delivery mechanism.

**Delivery mechanism: resolved.** Script-first (Python CLI), MCP conditional. The decision went through three rounds: (1) MCP assumed in Phase 1 research, (2) user challenged the assumption, (3) Claude/Opus analyzed and concluded MCP-first, (4) Codex independently reviewed, collected user's operational constraints, and recommended script-first. User adopted the script-first direction.

**Design inputs collected:**
- **Decision log ("captain's log"):** Spun out as its own subtask. See [[Build captain's log for design decisions]].
- **Terminal states:** Added `cancelled` status alongside `done`. Two terminal categories matching Things 3 / Linear model.
- **The Bases gap:** Obsidian Bases gives humans fast auto-updating views of frontmatter data across files. Claude can't see Bases views. This is a general problem: any frontmatter query across many files has the same tension. Current workarounds are manual index files that require dual writes and can drift.
### Phase 3: Build
Implement `task.py` Python CLI for all 8 actions. Required guardrails: file locking, atomic write-replace, schema validation, explicit errors (never silent fail), deterministic timestamps, idempotency. Refactor SKILL.md to conventions-only.
## Work Done
- Ran three parallel research agents covering: (1) how agent frameworks handle task state, (2) PM tool API capabilities for agent integration, (3) markdown vs database technical trade-offs
- Compiled findings into [[Agent-friendly task management format research]] with comparison matrices and evolutionary recommendation
- Follow-up research on three areas the user challenged:
  - **Obsidian scaling corrections:** Original research used 2021 stress test data (20K files) and conflated community Tasks plugin with Bases (core plugin). Corrected: Obsidian handles 100K+ files.
  - **MCP ecosystem analysis:** Verified most popular MCP servers. Identified key pattern: successful servers provide persistent state or bidirectional communication.
  - **40% context degradation claim:** Traced full citation chain. No research paper supports a 40% threshold. Four papers confirm degradation is continuous and starts within thousands of tokens.
  - **SKILL.md token analysis:** Measured 27,649 bytes (~8,508 tokens). ~5,231 tokens of file operations would move to deterministic code, ~3,262 tokens of judgment/conventions stay.
- Captain's log implemented as subtask: [[Build captain's log for design decisions]]
- **Phase 2 design brainstorm:**
  - Analyzed Vault Intuition server code for merge vs separate trade-off
  - Researched MCP token costs: each tool ~650-950 tokens, server count has zero impact on token budget
  - Designed tool surface: single dispatch with 8 actions (create, start, complete, pause, log, read, update, audit). 10 parameters total.
  - **Critical challenge from user: why MCP server at all?** A Python script achieves the same deterministic operations with zero token overhead. Reopened for first-principles analysis.
- **Delivery mechanism analysis:**
  - Evaluated four options: MCP server, Python script via Bash, script + disk index, script + Vault Intuition reads
  - Key finding: MCP servers do NOT share across sessions (each Claude Code session starts its own server process). The "server solves concurrency" argument was wrong.
  - Key finding: string escaping through Bash for text-heavy content is an entire class of intermittent bugs that MCP's structured JSON parameters eliminate
  - Conclusion revised to script-first after Codex independent review
- **Phase 3 build:**
  - Built 7-module task engine CLI at `.task-engine/`: task.py (CLI), schema.py (validation), operations.py (9 actions), tasks_md.py (TASKS.md ops), progress_log.py (log entries), fileops.py (atomic I/O + locking), audit.py (6 health checks)
  - Key design finding: PyYAML roundtrip breaks key order, quoting, and empty fields. Solution: `frontmatter.load()` for reading, manual string construction for writing
  - Refactored SKILL.md: replaced all file-editing instructions with task.py CLI calls. 44% reduction (655 to 390 lines, ~8,508 to ~4,752 tokens)
  - Ran gap analysis via two parallel agents: end-to-end testing (11/11 passed) + systematic diff audit. Found 9 gaps, fixed 6.
- **Bug fix: stdin UTF-8 encoding:** Added `sys.stdin.reconfigure(encoding='utf-8')` at task.py entry point. Root cause: Windows CP1252 stdin corrupted Unicode chars in heredoc input.
## Design
### Delivery Mechanism: Script-First, MCP Conditional
**Decision:** Python CLI script (`task.py`) as deterministic core. MCP wrapper only if measured need proves it.

**Options evaluated:**
1. **MCP server** - Persistent process, structured tool interface, one-time startup cost
2. **Python script via Bash** - Stateless, invoked per-call, zero token overhead
3. **Script + disk index** - Script maintains a JSON/SQLite index alongside markdown files
4. **Script (writes) + Vault Intuition (reads)** - Leverage existing index for queries

Options 3 and 4 eliminated. Option 3 introduces an index that goes stale whenever the user edits task files directly. Option 4 doesn't work because Vault Intuition doesn't expose structured frontmatter queries.

**Requirements that drove the decision:**
- All task operations go through AI infrastructure (no terminal usage)
- Multiple simultaneous Claude sessions are a regular pattern
- Markdown files are the source of truth (non-negotiable)
- Simplest solution that actually meets all requirements
### Operations Design: Single Dispatch with 8 Actions
| Action | Required | Optional | Server does |
|--------|----------|----------|-------------|
| `create` | `name` | `description`, `status`, `topic`, `parent` | Create file from template, fill frontmatter, add progress log entry |
| `start` | | `task_name` | Set status in-progress, add progress log. If idea, move file from ideas/ to tasks/ |
| `complete` | | `task_name` | Set status done, set completed date, move to archive/, move outputs to archive/ |
| `pause` | | `task_name` | Set status paused, add progress log |
| `log` | `entry` | `task_name` | Append timestamped entry under today's date heading |
| `read` | | `task_name` | Return parsed task (frontmatter + sections) or structured overview |
| `update` | `task_name`, `field`, `value` | | Update frontmatter field |
| `audit` | | | Run all review checks: date bucket re-sort, broken links, orphans, status mismatches |
### What Stays in SKILL.md (Judgment and Conventions)
The engine handles deterministic file operations. SKILL.md retains:
- Naming/title conventions (verb-first imperative, sentence case)
- Topic inference ("which MOC does this map to?")
- "IS a task" vs "NOT a task" guidance
- User confirmation before complete
- Git commit + push after complete
- Summary communication format
- When to brainstorm vs implement
- Output file linking rules
## Codex Reviewer Synthesis + Implementation Handoff
> **Provenance:** This section was produced by OpenAI Codex (GPT-5.3-Codex), not Claude/Opus. Codex was asked to critically review the task design, challenge assumptions, and produce implementation-ready context.

### Critical Assessment
**What the design got right:**
- Correctly identified the real bottleneck: correctness/safety of writes, not Obsidian scale
- Correctly separated storage decision from operation mechanism
- Strong decomposition of what stays in SKILL.md vs moves to code

**Where the design was still weak:**
1. No hard SLOs or decision thresholds
2. Concurrency model not concretely specified
3. Read-path and write-path conflated in mechanism debate
4. Action surface may be too coarse (`update` can become a schema escape hatch)
5. TASKS.md as mutable cache remains risky

### Definitive Recommendation (Codex)
**Build a script-first deterministic task engine now, with an internal architecture that can later be wrapped by MCP if needed.**

**Staged rollout plan:**
- **Stage 1 (implement now):** Script-based operations with file locking, atomic write-replace, schema validation, explicit errors, deterministic timestamps, idempotency
- **Stage 2 (measure):** Track write conflicts, read latency, validation errors, drift incidents
- **Stage 3 (conditional):** Add MCP wrapper only if measurement justifies it
## Progress Log
### 2026-02-28
4:53 PM *Status -> Done*

4:51 PM **Bug fix: force UTF-8 stdin on Windows**
- Added `sys.stdin.reconfigure(encoding='utf-8')` at task.py entry point
- Root cause: Windows bash defaults to CP1252, corrupting Unicode chars piped via heredoc
- Fix is systemic, callers no longer need to know the correct heredoc pattern

4:51 PM *Status -> In Progress (reopened)*
### 2026-02-19
11:52 PM *Status -> Done*
11:44 PM **Gap analysis complete, fixes applied**
- End-to-end testing: all 11 operations passed
- Gap audit found 9 items (3 high, 2 medium, 4 low)
- Fixed 6 gaps in SKILL.md
- Final SKILL.md: 390 lines (~4,752 tokens). Down from 655 lines (~8,508 tokens). 44% reduction.
11:23 PM **SKILL.md refactored to use task engine CLI.** Replaced all file-editing instructions with `task.py` calls. 51% initial reduction, 44% after gap analysis fixes.
11:10 PM **Phase 3 Stage 1 complete: task engine built and tested.** Built 7-module Python CLI at `.task-engine/`. Integration test passed: full lifecycle all working. One bug fixed during testing (None output field).
10:29 PM **Delivery mechanism revised to script-first after Codex independent review.** Codex identified five weaknesses, asked 8 critical design questions, and recommended script-first with MCP conditional on measured need.
09:17 PM **Delivery mechanism resolved: MCP server.** (Subsequently revised, see above.)
### 2026-02-16
02:08 PM **Created MCP vs CLI reference document.**
02:06 PM **Design input: the Bases gap.** Captain's log work surfaced a general problem: Bases solves frontmatter queries for humans, but Claude has no efficient equivalent.
01:51 PM **Added Peter Steinberger MCP vs CLI reference.** From Lex Fridman #491 transcript.
01:40 PM **Delivery mechanism challenged. Phase 2 reopened.** User asked: why an MCP server and not just a script?
01:03 PM Captain's log spun out as subtask: [[Build captain's log for design decisions]].
12:22 PM **Phase 2 design captured.**
### 2026-02-15
05:18 PM **Added `cancelled` terminal state.** Researched across 11 tools (Jira, Linear, GitHub, Azure DevOps, YouTrack, Asana, Trello, Todoist, Things 3, Taskwarrior, Obsidian Tasks). Found consensus: two terminal categories (done + cancelled).
02:24 PM **Task renamed and expanded.** Research -> Develop. Added Phase 2 (design) and Phase 3 (build).
01:45 PM **Research complete.** Three parallel agents returned. Compiled into output doc.
01:33 PM **Brainstorm complete.** Scoped three research layers.
01:13 PM *Status -> In Progress*
12:39 PM *Status -> Pending (task created)*
