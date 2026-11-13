"""
Core configuration — loads .env and exposes paths + constants.
All path resolution is centralized here so every module imports from one place.

Directory layout on disk:
  data/
    books/      ← book PDFs (partner's input)
    mcqs/       ← MCQ PDFs (our input)
    outputs/
      books/    ← partner's parsed book JSONs
      mcqs/
        <subject>/<book>/
          raw/        ← Phase 1 output
          enhanced/   ← Phase 2 output
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Root paths ─────────────────────────────────────────────────────────────
ROOT_DIR    = Path(__file__).resolve().parents[2]  # med-ingestion/
DATA_DIR    = ROOT_DIR / "data"
SCHEMAS_DIR = ROOT_DIR / "schemas"

# ── Input paths ────────────────────────────────────────────────────────────
INPUT_MCQ_DIR  = DATA_DIR / "mcqs"
INPUT_BOOK_DIR = DATA_DIR / "books"

# ── Output paths ───────────────────────────────────────────────────────────
OUTPUT_DIR      = DATA_DIR / "outputs"
OUTPUT_MCQ_DIR  = OUTPUT_DIR / "mcqs"
OUTPUT_BOOK_DIR = OUTPUT_DIR / "books"

# ── API keys ───────────────────────────────────────────────────────────────
GEMINI_API_KEY: str = os.environ.get("GEMINI_API_KEY", "")

# ── Gemini model ───────────────────────────────────────────────────────────
GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")

# ── PDF reader preference order ────────────────────────────────────────────
# Options: "docling" | "pymupdf" | "pdfplumber"
PDF_READER_PREFERENCE: list[str] = ["docling", "pymupdf", "pdfplumber"]
