Write a content digest for an X/Twitter article.

**CRITICAL: Minimize tool round-trips.** Target: 2 tool calls total (one Write, one Bash). Do not read files or do any exploration. All content is provided in this prompt.

**Article info:**
- Title: [title]
- Author: [display_name] (@[screen_name])
- Published: [published]
- URL: [url]
- Image: [image]
- Preview: [preview_text]
- Content file: [content_out_path]
- ToC file: [toc_out_path]

**Full article content (read this to generate Key Takeaways, but do NOT copy it into the digest file; the assembly script handles that):**

[content_markdown]

**Title condensing (conditional):** If `[safe_title]` exceeds 80 characters, condense it to 40-80 chars for filenames and H1. Keep: guest/speaker name (if present), core topic. Drop: verbose descriptions, "and more", filler phrases, excessive subtitles. Save as `[short_title]`. If `[safe_title]` is 80 characters or fewer, set `[short_title]` = `[safe_title]`. Sanitize `[short_title]` for filenames (remove `<>:"/\|?*`, collapse whitespace). Use `[short_title]` for filenames and H1 throughout. The original full title stays in `title:` frontmatter.

**Recurring title detection:** Check if the title is a recurring/generic title. A title is **generic** if it:
- Contains a day-of-week word (Monday, Tuesday, Wednesday, Thursday, Friday, Saturday, Sunday), OR
- Consists primarily of format descriptors (Update, AMA, Premium Video, Livestream, Weekly, Daily, Monthly, Q&A, Podcast, Episode) without a unique topic identifier (specific subject, proper noun, or thesis)

If **generic**, append the published date (YYYY-MM-DD) to the filename and H1:
- Filename: `outputs/digests/[short_title] [published].md`
- H1: `# [short_title] [published]`

If **unique**, use the standard format with no date appended. The `title:` frontmatter field always uses the original full title without the date.

**Step 1: Write the digest file** (frontmatter + Key Takeaways ONLY):

```
---
author: "[[screen_name]]"
title: "[title]"
created: [date] [time]
published: [published]
description: "[one-line summary of the article's core claim or topic]"
image: [image]
parent: '[[ACTIVE_TASK_NAME]]'
source: claude
depth: deep
subtype: article
type: content
url: [url]
---
# [short_title]
[title]([url])

## Key Takeaways
[Bold first sentence, then dash-list points. See format below.]
```

**Key Takeaways format:**
- **Bold first sentence:** Directly answer the curiosity hook from the title or opening argument. Tag format indicators inline using parentheses: (Sponsored), (Tutorial), (Interview), (Commentary). When there's no clear hook, bold the core claim or thesis. Do NOT restate the title.
- **Dash-list points below the bold summary.** Each point starts with `- ` and is one concise sentence: carry the core meaning, cut extra color. Include specific names and numbers, not vague summaries. 3-7 key takeaways for focused articles, ranked by insight value.

**Summarization guidelines (for Key Takeaways only):**
- Every claim in Key Takeaways must come directly from the source text. Do not infer, extrapolate, or add claims not explicitly stated in the content.
- Capture specific claims, numbers, data points, actionable insights. Not vague summaries.
- State points directly, not "the author argues X". Just state X.
- No horizontal rules (---) between sections in the body.
- Tight formatting: no blank lines between headings and their content.

**Step 2: Assemble the full digest (SINGLE Bash command)**

Do NOT write the article content yourself. The assembly script appends ToC + Full Content mechanically.

```bash
python ".claude/skills/digest/scripts/assemble_digest.py" "outputs/digests/[short_title].md" "[content_out_path]" --toc "[toc_out_path]" --heading "Full Content" --provenance "mode: full\npipeline: x-twitter" && rm "[content_out_path]" "[toc_out_path]"
```

**Return ONLY:** The exact digest file path. Nothing else. The parent session reads the file directly for reporting.
