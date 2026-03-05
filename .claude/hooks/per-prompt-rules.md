<per-prompt-rules>
IMPLEMENTATION GATE: If your next action involves Edit, Write, or Bash that modifies project files - and there is no in-progress task covering this work - STOP. Invoke `/task new` + `/task start` first. Hard prerequisite, not a suggestion.

BRAINSTORM GATE: Modifying behavior, adding features, changing conventions, or doing any design work? → `/brainstorm` first. User direction narrows the design space but doesn't eliminate it. "Format it like X" still requires field mapping, gap analysis, and trade-off decisions. Only skip brainstorm when executing a fully specified plan with no design decisions remaining.

RESEARCH GATE: About to launch Task tool agents for research? → `/research` first. Two modes, no default: `--quick` (fact lookup) or `--deep` (surveying a space). Announce mode + reasoning before launching. Unsure which? Ask. Does NOT apply to quick lookups, code exploration, or simple web fetches.

TASK MANAGEMENT CHECK - ask yourself before responding:
1. Work emerging that should be tracked? → `/task new`
2. Starting work on a pending task? → `/task start`
3. Did you modify a project file or complete a step since last update? → Update the task file NOW: Work Done (Edit), Progress Log (task engine), plus any stale sections (criteria, approach, specs).
4. Something done? → `/task complete`. Superseded/won't do? → `/task cancel`
5. About to edit task files directly? → STOP. Always use `/task` skill.
6. Created a file in `outputs/`? → Verify `parent:` is set correctly in its frontmatter. Tell the user: "Here's the output: filename."
7. Follow-up on a done/archived task? → Reopen if same scope. New task only if fundamentally different. No untracked work.
8. User mentions an idea, musing, "what if", feature thought, or anything worth preserving? → `/task new` with `status: idea`
9. Producing structured content (tables, comparisons, matrices)? → Write to file, not chat. Summarize and link.
10. Task tool agent just returned? → Does the output have standalone reference value (landscape analysis, deep-dive, recommendations, comparison matrix)? If yes, persist to `outputs/` with standard frontmatter. Then rule #6 kicks in.

Never create task files manually. Always use /task.
This is the rule you keep forgetting mid-session. Do not rationalize around it.

TASK SWITCHING: File changes between messages may come from other sessions or manual edits. Never treat as implicit task switches. Continue current work unless user explicitly asks.

SKILL HEALTH CHECK: If `<!-- skill-loaded: using-skills -->` is absent from context, read `.claude/skills/using-skills/SKILL.md` and apply it. This happens after compaction when the SessionStart hook content is lost.

TOOL SELECTION GATE - classify before first tool call:
- Workspace files, code → Read / Grep / Glob.
- Already in context → no search needed.
- Vault or past work → MANDATORY, use hierarchy below:
  1. Past work / "what have we done?" → vault_search with folder:"tasks" (active + archived). NOT vault_sessions.
  2. Current state / "what's active?" → task.py list.
  3. Decision tracing / "why X?" → task file → progress log session ID → vault_util(session_detail).
  4. Untracked discussions / "did we ever discuss X?" → vault_sessions. Only case where sessions come first.
  5. Personal content / "what was I thinking?" → vault_search or vault_semantic.
vault_sessions is the expensive fallback, not the entry point.
If classified as vault but reaching for Read/Grep, STOP. You are drifting.

PROTECTED FILE: per-prompt-rules.md is critical infrastructure. Never modify during task reviews, cleanup, or optimization. Changes require a dedicated task with explicit user approval. No exceptions.

IMPROVEMENT LOGGING: Notice a system gap bigger than this task, or learn a new preference from the user?
Log first, fix second. Append to `context/improvement-log.md` under today's date heading + current task subheading.
- **System gap** (drift, capability issue, wiring problem) → `## Machine Improvements` section. Include `[flag-machine]` in chat.
- **Preference** (something learned about the user) → `## Preferences` section. Include `[flag-pref]` in chat.
Format: `- HH:MM PM Observation <!-- session: UUID -->`. Include enough context for improvement mode to assess without tracing back.
Don't force it: only flag when something genuinely stands out. Session logs are the safety net.
**Close the loop:** If you fix an observation in the same session, write a JSON entry to `context/inbox-state.json` and delete the entry from the inbox. Do not leave fixed entries in the inbox.
</per-prompt-rules>
