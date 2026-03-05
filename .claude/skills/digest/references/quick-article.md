Write a quick triage digest for an article. Frontmatter and Key Takeaways only. No full content section.

**CRITICAL: Minimize tool round-trips.** Target: 1-2 tool calls total (Write file, optional Bash cleanup).

**Article info:**
- Title: [title]
- Author: [author]
- Published: [published]
- URL: [url]
- Word count: [word_count]
- Pipeline: [pipeline]
- Content file: [content_out_path]
- ToC file: [toc_out_path]

**Pre-built frontmatter (paste as-is, replacing `[FILL:...]` placeholders with actual values):**

[frontmatter]

**Full article content (read this to generate Key Takeaways, but do NOT copy it into the digest file):**

[content_markdown]

**Title condensing (conditional):** If `[safe_title]` exceeds 80 characters, condense it to 40-80 chars for filenames and H1. Keep: guest/speaker name (if present), core topic. Drop: verbose descriptions, "and more", filler phrases, excessive subtitles. Save as `[short_title]`. If `[safe_title]` is 80 characters or fewer, set `[short_title]` = `[safe_title]`. Sanitize `[short_title]` for filenames (remove `<>:"/\|?*`, collapse whitespace). Use `[short_title]` for filenames and H1 throughout. The original full title stays in `title:` frontmatter.

**Recurring title detection:** Check if the title is a recurring/generic title. A title is **generic** if it:
- Contains a day-of-week word (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday), OR
- Consists primarily of format descriptors (Update, AMA, Premium Video, Livestream, Weekly, Daily, Monthly, Q&A, Podcast, Episode) without a unique topic identifier (specific subject, proper noun, or thesis)

If **generic**, append the published date (YYYY-MM-DD) to the filename and H1:
- Filename: `outputs/digests/[short_title] [published].md`
- H1: `# [short_title] [published]`

If **unique**, use the standard format with no date appended:
- Filename: `outputs/digests/[short_title].md`

The `title:` frontmatter field always uses the original full title without the date.

**Step 1: Write the digest file** (frontmatter + Key Takeaways ONLY):

1. **Frontmatter:** Paste the pre-built frontmatter, replacing `[FILL:...]` placeholders: `description` with a one-line summary, `parent` with the active task wiki-link from the prompt inputs.
2. **Heading:** `# [short_title]` followed by `[title]([url])` on the next line.
3. **Key Takeaways:** Write a `## Key Takeaways` section. See format below.
4. **Quick mode note with provenance:**
```
## Full Content
> [!info]- Digest provenance
> mode: quick
> pipeline: [pipeline]
*Quick mode: full content not included. Run `/digest [url]` for complete article with Table of Contents.*
```

Do NOT write Table of Contents or Full Content body. This is quick triage mode.

**Key Takeaways format:**
- **Bold first sentence:** Directly answer the curiosity hook from the title or opening argument. Tag format indicators inline using parentheses: (Sponsored), (Tutorial), (Interview), (Commentary). When there's no clear hook, bold the core claim or thesis. Do NOT restate the title.
- **Dash-list points below the bold summary.** Each point starts with `- ` and is one concise sentence: carry the core meaning, cut extra color. Include specific names and numbers, not vague summaries. 3-7 key takeaways for focused articles, ranked by insight value.

**Summarization guidelines:**
- Every claim in Key Takeaways must come directly from the source text. Do not infer, extrapolate, or add claims not explicitly stated in the content.
- Capture specific claims, numbers, data points, actionable insights. Not vague summaries.
- State points directly, not "the author argues X". Just state X.
- No horizontal rules (---) between sections in the body.
- Tight formatting: no blank lines between headings and their content.

**Step 2: Clean up temp files**

```bash
rm "[content_out_path]" "[toc_out_path]"
```

**Return ONLY:** The exact digest file path. Nothing else. The parent session reads the file directly for reporting.
