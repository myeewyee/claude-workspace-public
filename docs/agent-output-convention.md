# Agent output convention
When launching any agent (Task tool) that may create output files, relay these specs in the agent prompt. Agents cannot read CLAUDE.md.
## What to include in the agent prompt
1. **Output file format:** frontmatter fields (`created`, `description` (2-4 sentences), `parent: '[[Task Name]]'`, `source: claude`, `type: artifact`). Context block after H1: **Why/When/How**, each on its own line. No `---` horizontal rules between sections. No blank lines around headings.
2. **Vault boundary:** Only `1. Vault/` (the user's personal Obsidian notes) is read-only. All workspace folders (`tasks/`, `outputs/`, `context/`, `docs/`) are writable.
3. **Parent task:** Include the active task name so the agent sets `parent: '[[Task Name]]'` in frontmatter.
4. **Date:** Run `date` first, include today's date so the agent writes accurate `created:` frontmatter.
5. **Temp vs permanent:** Evaluate before specifying the output path. Research outputs (landscape analyses, comparison matrices, deep-dives) are almost always permanent (`outputs/`). Digest outputs go to `outputs/digests/` (permanent, no `(temp)` suffix). Only use `outputs/temp/` + `(temp)` suffix when the file's value is consumed by the decision it informs.
6. **Systems reference:** When launching agents for workspace-internal tasks, include a pointer to `docs/systems.md`.
## After the agent returns
1. Verify `parent:` is set correctly on new files.
2. Immediately tell the user: "Here's the output [agent] created: filename." Don't wait.
3. See SKILL.md "Output File Convention" for full rules.
