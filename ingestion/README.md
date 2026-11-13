# med-ingestion

A modular data ingestion pipeline for MBBS practice platform. Handles MCQ extraction from PDFs and AI-powered enhancement via Gemini.

## Structure

```
 med-ingestion/
 ├── data/
 │   ├── mcqs/                  # Input PDFs organized by year/subject
 │   │   └── year_1/Physiology/Physiology MCQs Book.pdf
 │   ├── outputs/               # Pipeline results (logs, raw JSONs, exports)
 │   │   └── mcqs/year_1/Physiology/physiology_mcqs/
 │   │       ├── logs/          # Topic-specific execution logs
 │   │       ├── raw/           # Parsed JSON files (Phase 1)
 │   │       ├── export/        # Cleaned Markdown/Text exports
 │   │       └── toc.json       # Table of contents for the book
 │   └── books/                 # Raw PDFs/JSONs for book parsing (WIP)
 │
 ├── src/
 │   ├── mcqs/                  # All MCQ-specific logic
 │   │   ├── pdf_reader.py      # Docling (primary) + PyMuPDF + pdfplumber (fallback)
 │   │   ├── parser.py          # Extract questions, options, answers, short explanation
 │   │   ├── matcher.py         # Match question ↔ answer by number
 │   │   ├── cleaner.py         # Fix OCR noise, normalize text
 │   │   ├── validator.py       # Verify structure completeness
 │   │   └── enhancer.py        # Gemini: subtopic mapping + detailed explanation + difficulty
 │   │
 ├── schemas/
 │   ├── mcq_raw.schema.json    # JSON Schema for raw MCQ output
 │   └── mcq_enhanced.schema.json
 │
 ├── scripts/
 │   ├── parse_mcqs.py          # python scripts/parse_mcqs.py --book physiology_mcqs --topic 1
 │   ├── enhance_mcqs.py        # python scripts/enhance_mcqs.py --book physiology_mcqs --topic 1
 │   └── generate_viewer.py     # python scripts/generate_viewer.py 1
 │
 ├── .env.example
 ├── requirements.txt
 └── README.md
 ```
 
 ## Setup
 
 ```bash
 python -m venv .venv
 .venv\Scripts\activate        # Windows
 pip install -r requirements.txt
 cp .env.example .env          # Fill in your GEMINI_API_KEY
 ```
 
 ## Usage
 
 ### Phase 1 — Parse
 
 ```bash
 python scripts/parse_mcqs.py --book physiology_mcqs --topic 1
 # Output: data/outputs/mcqs/year_1/Physiology/physiology_mcqs/raw/topic_01.json
 ```
 
 ### Phase 2 — Enhance
 
 ```bash
 python scripts/enhance_mcqs.py --book physiology_mcqs --topic 1
 # Output: data/outputs/mcqs/year_1/Physiology/physiology_mcqs/enhanced/topic_01.json
 ```
