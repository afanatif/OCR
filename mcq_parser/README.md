# KLM Anatomy MCQs — Standalone Viewer

Portable copy containing the parsed KLM Anatomy MCQs book, the viewer frontend,
and the Python parser that generated the JSON. Copy this folder anywhere and it
works self-contained.

## Folder layout

```
klm_mcq_app/
├── mcqbook/                       Source PDF (input for the parser)
│   └── Klm Anatomy Mcqs.pdf
├── parser/                        Python parser
│   └── parse_mcq_book.py
├── public/
│   ├── books/Klm Anatomy Mcqs.pdf Served to the viewer (right-side PDF pane)
│   └── data/
│       ├── index.json             Library index (lists this one book)
│       └── klm_anatomy_mcqs/
│           ├── main.json          Metadata + TOC + all chapters
│           ├── ch_1.json … ch_7.json
│           ├── _report.json       Parser diagnostics
│           └── assets/            Extracted figures (fig_pNNN_xXX.png)
├── src/                           React app source
├── index.html
├── vite.config.js
├── package.json
└── requirements.txt
```

## Quick start

### 1. Run the viewer (uses the pre-generated JSON)

Requires Node.js 18+.

```powershell
cd klm_mcq_app
npm install
npm run dev
```

Then open http://localhost:5173/ — the library will show "KLM Anatomy MCQs"; click it
to browse all 795 questions with attached figures.

### 2. (Optional) Re-run the parser

Requires Python 3.9+.

```powershell
cd klm_mcq_app
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

python parser\parse_mcq_book.py `
  --pdf "mcqbook\Klm Anatomy Mcqs.pdf" `
  --book-id klm_anatomy_mcqs `
  --title "KLM Anatomy MCQs"
```

Output is written to `public/data/klm_anatomy_mcqs/` (overwriting the shipped
JSON + figure assets). On Linux/macOS use `source venv/bin/activate` and
forward-slash paths.

## What the JSON contains

Each `ch_N.json` / the combined `main.json` contains one section with a stream
of blocks:

- `heading` — chapter title.
- `paragraph` — `DIRECTIONS (Questions X through Y): …` lines, emitted in-place
  before the sub-questions they govern.
- `mcq` — one per MCQ, with:
  - `qnum`, `question`, `options` (key + text), `answer`, `explanation`
  - `kind` — `"standard"` (lettered A–E options) or `"image"` (identify-the-
    structure sub-question; `answer` holds the label text)
  - `page`, `bbox`, `set_id` (e.g. `set_84_88`), `synthetic` (true for
    auto-generated image placeholders)
  - `images` — array of figure objects `{src, page, bbox}` attached to that
    question via page + y-band matching

## Re-parsing other Appleton & Lange-style MCQ books

The parser auto-detects chapters from the table of contents, DIRECTIONS blocks,
multi-column layout, and image sets. To try another book, drop the PDF into
`mcqbook/`, add an entry to `public/data/index.json`, and run with
`--book-id <slug>` matching that entry.

## Stats for this book

- 7 chapters, 795 MCQs (Qs 1 through the image-set tails in each chapter)
- 643 standard-MCQ answers + 152 image-label answers
- 28 figure files extracted and attached to the matching sub-questions
- 0 questions missing options, 0 missing answers
