"""Book-specific parser for MCQs in Biochemistry - G. Vidya Sagar.

Output schema mirrors `parse_mcq_book.py` (KLM style) so the frontend can
consume both books identically.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data"
PUBLIC_BOOKS = ROOT / "public" / "books"

LIGATURES = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
    "–": "-", "“": '"', "”": '"', "‘": "'", "’": "'",
}

# --- Regexes ----------------------------------------------------------------
RE_CHAPTER_LINE = re.compile(r"^\s*chapter\s+(\d+)\b[:\-.\s]*(.*)$", re.I)
RE_QNUM_STANDALONE = re.compile(r"^(\d{1,3})\.\s*$")
RE_QNUM_INLINE = re.compile(r"^(\d{1,3})\.\s+(.+)$")
RE_OPTION_HEAD = re.compile(r"^\(([A-Ea-e])\)\s*(.*)$")
RE_EMBEDDED_OPT = re.compile(r"\s\(([A-Ea-e])\)\s*")
RE_ANSWERS_HEADER = re.compile(r"^\s*answers\s*$", re.I)
RE_ANSWER_PAIR = re.compile(r"(\d{1,3})\s*\.\s*([A-Ea-e])\b")
RE_ONLY_DIGIT = re.compile(r"^\s*\d{1,4}\s*$")
RE_DOT_ONLY = re.compile(r"^\s*\.\s*$")
RE_BLANK_PLACEHOLDER = re.compile(r"^\s*(this\s+page|intentionally\s+left|blank)\s*$", re.I)
RE_RUNNING_HEADER_WITH_PAGE = re.compile(r"^([A-Z][A-Z0-9 &\-,'/()]{4,})\s+\d{1,3}\s*$")
RE_RUNNING_HEADER = re.compile(r"^[A-Z][A-Z0-9 &\-,'/()]{4,}$")

BOOK_HEADER_BLACKLIST = {
    "MCQS IN BIOCHEMISTRY",
    "CONTENTS",
    "PREFACE",
    "INDEX",
    "EXPLANATIONS FOR THE ANSWERS",
    "ANSWERS",
    "FOREWORD",
    "ACKNOWLEDGEMENTS",
    "ACKNOWLEDGMENTS",
}


# --- Data classes -----------------------------------------------------------
@dataclass
class Line:
    text: str
    page: int
    bbox: Tuple[float, float, float, float]
    column: int = 0


@dataclass
class QuestionRec:
    qnum: int
    question: str = ""
    options: List[Dict[str, str]] = field(default_factory=list)
    page: int = 0
    bbox: Optional[Tuple[float, float, float, float]] = None


@dataclass
class Segment:
    questions: List[QuestionRec] = field(default_factory=list)
    answers: Dict[int, str] = field(default_factory=dict)
    pages: List[int] = field(default_factory=list)


# --- Utilities --------------------------------------------------------------
def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return s


def join_wrapped(buf: str, nxt: str) -> str:
    buf = buf.rstrip()
    if not buf:
        return nxt.lstrip()
    if buf.endswith("-") and nxt and nxt[0].islower():
        return buf[:-1] + nxt.lstrip()
    return buf + " " + nxt.lstrip()


def _detect_header_on_page(page_text: str) -> Optional[str]:
    if not page_text:
        return None
    lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
    for ln in lines[:4]:
        if RE_CHAPTER_LINE.match(ln):
            continue
        m = RE_RUNNING_HEADER_WITH_PAGE.match(ln)
        if m:
            cand = m.group(1).strip()
            if cand.upper() in BOOK_HEADER_BLACKLIST:
                continue
            if cand == cand.upper() and sum(1 for c in cand if c.isalpha()) >= 5:
                return cand.upper()
        if ln.upper() in BOOK_HEADER_BLACKLIST:
            continue
        if RE_RUNNING_HEADER.match(ln) and ln == ln.upper():
            letters = sum(1 for c in ln if c.isalpha())
            if letters >= 5:
                return ln.upper()
    return None


# --- Page extraction --------------------------------------------------------
def extract_page_lines(page: "fitz.Page") -> List[Line]:
    page_w = page.rect.width
    d = page.get_text("dict")

    raw: List[Dict[str, Any]] = []
    for block in d.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for ln in block.get("lines", []):
            spans = ln.get("spans", [])
            if not spans:
                continue
            text = normalize_text("".join(s.get("text", "") for s in spans).strip())
            if not text:
                continue
            if RE_ONLY_DIGIT.match(text) and len(text.strip()) <= 3:
                continue
            if RE_DOT_ONLY.match(text):
                continue
            bbox = ln.get("bbox", [0, 0, 0, 0])
            raw.append({"text": text, "bbox": (bbox[0], bbox[1], bbox[2], bbox[3])})

    if not raw:
        return []

    xs = [r["bbox"][0] for r in raw]
    mid_x = page_w / 2.0
    left_count = sum(1 for x in xs if x < mid_x - 20)
    right_count = sum(1 for x in xs if x > mid_x + 5)
    two_col = left_count >= 3 and right_count >= 3

    if two_col:
        left_xs = sorted(x for x in xs if x < mid_x)
        right_xs = sorted(x for x in xs if x >= mid_x)
        split_x = (max(left_xs) + min(right_xs)) / 2.0 if left_xs and right_xs else mid_x
        for r in raw:
            r["column"] = 0 if r["bbox"][0] < split_x else 1
    else:
        for r in raw:
            r["column"] = 0

    raw.sort(key=lambda r: (r["column"], round(r["bbox"][3] / 3.0), r["bbox"][0]))
    return [Line(text=r["text"], page=page.number + 1, bbox=r["bbox"], column=r["column"]) for r in raw]


# --- Option splitting -------------------------------------------------------
def _split_and_append_options(rec: QuestionRec, letter: str, text: str) -> None:
    """Append (letter, text), splitting further embedded '(X)' markers."""
    rec.options.append({"key": letter.upper(), "text": ""})
    remaining = text
    while True:
        m = RE_EMBEDDED_OPT.search(remaining)
        if not m:
            rec.options[-1]["text"] = remaining.strip()
            break
        rec.options[-1]["text"] = remaining[: m.start()].strip()
        next_letter = m.group(1).upper()
        remaining = remaining[m.end():]
        rec.options.append({"key": next_letter, "text": ""})


def _append_to_last_option(rec: QuestionRec, text: str) -> None:
    if not rec.options:
        return
    last = rec.options[-1]
    combined = join_wrapped(last["text"], text)
    m = RE_EMBEDDED_OPT.search(combined)
    if not m:
        last["text"] = combined
        return
    last["text"] = combined[: m.start()].strip()
    remaining = combined[m.end():]
    next_letter_match = re.match(r".*", "")
    # Re-split remainder
    next_letter = combined[m.start() + 2]
    _split_and_append_options(rec, next_letter, remaining)


# --- Flat chapter-splitting parser ------------------------------------------
def _is_answer_pair_line(s: str) -> bool:
    """True if a line is almost entirely composed of '<num>. <A-E>' pairs."""
    pairs = RE_ANSWER_PAIR.findall(s)
    if not pairs:
        return False
    remainder = RE_ANSWER_PAIR.sub(" ", s).strip()
    return len(remainder) <= max(3, len(s) // 6)


def parse_flat(lines: List[Line]) -> List[Segment]:
    """Walk the entire book line stream and split into chapter segments.

    A segment ends when we see an ANSWERS header, collect its answer pairs,
    and then encounter the start of a new question run (qnum=1 or a reset).
    """
    segments: List[Segment] = []
    cur = Segment()
    cur_q: Optional[QuestionRec] = None
    mode: Any = None  # "question" | ("option", idx) | None
    in_answers = False

    def flush_q() -> None:
        nonlocal cur_q
        if cur_q is None:
            return
        cur_q.question = cur_q.question.strip()
        for o in cur_q.options:
            o["text"] = o["text"].strip()
        if cur_q.question or cur_q.options:
            cur.questions.append(cur_q)
        cur_q = None

    def start_new_segment() -> None:
        nonlocal cur, cur_q, mode, in_answers
        flush_q()
        if cur.questions or cur.answers:
            segments.append(cur)
        cur = Segment()
        cur_q = None
        mode = None
        in_answers = False

    for ln in lines:
        s = ln.text.strip()
        if not s:
            continue
        if RE_BLANK_PLACEHOLDER.match(s):
            continue
        if s.upper() in BOOK_HEADER_BLACKLIST and not RE_ANSWERS_HEADER.match(s):
            continue
        # Running header like "INTRODUCTION TO BIOCHEMISTRY 3"
        if RE_RUNNING_HEADER_WITH_PAGE.match(s):
            continue
        # Running header like "INTRODUCTION TO BIOCHEMISTRY" (plain ALL CAPS)
        if (RE_RUNNING_HEADER.match(s) and s == s.upper()
                and sum(1 for c in s if c.isalpha()) >= 5
                and not RE_QNUM_INLINE.match(s)
                and not RE_OPTION_HEAD.match(s)
                and s.upper() not in {"ANSWERS"}):
            continue
        # Chapter heading lines ("CHAPTER 2", "CHAPTER 2 CHAPTER 2", etc.)
        if RE_CHAPTER_LINE.match(s):
            continue

        if ln.page not in cur.pages:
            cur.pages.append(ln.page)

        # ANSWERS header → enter answers collection mode for this segment
        if RE_ANSWERS_HEADER.match(s):
            flush_q()
            in_answers = True
            continue

        if in_answers:
            if _is_answer_pair_line(s):
                for qn, ans in RE_ANSWER_PAIR.findall(s):
                    cur.answers[int(qn)] = ans.upper()
                continue
            # Non-answer content after ANSWERS → next chapter begins here.
            start_new_segment()
            # Fall through; process this line in new segment.

        # Question markers
        m = RE_QNUM_STANDALONE.match(s)
        if m:
            qn = int(m.group(1))
            if qn == 1 and (cur.questions or cur.answers):
                start_new_segment()
            flush_q()
            cur_q = QuestionRec(qnum=qn, page=ln.page, bbox=ln.bbox)
            mode = "question"
            continue

        m = RE_QNUM_INLINE.match(s)
        if m:
            qn = int(m.group(1))
            q_text = m.group(2).strip()
            # Detect qnum-1 reset that actually begins a new chapter.
            if qn == 1 and (cur.questions or cur.answers):
                start_new_segment()
            flush_q()
            cur_q = QuestionRec(qnum=qn, page=ln.page, bbox=ln.bbox)
            cur_q.question = q_text
            mode = "question"
            continue

        # Option head
        m = RE_OPTION_HEAD.match(s)
        if m and cur_q is not None:
            letter = m.group(1).upper()
            text = m.group(2).strip()
            _split_and_append_options(cur_q, letter, text)
            mode = ("option", len(cur_q.options) - 1)
            continue

        if cur_q is None:
            # Stray text before first question; ignore.
            continue

        if mode == "question":
            cur_q.question = join_wrapped(cur_q.question, s)
        elif isinstance(mode, tuple) and mode[0] == "option":
            _append_to_last_option(cur_q, s)
        else:
            cur_q.question = join_wrapped(cur_q.question, s)

    flush_q()
    if cur.questions or cur.answers:
        segments.append(cur)

    # Deduplicate per segment by qnum (keep richest)
    for seg in segments:
        by_num: Dict[int, QuestionRec] = {}
        for q in seg.questions:
            key = q.qnum
            if key not in by_num or (
                len(q.question) + sum(len(o["text"]) for o in q.options)
                > len(by_num[key].question) + sum(len(o["text"]) for o in by_num[key].options)
            ):
                by_num[key] = q
        seg.questions = sorted(by_num.values(), key=lambda q: q.qnum)

    return segments


# --- Chapter titling --------------------------------------------------------
def pick_chapter_title(pages: List[int], page_headers: Dict[int, str], order: int) -> str:
    headers = [page_headers[p] for p in pages if p in page_headers]
    if not headers:
        return f"Chapter {order}"
    counts: Dict[str, int] = {}
    for h in headers:
        counts[h] = counts.get(h, 0) + 1
    top = max(counts.items(), key=lambda kv: kv[1])[0]
    return top.title().strip()


# --- Driver -----------------------------------------------------------------
def parse_book(pdf_path: Path, book_id: str, book_title: str) -> None:
    out_dir = DATA_DIR / book_id
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[biochem] opening {pdf_path}")
    with fitz.open(str(pdf_path)) as doc:
        # Detect first real chapter page (contains "CHAPTER 1" drop-cap)
        first_chapter_page = 1
        for p in range(doc.page_count):
            text = normalize_text(doc[p].get_text("text") or "")
            if re.search(r"(?im)^\s*chapter\s+1\b", text):
                first_chapter_page = p + 1
                break

        # Collect running header per page for chapter titling.
        page_headers: Dict[int, str] = {}
        for p in range(doc.page_count):
            text = normalize_text(doc[p].get_text("text") or "")
            h = _detect_header_on_page(text)
            if h:
                page_headers[p + 1] = h

        # Flatten all lines from the first chapter onward.
        all_lines: List[Line] = []
        for p in range(first_chapter_page - 1, doc.page_count):
            all_lines.extend(extract_page_lines(doc[p]))

        segments = parse_flat(all_lines)
        print(f"[biochem] parsed {len(segments)} chapter segments "
              f"(from page {first_chapter_page})")

        chapters_summary: List[Dict[str, Any]] = []
        total_q = total_ans = 0

        for idx, seg in enumerate(segments, start=1):
            order = idx
            start_page = seg.pages[0] if seg.pages else first_chapter_page
            title_core = pick_chapter_title(seg.pages, page_headers, order)
            chap_title = f"{order}. {title_core}"
            total_q += len(seg.questions)
            total_ans += len(seg.answers)

            section_id = f"ch_{order}_s1"
            blocks: List[Dict[str, Any]] = [
                {
                    "type": "heading",
                    "level": 1,
                    "text": chap_title,
                    "source": "mcq-parser",
                    "page": start_page,
                    "id": f"{section_id}_b0",
                    "confidence": 1.0,
                    "needs_review": False,
                }
            ]

            for q in seg.questions:
                blocks.append({
                    "type": "mcq",
                    "id": f"{section_id}_q{q.qnum}",
                    "qnum": q.qnum,
                    "question": q.question,
                    "options": q.options,
                    "answer": seg.answers.get(q.qnum),
                    "explanation": "",
                    "page": q.page,
                    "bbox": list(q.bbox) if q.bbox else None,
                    "kind": "standard",
                    "source": "mcq-parser",
                    "confidence": 0.85,
                    "needs_review": not bool(seg.answers.get(q.qnum)) or len(q.options) < 4,
                })

            chapter_json = {
                "metadata": {
                    "book_id": book_id,
                    "book_title": book_title,
                    "chapter_id": f"ch_{order}",
                    "chapter_title": chap_title,
                    "chapter_order": order,
                },
                "chapter": {
                    "id": f"ch_{order}",
                    "title": chap_title,
                    "order": order,
                    "page": start_page,
                    "sections": [{
                        "id": section_id,
                        "title": chap_title,
                        "order": 1,
                        "blocks": blocks,
                    }],
                },
            }

            ch_file = out_dir / f"ch_{order}.json"
            ch_file.write_text(json.dumps(chapter_json, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"   ch{order} '{chap_title}': questions={len(seg.questions)} answers={len(seg.answers)} pages={len(seg.pages)}")

            chapters_summary.append(chapter_json["chapter"])

        main_json = {
            "metadata": {
                "book_id": book_id,
                "book_title": book_title,
                "total_chapters": len(chapters_summary),
                "total_pages": doc.page_count,
                "source": "mcq-parser",
            },
            "toc": [
                {"id": c["id"], "title": c["title"], "order": c["order"], "page": c["page"]}
                for c in chapters_summary
            ],
            "chapters": chapters_summary,
        }
        main_path = out_dir / "main.json"
        main_path.write_text(json.dumps(main_json, ensure_ascii=False, indent=2), encoding="utf-8")

        print("\n[biochem] ===== SUMMARY =====")
        print(f"chapters={len(chapters_summary)} questions={total_q} answers={total_ans}")
        print(f"[biochem] wrote {main_path}")

    PUBLIC_BOOKS.mkdir(parents=True, exist_ok=True)
    dst = PUBLIC_BOOKS / pdf_path.name
    if not dst.exists() or dst.stat().st_size != pdf_path.stat().st_size:
        shutil.copy2(pdf_path, dst)
        print(f"[biochem] copied PDF -> {dst}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse G. Vidya Sagar biochemistry MCQ PDF into app JSON.")
    ap.add_argument("--pdf", required=True, help="Path to PDF")
    ap.add_argument("--book-id", required=True, help="Slug under public/data/<book-id>/")
    ap.add_argument("--title", required=True, help="Book title")
    args = ap.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)

    parse_book(pdf_path=pdf_path, book_id=args.book_id, book_title=args.title)


if __name__ == "__main__":
    main()
