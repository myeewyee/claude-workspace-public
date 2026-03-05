# Mode: new

## Input
```
/task new <task name> [optional description]
```

## Before Creating: Reopen Check

Before creating a new task, check whether an existing task (active or archived) already covers this scope. **Reopen** when:
- The new work would modify the same files the original task modified
- The new observation describes the same gap, just deeper or from a new angle
- The original task's success criteria would expand naturally to cover the new work

**Create new** when:
- Different root cause, even if the same area
- Different component entirely
- The original task's criteria are fully met and the new work is a genuinely separate concern

**Key test:** "Would adding this to the original task's Work Done make sense, or would it feel forced?" If it fits naturally, reopen. If you'd need to rewrite the task's identity, new task.

**To reopen an archived task:**
1. Reopen via task engine:
   ```bash
   python .task-engine/task.py reopen --task "Task Name"
   ```
   This moves the file from archive to tasks/, sets status to 1-active, clears the completed field, and logs the reopen.
2. Expand the task doc: update description, success criteria, context with the new scope

## Subtask vs Parked Item

When work relates to an existing task, decide whether to create a subtask or add a parked item:

| Signal | Route |
| ------ | ----- |
| Can be done in the same work session as the parent | Parked item |
| Needs its own brainstorm, approach, or success criteria | Subtask |
| Could be worked on independently of the parent | Subtask |
| Is just a note or reminder for a future version | Parked item |
| Has enough scope that you'd want to track progress | Subtask |

When promoting a parked item to a subtask, strikethrough the original line in the parent task and add a wiki-link to the new subtask (e.g., `~~Original text~~ Promoted to subtask: [[Subtask Name]]`).

## Process

1. **Apply conventions:** Sentence case filename, verb-first imperative title (see CLAUDE.md Conventions for naming rules).
2. **Infer parent:** Use containment: "what project or system is this task *part of*?" If it modifies an existing system, parent to that system's task (e.g., `[[Build Vault Intuition system]]`). If it's a subtask of an active project, parent to that project. If no natural container exists, leave parent empty. Don't use the spawning task as parent (spawning goes in the Context section, not `parent:`). If unclear, ask.
3. **Create via task engine:**
   ```bash
   python .task-engine/task.py create --name "Task name" --description "What and scope" --parent '[[$Parent]]' \
     --focus internal --category improvement --pillar workflow --session "UUID"
   ```
   Always pass `--session` with the current session UUID (detected during orientation). This embeds the birth session in the creation progress log entry for traceability.

   Always set classification fields at creation — don't defer to start time:
   - `--focus`: `internal` (workspace/system work) or `external` (user-facing product or feature)
   - `--category`: `feature` | `bug` | `improvement` | `research` | `maintenance`
   - `--pillar`: `memory` | `workflow` | `self-improve` (internal tasks only; omit for external)

   For ideas: add `--status 3-idea`. For recurring tasks: add `--status 4-recurring --cadence weekly` (or daily, monthly, quarterly, on-demand). For multi-line descriptions: add `--stdin` and pipe via heredoc `<<'EOF'`.
4. **Populate body sections:** The engine creates a skeleton with empty sections. Before confirming, fill in sections using only what was actually discussed in the conversation. Write these down now, not later. Leave sections empty only when there is genuinely nothing to capture yet (e.g., Approach for an early-stage idea). Never fabricate content to fill a section. The skeleton is not the finished product. **No blank lines around headings** (see `docs/markdown-formatting.md`).

   **Context section guidance:** Context is the most important body section. Cover these three elements:
   - **Trigger:** What event, conversation, or observation created this task. Be specific: name the session topic, the date, the incident. If this task was spawned by or surfaced during another task, name that task with a wiki-link (e.g., "Surfaced during [[Audit and standardize vault frontmatter]] while reviewing..."). This is the authoritative place for origin and provenance, since `parent:` expresses containment only, not spawning.
   - **Sources:** What existing notes, entries, sessions, or prior work informed the thinking. Link at the level of specificity that lets someone trace back: note name alone for focused notes (e.g., `[[Brainstorm self-improving machine]]`), subheading link for entries within larger notes (e.g., `[[AI Learning Log#21/2/26]]`), or note link plus inline context when no heading exists (e.g., `[[AI Learning Log]] 20/2 entry ("getting bogged down with incremental improvements")`). Generic bare links are insufficient when you're referencing something specific within a note. **Inbox processing provenance:** When a task is created from `/process` or improvement mode, link to the triage output file as the permanent record (not the source note, which may be deleted). Example: `**Origin:** Surfaced during inbox triage of [[AI Learning Log]], processed in [[Inbox triage - AI Learning Log 2026-03-05]] (item #3).`
   - **Scope:** What the work became. How it was framed, what it covers.

   **Formatting:** Bold-lead paragraphs. Each paragraph opens with a **Bold label:** that identifies its topic (e.g., **Problem:**, **Origin:**, **Key lesson:**). Labels are flexible, not fixed. Never write Context as a single block of text.

   **Context is prose only.** No subsection headings (###) inside Context. The engine creates `### Related` under `## Links` automatically. Use that, don't create a duplicate.

   **Context vs. Related:** Context links are provenance (where this task came from). Related links (under `### Related` in the `## Links` section) are adjacency (what's nearby). If a note is already linked with full context in the Context section, it doesn't need a bare repeat in Related.

   **Origin input callout:** When the task was spawned from substantial user input (voice-to-text messages, pasted external conversations, multi-paragraph explanations), include the user's verbatim words as a collapsible callout at the end of the Context section, after the summary paragraphs:
   ```
   > [!quote]- Origin input (session xxxxxxxx)
   > [User's original message verbatim]
   ```
   The `-` makes it collapsed by default in Obsidian. Include full verbatim up to ~500 words; beyond that, excerpt key passages and note the full input is in the linked session. Content: the user's originating message(s) only, not Claude's responses. Not needed for direct one-line instructions or when the user's input is already fully captured by the summary paragraphs.
5. **Context alignment (non-idea tasks only):** If the task is not `3-idea` status, run the context alignment gate after populating body sections. Read `references/context-alignment.md` for the full procedure. Check the `context-aligned:` frontmatter field: empty → full alignment (agent-based), populated → light refresh. Skip this step entirely for idea tasks (quick capture is the priority). The alignment may surface an existing task that should be reopened instead, see the reopen check in the procedure.
6. **Confirm:** `Task created: [Task Name] -> tasks/Task Name.md`
