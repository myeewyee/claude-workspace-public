# Markdown formatting
Formatting conventions for all workspace files. Applied to outputs, task files, context files, and instruction files.
## Heading spacing
- Headings are the visual separators. No blank lines around any heading (H1, H2, H3, H4).
- No blank lines between consecutive headings.
## Progress log format
- No blank line between `### date` heading and first timestamp entry.
- Blank line between each timestamp entry within a date group.
- Blank line between date groups (as separator).
- **Entry content format:** Major entries use bold heading + sub-bullets. One-liners stay as plain text. Never write dense paragraphs. Example:
  ```
  10:26 PM **What changed** <!-- session: UUID -->
  - Detail one
  - Detail two
  - Detail three
  ```
## Line breaks
- No backslash (`\`) Markdown line breaks anywhere. Plain newlines only.
## Tables
- Tables require a blank line before them (after headings, paragraphs, or other content) for Obsidian to render them correctly.
## Horizontal rules
- No `---` horizontal rules between sections. Use H2 headings for separation.
