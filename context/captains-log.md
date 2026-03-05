# Captain's log

Significant design decisions that shape how the workspace machine is built. Each entry records what was decided, why, and links to the task where the work happened. Includes both changes and deliberate confirmations (evaluated something and decided to keep the current approach).

Most tasks don't generate entries here. Only decisions that change or deliberately confirm the system's architecture, conventions, or behavior belong.

---

### 2026-01-15

**Example entry: chose skills over hardcoded CLAUDE.md rules**
Skills load context on demand instead of bloating the always-loaded CLAUDE.md. Each skill owns its SKILL.md, references, and scripts. CLAUDE.md points to skills but doesn't contain their logic. [[Example task name]]
