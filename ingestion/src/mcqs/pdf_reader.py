"""
PDF reader for MCQ PDFs.

Strategy (in order of preference, configured via PDF_READER_PREFERENCE):
  1. Docling  — best for complex layouts, tables, images, multi-column text
  2. PyMuPDF  — fast, good for clean text-based PDFs
  3. pdfplumber — good fallback, strong table detection

Returns a list of `PageResult` objects, one per page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.core.config import PDF_READER_PREFERENCE
from src.core.logger import logger


@dataclass
class PageResult:
    page_number: int          # 1-indexed
    text: str                 # Extracted plain text
    tables: list[list[list[str]]] = field(default_factory=list)  # [table][row][cell]
    has_images: bool = False
    reader_used: str = ""


def read_pdf(pdf_path: Path) -> list[PageResult]:
    """
    Extract all pages from `pdf_path` using the preferred reader.
    Falls back to the next reader if the preferred one fails or is unavailable.
    """
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    for reader_name in PDF_READER_PREFERENCE:
        try:
            logger.info(f"Trying reader: {reader_name} for {pdf_path.name}")
            if reader_name == "docling":
                return _read_with_docling(pdf_path)
            elif reader_name == "pymupdf":
                return _read_with_pymupdf(pdf_path)
            elif reader_name == "pdfplumber":
                return _read_with_pdfplumber(pdf_path)
        except ImportError:
            logger.warning(f"{reader_name} not installed, falling back...")
        except Exception as e:
            logger.warning(f"{reader_name} failed ({e}), falling back...")

    raise RuntimeError(f"All PDF readers failed for: {pdf_path}")


# ── Reader implementations ─────────────────────────────────────────────────

def _read_with_docling(pdf_path: Path) -> list[PageResult]:
    from docling.document_converter import DocumentConverter

    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    doc = result.document

    pages: list[PageResult] = []
    # Docling groups content by page; we export markdown per page
    for page_no, page in enumerate(doc.pages, start=1):
        text = page.export_to_markdown() if hasattr(page, "export_to_markdown") else ""
        pages.append(PageResult(
            page_number=page_no,
            text=text,
            reader_used="docling",
        ))

    logger.success(f"Docling extracted {len(pages)} pages from {pdf_path.name}")
    return pages


def _read_with_pymupdf(pdf_path: Path) -> list[PageResult]:
    import fitz  # PyMuPDF

    doc = fitz.open(str(pdf_path))
    pages: list[PageResult] = []

    for page in doc:
        text = page.get_text("text")
        image_list = page.get_images()
        pages.append(PageResult(
            page_number=page.number + 1,
            text=text,
            has_images=len(image_list) > 0,
            reader_used="pymupdf",
        ))

    doc.close()
    logger.success(f"PyMuPDF extracted {len(pages)} pages from {pdf_path.name}")
    return pages


def _read_with_pdfplumber(pdf_path: Path) -> list[PageResult]:
    import pdfplumber

    pages: list[PageResult] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            raw_tables = page.extract_tables() or []
            # Normalize tables: cells may be None
            tables = [
                [[cell or "" for cell in row] for row in table]
                for table in raw_tables
            ]
            pages.append(PageResult(
                page_number=i + 1,
                text=text,
                tables=tables,
                reader_used="pdfplumber",
            ))

    logger.success(f"pdfplumber extracted {len(pages)} pages from {pdf_path.name}")
    return pages
