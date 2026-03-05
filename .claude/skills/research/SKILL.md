---
name: research
description: Methodology guardrails for subagent research. Fires before launching Task tool agents for research, landscape analysis, or information gathering. Shapes agent prompts and adds verification steps.
---

# Research Methodology

## Overview

Methodology guardrails for subagent research. Two modes, no default: **quick** (`--quick`) for straightforward research, **deep** (`--deep`) for landscape analysis and option discovery. Always select explicitly from the criteria below, or ask if ambiguous. Quick mode keeps research fast with minimal guardrails. Deep mode prevents the most costly research failures: shallow discovery, unverified claims, and undocumented gaps.

## When This Fires

Before launching Task tool agents for:
- Landscape analysis or option discovery (APIs, tools, frameworks, products)
- Information gathering across multiple sources
- Market research, competitive analysis, investment research
- Any task where the output is "here are the options" or "here is what exists"

**Does NOT fire for:**
- Quick lookups or single fact-checks
- Code exploration (use Explore agent directly)
- Vault searches (use vault tools directly)
- Simple web fetches for a known URL

## Modes

| | Quick | Deep |
|---|---|---|
| Agents | 1 | 2-3 (parallel discovery + optional depth) |
| Query framing | 2-3 angles in agent prompt | Full multi-angle battery (5-6 sets, incumbent names, fallback categories, recency filters) |
| Verification | Inline: "verify key claims before reporting" in agent prompt | Structural: cross-verify from independent source after agents return |
| Gap documentation | None | Required "What I didn't find" section |
| Output destination | Chat (file only if requested or parent task benefits) | File in `outputs/` with full conventions |

**There is no default mode.** Always select explicitly: `/research --quick` or `/research --deep`.

**Decision rule:** Am I looking up a fact, or surveying a space?
- **Fact lookup** = quick. There's probably one right answer or a small set of facts. "Is it cherry blossom season?" "What visa do I need?" "How long is the bullet train?"
- **Surveying a space** = deep. I need to find what exists, compare options, or analyze from multiple angles. "What flight APIs exist?" "What are my hotel options in Kyoto?" "Analyze the Iran conflict."
- **Unsure** = ask. The cost of asking is low; the cost of shallow research when deep was expected is high.

**Always announce mode + reasoning before launching agents:**
> "Running `/research --quick`: fact lookup, cherry blossom timing."
> "Running `/research --deep`: surveying flight API options, missing one would be costly."
> "This could go either way. Quick or deep?" (when unsure)

## Quick Mode

1 agent, minimal guardrails. For travel lookups, fact-gathering, single-topic questions, "go check X."

**Agent prompt template:**

```
Research question: [THE QUESTION]

Search from 2-3 different angles (different query framings, not just one search).
Verify key claims before reporting. If you can't confirm something, say so.
Today's date is YYYY-MM-DD.
```

**Today's date:** Run `date` before composing the prompt. Subagents do not inherit date context.

**Output:** Return findings to chat. Only write to `outputs/` if the user requests it or a parent task would benefit from the reference.

## Deep Mode

Three guardrails, applied in order: before agents launch, after agents return, and in the output.

### Guardrail 1: Discovery Breadth (before launching agents)

The most common research failure is going deep on the first results found while missing entire categories of options. Prevent this by structuring the discovery pass:

- **Multiple independent search query sets.** Frame the same research question at least 3 different ways. Different framings surface different results. Example: "flight search API", "travel company MCP server launch 2025", "Google Flights alternatives for developers" are three framings of the same need.
- **Search by incumbent names, not just capability.** For any domain, list the known major players and search for each by name + the technology. Example: "Kiwi.com MCP", "Expedia API", "Booking.com developer tools" alongside generic "flight MCP server."
- **Include fallback-category searches.** General-purpose tools (web scraping, browser automation) alongside domain-specific tools. The best solution may not be domain-specific.
- **Temporal recency filters.** For fast-moving domains, add "2025 OR 2026" or "launched" or "new" to at least one search pass. Agents trained on older data bias toward established options and miss recent launches.
- **At least one discovery agent pass before any depth pass.** Do not go deep on the first option found. Sweep broadly first, then commit to depth on the most promising results.

### Guardrail 2: Cross-Verification (after agents return)

AI agents share blind spots with their training data. Same-model verification does not catch these. Verify from a different source.

- **Verify claims through a source independent of the generator.** If a subagent claims a product exists, verify via web search, GitHub, or official docs. Do not rely on the agent's confidence.
- **Cross-reference temporally sensitive claims** (product launches, new repos, pricing changes) with at least one other AI search engine or direct web verification. This catches both hallucinations and stale information.
- **Flag anything unverifiable.** If a claim cannot be confirmed through independent sources, mark it explicitly: "Unverified: [claim]. Could not confirm via [sources checked]."
- **Document hallucinations and their source.** When a claim is fabricated, record it: "[Product name] was hallucinated by [source]. Does not exist." This builds institutional knowledge about source reliability.

### Guardrail 3: Gap Documentation (in every research output)

Research is only as good as its awareness of what it missed. Every research output must include:

- **What was searched for but not found.** Categories where searches returned no results.
- **What categories or angles might have been missed.** Geographic blind spots, non-English sources, industry verticals not searched.
- **Root cause analysis.** Why were things missed? Query framing too narrow? Temporal bias? Category blindness?
- **Feed-forward note.** How would you search differently next time? What would you add to the methodology? This feeds back into improving this skill over time.

## Agent Prompting (Deep Mode)

When launching deep mode research agents, include these elements in the agent prompt:

1. **The research question** stated clearly
2. **Multiple search query sets** (not just one query, multiple angles)
3. **Explicit instruction to search by incumbent names** in the domain
4. **Instruction to include fallback categories** if applicable
5. **Recency filter instruction** for fast-moving domains
6. **Accuracy attribution:** When citing accuracy figures, benchmarks, or performance metrics, specify the exact model tested. If benchmark data comes from a different model tier than the one recommended, flag the mismatch explicitly.
7. **Content format expectation:** findings must include a "What I didn't find" section
8. **Today's date:** Subagents do not inherit the parent session's date context. Before composing the prompt, run `date` to get the current date, then include it explicitly (e.g., "Today's date is 2026-02-23"). This ensures accurate `created:` frontmatter and Context block dates.
9. **Output file format (when agent writes to `outputs/`):** Relay the workspace output file conventions to the agent. The canonical spec lives in CLAUDE.md (Output Workflow, rules #8-9). Before composing the agent prompt, re-read the current CLAUDE.md conventions and the header of a recent output file, then include the following aspects in the prompt: frontmatter schema (fields and values), Context block format (**Why:**/**When:**/**How:**), and the no-horizontal-rules formatting rule. Always relay from the source, never from memory, so the agent receives the current conventions even if they've changed since last use. **Before specifying the output path, evaluate temp vs permanent per CLAUDE.md rule #11.** Research outputs are almost always permanent (standalone reference value). Use `outputs/temp/` only for scratch analysis consumed by the decision it informs.

Example phrasing to include in agent prompts:

Research methodology:
> Search broadly using multiple query framings. Search by major player names in this space, not just by capability keywords. Include at least one search for recent launches (2025-2026). For each finding, capture: name, URL, what it does, and key details. Also report: what you searched for but found nothing, and what categories might have been missed.

Today's date is YYYY-MM-DD. Use this for the `created:` frontmatter field and any date references.

Output file format (derived from CLAUDE.md Output Workflow rules #8-9; verify still current before use):
> Write the output to `outputs/[filename].md` with this format:
>
> Frontmatter fields (alphabetical): `created` (YYYY-MM-DD HH:MM), `description` (one-line summary), `parent` ('[[TASK_NAME]]'), `source` (claude), `type` (artifact). No `title:`, `tags:`, or `task:` fields.
>
> After the H1 title, include a Context block:
> **Context:**
> **Why:** What prompted this document, linking to [[TASK_NAME]].
> **When:** Date produced + source recency window.
> **How:** Methodology and tools used (include when non-obvious).
>
> No `---` horizontal rules between sections. Use H2 headings for separation.

## Domain Profiles

Add domain-specific subsections (`### Profile: [Domain Name]`) when real research tasks reveal patterns worth capturing: query patterns, incumbent lists, verification sources.
