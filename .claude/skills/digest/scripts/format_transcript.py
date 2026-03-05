#!/usr/bin/env python3
"""
Deterministic transcript formatter for /digest skill.
Replaces the Haiku LLM agent with reliable mechanical formatting.

Input: raw transcript file from transcribe.py + optional chapters JSON
Output: formatted transcript text to stdout

Algorithm:
1. Strip frontmatter and H1 title
2. Parse [MM:SS] timestamped lines into segments
3. Concatenate segment text into continuous prose
4. Split at sentence boundaries, group into paragraphs (4-5 sentences)
5. Insert chapter subheadings at correct timestamp positions
6. Output formatted text with one timestamp per paragraph
"""

import argparse
import io
import json
import re
import sys


def parse_raw_transcript(text):
    """Parse raw transcript into segments.

    Returns list of (timestamp_seconds, text, speaker_or_None) tuples.

    Input format (from transcribe.py, optionally enriched by diarize.py):
    ---
    frontmatter
    ---
    # Title
    [00:00] First segment text
    [00:05] [SPEAKER_00] Second segment text (diarized)
    ...
    """
    # Strip frontmatter
    if text.startswith("---"):
        end = text.find("---", 3)
        if end != -1:
            text = text[end + 3 :].strip()

    lines = text.split("\n")
    segments = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Skip H1 title
        if line.startswith("# "):
            continue

        # Match [HH:MM:SS] or [MM:SS] timestamp, optionally followed by [SPEAKER_XX]
        m = re.match(r"\[(\d{1,2}):(\d{2}):?(\d{2})?\]\s*(.*)", line)
        if m:
            if m.group(3):  # HH:MM:SS
                secs = (
                    int(m.group(1)) * 3600
                    + int(m.group(2)) * 60
                    + int(m.group(3))
                )
            else:  # MM:SS
                secs = int(m.group(1)) * 60 + int(m.group(2))
            text_part = m.group(4).strip()

            # Strip all [SPEAKER_XX] tags from the start of text_part.
            # Handles duplicate tags (e.g., from diarize.py running twice).
            # Only matches SPEAKER_ prefixed IDs to preserve Whisper markers like [music].
            speaker = None
            while True:
                sm = re.match(r"\[(SPEAKER_\w+)\]\s*(.*)", text_part)
                if sm:
                    speaker = sm.group(1)
                    text_part = sm.group(2).strip()
                else:
                    break
            # Strip any [SPEAKER_XX] tags remaining mid-text (extra safety).
            # Only matches pyannoteAI-style speaker IDs, not Whisper markers like [music].
            text_part = re.sub(r'\[SPEAKER_\w+\]\s*', '', text_part).strip()

            if text_part:
                segments.append((secs, text_part, speaker))

    return segments


def format_timestamp(seconds):
    """Format seconds as [MM:SS] or [HH:MM:SS]."""
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    if h:
        return f"[{h:02d}:{m:02d}:{s:02d}]"
    return f"[{m:02d}:{s:02d}]"


def merge_segments_to_text(segments):
    """Concatenate segment text into continuous prose.

    Accepts segments as either (ts, text) or (ts, text, speaker) tuples.
    Returns (full_text, ts_markers) where ts_markers is a list of
    (char_offset, timestamp_seconds) marking where each segment starts
    in the merged text.
    """
    full_text = ""
    ts_markers = []

    for seg in segments:
        ts, text = seg[0], seg[1]
        if full_text:
            ts_markers.append((len(full_text) + 1, ts))
            full_text += " " + text
        else:
            ts_markers.append((0, ts))
            full_text = text

    return full_text, ts_markers


def split_sentences(text):
    """Split text into sentences at boundary punctuation.

    First tries splitting at . ? ! followed by space + uppercase letter,
    opening quote, or opening parenthesis. If that produces oversized
    chunks (common with Whisper lowercase output), falls back to
    splitting at . ? ! followed by any letter. Final fallback splits
    on word count for completely unpunctuated runs.
    """
    # Primary: sentence-ending punctuation + space + capital/quote
    parts = re.split(r'(?<=[.!?])\s+(?=[A-Z"\'\(])', text)
    parts = [p.strip() for p in parts if p.strip()]

    # Check if any part is oversized (>150 words = ~45 seconds of speech)
    MAX_WORDS = 150
    needs_resplit = any(len(p.split()) > MAX_WORDS for p in parts)

    if needs_resplit:
        # Fallback: split at sentence-ending punctuation + space + any letter
        parts = re.split(r'(?<=[.!?])\s+(?=[a-zA-Z"\'\(])', text)
        parts = [p.strip() for p in parts if p.strip()]

    # Final fallback: force-split any remaining oversized chunks by word count
    HARD_MAX = MAX_WORDS * 2  # Force break even without punctuation
    final_parts = []
    for part in parts:
        words = part.split()
        if len(words) > MAX_WORDS:
            chunk_words = []
            for word in words:
                chunk_words.append(word)
                at_punctuation = word.endswith(('.', '!', '?'))
                at_hard_max = len(chunk_words) >= HARD_MAX
                if (len(chunk_words) >= MAX_WORDS and at_punctuation) or at_hard_max:
                    final_parts.append(' '.join(chunk_words))
                    chunk_words = []
            if chunk_words:
                final_parts.append(' '.join(chunk_words))
        else:
            final_parts.append(part)

    return final_parts


def get_timestamp_for_position(char_pos, ts_markers):
    """Find the timestamp corresponding to a character position."""
    ts = 0
    for offset, t in ts_markers:
        if offset <= char_pos:
            ts = t
        else:
            break
    return ts


def has_speaker_data(segments):
    """Check if any segments have speaker labels."""
    return any(len(seg) > 2 and seg[2] is not None for seg in segments)


def get_speaker_at_position(char_pos, speaker_markers):
    """Find the speaker at a character position in the merged text."""
    speaker = None
    for offset, spk in speaker_markers:
        if offset <= char_pos:
            speaker = spk
        else:
            break
    return speaker


def build_paragraphs(segments, chapters=None, target_sentences=5,
                     speaker_names=None):
    """Group segments into paragraphs with chapter headings and speaker labels.

    Args:
        segments: list of (timestamp_seconds, text, speaker_or_None)
        chapters: list of {"start_time": seconds, "title": str} or None
        target_sentences: target number of sentences per paragraph
        speaker_names: dict mapping SPEAKER_XX to real names, or None

    Returns:
        Formatted transcript string ready for output
    """
    if not segments:
        return ""

    has_speakers = has_speaker_data(segments)

    if has_speakers and speaker_names:
        return _build_speaker_paragraphs(
            segments, chapters, target_sentences, speaker_names
        )

    # Non-speaker path (original behavior)
    return _build_plain_paragraphs(segments, chapters, target_sentences)


def _build_plain_paragraphs(segments, chapters=None, target_sentences=5,
                            max_words_per_para=120):
    """Original paragraph building without speaker awareness."""
    # Merge all segments into continuous text
    full_text, ts_markers = merge_segments_to_text(segments)

    if not full_text:
        return ""

    # Split into sentences
    sentences_raw = split_sentences(full_text)

    # Map each sentence to its timestamp by finding its position in full_text
    sentences = []  # (timestamp_seconds, sentence_text)
    search_from = 0
    for sent in sentences_raw:
        # Find where this sentence starts in the full text
        pos = full_text.find(sent[:30], search_from)
        if pos == -1:
            pos = search_from
        ts = get_timestamp_for_position(pos, ts_markers)
        sentences.append((ts, sent))
        search_from = pos + len(sent)

    # Sort chapters by start_time
    pending_chapters = []
    if chapters:
        pending_chapters = sorted(chapters, key=lambda c: c["start_time"])
    ch_idx = 0

    # Build output
    output_parts = []
    para_sentences = []
    para_ts = sentences[0][0] if sentences else 0

    for sent_ts, sent_text in sentences:
        # Check if chapter heading(s) should be inserted before this sentence
        while (
            ch_idx < len(pending_chapters)
            and pending_chapters[ch_idx]["start_time"] <= sent_ts
        ):
            # Flush current paragraph before heading
            if para_sentences:
                ts_str = format_timestamp(para_ts)
                output_parts.append(f"{ts_str} {' '.join(para_sentences)}")
                para_sentences = []

            output_parts.append(
                f"### {pending_chapters[ch_idx]['title']}"
            )
            ch_idx += 1
            para_ts = sent_ts

        # Start new paragraph if needed
        if not para_sentences:
            para_ts = sent_ts

        para_sentences.append(sent_text)

        # Break paragraph at target sentence count OR word limit
        para_word_count = sum(len(s.split()) for s in para_sentences)
        if len(para_sentences) >= target_sentences or para_word_count >= max_words_per_para:
            ts_str = format_timestamp(para_ts)
            output_parts.append(f"{ts_str} {' '.join(para_sentences)}")
            para_sentences = []

    # Flush remaining sentences
    if para_sentences:
        ts_str = format_timestamp(para_ts)
        output_parts.append(f"{ts_str} {' '.join(para_sentences)}")

    # Insert any remaining chapter headings (at the very end of the video)
    while ch_idx < len(pending_chapters):
        output_parts.append(
            f"### {pending_chapters[ch_idx]['title']}"
        )
        ch_idx += 1

    return "\n\n".join(output_parts)


def _build_speaker_paragraphs(segments, chapters=None, target_sentences=5,
                              speaker_names=None):
    """Speaker-aware paragraph building.

    Groups consecutive same-speaker segments, merges into paragraphs,
    inserts bold speaker name prefixes at turn boundaries.
    """
    if not speaker_names:
        speaker_names = {}

    def resolve_name(speaker_id):
        return speaker_names.get(speaker_id, speaker_id)

    # Group consecutive segments by speaker into "turns"
    turns = []  # list of (speaker, [(ts, text), ...])
    current_speaker = None
    current_segs = []

    for seg in segments:
        ts, text = seg[0], seg[1]
        speaker = seg[2] if len(seg) > 2 else None

        if speaker != current_speaker:
            if current_segs:
                turns.append((current_speaker, current_segs))
            current_speaker = speaker
            current_segs = [(ts, text)]
        else:
            current_segs.append((ts, text))

    if current_segs:
        turns.append((current_speaker, current_segs))

    # Sort chapters by start_time
    pending_chapters = []
    if chapters:
        pending_chapters = sorted(chapters, key=lambda c: c["start_time"])
    ch_idx = 0

    output_parts = []

    for speaker, turn_segs in turns:
        turn_start_ts = turn_segs[0][0]

        # Insert chapter headings that fall before this turn
        while (
            ch_idx < len(pending_chapters)
            and pending_chapters[ch_idx]["start_time"] <= turn_start_ts
        ):
            output_parts.append(
                f"### {pending_chapters[ch_idx]['title']}"
            )
            ch_idx += 1

        # Merge turn segments into text
        full_text = " ".join(text for _, text in turn_segs)
        if not full_text:
            continue

        # Build timestamp markers for this turn
        ts_markers = []
        offset = 0
        for ts, text in turn_segs:
            ts_markers.append((offset, ts))
            offset += len(text) + 1  # +1 for the space

        # Split into sentences
        sentences_raw = split_sentences(full_text)

        # Map sentences to timestamps
        sentences = []
        search_from = 0
        for sent in sentences_raw:
            pos = full_text.find(sent[:30], search_from)
            if pos == -1:
                pos = search_from
            ts = get_timestamp_for_position(pos, ts_markers)
            sentences.append((ts, sent))
            search_from = pos + len(sent)

        # Build paragraphs for this turn
        name = resolve_name(speaker)
        first_para = True
        para_sentences = []
        para_ts = sentences[0][0] if sentences else turn_start_ts

        for sent_ts, sent_text in sentences:
            if not para_sentences:
                para_ts = sent_ts

            para_sentences.append(sent_text)

            if len(para_sentences) >= target_sentences:
                ts_str = format_timestamp(para_ts)
                text_block = " ".join(para_sentences)
                if first_para:
                    output_parts.append(
                        f"{ts_str} **{name}:** {text_block}"
                    )
                    first_para = False
                else:
                    output_parts.append(f"{ts_str} {text_block}")
                para_sentences = []

        # Flush remaining
        if para_sentences:
            ts_str = format_timestamp(para_ts)
            text_block = " ".join(para_sentences)
            if first_para:
                output_parts.append(f"{ts_str} **{name}:** {text_block}")
            else:
                output_parts.append(f"{ts_str} {text_block}")

    # Insert any remaining chapter headings
    while ch_idx < len(pending_chapters):
        output_parts.append(
            f"### {pending_chapters[ch_idx]['title']}"
        )
        ch_idx += 1

    return "\n\n".join(output_parts)


def extract_toc_from_formatted(formatted_text):
    """Extract ### headings with timestamps for Table of Contents.

    Scans the formatted transcript for ### headings, finds the first
    timestamp in the lines following each heading, and builds ToC entries
    in the format: "timestamp – [[#Heading]]".

    Returns list of ToC line strings (empty if no headings found).
    """
    lines = formatted_text.split("\n")
    toc_lines = []
    for i, line in enumerate(lines):
        if line.startswith("### "):
            heading = line[4:].strip()
            timestamp = None
            for j in range(i + 1, min(i + 5, len(lines))):
                m = re.match(r"\[(\d{1,2}):(\d{2}):?(\d{2})?\]", lines[j])
                if m:
                    if m.group(3):  # HH:MM:SS
                        h, mi, s = (
                            int(m.group(1)),
                            int(m.group(2)),
                            int(m.group(3)),
                        )
                        timestamp = f"{h}:{mi:02d}:{s:02d}"
                    else:  # MM:SS
                        mi, s = int(m.group(1)), int(m.group(2))
                        timestamp = f"{mi}:{s:02d}"
                    break
            if timestamp:
                toc_lines.append(f"{timestamp} [[#{heading}]]")
    return toc_lines


def main():
    parser = argparse.ArgumentParser(
        description="Format raw transcript into readable paragraphs"
    )
    parser.add_argument("transcript_path", help="Path to raw transcript .md file")
    parser.add_argument(
        "--chapters",
        default="[]",
        help="JSON array of chapters: [{start_time, title}, ...]",
    )
    parser.add_argument(
        "--target-sentences",
        type=int,
        default=5,
        help="Target sentences per paragraph (default: 5)",
    )
    parser.add_argument(
        "--toc-out",
        default=None,
        help="Write Table of Contents to this file (timestamp + heading per line)",
    )
    parser.add_argument(
        "--speaker-names",
        default=None,
        help='JSON mapping of speaker IDs to names: \'{"SPEAKER_00": "Host Name"}\'',
    )
    args = parser.parse_args()

    with open(args.transcript_path, "r", encoding="utf-8") as f:
        text = f.read()

    chapters = json.loads(args.chapters) if args.chapters else []
    segments = parse_raw_transcript(text)

    if not segments:
        print("ERROR: No transcript segments found", file=sys.stderr)
        sys.exit(1)

    speaker_names = None
    if args.speaker_names:
        speaker_names = json.loads(args.speaker_names)

    formatted = build_paragraphs(
        segments, chapters, args.target_sentences,
        speaker_names=speaker_names,
    )

    # Write ToC file if requested
    if args.toc_out:
        toc_lines = extract_toc_from_formatted(formatted)
        with open(args.toc_out, "w", encoding="utf-8") as f:
            f.write("\n".join(toc_lines))

    # Force UTF-8 stdout on Windows to avoid codepage mangling
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    print(formatted)


if __name__ == "__main__":
    main()
