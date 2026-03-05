# Claude Workspace

A self-managing Claude Code workspace built over weeks of daily use. It handles task management, research, content digestion, travel planning, and self-improvement, all orchestrated through skills, hooks, and a custom task engine.

It's designed to be cloned and used: point your Claude at this repo, and it can walk you through setup, explain how everything works, and help you customize it. That's the point: if a system is built with agents in mind, the agent can do the knowledge transfer.

## How It Works

```
CLAUDE.md          The brain. Rules, conventions, environment config.
                   Loaded every request. Tells Claude how to behave.
       |
       v
   Hooks           Automatic behavior injection.
   (per-prompt)    per-prompt-rules.md fires every message:
                   task gates, brainstorm gates, research gates.
       |
       v
   Skills          On-demand capabilities. /task, /digest, /research,
   (.claude/       /brainstorm, /travel, /shop, /process, /ingest.
    skills/)       Each has a SKILL.md that loads when invoked.
       |
       v
   Task Engine     State management. Python CLI tracks tasks through
   (.task-engine/) idea -> active -> done. Progress logs, frontmatter
                   schemas, file operations.
       |
       v
   Scripts         Utility layer. Flight search, accommodation search,
   (.scripts/)     product search, YouTube browsing, vault utilities.
                   Called by skills, not directly by the user.
       |
       v
   Vault Intuition Custom MCP server. Gives Claude deep search access
   (.mcp-server/)  to an Obsidian vault: keyword search, semantic search,
                   past conversation lookup, note retrieval.
       |
       v
   Docs            Reference documentation. System map, conventions,
   (docs/)         decision frameworks. The "how and why" layer.
```

## Key Concepts

### Skills
Structured behaviors that fire on demand. Each skill has a `SKILL.md` that defines its trigger, process, and conventions. Skills range from simple (task management) to complex (travel search with multi-source comparison). They're the primary way the workspace extends Claude's capabilities.

Skills in this workspace: `task`, `brainstorm`, `research`, `digest`, `travel`, `shop`, `process`, `ingest`, `autonomous`, `skill-creator`, `using-skills`.

### Hooks
Automatic injection points. The `SessionStart` hook loads the skill enforcement system on every new conversation. The `UserPromptSubmit` hook injects per-prompt rules (task gates, brainstorm gates, improvement logging) before every response. Together, they ensure Claude follows the workspace's conventions without being asked.

### Task Engine
A Python CLI (`.task-engine/task.py`) that manages task lifecycle: create, start, pause, complete, cancel, log progress. Tasks live as markdown files with YAML frontmatter, organized by status (`tasks/`, `tasks/ideas/`, `tasks/archive/`). The engine handles status transitions, progress log formatting, and file moves.

### Context Architecture
Three tiers of context, from most persistent to most ephemeral:
1. **CLAUDE.md** - loaded every request. Operational rules, conventions, environment.
2. **context/** - loaded on demand. Personal reference files, improvement log, design decisions.
3. **Vault** - searched via MCP. The user's knowledge base (read-only for Claude).

## Showcase: Interesting Skills

### /digest
Processes YouTube videos, X/Twitter threads, blog posts, and podcasts into structured key takeaways. Quick mode uses auto-captions; full mode runs Whisper transcription with speaker diarization. Supports batch processing of multiple URLs in parallel.

### /travel
Multi-source travel search: flights (Kiwi, Google Flights), accommodation (Booking.com, Airbnb), car rental (Kayak), air quality (WAQI, OpenAQ), and location reviews (Google Maps, Booking.com). Each module wraps Python scripts that call external APIs via Apify actors.

### /brainstorm
Fires before any creative or design work. Searches for related prior work, asks questions one at a time (preferring multiple choice), proposes approaches with trade-offs, then presents the design in small sections for incremental validation. The brainstorm gate in per-prompt-rules enforces this automatically.

### /task
Full task lifecycle management. Tasks flow through idea -> active -> paused -> done/cancelled. Progress logging with session IDs for traceability. Daily task reviews audit link integrity, output orphans, and idea surfacing.

## Getting Started

1. **Clone this repo** into your Obsidian vault (or any directory if you don't use Obsidian)
2. **Edit `CLAUDE.md`** - the starter config has `<your-vault-path>` placeholders to fill in with your actual paths. Study `CLAUDE.example.md` to see what a mature production config looks like.
3. **Configure hooks** - copy `.claude/settings.example.json` to `.claude/settings.json` and replace `<your-workspace-path>` with the absolute path to this repo (e.g., `/Users/robin/Documents/vault/workspace` or `C:\Users\robin\Documents\vault\workspace`).
4. **Configure paths** in these files:
   - `.task-engine/task.py` and `.task-engine/operations.py` - update `DEFAULT_WORKSPACE` in both files to your workspace path
   - `.mcp-server/src/atlas.py` - update `VAULT_ROOT` to your Obsidian vault root (skip if not using Obsidian)
   - `.scripts/detect-session-id.sh` - update `SESSION_DIR` with your Claude project hash, or pass `--workspace` to task engine commands instead
5. **Install dependencies**:
   - Task engine: `cd .task-engine && pip install -r requirements.txt`
   - MCP server: `cd .mcp-server && pip install -r requirements.txt` (skip if not using Obsidian)
   - Digest skill: `pip install -r .claude/skills/digest/scripts/requirements.txt` plus `yt-dlp` and `ffmpeg` system-wide
   - Ingest skill: `pip install pymupdf Pillow` (for scanned PDF transcription)
   - Other scripts: see `.scripts/README.md` for per-script dependencies
6. **Configure API keys** (all optional, skills degrade gracefully without them):
   - `APIFY_API_TOKEN` - accommodation, car rental, product search, review scraping
   - `YOUTUBE_API_KEY` - YouTube channel browsing
   - `GROQ_API_KEY` - audio transcription (digest skill, full mode)
   - `ANTHROPIC_API_KEY` - LLM-powered vault operations (MCP server)
   - `WAQI_TOKEN` + `OPENAQ_API_KEY` - air quality search
   - `ASANA_PAT` - Asana workspace queries

**Not using Obsidian?** The task engine, skills, hooks, and scripts all work without it. Skip the MCP server setup and ignore vault-search references in skill files. The core workflow (task management, brainstorming, digests, travel search) is fully functional without a vault.

## Design Philosophy

**Files over memory.** After context compaction, Claude re-reads actual files rather than trusting summaries. Every convention, decision, and preference is written down.

**Skills are structured behavior.** Instead of hoping Claude remembers how to do something, skills codify the process: triggers, steps, conventions, references. The skill loads its full context when invoked.

**Gates prevent drift.** Per-prompt rules enforce that tasks exist before implementation, brainstorming happens before design work, and research methodology is applied before launching agents. These aren't suggestions; they're automatic checks every message.

**Self-improvement loops.** The workspace includes improvement logging (observations captured during work), weekly health reviews (two-agent audit of system integrity), and periodic improvement processing (triage observations into actions). The system actively tries to get better.

**Desired behavior per token.** Instruction files are ordered by cost-of-failure, not alphabetically. Safety-critical rules first, reference material last. Content is evaluated by how much correct behavior it produces relative to its token cost.

## If You Don't Use Obsidian

The task engine, skills, hooks, and scripts all work independently of Obsidian. Skip the MCP server setup and ignore vault-search references in skill files. The core workflow (task management, brainstorming, digests, travel search) is fully functional without a vault.

## What You're Looking At

This repo was packaged using its own task management system. The export script (`.scripts/export-public.sh`) copies the workspace infrastructure, redacts personal paths, runs a security scan, and produces this clean output. The `tasks/` and `outputs/` directories contain meta-examples from the packaging process itself, demonstrating the system working in practice.

See `CLAUDE.example.md` for the full production configuration that powers the private workspace.

## License

This is shared as a reference, not a product. Use whatever is useful to you.
