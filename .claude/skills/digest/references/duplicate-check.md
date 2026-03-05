# Duplicate Check (Step 1.7)

Skip this step if `FORCE_MODE = true`.

For each classified URL, check if it already has a digest in `outputs/digests/`. Single grep call:

```bash
grep -rH "^url:" outputs/digests/*.md
```

Match each input URL against the results. For each match:
1. Read the matched file's frontmatter for `created` and `depth`
2. Compare requested depth (`shallow` if quick mode, `deep` if full mode) against existing depth

**Decision table:**

| Existing | Requested | Action |
|----------|-----------|--------|
| shallow  | shallow   | Skip   |
| deep     | deep      | Skip   |
| deep     | shallow   | Skip   |
| shallow  | deep      | Upgrade (ask user) |

If `depth` is missing from the existing file (legacy), treat as unknown. Default to skip for same-mode requests, flag as "upgrade available (depth unknown)" for full-mode requests.

**Report to user before proceeding:**

```
Duplicate check: N of M URLs already digested

  SKIP: "Title" (shallow, 2026-03-03) → outputs/digests/Title.md
  UPGRADE? "Title" (shallow → deep, 2026-02-27) → outputs/digests/Title.md

Proceeding with X new URLs. Use --force to override.
```

If all URLs are skipped (no new, no upgrades), report and stop.
If upgrades are available, wait for user confirmation before including them.
Remove skipped URLs from the processing list before continuing to agent launch steps.
