# Improvement log

Observations captured during work sessions, triaged during processing mode. Two types:

- **Machine Improvements:** Observations about the machine itself (system gaps, drift, capabilities).
- **Preferences:** Observations about the user (personal preferences, patterns, tastes).

**This is an inbox, not an archive.** Entries arrive, get triaged, then exit. If an inbox section is long, processing is overdue. If both are empty, the system is healthy.

Each entry should contain enough context that processing mode can assess it without tracing back. The observation, why it matters, what prompted it. Don't propose solutions, that's processing mode's job.

**Inbox entry format:**

```
[[Task Name or conversation context]]
- HH:MM PM Observation text <!-- session: UUID -->
```

Grouped by date (newest first) within each inbox section. Entries grouped by task/context within each date. Session ID (HTML comment, invisible in Obsidian reading mode) links to the conversation where the observation was made via `vault_util(action="session_detail")`.

**Machine triage exits:** `task` (create via `/task new`, link), `direct fix` (fix now, describe what was done), `accepted risk` (valid but not worth acting on), or `dismissed` (wrong/outdated/irrelevant).

**Preference triage exits:** `new` (add to preferences file), `modified` (update existing preference), `merged` (combine with existing preference), or `dismissed` (situational, not a real pattern).

## Machine Improvements

## Preferences
