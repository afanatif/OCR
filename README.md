# MCQ Book OCR & Ingestion

Turn scanned or digital **MCQ / textbook PDFs into clean, structured JSON**, where every block (heading, paragraph, question, figure) keeps its **page number, bounding box, source, confidence and a `needs_review` flag**. Then browse the result in a side-by-side viewer next to the original PDF.

Built for medical MCQ books (anatomy, physiology, biochemistry), with complex layouts: two columns, running headers, hyphenation, shared-option "matching" sets and image-based questions.

This repo has two parts:

| Folder | What it does |
|---|---|
| [`mcq_parser/`](mcq_parser) | **PDF → structured JSON parser + React viewer.** Layout-aware extraction with PyMuPDF: reading-order lines with bounding boxes, column detection, header/footer stripping, image extraction and attachment of figures to the right question. Produces per-chapter JSON plus a diagnostics report. |
| [`ingestion/`](ingestion) | **Modular ingestion pipeline:** Docling (layout/tables) with PyMuPDF and pdfplumber fallbacks, text cleaning, question↔answer matching, validation, and optional Gemini enhancement (sub-topics, explanations, difficulty). |

---

## Output format

Each chapter is a stream of blocks. A small real sample is in [`samples/sample_chapter.json`](samples/sample_chapter.json).

```jsonc
{
  "metadata": { "book_id": "klm_anatomy_mcqs", "chapter_id": "ch_1", "chapter_title": "1. The Back" },
  "chapter": { "id": "ch_1", "page": 8, "sections": [{ "id": "ch_1_s1", "blocks": [
    { "type": "heading",   "text": "1. The Back", "page": 8, "id": "ch_1_s1_b0",
      "source": "mcq-parser", "confidence": 1.0, "needs_review": false },
    { "type": "mcq", "id": "ch_1_s1_q1", "qnum": 1,
      "question": "…", "options": [{ "key": "A", "text": "…" }, …], "answer": "E", "explanation": "…",
      "page": 8, "bbox": [36.7, 271.2, 44.6, 281.7],          // PDF points: x0, y0, x1, y1
      "kind": "standard", "set_id": "set_1_40",
      "images": [{ "src": "/data/<book>/assets/fig_p013_x41.png", "page": 13, "bbox": [ … ] }],
      "source": "mcq-parser", "confidence": 0.85, "needs_review": false }
  ]}]}
}
```

- **`bbox`** gives the exact position on the page, so the viewer (or any tool) can highlight the source.
- **`images`** are figures extracted from the PDF and attached to the question they belong to, by page and vertical position.
- **`confidence` / `needs_review`** are lowered or set when something is incomplete (missing options or answer, or a "see figure" with no image). Nothing is silently dropped.
- **`kind`** is `standard` (A–E options), `matching` (options shared across a set) or `image` ("identify the labelled structure"; the answer is the label).
- **`_report.json`** gives per-chapter diagnostics: questions found, answers matched, orphans, missing options or images. See [`samples/sample_parser_report.json`](samples/sample_parser_report.json).

---

## Quick start

### 1. Parse a book → JSON (`mcq_parser`)
```bash
cd mcq_parser
python -m venv venv && venv\Scripts\activate          # macOS/Linux: source venv/bin/activate
pip install -r requirements.txt                       # PyMuPDF, Pillow
# put your PDF in mcqbook/ (no books are included: they are copyrighted)
python parser/parse_mcq_book.py --pdf "mcqbook/<your book>.pdf" --book-id my_book --title "My Book"
```
The output goes to `public/data/my_book/`: `main.json`, `ch_N.json`, `_report.json` and `assets/` (extracted figures).

### 2. Browse it next to the PDF (viewer)
```bash
npm install
# add an entry for your book to public/data/index.json, e.g.
# [{"id":"my_book","title":"My Book","dataPath":"/data/my_book/main.json","pdfPath":"/books/<your book>.pdf"}]
# and copy the PDF to public/books/
npm run dev        # http://localhost:5173
```
The viewer shows the table of contents, questions with their attached figures, search, highlights, notes and bookmarks, with the original PDF page alongside.

### 3. Ingestion pipeline (`ingestion`)
```bash
cd ingestion
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt                       # docling, pymupdf, pdfplumber, google-genai, pydantic, loguru
copy .env.example .env                                # add GEMINI_API_KEY only if you use enhancement
python scripts/export_book.py --book physiology_mcqs  # Phase 0: Docling markdown + image manifest
python scripts/parse_mcqs.py --book physiology_mcqs --topic 1     # Phase 1: parse
python scripts/enhance_mcqs.py --book physiology_mcqs --topic 1   # Phase 2: Gemini enhancement (optional)
```
Books are configured in `ingestion/src/core/books.py`. See [`ingestion/README.md`](ingestion/README.md) for details.

---

## How the parser handles hard layouts

- **Reading order:** PyMuPDF `dict` spans become lines with bounding boxes. Two-column pages are detected by splitting at the median x position. Lines are sorted by column, then baseline (3 pt rows), then x.
- **Noise removal:** running headers and footers ("3: The Thorax", page numbers, "Questions: 1–40") are removed only inside the top and bottom page bands, so real content is never lost.
- **Text repair:** ligatures, hyphenation across lines, smart quotes and zero-width characters are fixed.
- **Question structure:** a state machine handles `NN.` question starts, `(A)` options, DIRECTIONS segments, shared-option matching sets and image-only sub-questions (placeholders are created so answers and figures still attach).
- **Figures:** decorative images (too small, full-page or hairlines) are filtered out. Each remaining figure attaches to the closest question above it on the same page.
- **Recovery chain (ingestion):** Docling → PyMuPDF → pdfplumber. If one reader fails, the next is tried and the failure is logged.

---

## Repository layout
```
mcq_parser/
  parser/parse_mcq_book.py          main layout-aware parser (KLM / Appleton & Lange style books)
  parser/parse_biochemistry_mcq_book.py
  src/                              React 19 + Vite viewer (PDF pane via pdf.js, TOC, search, annotations)
  public/data/index.json            library index (empty: add your own parsed books)
ingestion/
  src/mcqs/                         pdf_reader, cleaner, parser, matcher, validator, image_mapper, enhancer
  src/core/                         config, books, gemini_client, logger, json writer
  scripts/                          export_book, parse_mcqs, enhance_mcqs, generate_viewer
  schemas/                          JSON Schemas for raw and enhanced MCQs
samples/                            small output samples (format only)
```

---

## What is *not* included, and why
The source books (and therefore their full text, questions, explanations and figures) are **copyrighted**, so no PDFs or full parsed chapters are in this repo. `samples/` contains only a few blocks to show the format. Bring your own PDF to reproduce the results.

## Credits and licences
- `ingestion/` is based on **med-ingestion** by **Muhammad Shariq Usman** ([@Shar1qq](https://github.com/Shar1qq), original repo: [Shar1qq/med-ingestion](https://github.com/Shar1qq/med-ingestion)), MIT-licensed. See [`ingestion/LICENSE`](ingestion/LICENSE).
- `mcq_parser/` uses PyMuPDF, Pillow, React, Vite and pdf.js.
- The layout-reading code from this project was later reused in **[CaseLens](https://github.com/afanatif/CaseLens)**, an evidence-first case-file assistant for legal aid.
