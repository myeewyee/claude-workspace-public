---
completed: 2026-02-21 17:29
created: 2026-02-21 10:18
decision: null
description: 'Codify a reusable decision framework for when to build an MCP server
  vs standalone scripts vs other integration patterns. Core variables: session frequency
  and always-on token cost. Pull in prior work from context management audit, model
  selection evaluation, and any other relevant research across past tasks. Output:
  a conventions/framework document that future build decisions can reference.'
parent: ''
source: claude
status: 5-done
type: task
focus: internal
category: research
pillar: memory
---
# Build MCP-vs-scripts decision framework
## Context
Emerged during a review scraper brainstorm. We needed to decide MCP server vs scripts and realized there's no codified framework for this recurring decision. Initial analysis concluded that only two variables matter: (1) session frequency (what % of sessions use the capability) and (2) always-on token cost (MCP tool descriptions load every session regardless). "Conversational integration" was initially proposed as a third variable but rejected as noise: from the user's perspective, a Bash-invoked script and a native tool call are indistinguishable.

Working numbers from [[Context management token analysis]]: MCP tools cost ~200-400 tokens each (name + description + JSON schema). Vault-intuition's 10 tools contribute an estimated 2,800-5,600 tokens to every session start. The rough heuristic proposed: >50% session usage = MCP server, <50% = scripts.

This needs to be validated against prior work and external opinions before codifying.
## Links
### Related
- [[Audit context management overhead]] (token cost measurements, drift-risk framing)
- [[Context management token analysis]] (actual session token data)
- [[Evaluate model selection across task types]] (similar "codify a recurring decision" pattern)
- [[Build Vault Intuition system]] (example of MCP server decision)
- [[MCP vs CLI and stateful vs stateless operations]] (prior analysis, to be absorbed into new framework)
- [[Build review scraper]] (where this idea originated, MCP reversed to scripts)
### Subtasks
```base
filters:
  and:
    - type == "task"
    - parent == "[[Build MCP-vs-scripts decision framework]]"
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
    - parent == "[[Build MCP-vs-scripts decision framework]]"
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
A single conventions document that future build decisions can reference. Should include: decision tree, token cost formulas, worked examples from past decisions, and clear thresholds.
## Design
### Decision Variables (5)
1. **Statefulness**: Does the tool need persistent runtime state (RAM)? Embedding models, browser sessions, connection pools.
2. **Session frequency**: What % of sessions use this capability?
3. **Tool definition token cost**: How many tokens do the tool definitions add to every session?
4. **Call pattern**: One-shot or multiple sequential calls per session? Multi-call amplifies RAM benefit.
5. **Build vs install**: Building the tool (you choose architecture) vs installing a third-party MCP (install/don't install).
### Decision Tree: Build
First split is statefulness (hard constraint):
- **Needs persistent RAM** (embedding models, browser sessions) -> MCP server. But check: can the state move to disk? If disk-based is fast enough -> script with disk index.
- **Stateless** (read/process/write) -> Default to script.
  - High frequency (>50%) AND multi-call pattern -> consider MCP only if scripts have a proven performance bottleneck.
  - Low frequency OR single-call -> script, always.
- **Simplicity tiebreaker** (Peter Steinberger): if scripts work, use scripts, regardless of token math.
### Decision Tree: Install (Third-Party MCPs)
Frequency bands:
- **>30% of sessions** -> Install. Token cost amortizes.
- **5-30% of sessions** -> Install IF token cost < ~800 tokens. Otherwise evaluate alternatives.
- **<5% of sessions** -> Don't install. Use alternatives.
### Token Cost Formula
Wasted tokens per session = tool_definition_tokens x (1 - usage_frequency). Useful as a tiebreaker for edge cases, not the primary driver.
### Worked Examples (5)
1. **Vault Intuition -> MCP** (justified, but only 1 of 10 tools genuinely needs RAM: vault_semantic for embedding model. 7 tools could be scripts.)
2. **Task engine -> Script** (stateless, works fine via Bash. Stage 3 MCP wrapper not worth pursuing.)
3. **Review scraper -> Script** (infrequent <5%, stateless, MCP explicitly rejected.)
4. **Context7 -> Install** (moderate use ~25%, low token cost ~600 tokens.)
5. **Kiwi.com -> Don't install** (rare use ~2%, alternatives exist. Framework flags this as wrong decision.)
### Recommendations
- Slim Vault Intuition to 1-3 MCP tools (vault_semantic, possibly vault_search/vault_sessions), move remaining 7 to scripts
- Remove Kiwi.com MCP, use web search or script alternative
- Drop task engine Stage 3 (conditional MCP wrapper)
## Approach
1. Write the framework document in `docs/` (absorbing prior MCP-vs-CLI doc content)
2. Update task file with work done
3. Add review integration references
4. Update systems.md to reference the new convention
## Work Done
- Framework document written: [[MCP vs scripts decision framework]] at `docs/mcp-vs-scripts-framework.md`
- Absorbs Peter Steinberger's analysis and state-vs-stateless definitions from [[MCP vs CLI and stateful vs stateless operations]]
- Includes all 5 worked examples with Vault Intuition per-tool breakdown
- 3 actionable recommendations (slim VI, remove Kiwi, drop Stage 3)
- systems.md updated with Decision Frameworks section
## Progress Log
### 2026-02-21
5:29 PM *Status -> Done*
5:24 PM **Framework document written**
- Full document at docs/mcp-vs-scripts-framework.md
- Core principles, two decision trees, token formula, 5 worked examples, 3 recommendations
- Absorbs and supersedes [[MCP vs CLI and stateful vs stateless operations]]
5:18 PM **Brainstorm complete: design validated**
- 5 decision variables identified: statefulness, session frequency, token cost, call pattern, build-vs-install
- Two decision trees: build (statefulness gate) and install (frequency bands)
- Token cost formula as quantitative tiebreaker
- 5 worked examples validated against past decisions (4/5 match, Kiwi.com flagged)
- Design section added to task file
4:58 PM *Status -> In Progress*
10:18 AM *Status -> Idea (task created)*
