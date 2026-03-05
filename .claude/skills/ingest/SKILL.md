---
name: ingest
description: "Transcribe scanned handwritten PDFs into vault-ready text. Usage: /ingest <pdf path>. Also: /ingest scan (check for new PDFs), /ingest status (show index). PDF pages are OCR'd via parallel Sonnet agents, combined into a raw transcription for review, then formatted into vault notes."
---

# Ingest: Scanned PDF Transcription

## Usage

- `/ingest <pdf path>` - Transcribe a single PDF
- `/ingest scan` - Scan Google Drive folder, compare against index, report new/pending
- `/ingest status` - Show current tracking index state

## Prerequisites

- Python packages: `pymupdf`, `Pillow` (both installed)
- Source PDFs location: `<your-scan-folder>/`

## Pipeline

### Step 1: Extract pages

```bash
python ".claude/skills/ingest/scripts/extract_pages.py" "<pdf_path>"
```

Parse the JSON output. Save `hash`, `page_count`, `output_dir`, `image_paths`.

If `skipped: true`, images already exist. Proceed to Step 2.

### Step 2: Check tracking index

Read `outputs/Journal ingestion index.md`. If the hash already has status `complete`, tell the user:
"This PDF has already been processed. Output notes: [links]. Re-run with --force if you want to redo it."

If status is `transcribed`, skip to Step 4 (raw transcription exists, awaiting review).

If no entry or status is `pending`, continue to Step 3.

### Step 3: Launch OCR agents

Divide the image paths into batches of 5. Launch **parallel Sonnet subagents** (`Task` tool, `model: "sonnet"`, `subagent_type: "general-purpose"`, `max_turns: 8`), one per batch.

Send a **single message** with all Task tool calls to maximize parallelism.

Read the agent prompt from `references/ocr-agent-prompt.md`. Fill in `[bracketed]` values before launching each agent.

After all agents return, proceed to Step 4.

### Step 4: Combine transcriptions

```bash
python ".claude/skills/ingest/scripts/combine_transcriptions.py" "[work_dir]" --output "outputs/temp/[pdf_name] - raw transcription (temp).md" --pdf-name "[pdf_name]"
```

Parse the JSON output. Report to the user:

```
**Ingest: [pdf_name]**
- Pages: [page_count]
- Dates found: [count] ([date_range])
- Content type: [content_type_guess]
- Raw transcription: outputs/temp/[pdf_name] - raw transcription (temp).md

Review in Obsidian alongside the source PDF. Fix any errors, then tell me to proceed with formatting.
```

Update the tracking index: add or update the row with status `transcribed`.

### Step 5: Format (after user review)

When the user confirms the transcription looks good and specifies the content type:

**For daily journals:**
1. Parse the raw transcription for date boundaries (##### headings)
2. Group entries by month
3. Create one file per month in `outputs/`: `YYYY-MM Journal.md`
4. Frontmatter: `type: journal`, `created: [earliest date in month]`, `source: human`, `parent: '[[Ingest scanned journals into vault]]'`
5. Entry format: `##### Day DD/MM/YY time` headings with free-form text below

**For other content types:**
- Format per the type's vault convention
- Ask the user if unclear

Update the tracking index: status `complete`, add output note links and date range.

### Step 6: Clean up

After formatting is confirmed:
- The raw transcription temp file can be deleted (or kept if the user wants it)
- The work directory (`outputs/temp/.ocr_work/<hash>/`) can be deleted
- Keep the tracking index updated

## `/ingest scan` Mode

1. List all PDF files in `<your-scan-folder>/`
2. Read the tracking index
3. For each PDF: compute hash, check against index
4. Report: new files (not in index), pending (in index but not complete), complete

## `/ingest status` Mode

Read and display the tracking index table from `outputs/Journal ingestion index.md`.

## Tracking Index Format

File: `outputs/Journal ingestion index.md`

```markdown
---
created: YYYY-MM-DD HH:MM
description: "Tracking index for scanned PDF ingestion. Maps source PDFs to their processing state and output vault notes."
parent: '[[Ingest scanned journals into vault]]'
source: claude
type: artifact
---
# Journal ingestion index

| PDF File | Hash | Status | Pages | Date Range | Output Notes | Processed |
|---|---|---|---|---|---|---|
| example.pdf | a3f2... | complete | 46 | Nov 2024 | [[2024-11 Journal]] | 2026-02-28 |
```

Status values: `pending`, `transcribed`, `complete`, `skipped`

## Error Handling

| Error | Response |
|-------|----------|
| PDF not found | Check path. Google Drive may not be synced. |
| pymupdf/Pillow not installed | `pip install pymupdf Pillow` |
| Agent fails mid-batch | Report which batch failed. Re-run: existing batches are kept, only missing ones need re-processing. |
| No batch files found | Agents may not have written output. Check work directory manually. |
| Hash collision | Extremely unlikely (16-char SHA-256 prefix). If it happens, delete the work directory and re-extract. |

## File Lifecycle

- **Page images** (`outputs/temp/.ocr_work/<hash>/page_*.jpg`): Ephemeral. Deleted after formatting is confirmed.
- **Batch transcriptions** (`outputs/temp/.ocr_work/<hash>/batch_*.md`): Ephemeral. Consumed by combine step.
- **Raw transcription** (`outputs/temp/<name> - raw transcription (temp).md`): Temp. Human reviews this. Deleted after formatting.
- **Formatted notes** (`outputs/YYYY-MM Journal.md`): Permanent output. the user moves to vault when ready.
- **Tracking index** (`outputs/Journal ingestion index.md`): Permanent. Source of truth for processing state.
