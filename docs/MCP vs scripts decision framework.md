---
type: artifact
source: claude
created: 2026-02-21 17:25
parent: "[[Build MCP-vs-scripts decision framework]]"
description: "Reusable decision framework for MCP server vs scripts vs third-party MCP install. Five decision variables, two decision trees, token cost formula, worked examples from past workspace decisions, and actionable recommendations."
---

# MCP vs scripts decision framework

**Context:**
**Why:** Created during [[Build MCP-vs-scripts decision framework]]. The workspace has made this decision repeatedly (Vault Intuition, task engine, review scraper, Context7, Kiwi.com) without a codified framework. Each time, the reasoning was ad hoc. This document standardizes the decision process.
**When:** 2026-02-21. Based on 5 past workspace decisions, Peter Steinberger's analysis from Lex Fridman Podcast #491, and token measurements from [[Context management token analysis]] (22 sessions, 2026-02-19 to 2026-02-20).
**How:** Brainstorm-driven design validated against all 5 past decisions (4/5 match, 1 flagged as wrong). Absorbs and supersedes [[MCP vs CLI and stateful vs stateless operations]].

## Core Principles

Three principles from Peter Steinberger (OpenClaw founder, Lex Fridman Podcast #491) form the foundation:

**1. Training advantage.** Models are trained on Unix commands. A CLI is just another Unix command. An MCP tool requires learning a new structured protocol. When you build a CLI, you leverage existing capabilities. When you build an MCP, you ask the model to learn something new.

**2. Composability.** MCP tools return monolithic data blobs. The full response enters context every time. CLIs compose via pipes: `weather-api | jq '.temperature'` means the model only sees the filtered value. MCP tools have no equivalent of `jq` filtering before the result hits context.

**3. Simplicity default.** If stateless scripts work, use them. Only add the complexity of a persistent server when the problem requires it. The Unix philosophy (small, composable, stateless tools) is simpler, more robust, and easier to understand than monolithic stateful services.

## Key Distinction: State vs Data

The word "state" causes confusion because tools often have persistent data (task status in YAML, cached files on disk). The distinction that matters:

| Concept | Where it lives | Survives restart? | Examples |
|---------|----------------|-------------------|----------|
| **State** (runtime) | RAM | No | Embedding models, browser sessions, connection pools, in-memory indexes |
| **Data** (persistent) | Disk | Yes | Task status in YAML, cached JSON, file contents, disk-based indexes |

A tool that reads a YAML file, modifies it, and writes it back is **stateless** even though the data persists. The tool holds nothing in memory between calls.

A tool that loads an embedding model at startup and keeps it in RAM for fast queries is **stateful**. If the process dies, the state is lost and must be rebuilt.

**The grey area: disk-based indexes.** A script that reads a JSON index file on each call is stateless but optimized. You get most of the speed benefit of an in-memory index without the runtime state complexity. For small-to-medium datasets (hundreds of files, a few MB of index), this is usually fast enough.

## Decision Variables

Five variables determine the right choice:

1. **Statefulness**: Does the tool need persistent runtime state (RAM)? Embedding models, browser sessions, connection pools.
2. **Session frequency**: What percentage of sessions use this capability?
3. **Tool definition token cost**: How many tokens do the MCP tool definitions add to every session? (~200-400 tokens per tool for name + description + JSON schema)
4. **Call pattern**: One-shot per session, or multiple sequential calls? Multi-call patterns amplify the performance benefit of keeping state in RAM.
5. **Build vs install**: Are you building the tool (you control architecture) or installing a third-party MCP (install/don't install decision)?

## Decision Tree: Build

Use this when you're building a new capability and choosing the delivery mechanism.

```
Does the tool require persistent runtime state?
│
├─ YES (embedding models, browser sessions, connection pools)
│   │
│   └─ Can the state be moved to disk?
│       │
│       ├─ YES, and disk-based is fast enough
│       │   └─ SCRIPT with disk index
│       │
│       └─ NO (model loading too slow, live sessions required)
│           └─ MCP SERVER
│
└─ NO (stateless: read/process/write operations)
    │
    └─ Default: SCRIPT
        │
        └─ Check frequency + call pattern:
            │
            ├─ High frequency (>50%) AND multi-call pattern
            │   AND scripts have a proven performance bottleneck
            │   └─ Consider MCP (but only with measured evidence)
            │
            └─ All other cases
                └─ SCRIPT
```

**The simplicity tiebreaker:** When the decision tree lands in a grey area, default to scripts. Scripts are simpler to build, simpler to debug, simpler to maintain, and cost zero tokens when not invoked. Only escalate to MCP with proven justification.

## Decision Tree: Install (Third-Party MCPs)

Use this when deciding whether to add a third-party MCP server to your workspace.

```
How often will I use this capability?
│
├─ Frequently (>30% of sessions)
│   └─ INSTALL
│       Token cost amortizes across frequent use.
│
├─ Occasionally (5-30% of sessions)
│   │
│   └─ Token cost < ~800 tokens (2-3 tools)?
│       │
│       ├─ YES → INSTALL
│       │
│       └─ NO → Evaluate alternatives:
│           - Web search for the same information?
│           - Bash script wrapping the same API?
│           - Lighter MCP with fewer tools?
│
└─ Rarely (<5% of sessions)
    └─ DON'T INSTALL
        Use alternatives: web search, direct API calls
        via Bash, one-off scripts.
```

**Maintenance consideration:** Third-party MCPs can break, change APIs, or add tools you didn't ask for. This isn't a decision variable (hard to quantify upfront) but should factor into borderline cases.

## Token Cost Formula

For quantifying the cost of an always-on MCP:

```
Wasted tokens per session = tool_definition_tokens × (1 - usage_frequency)
```

Example calculations from this workspace:

| Tool/Server | Est. tokens | Usage freq. | Wasted/session |
|-------------|-------------|-------------|----------------|
| Vault Intuition (10 tools) | ~4,200 | ~50% | ~2,100 |
| Context7 (2 tools) | ~600 | ~25% | ~450 |
| Kiwi.com (2 tools) | ~600 | ~2% | ~588 |
| Task engine (hypothetical MCP, 2 tools) | ~400 | ~90% | ~40 |

**Important caveats:**
- The ~200-400 tokens per tool estimate is derived from the [[Context management token analysis]] methodology, not from running an actual tokenizer. Treat as approximate.
- This formula is a **tiebreaker for edge cases**, not the primary decision driver. The decision trees handle the main logic.
- For servers with many tools, the cumulative cost matters more than per-tool cost. 10 tools at 400 tokens each = 4,000 tokens every session.

## Worked Examples

### 1. Vault Intuition → MCP Server (justified, with caveats)

**Decision:** MCP server with 10 tools.
**Framework says:** MCP, because `vault_semantic` requires the e5-small-v2 embedding model in RAM (~500MB, 10-15 second cold start). Scripts can't hold this between calls.

**However:** Only 1 of 10 tools genuinely requires RAM:

| Tool | Needs RAM? | Why |
|------|-----------|-----|
| `vault_semantic` | **Yes** | Embedding model must be loaded for query vectorization |
| `vault_search` | Benefits | BM25 index in memory is faster, but a disk-based index works |
| `vault_sessions` | Benefits | Same BM25 pattern as vault_search |
| `vault_note` | No | Fuzzy match a filename, read the file |
| `vault_graph` | No | Load link map from JSON, traverse |
| `vault_browse` | No | Directory listing with metadata |
| `vault_recent` | No | Sort files by modification time |
| `vault_stats` | No | Count files, sum sizes |
| `vault_rebuild` | No | Batch operation, more natural as script |
| `vault_session_detail` | No | Read a single JSONL file and format it |

**Recommendation:** Slim to 1-3 MCP tools (`vault_semantic`, possibly `vault_search` and `vault_sessions`). Move the other 7 to scripts. This could save ~1,500-3,000 tokens per session while keeping the capability that actually needs MCP.

### 2. Task Engine → Script (correct)

**Decision:** Python CLI called via Bash.
**Framework says:** Script. Operations are stateless (read file, modify, write back). Used in ~90% of sessions with multi-call patterns, so the "consider MCP" branch triggers. But scripts work fine with no performance bottleneck, so the simplicity tiebreaker applies.

**Additional note:** The task engine had a "Stage 3: conditional MCP wrapper" planned, pending measurement data. The framework concludes this isn't worth pursuing. No performance problem exists to solve.

### 3. Review Scraper → Script (correct)

**Decision:** Python script at `.scripts/review_scraper.py`.
**Framework says:** Script. Stateless (call API, cache JSON). Used <5% of sessions (a few times per month). Falls squarely in "script, always" territory.

**History:** This decision was originally MCP, then reversed to scripts, then briefly re-reversed when research found existing MCP servers, then re-reversed again when token cost analysis showed 95% of sessions would pay for unused tool definitions. The framework would have avoided this flip-flopping by starting at the statefulness gate (stateless → default script) and never reaching the MCP branch.

### 4. Context7 → Install (correct)

**Decision:** Installed third-party MCP (2 tools).
**Framework says:** Install. Used in ~20-30% of sessions (whenever building or researching libraries). Token cost is low (~600 tokens, 2 tools). Falls in the "occasionally used + low cost → install" zone.

### 5. Kiwi.com → Install (framework says: wrong)

**Decision:** Installed third-party MCP (2 tools).
**Framework says:** Don't install. Used in ~1-2% of sessions (one-off trip planning). ~600 tokens loaded every session for essentially zero benefit. Flight search via web search or a script would work for the rare occasions it's needed.

**Recommendation:** Remove from workspace MCP configuration.

## Recommendations

Three immediate actions from applying this framework to the current workspace:

1. **Slim Vault Intuition** to 1-3 MCP tools (vault_semantic, possibly vault_search/vault_sessions). Move remaining tools to scripts. Estimated savings: ~1,500-3,000 tokens per session.

2. **Remove Kiwi.com MCP.** Use web search or a Bash script for the rare flight search. Estimated savings: ~600 tokens per session.

3. **Drop task engine Stage 3** (conditional MCP wrapper). The framework confirms scripts are the right choice. No measurement data needed because there's no performance problem.

## Review Integration

Reference this framework:
- During `/task review` when evaluating new build or install decisions
- During best practices audit when reviewing MCP configuration
- When brainstorming any new capability that could be MCP or script
- When considering installing a new third-party MCP server

## Related

- [[Context management token analysis]] (token measurements this framework relies on)
- [[Audit context management overhead]] (drift-risk framing, placement rules)
- [[MCP vs CLI and stateful vs stateless operations]] (prior analysis, superseded by this document)
- [[Build review scraper]] (where this framework idea originated)
- [[Build Vault Intuition system]] (primary MCP server example)
- [[Develop agent-friendly task management system]] (task engine MCP-vs-script decision)
- [[OpenClaw The Viral AI Agent that Broke the Internet - Peter Steinberger  Lex Fridman Podcast 491]] (source for core principles)
