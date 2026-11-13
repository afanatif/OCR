#!/usr/bin/env python
"""
Phase 0 — Export Book Content.

Converts a PDF to a clean, image-resolved Markdown export using two tools:
  1. Docling  — high-quality text + table markdown (batch processing)
  2. PyMuPDF  — precise per-page image extraction with bbox metadata

Pipeline
--------
  PDF
   ├── [Docling batch]   → raw markdown with generic `<!-- image -->` tags
   └── [PyMuPDF]         → image files + manifest {page → [ImageEntry]}
                                         ↓
                  resolve_image_tags()  replaces each `<!-- image -->` with
                  `<!-- image: images/pN_iM.ext -->` using reading-order matching
                                         ↓
                  split_into_units()    writes unit_XX.txt files

Flags
-----
  --book        Book key from BOOK_METADATA (required)
  --batch-size  Pages per Docling batch (default: 10)
  --force       Re-run Docling even if full_text.txt already exists
  --min-px      Minimum image pixel dimension to keep (default: 60)
"""

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.core.books import BOOK_METADATA
from src.core.config import INPUT_MCQ_DIR, OUTPUT_MCQ_DIR
from src.mcqs.image_mapper import build_image_manifest, resolve_image_tags
from src.mcqs.parser import split_into_units
from src.core.logger import logger


# ── CLI ────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export PDF text and images with resolved image references."
    )
    parser.add_argument("--book",       required=True,          help="Book key (e.g. physiology_mcqs)")
    parser.add_argument("--batch-size", type=int, default=10,   help="Pages per Docling batch (default: 10)")
    parser.add_argument("--force",      action="store_true",    help="Re-run Docling even if full_text.txt exists")
    parser.add_argument("--min-px",     type=int, default=60,   help="Min image pixel dimension to keep (default: 60)")
    # Page-range options for fast testing — both are 1-indexed and inclusive.
    parser.add_argument("--pages-from", type=int, default=None,
                        help="First page to process, 1-indexed (default: 1 / beginning)")
    parser.add_argument("--pages-to",   type=int, default=None,
                        help="Last page to process, 1-indexed inclusive (default: last page)")
    return parser.parse_args()


# ── Docling conversion ─────────────────────────────────────────────────────

def _build_converter() -> DocumentConverter:
    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr             = False
    pipeline_options.do_table_structure = True
    pipeline_options.generate_page_images = False

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)
        }
    )


def _run_docling_batches(
    doc: fitz.Document,
    total_pages: int,
    batch_size: int,
    start_page: int = 0,
    end_page: Optional[int] = None,
) -> str:
    """
    Run Docling on the PDF in batches.  Each batch output is prefixed with
    a `<!-- pages X-Y -->` marker so that resolve_image_tags() can later
    determine which page range each section of markdown covers.

    Parameters
    ----------
    start_page : 0-indexed first page to process (inclusive)
    end_page   : 0-indexed last page to process (inclusive); defaults to total_pages-1
    """
    if end_page is None:
        end_page = total_pages - 1

    converter     = _build_converter()
    chunks:  list[str] = []
    failed_batches = 0

    for batch_start in range(start_page, end_page + 1, batch_size):
        batch_end = min(batch_start + batch_size - 1, end_page)  # 0-indexed, inclusive
        # Human-readable 1-indexed labels for the marker
        label_from = batch_start + 1
        label_to   = batch_end   + 1
        logger.info(f"  Docling batch: pages {label_from}–{label_to} ...")

        tmp_path = Path(tempfile.mktemp(suffix=".pdf"))
        try:
            batch_doc = fitz.open()
            batch_doc.insert_pdf(doc, from_page=batch_start, to_page=batch_end)
            batch_doc.save(str(tmp_path))
            batch_doc.close()

            result   = converter.convert(str(tmp_path))
            chunk_md = result.document.export_to_markdown()
            header   = f"<!-- pages {label_from}-{label_to} -->\n"
            chunks.append(header + chunk_md)
            logger.success(f"  Batch {label_from}–{label_to} done.")
        except Exception as exc:
            logger.error(f"  Batch {label_from}–{label_to} failed: {exc}")
            chunks.append(f"<!-- pages {label_from}-{label_to} -->\n")
            failed_batches += 1
        finally:
            tmp_path.unlink(missing_ok=True)

    if failed_batches:
        logger.warning(f"{failed_batches} Docling batch(es) failed — those pages may be incomplete.")

    return "\n\n".join(chunks)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()

    meta = BOOK_METADATA.get(args.book)
    if not meta:
        logger.error(f"Unknown book key: {args.book}")
        sys.exit(1)

    pdf_path = INPUT_MCQ_DIR / meta["year"] / meta["subject"] / meta["filename"]
    if not pdf_path.exists():
        logger.error(f"PDF not found: {pdf_path}")
        sys.exit(1)

    export_dir = (
        OUTPUT_MCQ_DIR / meta["year"] / meta["subject"]
        / meta["display_name"] / "export"
    )
    export_dir.mkdir(parents=True, exist_ok=True)
    img_dir = export_dir / "images"
    img_dir.mkdir(exist_ok=True)

    doc         = fitz.open(pdf_path)
    total_pages = len(doc)

    # ── Resolve page range ────────────────────────────────────────────────
    page_from = max(1, args.pages_from or 1)
    page_to   = min(total_pages, args.pages_to or total_pages)
    if page_from > page_to:
        logger.error(f"--pages-from ({page_from}) must be <= --pages-to ({page_to})")
        sys.exit(1)

    partial = (page_from != 1 or page_to != total_pages)
    page_range_label = f"p{page_from}-{page_to}" if partial else "full"

    if partial:
        logger.info(
            f"=== Export (PARTIAL {page_from}–{page_to}): "
            f"{meta['display_name']} | {total_pages} total pages ==="
        )
    else:
        logger.info(f"=== Export: {meta['display_name']} | {total_pages} pages ===")

    # ── Choose output filenames ───────────────────────────────────────────
    # Partial exports get their own filename so they never overwrite a full export.
    suffix       = f"_{page_range_label}" if partial else ""
    raw_md_path  = export_dir / f"full_text_raw{suffix}.txt"
    full_md_path = export_dir / f"full_text{suffix}.txt"

    # ── Step 1: Docling — text + tables → raw markdown ────────────────────
    if full_md_path.exists() and not args.force:
        logger.info(f"{full_md_path.name} exists — skipping Docling (use --force to re-run).")
        full_text = full_md_path.read_text(encoding="utf-8")
    else:
        if args.force and full_md_path.exists():
            logger.info("--force: re-running Docling conversion.")

        logger.info(f"Running Docling on pages {page_from}–{page_to} ...")
        # Convert to 0-indexed for fitz/Docling
        raw_markdown = _run_docling_batches(
            doc, total_pages, args.batch_size,
            start_page=page_from - 1,
            end_page=page_to - 1,
        )

        # Save raw (unresolved) markdown for debugging
        raw_md_path.write_text(raw_markdown, encoding="utf-8")
        logger.info(f"Raw markdown saved → {raw_md_path}")

        # ── Step 2: PyMuPDF — extract images with bbox + manifest ─────────
        logger.info(f"Building image manifest (min_px={args.min_px}) for pages {page_from}–{page_to} ...")
        manifest = build_image_manifest(
            doc, img_dir,
            min_px=args.min_px,
            page_from=page_from,
            page_to=page_to,
        )

        # ── Step 3: Resolve `<!-- image -->` → `<!-- image: path -->` ──────
        logger.info("Resolving image placeholders ...")
        full_text = resolve_image_tags(raw_markdown, manifest)

        full_md_path.write_text(full_text, encoding="utf-8")
        logger.success(
            f"Resolved markdown saved → {full_md_path}\n"
            f"  Pages with images: {len(manifest)}"
        )

    # ── Step 4: Split into per-unit files (only for full exports) ─────────
    if partial:
        logger.info(
            "Partial export — skipping unit split.\n"
            f"  Inspect the output at: {full_md_path}"
        )
    else:
        logger.info("Splitting into units ...")
        units = split_into_units(full_text)
        for unit_num, unit_text in units.items():
            unit_path = export_dir / f"unit_{unit_num:02d}.txt"
            unit_path.write_text(unit_text, encoding="utf-8")
            logger.info(f"  Written: {unit_path.name}")
        logger.success(
            f"Export complete!\n"
            f"  Units:  {len(units)}\n"
            f"  Output: {export_dir}"
        )

    doc.close()


if __name__ == "__main__":
    main()
