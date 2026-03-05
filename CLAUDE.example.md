---
source: claude
---
# CLAUDE
**Post-compaction check:** If `<per-prompt-rules>` absent from context: read `.claude/hooks/per-prompt-rules.md`, apply it, tell <your-name>: "per-prompt-rules.md absent, loaded manually."
If `<!-- skill-loaded: using-skills -->` absent: read `.claude/skills/using-skills/SKILL.md`, apply it, tell <your-name>: "SKILL.md absent, loaded manually."
If both present: say nothing.
# STRICT RULES
## Obsidian Vault - READ ONLY
`<your-vault-path>\1. Vault` - READ ONLY. Never write, edit, create, delete, move, or rename any file in the vault. Non-negotiable.
## Output Workflow
1. Read from the vault when asked. Output generated content to `outputs/`. Exception: `context/` holds persistent reference files.
2. <your-name> reviews output and manually integrates what he wants into the vault.
3. **Link related files** - hyperlink to sources, related tasks, prior work. No orphan files.
4. **Persist agent research** - when a subagent returns output with standalone reference value (landscape analysis, deep-dives, comparison matrices), persist to `outputs/` with standard frontmatter. Not quick lookups or intermediate research.
5. **Output file format** - frontmatter: `created`, `description` (2-4 sentences), `parent: '[[Task Name]]'`, `source: claude`, `type: artifact`. Exception: digest outputs use `type: content` (see [[Vault frontmatter conventions]]). Context block after H1: **Why/When/How**, each on its own line. No `---` horizontal rules.
6. **Agent output convention** - when launching agents that may create files, read `docs/agent-output-convention.md` for the relay spec (frontmatter, context block, date, parent, temp vs permanent evaluation).
7. **Externalize working content** - structured content (tables, taxonomies, decision matrices, comparisons) goes in files, not chat. <your-name> reads files in Obsidian where formatting and persistence are better. Summarize in chat and link.
8. **Temporary files** - suffix with `(temp)`, place in `outputs/temp/`. Delete during `/task complete`. Temp = value consumed by the decision it informed. Permanent = standalone reference value. When in doubt, ask. Digest outputs are permanent: `outputs/digests/`, no `(temp)` suffix.
9. **Show, don't describe** - for design review, create a worked example with real data as the primary deliverable. The worked example is never optional.
# Workspace Patterns
- **Systems reference** - `docs/systems.md` is the entry point for workspace infrastructure. Read it before making claims about capabilities. When launching agents for internal tasks, include a pointer to it. Only drill into component docs (README.md, SKILL.md) after consulting the index. This applies to: "how does X work?", "what hooks do we have?", "how is the system structured?", token cost analysis, or any question about the machine's own infrastructure.
- **Document what you build** - every component gets a reference doc (README.md or SKILL.md) written as part of building, not after. A component without docs is like a task without a task file. Consult README before making claims about what a system can or can't do. Docs audit runs as part of `/task review`.
- **Captain's log** - file: `context/captains-log.md`. When a significant design decision is made, add an entry immediately. During `/task complete`, verify no decisions were missed. Add `## Rollback` section in task file for any logged decision. `decision:` frontmatter on task files: one-liner summary, most tasks leave it blank.
- **Vault conventions reference** - when conversation touches vault structure topics (note types, frontmatter properties, parent hierarchy, topic hubs, `$` prefix, Bases queries, file classification, naming conventions): read `outputs/Vault frontmatter conventions.md` before making decisions.
- **Test before committing at scale** - when facing a technical decision with significant volume, proactively suggest a small comparative test (5-10 items through competing approaches). Initiative comes from Claude.
- **Model selection for subagents** - default Task tool calls to `model: "sonnet"`. Use `model: "haiku"` only for rough sorting where errors are cheap. Primary session stays on Opus. Rationale: [[Claude model selection evaluation]]
- **Sweep for untracked files when committing** - before staging, run `git status` and check for untracked files (not in `.gitignore`). Include them in the commit. Obsidian and <your-name> create files (`.base`, notes, configs) that Claude doesn't know about. If they're not committed, they can't be recovered. Learned from 2026-03-05 incident where untracked `.base` files were permanently lost.
- **Auto-fix trivial admin issues** - fix simple sync issues (status mismatches, missing timestamps) without asking. Only prompt for substantive decisions.
- **Name the task in summaries** - always lead with the task name when reporting progress. See SKILL.md "Summary Communication."
- **MCP vs scripts decisions** - consult `docs/MCP vs scripts decision framework.md` before any MCP/script architecture decision (build or install). Statefulness is the gate, session frequency determines install decisions, simplicity default wins ties.
- **Scripts convention** - `.scripts/README.md` is the catalog. Update it when creating or archiving scripts. Spent scripts go in `.scripts/archive/`.
- **Markdown formatting** - read `docs/markdown-formatting.md` for heading spacing, progress log format, and Obsidian rendering rules. Applies to ALL files, not just outputs.
- **Refactor instruction files after adding significant content** - evaluate: duplication? Always-on content that could load on demand? Dead weight? Metric: desired behavior per token. **Ordering principle:** sections and bullets are ordered by cost-of-failure (severity x frequency), not alphabetically. Primacy position (top of file) gets most reliable LLM attention. Safety-critical rules first, reference material last. Do not reorder without re-evaluating cost-of-failure. Evidence base: [[LLM instruction format effectiveness research]].
# Conventions
## Frontmatter
- **Date format:** `YYYY-MM-DD HH:mm` (24-hour). **All Claude-created files** get `source: claude`.
- **Wiki-links in YAML** must be quoted: `"[[filename]]"` - captured by Obsidian `file.links`.
- **Schemas:** Task (`type: task`), Output (`type: artifact`), Context (`type: context`). Full specs in task SKILL.md and [[Vault frontmatter conventions]].
## File Naming
- **Sentence case** for all workspace files. **Task titles:** verb-first imperative, 30-50 chars. **Output titles:** descriptive noun phrases.
- No date prefix in filenames. Full convention in task SKILL.md.
- **No Windows-forbidden characters in filenames:** `\ / : * ? " < > |`. Use hyphens instead of colons. Obsidian silently substitutes, causing mismatches in Bases queries and wiki-links.
## File Rename Protocol
- **Trigger:** After ANY file rename, write JSON manifest to `.scripts/renames.json` and give <your-name> a ready-to-paste command block. Don't skip even for "internal" files.
- **What to tell <your-name>:** "Open VS Code PowerShell terminal and paste:" then: `cd "<your-vault-path>"` and `powershell -ExecutionPolicy Bypass -File "2. Claude\.scripts\rename-links.ps1" -Manifest "2. Claude\.scripts\renames.json" -Execute`
- **Obsidian-side renames:** Bases queries reference property values, not file paths. Renaming a file that's referenced by `parent:` or `topic:` in other files' frontmatter will make those queries return empty. The rename script fixes wiki-links but not Bases query filters.
- **WhatsApp messages** - when formatting for WhatsApp: **no markdown** (no tables, bold, code blocks, links). Plain text: numbered lists, dashes, line breaks, CAPS for emphasis.
# Per-Prompt Rules
- **File:** `.claude/hooks/per-prompt-rules.md`. Injected every user message via UserPromptSubmit hook.
- **Critical infrastructure:** Changes require a dedicated task with explicit user approval.
- **Admission criteria for new rules:** Must meet ALL four: (1) trigger-shaped, (2) proven drift, (3) visible harm, (4) under 10 lines.
- When a candidate is identified: log in improvement log AND propose to <your-name>. Don't auto-add.
# Operational Lessons
- **Never fabricate timestamps.** Run `date` first, use exact output. Never reuse, estimate, or "correct." Progress logs: 12-hour AM/PM. Frontmatter: 24-hour.
- **Edit tool batch read:** Reading 20+ files in parallel then editing next message fails. Use scripts for bulk edits, or read+edit one at a time.
- **Don't copy before conventions are settled.** Finish ALL format changes in the source first.
- **PowerShell is case-insensitive by default.** Use `-ceq`, `-cmatch`, `-creplace` for case-sensitive operations.
# Environment
- **Vault root:** `<your-vault-path>`. **`1. Vault/`** = your content (READ ONLY). **`2. Claude/`** = Claude's workspace (writable, primary working directory).
- Dot-prefixed folders (`.claude/`, `.scripts/`, `.vscode/`, `.git/`) invisible to Obsidian. Content folders (`tasks/`, `outputs/`, `context/`) visible.
- **Windows hooks:** PreToolUse and PostToolUse don't fire in VS Code extension mode. Only SessionStart and UserPromptSubmit work. Tool-gating via hooks is not viable.
- **Context7 MCP server**: Library docs lookup. Tools: `resolve-library-id` + `query-docs`. Free tier: 1,000 req/month.
- **Toggl integration**: Time tracking via REST API. Reference: `docs/toggl-integration.md`.
- **YouTube Data API v3**: Channel browsing via `.scripts/youtube-browse.py`. `YOUTUBE_API_KEY` in env. Free tier: 10K units/day.
- Session logs: `~/.claude/projects/<project-hash>/<session-id>.jsonl`.
- See `docs/systems.md` for the full system map and placement rules.
