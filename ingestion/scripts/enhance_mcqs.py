#!/usr/bin/env python
"""
Phase 2 — Enhance raw MCQs using Gemini API.

Reads: data/outputs/mcqs/<year>/<subject>/<book>/raw/topic_<N>.json
Writes: data/outputs/mcqs/<year>/<subject>/<book>/enhanced/topic_<N>.json

Usage:
    python scripts/enhance_mcqs.py --book physiology_mcqs --topic 1
    python scripts/enhance_mcqs.py --book physiology_mcqs --topic 1 --sub-topics path/to/sub_topics.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.mcqs.enhancer import enhance_unit
from src.mcqs.schemas import RawUnit
from src.core.config import OUTPUT_MCQ_DIR
from src.core.json_writer import read_json, write_json
from src.core.books import BOOK_METADATA
from src.core.logger import logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enhance raw MCQs via Gemini.")
    parser.add_argument("--book",  required=True, help="Book key from BOOK_METADATA (e.g. physiology_mcqs)")
    parser.add_argument("--topic", type=int, required=True)
    parser.add_argument(
        "--sub-topics",
        type=Path,
        default=None,
        help=(
            "Path to a JSON file mapping topic → [sub-topic list]. "
            "Defaults to <output_dir>/<book>/sub_topics.json if it exists."
        ),
    )
    return parser.parse_args()


def load_sub_topics(path: Path | None, book_dir: Path) -> dict[str, list[str]]:
    """Load sub-topics map from provided path or fall back to book-level default."""
    candidates = [path, book_dir / "sub_topics.json"]
    for candidate in candidates:
        if candidate and candidate.exists():
            data = read_json(candidate)
            logger.info(f"Loaded sub-topics from {candidate}")
            return data
    logger.warning(
        "No sub_topics.json found. Gemini will infer sub-topics from context only."
    )
    return {}


def main() -> None:
    args = parse_args()

    meta = BOOK_METADATA.get(args.book)
    if not meta:
        logger.error(f"Unknown book key: '{args.book}'.")
        sys.exit(1)

    book_dir = OUTPUT_MCQ_DIR / meta["year"] / meta["subject"] / meta["display_name"]
    raw_path = book_dir / "raw" / f"topic_{args.topic:02d}.json"

    if not raw_path.exists():
        logger.error(
            f"Raw file not found: {raw_path}. "
            "Run parse_mcqs.py first."
        )
        sys.exit(1)

    logger.info(f"=== Phase 2: ENHANCE | {meta['display_name']} | Topic {args.topic} ===")

    # Load raw unit
    raw_data = read_json(raw_path)
    raw_unit = RawUnit.model_validate(raw_data)
    logger.info(f"Loaded {len(raw_unit.mcqs)} raw MCQs")

    # Load sub-topics map
    sub_topics_map = load_sub_topics(args.sub_topics, book_dir)

    # Enhance
    enhanced_unit = enhance_unit(raw_unit, sub_topics_map)

    # Write output
    out_path = book_dir / "enhanced" / f"topic_{args.topic:02d}.json"
    write_json(enhanced_unit.model_dump(), out_path)
    logger.success(f"Done — {len(enhanced_unit.mcqs)} enhanced MCQs written to {out_path}")


if __name__ == "__main__":
    main()
