# CLAUDE

A starter configuration for the Claude Code workspace. See `CLAUDE.example.md` for a full production config.

# Strict Rules

## Vault - READ ONLY
Your vault directory (configure the path below) is READ ONLY. Never write, edit, create, delete, move, or rename any file in the vault.

## Output Workflow
1. Read from the vault when asked. Output generated content to `outputs/`.
2. The user reviews output and manually integrates what they want into the vault.
3. Link related files: hyperlink to sources, related tasks, prior work. No orphan files.
4. Temporary files: suffix with `(temp)`, place in `outputs/temp/`. Permanent outputs go in `outputs/`.

# Workspace Patterns

- **Systems reference**: `docs/systems.md` is the entry point for workspace infrastructure. Read it before making claims about capabilities.
- **Document what you build**: every component gets a reference doc (README.md or SKILL.md) written as part of building, not after.
- **Model selection for subagents**: default Task tool calls to `model: "sonnet"`. Primary session stays on Opus.
- **Scripts convention**: `.scripts/README.md` is the catalog. Update it when creating or archiving scripts.

# Conventions

## Frontmatter
- **Date format:** `YYYY-MM-DD HH:mm` (24-hour). All Claude-created files get `source: claude`.
- **Wiki-links in YAML** must be quoted: `"[[filename]]"`.
- **Schemas:** Task (`type: task`), Output (`type: artifact`), Context (`type: context`).

## File Naming
- **Sentence case** for all workspace files.
- **Task titles:** verb-first imperative, 30-50 chars.
- **Output titles:** descriptive noun phrases.

# Per-Prompt Rules
- **File:** `.claude/hooks/per-prompt-rules.md`. Injected every user message via UserPromptSubmit hook.
- See `CLAUDE.example.md` for the full production per-prompt rules configuration.

# Environment

Configure these paths for your setup:

- **Vault root:** `<your-vault-path>`
- **Workspace:** `<your-vault-path>/<workspace-folder>/`
- Dot-prefixed folders (`.claude/`, `.scripts/`, `.task-engine/`) are invisible to Obsidian.
- Content folders (`tasks/`, `outputs/`, `context/`) are visible in Obsidian.
- See `docs/systems.md` for the full system map.
