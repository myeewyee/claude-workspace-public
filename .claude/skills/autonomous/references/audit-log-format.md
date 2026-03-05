# Autonomy Log Format

Write each scan entry to `context/autonomy-log.md` using this format.

```markdown
### YYYY-MM-DD HH:MM AM/PM <!-- session: SESSION_ID -->

**Scanned [N] tasks ([breakdown by category])**

Eliminated (triage):
- Paused ([N]): skip (no unblock detected)
- Ideas ([N]): brainstorm veto
- Recurring not due ([N]): [names] ([due dates])
- Paused blocked ([N]): [names] ([block reason])
- In-progress recent ([N]): [names] (last entry [TIME], ~[N] min ago)

Candidates evaluated: [N]

Proceeding autonomously:
- [[Task Name]]: [specific work item]
  ([specific files or targets])
  Evaluated against: [reference standard, e.g., "CLAUDE.md § Frontmatter"]
  Autonomy basis: [criterion 1 reasoning]. [criterion 2 reasoning: evidence of prior
  demonstration]. [criterion 3 reasoning]. [criterion 4: boundary definition].
  Counter-argument: [strongest case against autonomy from step 2]
  Override: [why the counter-argument doesn't hold]

Needs the user:
- [[Task Name]]: [what's blocking]
  Classification: [which criterion fails, or brainstorm veto]
```

**Detail requirements for candidate entries** (full detail, not abbreviated):
- Specific files or items targeted (not just task names)
- The reference standard being evaluated against
- Evidence that the pattern has been demonstrated before (link to prior work)
- The boundary definition (what's in scope, what would be out of scope)

Labels alone ("objective criteria, established pattern") are insufficient. Those are conclusions, not reasoning. Include the reasoning that led to the conclusion.

**Abbreviated entries** (eliminated by triage) need only: count, group name, and one-line reason.
