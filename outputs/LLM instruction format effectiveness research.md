---
created: 2026-02-27 12:40
description: Research comparing terse imperative vs verbose explanatory instruction formats for LLM system prompts, framed around behavior effectiveness per token.
parent: '[[Research LLM instruction format effectiveness]]'
source: claude
type: artifact
---
# LLM instruction format effectiveness research
**Context:**
**Why:** the user shared a screenshot of a terse, programming-focused CLAUDE.md and asked whether that style is more effective than our verbose, rationale-heavy format. Spawned from [[Research LLM instruction format effectiveness]], building on the "behavior effectiveness per token" metric defined in [[Audit context management overhead]].
**When:** 2026-02-27. Two parallel Sonnet research agents surveyed 40+ sources: academic papers (2022-2026), Anthropic official documentation, practitioner analysis.
**How:** Web research via multiple query framings per the /research methodology. Cross-verified key claims against primary sources. Gaps documented in final section.
## The Two Formats
### Screenshot format (terse imperative)
Source: an external (CLAUDE.md screenshot).

The shared CLAUDE.md uses a distinctly different writing style:
- **Short imperative sentences:** "Use X." "Never do Y." "Prefer Z over W."
- **Minimal rationale:** Rules stated as facts, not explained
- **Programming-focused:** Code style, build commands, architectural conventions
- **Dense bullet lists:** Many rules per screen, low token cost per rule
- **Flat structure:** Headers + bullets, no decision trees or self-referential patterns
- **Binary rules:** Most rules have clear right/wrong answers (tabs vs spaces, this library vs that one)
### Our format (verbose explanatory)
Our instruction set across per-prompt-rules.md, SKILL.md, and CLAUDE.md uses:
- **Question-answer patterns:** "Ask yourself before responding: 1. Work emerging? 2. Starting work?"
- **Rationale with drift evidence:** "Claude demonstrably forgets this mid-session" with specific dates
- **Decision trees:** Tool selection gate with 5-level hierarchy, content placement tree
- **Red Flags tables:** "If you're thinking X, the reality is Y" pattern
- **Process definitions:** Full workflow specs (orientation, post-compaction, skill routing)
- **Judgment-heavy rules:** Many rules require the model to assess a situation, not just check a boolean
## What Research Says
### Finding 1: Rationale improves generalization (but should be compressed)
Anthropic's own documentation contrasts bare imperative with explanatory instruction:
- Less effective: `NEVER use ellipses`
- More effective: `Your response will be read aloud by a text-to-speech engine, so never use ellipses since the text-to-speech engine will not know how to pronounce them.`
Their commentary: "Claude is smart enough to generalize from the explanation." The rationale lets the model handle edge cases the instruction didn't anticipate. A bare prohibition can be followed literally but in the wrong spirit.
The "Reasoning Up the Instruction Ladder" paper (arXiv:2511.04694, 2025) supports this: when models reason about the relationship between an instruction and a response before generating, compliance improves by ~20% in conflict settings.
**Implication for us:** Our rationale-bearing rules ("this exists because Claude demonstrably forgets X mid-session") are doing real work. They help the model understand the *purpose* of the rule, which matters for edge cases. But the rationale should be one sentence, not a paragraph.
### Finding 2: Instruction count is the binding constraint
The "Curse of Instructions" paper (Harada et al., 2024) quantifies the problem:
- Probability of following ALL instructions: `P(all) = P(individual)^n`
- At 95% individual compliance, 10 simultaneous instructions succeed only ~60% of the time
- To achieve 80% reliability, you're limited to roughly 4-5 simultaneous hard constraints
The IFScale benchmark (arXiv:2507.11538, July 2025) tested 20 frontier models on 500 simultaneous instructions: even the best achieved only 68% accuracy. Models also show strong bias toward earlier instructions.
Anthropic's CLAUDE.md guidance: "If Claude keeps doing something you don't want despite having a rule against it, the file is probably too long and the rule is getting lost."
**Implication for us:** Every instruction we add dilutes every other instruction uniformly. This is the strongest argument for the terse format: fewer tokens means room for more signal before hitting the compliance ceiling. But this is an argument about *count*, not *style*. Fewer well-explained rules beats many terse rules.
### Finding 3: The compression U-curve (medium compression is worst)
The CDCT paper (arXiv:2512.17920, December 2025) is the most directly relevant finding. Testing 9 frontier LLMs across 5 compression levels:
- A universal U-curve appears in 97.2% of experiments
- Compliance peaks at **extreme compression** (~2 words) and **no compression** (~135 words)
- Compliance is worst at **medium compression** (~27 words)
- The cause: RLHF "helpfulness" training fights against constraint compliance when instructions are ambiguous. Removing RLHF signals improved compliance by 598% on average
- Reasoning models (o3, GPT-5) show 27.5% higher compliance at the vulnerable midpoint
**Implication for us:** This is the most surprising finding. The danger zone is not "too long" or "too short," it's the middle: instructions that are compressed enough to lose clarity but not compressed enough to be unambiguous directives. Our verbose format with clear rationale actually lands in the safe zone (full-length). The terse format also lands in a safe zone (very short). The worst format would be *partially* compressed instructions that try to be concise but end up ambiguous.
### Finding 4: Position effects are real and structural
"Lost in the Middle" (Liu et al., 2024, Transactions of the ACL) established a U-shaped attention curve: instructions at the beginning and end of context are followed most reliably. Information in the middle degrades significantly. This is caused by the RoPE positional encoding architecture, not just training.
Context Rot research (Chroma, July 2025) extends this: adding ~113k tokens of context drops accuracy by 30% compared to a focused 300-token version. Concise prompts degrade more slowly in long sessions because they consume less context budget.
**Implication for us:** Our per-prompt-rules (injected at the end of every message, 3,144 chars) benefit from recency position. Our SKILL.md (session start, 11,043 chars) gets primacy position. This is actually well-designed for the position effect. But overall context budget matters: shorter instructions degrade more slowly over long sessions.
### Finding 5: Format should match task type
Anthropic recommends XML tags for separating concerns, bullet lists for discrete steps, and prose for nuanced connected ideas. They explicitly warn against "hardcoding complex, brittle if-else logic" into prompts, calling it a fragility pattern.
Newer Claude models (4.6+) are more responsive to system prompts and less prone to under-triggering. The docs advise against aggressive imperative language (all-caps, "YOU MUST") which can cause overtriggering.
### Finding 6: RLHF creates a helpfulness-compliance tension
The CDCT paper's most important finding: the model's training to be helpful actively fights against strict constraint compliance when instructions are ambiguous or incomplete. RLHF creates a bias toward producing something useful even when the instruction says to stay constrained.
**Implication for us:** Instructions with explicit, unambiguous constraint boundaries perform better than instructions that leave room for the model's helpfulness instinct to fill gaps. Our format's explicitness (decision trees, if-then routing) actually helps here, as long as it doesn't become so complex that it creates ambiguity.
## The Domain Hypothesis
the user's intuition: "Their CLAUDE.md is better for programming, but our verbosity works because we have a lot more generalized use cases."
**The research supports this.** Here's why:
### Programming rules are binary
Code conventions have clear right/wrong answers: use tabs or spaces, this import style or that one, run this linter, use this build command. These are:
- **Low ambiguity:** No judgment call needed
- **Self-evident:** The model can verify compliance by checking the output
- **Context-independent:** The rule applies the same way in every situation
For binary rules, a terse imperative is maximally effective. Adding rationale ("use tabs because our codebase uses tabs") adds tokens without adding compliance. The terse format wins on behavior effectiveness per token.
### Our rules require judgment
Our instruction set deals with situations like:
- **When to search vault vs workspace** (requires classifying the user's intent)
- **When to brainstorm vs just execute** (requires assessing scope clarity)
- **How to format natural language output** (requires understanding context and audience)
- **When to flag an observation vs ignore it** (requires pattern recognition)
- **When a task needs tracking vs is too small** (requires judging effort scope)
These are:
- **High ambiguity:** Reasonable people could disagree on the right action
- **Context-dependent:** The same situation might warrant different responses
- **Judgment-heavy:** The model needs to reason about the purpose, not just check a boolean
For judgment rules, rationale is essential. "Search vault, not workspace" is useless without the hierarchy that explains *which vault tool for which situation*. The terse format would produce frequent misapplication.
### The format-domain matrix
| Rule type | Best format | Why | Example |
|-----------|-------------|-----|---------|
| Binary code convention | Terse imperative | No ambiguity, no edge cases | "Use 2-space indentation" |
| Build/tooling command | Terse imperative | Literal execution, no interpretation | "Run `npm test` before committing" |
| Behavioral gate | Compressed imperative + one-line rationale | Needs trigger recognition but not deep reasoning | "IMPLEMENTATION GATE: Write/Edit requires an in-progress task" |
| Judgment-heavy process | Full rationale with examples | Model must generalize to novel situations | Tool selection hierarchy, observation flagging |
| Anti-pattern correction | Red Flags table (thought vs reality) | Addresses specific reasoning failures the model makes | "I already know the task state" vs "You might not. Run list." |
| Multi-step workflow | Process definition with steps | Sequential execution needs clear ordering | Session orientation, post-compaction protocol |
## Assessment of Our Current Format
### What's working well (high behavior effectiveness per token)
1. **Per-prompt gates** (IMPLEMENTATION, BRAINSTORM, RESEARCH): Short, trigger-shaped, proven drift. These are our best-formatted rules: compressed imperative with one-line rationale. ~3,144 chars for 7 high-drift rules.
2. **Tool selection hierarchy:** The 5-level numbered list is the right format for a priority-ordered decision. Encodes judgment guidance in minimal space.
3. **Red Flags table in SKILL.md:** Directly addresses observed reasoning failures. Format is tight (thought | reality pairs) and the model can pattern-match against its own reasoning.
### What could be tightened (lower behavior effectiveness per token)
1. **SKILL.md skill trigger table:** The descriptions in the table are verbose. Some entries repeat information available in the skill files themselves. Could compress trigger descriptions and rely on the skill file for detail.
2. **SKILL.md vault tool selection:** Two tables (when to use, when not to use) plus a quick reference. This is 3 presentations of the same information. Could consolidate to a single decision table.
3. **CLAUDE.md output workflow:** 12 numbered rules, some quite long. Rules 8-9 (format conventions) are the most detailed. These could potentially move to a reference doc with a short pointer in CLAUDE.md, per the placement framework's principle of "pointers to detail, not detail itself."
4. **SKILL.md session orientation:** Detailed step-by-step for both directed and open sessions. This is process documentation that's needed ~once per session. Appropriate for session-start tier but could be more compressed.
### What's correctly verbose (would lose effectiveness if compressed)
1. **Observation flagging:** The full specification with entry format, when/when-not guidance, and close-the-loop instructions. This is a complex behavior that requires both format compliance and judgment. Compressing it would produce more malformed entries.
2. **Task management 10-question check:** Each question encodes a specific trigger-action pair. The Q&A format is actually efficient here: the model can scan the list as a checklist.
3. **Post-compaction protocol:** The model literally has lost context and needs explicit re-orientation steps. Verbosity is correct because the model's state is degraded.
## Key Takeaways
### 1. Both formats are locally optimal for their domains
The terse format is optimal for binary, code-focused rules. Our verbose format is optimal for judgment-heavy, multi-domain rules. Neither is universally better. The right metric is behavior effectiveness per token, which depends on rule type.
### 2. The real risk is medium compression, not verbosity
The CDCT U-curve finding is counterintuitive: medium compression (~27 words) is worse than both very short (~2 words) and full-length (~135 words). If we tried to compress our judgment-heavy rules into terse imperatives, we'd likely land in the dangerous middle zone: ambiguous enough to trigger RLHF helpfulness override, not explicit enough to constrain.
### 3. Instruction count matters more than token count
Adding a 20th rule is more costly (in compliance dilution) than making existing rules verbose. The priority should be reducing rule count, not compressing rule length. Every rule we can eliminate improves all remaining rules.
### 4. Our tiered placement system is well-aligned with position effects
Per-prompt rules get recency position (end of context). SKILL.md gets primacy position (session start). CLAUDE.md gets always-on position. This naturally maps to the U-shaped attention curve from Lost in the Middle.
### 5. Opportunities exist to compress without losing effectiveness
Some sections (vault tool selection, skill trigger table, output workflow details) could be tightened by consolidating redundant presentations and moving reference detail to docs. This would reduce count/tokens without touching the judgment-heavy rules that need their rationale.
## Research Gaps
- **No controlled study exists** comparing terse vs explanatory system prompts head-to-head on identical tasks across models
- **No "rules per token" optimal density** has been established empirically
- **Multi-turn degradation** of system prompt authority over long conversations is understudied (most research is single-turn)
- **Decision tree format** in system prompts has no empirical validation (Anthropic warns against if-else logic but our tool selection hierarchy may be an exception since it's a priority list, not branching logic)
- **Domain-specific format effectiveness** (programming vs general-purpose instructions) has not been directly studied
## Sources
### Academic papers
- [Separating Constraint Compliance from Semantic Accuracy: CDCT](https://arxiv.org/abs/2512.17920) (arXiv, Dec 2025). Compression-compliance U-curve.
- [How Many Instructions Can LLMs Follow at Once? IFScale](https://arxiv.org/abs/2507.11538) (arXiv, July 2025). Instruction density limits.
- [Lost in the Middle](https://arxiv.org/abs/2307.03172) (TACL, 2024). U-shaped attention curve, position effects.
- [Reasoning Up the Instruction Ladder](https://arxiv.org/abs/2511.04694) (arXiv, 2025). Rationale improves compliance ~20%.
- [Curse of Instructions](https://openreview.net/forum?id=R6q67CDBCH) (OpenReview, 2024). P(all) = P(individual)^n.
- [The Instruction Gap](https://arxiv.org/abs/2601.03269) (arXiv, Dec 2025). Compliance vs accuracy independence.
- [Measuring Pragmatic Influence in LLM Instructions](https://arxiv.org/abs/2602.21223) (arXiv, Feb 2026). Framing cues shift directive prioritization.
- [The Instruction Hierarchy](https://arxiv.org/abs/2404.13208) (arXiv, 2024). Authority framing improves compliance.
- [Chain-of-Thought Prompting](https://arxiv.org/abs/2201.11903) (arXiv, 2022). Foundational CoT paper.
- [Context Rot](https://research.trychroma.com/context-rot) (Chroma Research, July 2025). Performance degradation with context length.
- [Prompt Compression Survey](https://aclanthology.org/2025.naacl-long.368.pdf) (NAACL, 2025).
- [LLMLingua](https://github.com/microsoft/LLMLingua) (Microsoft Research, EMNLP 2023 / ACL 2024).
### Anthropic official
- [Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)
- [Claude 4.6 Prompting Best Practices](https://platform.claude.com/docs/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [Effective Context Engineering for AI Agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
### Practitioner
- [Writing a Good CLAUDE.md](https://www.humanlayer.dev/blog/writing-a-good-claude-md) (HumanLayer)
