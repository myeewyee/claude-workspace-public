# Context Alignment

Unified procedure for discovering related prior work and situating a task within the broader landscape. Called from multiple entry points: `new.md`, `start.md`, `brainstorming/SKILL.md`. This file is the single source of truth.

## Gate Check

Read the task's `context-aligned:` frontmatter field:
- **Empty** → run full alignment (below)
- **Populated** → run light refresh (below)

## Full Alignment (first run)

Run as a subagent (Agent tool, `subagent_type: "general-purpose"`, `model: "sonnet"`) to keep the main context window clean. The agent prompt must include:

### Agent prompt template

```
You are performing context alignment for a task. Your job: search for related prior work, read it deeply, and enrich the task file.

**Task file:** [paste full task file content]

**Instructions:**

1. **Context enrichment (sparse tasks only):** If the task has minimal context (name only, one-line description, empty Context section), check the Progress Log for a `<!-- session: UUID -->` on the creation entry. If found, use `vault_util(action="session_detail", session_id="UUID")` to pull the originating conversation. Extract relevant context to build better search terms. Skip this step if the Context section already has substantive content.

2. **Extract search terms** from: task name + description + Context section content.

3. **Search** (parallel, both zones, no folder filter):
   - `vault_search(query="[key terms]", limit=10)` — keyword search
   - `vault_semantic(query="[task description]", limit=10)` — conceptual search
   - If vault tools are unavailable, fall back to Grep across `tasks/`, `tasks/archive/`, `tasks/ideas/`, `outputs/`

4. **Deep read** top 5-8 results (ranked: parent/child first, shared-topic tasks, conceptual overlap, vault notes). For each, extract:
   - What approach was used?
   - What lessons were learned?
   - What's still unfinished or unresolved?
   - Status: active, paused, done, cancelled?

5. **Reopen check:** If a discovered task overlaps in scope, flag it. Apply these criteria:
   - Would the new work modify the same files?
   - Does it describe the same gap, just deeper or from a new angle?
   - Would adding to the original task's Work Done feel natural?
   If reopen seems warranted, DO NOT reopen. Flag it in your return summary for the main session to decide.

6. **Write to task file:**
   - Add a `**Landscape:**` bold paragraph to the Context section (append after existing content, prose only, no H3 headings inside Context)
   - Populate `### Related` with discovered links, format: `- [[Task Name]] -- brief inline context explaining the connection`
   - Do not duplicate links already present in Context or Related
   - Follow existing agent output conventions: no blank lines around headings, no horizontal rules

7. **Return a chat summary** (2-4 sentences) to the main session. Distinguish Claude-workspace findings from vault-side findings. Example:
   > "Found 3 related tasks: [[X]] (done, used approach A), [[Y]] (paused, blocked on Z), [[W]] (idea). Vault has relevant notes in the journal about this topic from January."

8. **Set context-aligned timestamp:** After writing, update the frontmatter:
   ```bash
   python .task-engine/task.py update --task "Task Name" --field "context-aligned" --value "YYYY-MM-DD HH:mm"
   ```
   Use the actual current timestamp (run `date` first).
```

### Enforcement
This step is non-skippable. "We already discussed the landscape" is rationalization. The search surfaces connections you don't know about. Even if the user described related work, the search may find more.

## Light Refresh (subsequent visits)

Run in the main session (no agent needed). This is a quick check, not a deep dive.

1. Extract key terms from task name + description + Context section.
2. Re-run `vault_search(query="[key terms]", limit=10)`.
3. Compare results against existing `### Related` links.
4. If new items found that weren't in Related:
   - Surface in chat: "Since last alignment, these related items appeared: [list with brief context]"
   - Add to `### Related` if warranted
5. Update `context-aligned:` timestamp via task engine.

## When to Skip Entirely

- **Idea capture** (`/task new --status 3-idea`): Context alignment deferred. Quick capture is the priority.
- **No task exists** (exploratory brainstorm without a task file): Nothing to write to.
