# Improvement Logging Procedure

Two types of observations worth capturing during work:

1. **System gaps** (`[flag-machine]`): A skill with friction, a missing capability, a knowledge gap, a wiring issue.
2. **Preferences** (`[flag-pref]`): Something learned about the user: a taste, a pattern, a preference, a reaction.

**Log first, fix second.** The observation exists independently of the fix. Even when about to fix the issue immediately, log it first. The improvement log tracks patterns and evidence; the fix tracks the work. Both matter.

## How to log

1. Append to `context/improvement-log.md` under today's `### YYYY-MM-DD` heading in the appropriate section (`## Machine Improvements` or `## Preferences`).
2. Group entries under a task/context wiki-link header: `[[Task Name]]`
3. **Get the actual time from `date` first. Never fabricate timestamps.** Format entries as bullet points: `- HH:MM AM/PM Observation text <!-- session: UUID -->` (use the session UUID detected during orientation).
4. If adding to an existing task group for today, append a new bullet.
5. **Task/context link is mandatory.** If no task exists, flag that gap before continuing.
6. Include `[flag-machine]` or `[flag-pref]` in the chat response when logging. This creates a searchable breadcrumb via `vault_sessions`.
7. Continue current work. Do not stop to fix or process.
8. **Close the loop:** If acting on the observation in the same session, write a JSON entry to `context/inbox-state.json` (under `processed.improvement-log`) and delete the entry from the inbox. Format: `{"source": "improvement-log", "original_text": "full entry text", "date": "YYYY-MM-DD", "summary": "one-line", "bucket": "direct_fix", "action": "Fixed: [what was done]", "cluster": null, "run": "session:UUID", "processed_at": "ISO"}`. Do not leave fixed entries in the inbox.

## Entry quality

Include enough context that processing mode can assess without tracing back to the session. The observation, why it matters, what prompted it. A few sentences is fine. Do not propose solutions; that is processing mode's job.

## When to flag

**Machine:** Something about the machine's structure, knowledge, or capabilities that could be improved. Not task-specific issues (those go in the task file). Machine-level observations only.

**Preferences:** Something learned about the user during a conversation: a preference, a pattern, a taste, a reaction. Things that help future conversations be more tailored.

## When NOT to flag

Do not force it. If nothing stands out, write nothing. Session JSONL logs are a safety net. Processing mode can mine them for unflagged patterns.
