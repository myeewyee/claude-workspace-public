---
name: process
description: "Process vault notes as inboxes. Triages unstructured entries into destination buckets (idea tasks, conventions, existing task context, etc.). Usage: /process <note name> [#section]."
---

# Process: Vault Inbox Triage

## Usage

```
/process <note name>              -> Process all unprocessed entries in a note
/process <note name>#<section>    -> Process a specific section (e.g., #23/2/26)
/process --scan                   -> Check registered inbox notes for new content
```

## Prerequisites

- Vault Intuition MCP server running (for `vault_util` action="note")
- State file exists at `context/inbox-state.json`

If the state file doesn't exist, create it with an empty registry and processed log before proceeding.

## Processing Flow

### Step 1: Read and diff

Read the note via `vault_util(action="note")`. Read the state file (`context/inbox-state.json`), specifically the section for this note.

Compare the note content against processed items to identify unprocessed content:
- For **date-headed logs** (entries under `##### DD/M/YY` or `### YYYY-MM-DD` headings): the natural unit is a date entry.
- For **less structured notes**: use paragraph-level chunking.

If a specific section was requested (`#section`), only process that section.

### Step 2: Extract items

Parse each unprocessed section into discrete items. A single date entry may contain multiple items (an idea, a reflection, a decision, etc.).

For each item, capture:
- **Original text:** The full entry text as written in the source note (verbatim, including timestamps and session comments). This is preserved in the JSON state for provenance.
- **Summary:** A one-line summary
- **Source reference:** Note name + section/date identifier (e.g., `AI Learning Log#23/2/26`)
- **Recommended bucket:** See Destination Buckets below
- **Reasoning:** Why this bucket (one sentence)
- **Proposed action:** What specifically to do

### Step 3: Present triage batch

Write the triage to a **permanent output file** (not chat, not temp). File naming: `outputs/Inbox triage - [Note Name] [YYYY-MM-DD].md`

Triage files are permanent audit trails, not disposable working material. They record what was processed, what was created, and what was skipped. After execution, update the Action column from "**Approve?**" to final outcomes ("Created", "Skipped", etc.).

Use this format:

```
---
created: [YYYY-MM-DD HH:MM]
description: "Inbox triage for [Note Name]"
parent: "[[active task name that triggered /process]]"
source: claude
type: artifact
---
# Inbox triage - [Note Name] [YYYY-MM-DD]

**Why:** Processing unprocessed entries from [[Note Name]].
**When:** [date]. Content window: [date range of entries being processed].

## Triage

| # | Item | Action | Reasoning | Outcome |
| --- | --- | --- | --- | --- |
| 1 | Item summary | Stays in log | Why this doesn't need action | None |
| 2 | Item summary | **New idea task** | Why this warrants a task. **Task name**: one-sentence scope. | **Approve?** |
| 3 | Item summary | Existing task context | Why it belongs to that task | Added to [[task name]] |
```

**Outcome column uses wiki-links:** When a task is created, use `[[Task Name]]` Created, not bold plain text. This makes outcomes navigable in Obsidian.

The **Reasoning** column includes the proposed task name (bold) and a one-sentence description inline for items that create tasks. Merges are visible directly: "(MERGED with #N)" in the description. Items merged into another row show "(merged into #N)" in the Action column.

Items are numbered sequentially in the order they appear in the source note.

**Action Plan (executed) section** at the end of the file. Categorized lists: Tasks created (with wiki-links), Direct fixes applied (with descriptions), Preferences added (with topic path), items with no action (compact list). Quick-scan summary of all outcomes.

Ensure the output file has `parent:` set to the active task in its frontmatter.

In chat, summarize: "Triage written to filename. X items auto-processed, Y items need your approval. Review in Obsidian and let me know."

### Step 4: Review

Wait for the user to review the triage file in Obsidian. He may:
- Approve items as-is
- Override bucket assignments
- Add notes or context
- Reject items (mark as "skip")

When he responds, proceed to execution.

### Step 5: Execute approved actions

Process each approved item using the appropriate mechanism:

- **New idea task:** `/task new --status idea`. Follow full `/task new` conventions: after engine creates the skeleton, populate Context (trigger, sources, scope) and Related sections before moving to the next item. Batch speed does not override task quality. **Provenance:** Context section links to the triage output file, not the source note (which may be deleted). Example: `**Origin:** Surfaced during inbox triage of [[AI Learning Log]], processed in [[Inbox triage - AI Learning Log 2026-03-05]] (item #3).` **Verbatim source:** Include the original source text as a collapsed callout at the end of the Context section (before `## Links`), per task skill convention: `> [!quote]- Origin input (Note Name, section)\n> [verbatim text from source note]`. For merged items, include all merged source texts.
- **New actionable task:** `/task new` with appropriate status. Same provenance rule: link to triage file in Context.
- **Existing task context:** Edit the task file directly (Work Done or Context section), log via task engine
- **Decision/convention:** Propose exact text and placement. Write only after the user confirms the specific wording and location.
- **Claude behavior correction:** Follow CLAUDE.md lesson protocol: `PROPOSED LESSON: [Problem] → [Correction] - Approve?`

**Execute one item at a time.** Do not batch-create tasks or batch-edit files. Complete each item fully (create, populate, verify) before moving to the next. Batch execution leads to pattern-matching instead of verification, and convention shortcuts.

Auto-processed items (reflection, already captured, domain knowledge, existing task context) are executed during Step 3 without individual approval. However, auto-processing still requires real verification:
- **Already captured:** Actually open the linked task/idea and confirm the specific item is there. Pattern-matching on keywords is not verification.
- **Existing task context:** Actually edit the target task file. Writing "approach note for X" in the triage table without editing X is not processing, it's deferring.

### Step 6: Update state file

After all items are processed, update `context/inbox-state.json`:

For each processed item, add an entry to the note's processed array:
```json
{
  "source": "AI Learning Log#23/2/26",
  "original_text": "Full entry text as written in source note",
  "date": "2026-02-23",
  "summary": "Spanish coach idea",
  "bucket": "new_idea_task",
  "action": "Created: [[Build Spanish learning coach]]",
  "cluster": null,
  "run": "[[Inbox triage - AI Learning Log 2026-02-24]]",
  "processed_at": "2026-02-24T14:30:00"
}
```

Fields: `source` (note#section), `original_text` (full entry verbatim), `date` (observation date), `summary` (one-line), `bucket` (exit type key), `action` (outcome with wiki-link), `cluster` (null for /process, used by improvement mode), `run` (wiki-link to triage output file), `processed_at` (ISO timestamp).

Update `last_scanned` for the note.

### Step 7: Report summary

In chat: "Processed X items from [Note Name]. Created N idea tasks, added context to N existing tasks, N reflections skipped, N already captured. [Link to triage file]."

## Destination Buckets

| Bucket | Key | Action | Autonomy |
|--------|-----|--------|----------|
| **New idea task** | `new_idea_task` | `/task new --status idea` with context linking to source | Escalate |
| **New actionable task** | `new_actionable_task` | `/task new` (idea or start immediately) | Escalate |
| **Existing task context** | `existing_task_context` | Edit task file, log via task engine | Auto |
| **Decision/convention** | `decision_convention` | Propose text and location, write after approval | Escalate |
| **Claude behavior correction** | `claude_correction` | CLAUDE.md Lessons Learned, existing approval process | Escalate |
| **Domain knowledge/insight** | `domain_knowledge` | Already in the log. Mark processed. If relates to task, route to existing_task_context. | Auto |
| **Reflection, no action** | `reflection` | Mark processed | Auto |
| **Already captured** | `already_captured` | Verify link/task exists, mark processed | Auto |

## Classification Guide

**Decision/convention vs domain knowledge:** "Would Claude need to know this to do its job differently?" If yes, it's a workspace convention (goes to CLAUDE.md or skill files). If no, it's a personal decision or heuristic that belongs in the log or the user's vault. Personal rules about how the user organizes his life, when to use tools, or how to approach problems are NOT workspace conventions, even though they are "decisions." Only decisions that change Claude's operating behavior qualify.

**Knowledge vs Claude correction:** "Is this about fixing how Claude operates, or is it knowledge the user has learned?" If the latter, the log is the right home. Claude corrections are rare and specific: recurring behavioral patterns where Claude gets something wrong.

**Reflection vs idea:** Does it imply future action ("I should..." / "We need to..." / "What if...")? That's an idea or task. Is it an observation about the present or past with no implied action ("I noticed..." / "Feeling like..." / "Today was...")? That's a reflection.

**Idea vs actionable task:** Is it concrete enough to start on? Actionable task. Is it a seed that needs scoping/research first? Idea.

**Already captured check:** Before classifying as "already captured," verify the *specific idea* exists in the target, not just a keyword match. Check:
1. Existing task list (via `task.py list`)
2. Existing idea tasks (check `tasks/ideas/`)
3. Links already present in the note (if the entry links to a task, it's already captured)
4. If claiming "part of [task]," read the task file and confirm the specific suggestion appears in its scope, approach, or work done. A task about the same general area does not mean this specific item is captured.

**Existing task context:** If an item mentions work related to a known 1-active or 2-paused task, route it there rather than creating a new task.

## State File

**Location:** `context/inbox-state.json`

**Schema (unified with improvement mode):**
```json
{
  "registry": [
    {
      "name": "Note Name",
      "type": "vault",
      "last_scanned": "2026-02-24T14:30:00"
    }
  ],
  "processed": {
    "Note Name": [
      {
        "source": "Note Name#section",
        "original_text": "Full entry text verbatim",
        "date": "2026-02-23",
        "summary": "One-line summary",
        "bucket": "bucket_key",
        "action": "Created: [[Task Name]]",
        "cluster": null,
        "run": "[[Inbox triage - Note Name 2026-02-24]]",
        "processed_at": "ISO timestamp"
      }
    ]
  }
}
```

**Reading:** Only read the section for the note being processed. Don't load the full file into context unnecessarily.

**Archival:** Entries older than 3 months can be moved to a separate `context/inbox-state-archive.json`. The active file stays lean.

**Scan mode** (`/process --scan`): Read only the registry and compare `last_scanned` timestamps against note modification dates (via `vault_util(action="note")` metadata). Report which notes have new content. Don't process anything.

## Error Handling

| Error | Response |
|-------|----------|
| Note not found via `vault_util(action="note")` | Report: "Note '[name]' not found. Check the name or try a different spelling." |
| State file missing | Create a new one with empty registry and processed log |
| State file corrupt | Report to user, offer to rebuild from scratch |
| Note has no unprocessed items | Report: "All items in [Note Name] are already processed." |
| Bucket classification uncertain | Default to escalate. Present the item with "Uncertain" bucket and reasoning. |
