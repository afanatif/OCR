#!/usr/bin/env python
"""
Phase 1 — Parse MCQs from a PDF.

Usage:
    python scripts/parse_mcqs.py --book physiology_mcqs --topic 1

Output:
    data/outputs/mcqs/<year>/<subject>/<book>/raw/topic_<N>.json
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mcqs.pdf_reader import read_pdf
from src.mcqs.cleaner import clean_pages
from src.mcqs.parser import split_into_units, parse_mcq_block, parse_answer_block
from src.mcqs.matcher import match
from src.mcqs.validator import validate
from src.mcqs.schemas import RawUnit
from src.core.config import INPUT_MCQ_DIR, OUTPUT_MCQ_DIR
from src.core.json_writer import write_json
from src.core.books import BOOK_METADATA
from src.core.logger import logger

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse MCQs from a PDF or exported text.")
    parser.add_argument("--book",  required=True, help="Book key from BOOK_METADATA (e.g. physiology_mcqs)")
    parser.add_argument("--topic", type=int, required=True, help="Topic/unit number to parse")
    parser.add_argument("--file",  type=str, help="Optional: specific text file to parse (e.g. full_text_p1-35.txt)")
    parser.add_argument(
        "--allow-incomplete", action="store_true",
        help="Write output even if validation finds issues",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    meta = BOOK_METADATA.get(args.book)
    if not meta:
        logger.error(f"Unknown book key: '{args.book}'. Add it to BOOK_METADATA.")
        sys.exit(1)

    # ── Step 0: Set up Log File ───────────────────────────────────────────
    log_dir = (
        OUTPUT_MCQ_DIR
        / meta["year"]
        / meta["subject"]
        / meta["display_name"]
        / "logs"
    )
    log_dir.mkdir(parents=True, exist_ok=True)
    log_filename = f"{args.book}_topic_{args.topic:02d}.log"
    log_path = log_dir / log_filename
    
    # We add a new sink, keep the terminal one (which is default in src.core.logger)
    logger.add(log_path, rotation="1 MB", encoding="utf-8", level="DEBUG")
    
    logger.info(f"=== Phase 1: PARSE | {meta['display_name']} | Topic {args.topic} ===")
    logger.info(f"Logging to: {log_path}")

    # ── Step 1 & 2: Get Unit Text ──────────────────────────────────────────
    if args.file:
        source_path = Path(args.file)
        if not source_path.exists():
            logger.error(f"Source file not found: {source_path}")
            sys.exit(1)
        logger.info(f"Parsing topic {args.topic} from file: {source_path.name}")
        full_text = source_path.read_text(encoding="utf-8")
        units = split_into_units(full_text)
        unit_text = units.get(args.topic)
    else:
        export_dir = OUTPUT_MCQ_DIR / meta["year"] / meta["subject"] / meta["display_name"] / "export"
        unit_export_path = export_dir / f"unit_{args.topic:02d}.txt"

        if unit_export_path.exists():
            logger.info(f"Using pre-exported unit text from: {unit_export_path}")
            unit_text = unit_export_path.read_text(encoding="utf-8")
        else:
            pdf_path = INPUT_MCQ_DIR / meta["year"] / meta["subject"] / meta["filename"]
            if not pdf_path.exists():
                logger.error(f"PDF not found: {pdf_path}")
                sys.exit(1)
            logger.info(f"Pre-exported file not found. Extracting from PDF: {pdf_path}")
            pages = read_pdf(pdf_path)
            pages = clean_pages(pages)
            full_text = "\n".join(p.text for p in pages)
            units = split_into_units(full_text)
            unit_text = units.get(args.topic)

    if not unit_text:
        logger.error(f"Could not find unit {args.topic} in the source.")
        sys.exit(1)

    # ── Step 4: Resolve TOC ──────────────────────────────────────────────────
    hardcoded_toc = meta.get("toc", {})
    unit_title = hardcoded_toc.get(args.topic)

    # Also save toc.json once
    toc_dir  = OUTPUT_MCQ_DIR / meta["year"] / meta["subject"] / meta["display_name"]
    toc_path = toc_dir / "toc.json"
    write_json(
        [{"unit_number": k, "unit_title": v} for k, v in sorted(hardcoded_toc.items())],
        toc_path,
    )

    if unit_title:
        logger.info(f"Topic {args.topic} → '{unit_title}'")

    # ── Step 6: Parse MCQ block and Answer block ────────────────────────────
    questions = parse_mcq_block(unit_text)
    answers   = parse_answer_block(unit_text)

    # ── Step 7: Match questions ↔ answers ───────────────────────────────────
    raw_mcqs = match(questions, answers, unit_title=unit_title)

    # ── Step 8: Validate ────────────────────────────────────────────────────
    report = validate(raw_mcqs)
    if not report.is_clean and not args.allow_incomplete:
        logger.error(f"Validation failed. Use --allow-incomplete to write anyway.")
        sys.exit(1)

    # ── Step 9: Write output ────────────────────────────────────────────────
    unit = RawUnit(
        book=meta["display_name"],
        subject=meta["subject"],
        unit_number=args.topic,
        unit_title=unit_title,
        mcqs=raw_mcqs,
    )

    out_path = (
        OUTPUT_MCQ_DIR
        / meta["year"]
        / meta["subject"]
        / meta["display_name"]
        / "raw"
        / f"topic_{args.topic:02d}.json"
    )
    write_json(unit.model_dump(), out_path)
    logger.success(f"Done — {len(raw_mcqs)} MCQs written to {out_path}")
    logger.success(f"Done — {len(raw_mcqs)} MCQs written to {out_path}")


if __name__ == "__main__":
    main()
