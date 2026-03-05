#!/usr/bin/env python3
"""Extract page images from a scanned PDF for OCR processing.

Reads a PDF file, exports each page as a JPEG image, and computes a
file hash for deduplication. Skips extraction if images already exist
for the same hash.

Input:  PDF file path (positional)
Output: JSON to stdout with pdf_name, hash, page_count, output_dir, image_paths
Progress messages go to stderr.

Dependencies: pymupdf (fitz), Pillow
"""

import argparse
import hashlib
import io
import json
import os
import sys

CHUNK_SIZE = 65536  # 64KB chunks for hashing
DEFAULT_DPI = 150
DEFAULT_QUALITY = 80
DEFAULT_OUTPUT_DIR = "outputs/temp/.ocr_work"


def compute_hash(pdf_path):
    """Compute SHA-256 hash of a file."""
    sha = hashlib.sha256()
    with open(pdf_path, "rb") as f:
        while True:
            chunk = f.read(CHUNK_SIZE)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()[:16]  # First 16 chars is plenty for dedup


def extract(pdf_path, output_dir, dpi, quality):
    """Extract pages from PDF as JPEG images.

    Returns dict with extraction results.
    """
    import fitz  # pymupdf
    from PIL import Image

    pdf_name = os.path.basename(pdf_path)
    file_hash = compute_hash(pdf_path)
    work_dir = os.path.join(output_dir, file_hash)

    # Open PDF to get page count
    doc = fitz.open(pdf_path)
    page_count = len(doc)

    # Check if already extracted
    if os.path.isdir(work_dir):
        existing = [f for f in os.listdir(work_dir) if f.startswith("page_") and f.endswith(".jpg")]
        if len(existing) == page_count:
            doc.close()
            image_paths = sorted(
                [os.path.join(work_dir, f).replace("\\", "/") for f in existing]
            )
            print(f"Skipping extraction: {page_count} pages already exist for hash {file_hash}", file=sys.stderr)
            return {
                "pdf_name": pdf_name,
                "hash": file_hash,
                "page_count": page_count,
                "output_dir": work_dir.replace("\\", "/"),
                "image_paths": image_paths,
                "skipped": True,
            }

    # Create work directory
    os.makedirs(work_dir, exist_ok=True)

    image_paths = []
    for i, page in enumerate(doc):
        page_num = i + 1
        pix = page.get_pixmap(dpi=dpi)

        # Convert to PIL Image for JPEG export with quality control
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        out_path = os.path.join(work_dir, f"page_{page_num:03d}.jpg")
        img.save(out_path, "JPEG", quality=quality)

        image_paths.append(out_path.replace("\\", "/"))

        if page_num % 10 == 0 or page_num == page_count:
            print(f"Extracted {page_num}/{page_count} pages", file=sys.stderr)

    doc.close()

    return {
        "pdf_name": pdf_name,
        "hash": file_hash,
        "page_count": page_count,
        "output_dir": work_dir.replace("\\", "/"),
        "image_paths": image_paths,
        "skipped": False,
    }


def main():
    parser = argparse.ArgumentParser(description="Extract PDF pages as JPEG images")
    parser.add_argument("pdf_path", help="Path to the PDF file")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Output directory for extracted images")
    parser.add_argument("--dpi", type=int, default=DEFAULT_DPI, help="DPI for image extraction")
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY, help="JPEG quality (1-100)")
    args = parser.parse_args()

    # Ensure UTF-8 stdout on Windows
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    try:
        if not os.path.isfile(args.pdf_path):
            raise FileNotFoundError(f"PDF not found: {args.pdf_path}")

        result = extract(args.pdf_path, args.output_dir, args.dpi, args.quality)
        print(json.dumps(result, indent=2))

    except Exception as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)


if __name__ == "__main__":
    main()
