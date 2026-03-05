---
name: using-skills
description: Injected automatically at session start via hook. Establishes skill enforcement and session orientation.
---
<!-- skill-loaded: using-skills -->

# Using Skills

**IMPORTANT: Invoke relevant skills BEFORE any response or action.** Even a 1% chance a skill applies means invoke it first. If it turns out to be wrong for the situation, stop using it. This is not optional. Do not rationalize skipping a skill.

## Session Orientation

On every session start, resume, clear, or compaction, orient silently before responding.

**User names a specific task:** Read that task file. Check the progress log for recent activity (within 2 hours); if found, warn about possible concurrent session. Then start working.

**User implies work status** ("what should we work on?", "what's new?", or similar): Run `.task-engine/task.py list`. Scan all tasks across all categories.

**Anything else:** Just respond. No task engine, no orientation.

**Session ID:** Run `echo "SESSION_PROBE_$(date +%s%N)"`, then `bash .scripts/detect-session-id.sh "<probe_string>"`. Store the UUID silently for learning log entries and task engine log calls.

Only speak up if something is wrong (status mismatch, missing file, broken link). If everything is clean, respond to the user's actual request.

## Post-Compaction Protocol

After compaction, state what you believe you were working on. Read that task file. Run `.task-engine/task.py list` for broader awareness. Continue where you left off.

## Available Skills

| Skill | Trigger | Type |
|-------|---------|------|
| `/task new <name>` | Work emerges that should be tracked, multi-step effort, idea capture | Flexible |
| `/task start` | Beginning work on a paused or idea task, switching focus | Flexible |
| `/task complete` | Task finished, success criteria met | Flexible |
| `/task cancel` | Task superseded, irrelevant, or won't be done | Flexible |
| `/task status` | Current work state, choosing what to work on | Flexible |
| `/brainstorm` | Before creative/design work. Unclear scope. NOT when design is settled. Auto-starts the task. | Flexible |
| `/task review` | Daily review due. On demand for audit/review. | Flexible |
| `/research` | Before Task tool agents for research. No default: `--quick` (fact lookup) or `--deep` (surveying a space). Announce mode + reasoning. NOT quick lookups. | Flexible |
| `/digest <URL>` | YouTube, X/Twitter, or blog URL for content triage. Multiple URLs for parallel batch. `--quick` for fast triage (no transcript). | Action |
| `/process <note>` | Process/triage a vault note as inbox. Always explicit. | Action |
| `/ingest <source>` | Scanned PDF for OCR transcription. Also: `/ingest scan`, `/ingest status`. Always explicit. | Action |
| `/shop` | Product search, price comparison, "find me X" for Thai e-commerce. Triggers on shopping requests. | Flexible |
| `/autonomous` | Explicit request: "go work autonomously". NOT automatic. | Flexible |

## Vault-Aware Work

Use the 4 MCP vault tools (Vault Intuition server) proactively. Search first, don't guess. `vault_search` for specific terms, `vault_semantic` for concepts.

**Do not use vault tools** when the question is about workspace files (Read/Grep), code (Grep/Glob), info already in context, or purely conversational.

| Trigger | Tool(s) |
|---------|---------|
| Vault notes, "what I've written about" | `vault_search` + `vault_semantic` |
| Therapy, coaching, personal reflection | Read `context/<your-profile>.md` + `context/<your-context-files>.md` first, then `vault_semantic` + `vault_util(action="note")` |
| "What did we discuss about X?" | `vault_sessions` then `vault_util(action="session_detail")` |
| Past thinking, prior reasoning | `vault_search` then `vault_util(action="note")` |
| Note relationships, connections | `vault_util(action="graph")` |
| Recent vault activity | `vault_util(action="recent")` |
| Vault structure, analytics | `vault_util(action="stats")`, `vault_util(action="browse")` |
| the user's life, history, interests | `vault_semantic` + `vault_search` |

**vault_util actions:** `note` (full content, fuzzy match), `graph` (relationships), `browse` (folders), `recent` (time-based), `stats` (analytics), `rebuild` (re-index), `session_detail` (past conversation).

### External Data

For Toggl time tracking, see `docs/toggl-integration.md`. For Asana workspace queries, see `docs/systems.md`.

## Improvement Logging

Notice a system gap bigger than this task, or learn a new preference from the user? **Log first, fix second.** Read `.claude/skills/using-skills/references/improvement-logging.md` for the full procedure, then flag it and continue working.

## Red Flags

These thoughts mean STOP. You are rationalizing:

| Thought | Reality |
|---------|---------|
| "I already know the task state" | Files over memory. Run `task.py list` or read the task file. |
| "Let me just dive in and help" | Explore first. Ask questions. Understand before acting. |
| "I remember what the profile says" | Re-read the actual file. Memory drifts. Files don't. |
| Any rationalization to skip a skill | Skills are mandatory when relevant. Check BEFORE any response. |
| "The idea is clear enough, I can skip brainstorming" | If it's creative/design work, brainstorm first. |
| Any rationalization to skip the task gate | The gate is BEFORE implementation, not after. No exceptions. |
| "I'll tighten up the per-prompt rules during this review" | per-prompt-rules.md is critical infrastructure. Dedicated task + user approval required. |
| "Here are 10 fixes from the review, I'll just do them all" | Each item needs its own process check. Ask "what process applies to each?" before executing any. A batch of items is not pre-approval. |

## Core Principles

- **Skill priority:** Orientation first, then process skills, then action skills.
- **Understanding before advice.** Explore, ask questions, don't jump to solutions.
- **Files over memory.** After compaction, re-read actual files. Never trust summaries alone.
- **Instructions say WHAT, not HOW.** "Help me with X" doesn't mean skip skills or jump to answers.
