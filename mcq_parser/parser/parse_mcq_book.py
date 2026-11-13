"""
MCQ Book Parser — KLM Anatomy MCQs (and similar Appleton & Lange style)
----------------------------------------------------------------------
Produces structured JSON where each question is a single `mcq` block matching
the frontend schema in src/components/TextPanel.jsx:

    {type: "mcq", qnum, question, options:[{key,text}], answer, explanation,
     images:[{src,page,bbox}], page, bbox, id, source, confidence, needs_review}

Strategy
========
1. Use the PDF's TOC to split into chapters. Each chapter has a "Questions"
   region followed by an "Answers and Explanations" region.
2. For every page, rebuild two-column reading order from PyMuPDF "dict" spans
   (median-x column split + header/footer stripping + hyphenation fix +
   ligature normalization).
3. Stream lines through a state machine:
     - `NN.` on its own line opens a new question/answer
     - `(A) ...` opens an option (for questions) or the answer letter + start
       of explanation (for answers).
     - Non-marker lines append to the current option / question / explanation.
4. Pair Q# -> A# to merge answer+explanation into each mcq block.
5. Extract embedded raster images per page; attach to the MCQ whose bbox
   overlaps (or the nearest one above it).
6. Write per-chapter JSON + main.json (chapters[]) + _report.json.

CLI:
    python parser/parse_mcq_book.py \
        --pdf "mcqbook/Klm Anatomy Mcqs.pdf" \
        --book-id klm_anatomy_mcqs \
        --title "Klm Anatomy Mcqs"
"""
from __future__ import annotations

import argparse
import io
import json
import re
import shutil
import statistics
import sys
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import fitz  # PyMuPDF
from PIL import Image

# ── Windows console UTF-8 ────────────────────────────────────────────────────
try:
    sys.stdout.reconfigure(encoding="utf-8")  # py>=3.7
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "public" / "data"
PUBLIC_BOOKS = ROOT / "public" / "books"

# ── Regexes ───────────────────────────────────────────────────────────────────
RE_QNUM       = re.compile(r"^(\d{1,3})\.\s*$")           # "1." on own line
RE_QNUM_INL   = re.compile(r"^(\d{1,3})\.\s+(.+)$")       # "1. Question text"
RE_OPTION     = re.compile(r"^\(([A-Ea-e])\)\s*(.*)$")    # "(A) text"
RE_OPTION_ALT = re.compile(r"^([A-E])\.\s+(.*)$")          # "A. text" fallback
RE_ANSWER_H   = re.compile(r"^\s*Answers?\s+and\s+Explanations?\s*$", re.I)
RE_DIRECTIONS = re.compile(r"^\s*DIRECTIONS\b.*", re.I)
RE_ONLY_DIGIT = re.compile(r"^\s*\d{1,4}\s*$")
RE_DOT_ONLY   = re.compile(r"^\s*\.\s*$")
RE_EMBED_OPT  = re.compile(r"\s\(([A-E])\)\s")              # split run-together options

# Ligature / unicode fixups
LIGATURES = {"ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl",
             "—": "—", "–": "-", "“": "\"", "”": "\"", "‘": "'", "’": "'"}


def normalize_text(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    for k, v in LIGATURES.items():
        s = s.replace(k, v)
    return s


# ── Data classes ─────────────────────────────────────────────────────────────
@dataclass
class Line:
    text: str
    page: int           # 1-indexed
    bbox: Tuple[float, float, float, float]
    column: int = 0     # 0=left, 1=right


@dataclass
class QuestionRec:
    qnum: int
    question: str = ""
    options: List[Dict[str, str]] = field(default_factory=list)
    page: int = 0
    bbox: Optional[Tuple[float, float, float, float]] = None
    directions: Optional[str] = None
    set_options: Optional[List[Dict[str, str]]] = None
    set_id: Optional[str] = None
    kind: str = "standard"   # "standard" | "matching" | "image"
    synthetic: bool = False  # True if placeholder created for image-only sub-question
    needs_review: bool = False


@dataclass
class DirectionsSeg:
    """One DIRECTIONS block — covers a range of qnums, possibly image-based."""
    text: str
    qstart: Optional[int] = None
    qend: Optional[int] = None
    kind: str = "standard"   # "standard" | "matching" | "image"
    line_start: int = 0      # index into the full line stream (inclusive)
    line_end: int = 0        # exclusive
    pages: List[int] = field(default_factory=list)
    set_options: Optional[List[Dict[str, str]]] = None  # shared lettered options (matching)


@dataclass
class AnswerRec:
    qnum: int
    answer: Optional[str] = None
    explanation: str = ""


@dataclass
class Chapter:
    order: int          # 1-indexed (skipping front matter)
    title: str
    start_page: int     # 1-indexed PDF page (inclusive)
    end_page: int       # exclusive
    answers_page: int   # 1-indexed, start of Answers section (inside chapter)


# ── Page line extraction ─────────────────────────────────────────────────────
RE_RUNNING_HEADER = re.compile(r"^\d+\s*:\s+[A-Z]")        # e.g. "3: The Thorax"
RE_QUESTIONS_FOOT = re.compile(r"^Questions?:\s*\d+\s*[-–]\s*\d+\s*$")


def _is_margin_noise(text: str) -> bool:
    """True if a short line near a page edge is obvious running header/footer noise."""
    t = text.strip()
    if not t:
        return True
    if RE_ONLY_DIGIT.match(t) and len(t) <= 4:
        return True
    if RE_DOT_ONLY.match(t):
        return True
    if RE_RUNNING_HEADER.match(t):
        return True
    if RE_QUESTIONS_FOOT.match(t):
        return True
    # Chapter title repeats like "The Thorax" alone in the header strip
    if len(t.split()) <= 4 and t.istitle():
        return True
    return False


def extract_page_lines(page: "fitz.Page") -> List[Line]:
    """Return reading-order lines for a page (two-column aware, header/footer stripped)."""
    page_w = page.rect.width
    page_h = page.rect.height
    # Header/footer strips are content-aware: only remove noise lines near the
    # page edges, never real content (DIRECTIONS sometimes sits at y~27 because
    # the book uses its full margin).
    header_band = 45.0
    footer_band = page_h - 45.0

    d = page.get_text("dict")
    raw_lines: List[Dict[str, Any]] = []
    for block in d.get("blocks", []):
        if block.get("type", 0) != 0:
            continue
        for ln in block.get("lines", []):
            spans = ln.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            bbox = ln.get("bbox", [0, 0, 0, 0])
            x0, y0, x1, y1 = bbox
            in_header_band = y1 < header_band
            in_footer_band = y0 > footer_band
            if (in_header_band or in_footer_band) and _is_margin_noise(text):
                continue
            raw_lines.append({"text": text, "bbox": (x0, y0, x1, y1)})

    if not raw_lines:
        return []

    # Column detection: if there are two tight clusters of x0, we're two-column.
    xs = [r["bbox"][0] for r in raw_lines]
    mid_x = page_w / 2.0
    # Consider two-column layout if meaningful amount of lines on each side
    left_count = sum(1 for x in xs if x < mid_x - 20)
    right_count = sum(1 for x in xs if x > mid_x + 5)
    two_col = left_count >= 3 and right_count >= 3

    if two_col:
        # Refine split using gap between left and right column x0 clusters
        left_xs = sorted(x for x in xs if x < mid_x)
        right_xs = sorted(x for x in xs if x >= mid_x)
        if left_xs and right_xs:
            split_x = (max(left_xs) + min(right_xs)) / 2.0
        else:
            split_x = mid_x
        for r in raw_lines:
            r["column"] = 0 if r["bbox"][0] < split_x else 1
    else:
        for r in raw_lines:
            r["column"] = 0

    # Sort: column asc, then BASELINE (bbox y1) quantized to 3pt rows, then x asc.
    # Using y1 (bottom) keeps numeric labels like "1." on the same visual row as the
    # question text they hang-indent (which has a taller bbox → smaller y0).
    raw_lines.sort(key=lambda r: (r["column"], round(r["bbox"][3] / 3.0), r["bbox"][0]))

    out: List[Line] = []
    for r in raw_lines:
        text = normalize_text(r["text"])
        # Skip pure page-number lines and decorative dots
        if RE_ONLY_DIGIT.match(text) and len(text.strip()) <= 3:
            continue
        if RE_DOT_ONLY.match(text):
            continue
        # Skip the obvious "Questions: a-b" continuation footer
        if re.match(r"^Questions?:\s*\d+\s*[-–]\s*\d+\s*$", text):
            continue
        out.append(Line(text=text, page=page.number + 1, bbox=r["bbox"], column=r["column"]))
    return out


# ── Line joining (hyphenation) ───────────────────────────────────────────────
def join_wrapped(buf: str, nxt: str) -> str:
    """Append `nxt` to `buf` handling hyphenation & spacing."""
    buf = buf.rstrip()
    if not buf:
        return nxt.lstrip()
    if buf.endswith("-") and nxt and nxt[0].islower():
        return buf[:-1] + nxt.lstrip()
    # word-final em-dash or explicit hyphen with capitalized continuation: keep dash, add nothing
    return buf + " " + nxt.lstrip()


# ── Chapter detection from TOC ───────────────────────────────────────────────
def build_chapters(doc: "fitz.Document") -> List[Chapter]:
    toc = doc.get_toc()  # list of [level, title, page(1-indexed)]
    chapters: List[Chapter] = []
    # Find level-1 entries matching "N. Title" pattern (KLM numeric chapters)
    top_entries = []
    for i, (lvl, title, pg) in enumerate(toc):
        if lvl == 1 and re.match(r"^\d+\.\s+", title.strip()):
            # Find nested "Answers and Explanations"
            ans_pg = None
            for j in range(i + 1, len(toc)):
                lvl2, title2, pg2 = toc[j]
                if lvl2 <= 1:
                    break
                if re.search(r"answers?\s+and\s+explanations?", title2, re.I):
                    ans_pg = pg2
                    break
            top_entries.append({"idx": i, "lvl": lvl, "title": title.strip(),
                                "page": pg, "answers_page": ans_pg})
    # Determine end_page for each
    # End = start page of next numeric chapter, OR start of References/Index, OR doc end
    flat_breaks = [e["page"] for e in top_entries]
    # Also include non-chapter level-1 entries that come AFTER the last chapter
    for lvl, title, pg in toc:
        if lvl == 1 and not re.match(r"^\d+\.\s+", title.strip()) and pg > (top_entries[-1]["page"] if top_entries else 0):
            flat_breaks.append(pg)
    flat_breaks = sorted(set(flat_breaks))

    for order, e in enumerate(top_entries, start=1):
        start = e["page"]
        # Next break strictly greater than start
        end = next((p for p in flat_breaks if p > start), doc.page_count + 1)
        ans_pg = e["answers_page"] or end  # if missing, treat whole block as questions
        chapters.append(Chapter(order=order, title=e["title"],
                                start_page=start, end_page=end, answers_page=ans_pg))
    return chapters


# ── Directions detection ─────────────────────────────────────────────────────
RE_DIR_RANGE = re.compile(r"Questions?\s+(\d+)\s*(?:through|thru|to|[-–—])\s*(\d+)", re.I)
RE_DIR_IMAGE = re.compile(
    r"\b(art\s+below|figure\s+below|illustration\s+below|diagram\s+below|"
    r"indicated\s+on|identify\s+the\s+(anatomical|structure|feature|part)|"
    r"labeled\s+(?:structure|on|in))\b",
    re.I,
)
RE_DIR_MATCH = re.compile(
    r"\b(match(?:ing)?|lettered\s+heading|most\s+closely\s+associated|"
    r"may\s+be\s+selected\s+(?:once|more\s+than\s+once)|"
    r"each\s+(?:numbered\s+)?item.*(?:lettered|heading))\b",
    re.I,
)


def _classify_directions(text: str) -> str:
    if RE_DIR_IMAGE.search(text):
        return "image"
    if RE_DIR_MATCH.search(text):
        return "matching"
    return "standard"


def scan_directions_segments(lines: List[Line]) -> List[DirectionsSeg]:
    """Find every DIRECTIONS block in the line stream and capture its text, qnum range,
    and page range. Each segment ends at the next DIRECTIONS block or end-of-stream.
    """
    # Find the index of every DIRECTIONS line
    dir_indices: List[int] = []
    for i, ln in enumerate(lines):
        if RE_DIRECTIONS.match(ln.text.strip()):
            dir_indices.append(i)

    segs: List[DirectionsSeg] = []
    for k, i in enumerate(dir_indices):
        # Gather the DIRECTIONS text + any continuation until a qnum or next DIRECTIONS
        text_parts = [lines[i].text.strip()]
        j = i + 1
        next_bound = dir_indices[k + 1] if k + 1 < len(dir_indices) else len(lines)
        while j < next_bound:
            s = lines[j].text.strip()
            # Stop if we've reached a qnum, option marker, or another DIRECTIONS —
            # anything beyond the directions sentence proper.
            if (RE_QNUM.match(s) or RE_QNUM_INL.match(s)
                    or RE_OPTION.match(s) or RE_OPTION_ALT.match(s)):
                break
            # Skip obvious header/chapter noise inside directions continuation
            if re.match(r"^CHAPTER\s+\d+\b", s, re.I) or s in ("Questions", "Answers"):
                j += 1
                continue
            # Heuristic: a DIRECTIONS sentence ends at its first terminal period.
            # Stop once the accumulated text ends with "." and the next line is
            # something substantial (>= 3 words or starts with a capital).
            text_parts.append(s)
            j += 1
            acc = " ".join(text_parts).rstrip()
            if acc.endswith(".") and len(acc.split()) >= 8:
                # Directions sentence looks complete. Stop to avoid absorbing
                # unrelated content that appears at later line indices due to
                # column-first sort.
                break
        dtext = " ".join(text_parts).strip()
        m = RE_DIR_RANGE.search(dtext)
        qstart = int(m.group(1)) if m else None
        qend = int(m.group(2)) if m else None
        pages = sorted({lines[p].page for p in range(i, next_bound)})
        segs.append(DirectionsSeg(
            text=dtext, qstart=qstart, qend=qend,
            kind=_classify_directions(dtext),
            line_start=j, line_end=next_bound,
            pages=pages,
        ))
    return segs


# ── Question stream parser ───────────────────────────────────────────────────
def parse_question_stream(lines: List[Line]) -> Tuple[List[QuestionRec], List[DirectionsSeg]]:
    """Parse Questions region. Returns (questions, directions_segments)."""
    segments = scan_directions_segments(lines)
    questions: List[QuestionRec] = []

    def _parse_segment(seg_lines: List[Line], seg: Optional[DirectionsSeg]) -> List[QuestionRec]:
        """Run the question state machine over a slice of lines."""
        out: List[QuestionRec] = []
        cur: Optional[QuestionRec] = None
        mode: Any = None

        def _flush():
            nonlocal cur
            if cur is not None:
                cur.question = cur.question.strip()
                for o in cur.options:
                    o["text"] = o["text"].strip()
                # Keep question even if text empty for image-type segments
                if cur.question or cur.options or (seg and seg.kind == "image"):
                    out.append(cur)
            cur = None

        for ln in seg_lines:
            s = ln.text.strip()
            if not s:
                continue
            if RE_DIRECTIONS.match(s):
                continue
            if RE_ANSWER_H.match(s):
                break
            if re.match(r"^CHAPTER\s+\d+\b", s, re.I):
                continue
            if s in ("Questions", "Answers", "Answers and Explanations"):
                continue

            m = RE_QNUM.match(s)
            if m:
                _flush()
                cur = QuestionRec(qnum=int(m.group(1)), page=ln.page, bbox=ln.bbox,
                                  kind=(seg.kind if seg else "standard"))
                mode = "question"
                continue
            m = RE_QNUM_INL.match(s)
            if m:
                _flush()
                cur = QuestionRec(qnum=int(m.group(1)), page=ln.page, bbox=ln.bbox,
                                  kind=(seg.kind if seg else "standard"))
                cur.question = m.group(2).strip()
                mode = "question"
                continue

            m = RE_OPTION.match(s)
            if m and cur is not None:
                key = m.group(1).upper()
                rest = m.group(2)
                cur.options.append({"key": key, "text": rest.strip()})
                mode = ("option", len(cur.options) - 1)
                _split_embedded_options(cur)
                continue
            # Matching-set shared options appear BEFORE the first qnum — collect onto segment
            if m and cur is None and seg is not None and seg.kind in ("matching", "image"):
                if seg.set_options is None:
                    seg.set_options = []
                seg.set_options.append({"key": m.group(1).upper(), "text": m.group(2).strip()})
                mode = ("set_option", len(seg.set_options) - 1)
                continue

            # Continuation
            if cur is None:
                # Could be continuation of a shared set_option
                if (isinstance(mode, tuple) and mode[0] == "set_option"
                        and seg is not None and seg.set_options):
                    idx = mode[1]
                    seg.set_options[idx]["text"] = join_wrapped(seg.set_options[idx]["text"], s)
                continue
            if mode == "question":
                cur.question = join_wrapped(cur.question, s)
            elif isinstance(mode, tuple) and mode[0] == "option":
                idx = mode[1]
                cur.options[idx]["text"] = join_wrapped(cur.options[idx]["text"], s)
                _split_embedded_options(cur)
            else:
                cur.question = join_wrapped(cur.question, s)
        _flush()
        return out

    # Parse prelude (any lines before the first DIRECTIONS) — may contain a raw
    # question stream for a chapter that has no explicit DIRECTIONS header.
    if not segments:
        questions.extend(_parse_segment(lines, None))
    else:
        if segments[0].line_start > 0:
            prelude = [ln for ln in lines[: max(0, segments[0].line_start - 1)]
                       if not RE_DIRECTIONS.match(ln.text.strip())]
            # Prelude should be empty normally; if it contains qnums, include.
            pre_qs = _parse_segment(prelude, None)
            questions.extend(pre_qs)

        for si, seg in enumerate(segments):
            seg_end = segments[si + 1].line_start - 1 if si + 1 < len(segments) else len(lines)
            # Start from line_start (first post-DIRECTIONS, possibly post set-options)
            seg_lines = lines[seg.line_start:seg_end]
            parsed = _parse_segment(seg_lines, seg)

            # --- Cross-column rescue ---
            # Two-column layouts occasionally split a question's options across
            # columns on a page that also holds a new DIRECTIONS line (e.g. KLM
            # ch5 p84 where Q100 option (A) is in col-0 while (B)-(E) live in
            # col-1 above a new DIRECTIONS block). Column-first sort places the
            # DIRECTIONS line before the col-1 tail, so those options leak into
            # this new segment's set_options. Detect that and donate them back
            # to the last question of the previous segment when it has <5
            # options.
            if (seg.set_options and questions
                    and len(questions[-1].options) < 5):
                prev_q = questions[-1]
                existing_keys = {o["key"] for o in prev_q.options}
                donated: List[Dict[str, str]] = []
                leftover: List[Dict[str, str]] = []
                for opt in seg.set_options:
                    if opt["key"] not in existing_keys:
                        donated.append(opt)
                    else:
                        leftover.append(opt)
                if donated:
                    prev_q.options.extend(donated)
                    # Preserve any lettered options that genuinely belong here
                    seg.set_options = leftover or None

            # Attach segment metadata to each sub-question
            for q in parsed:
                q.directions = seg.text
                if seg.set_options:
                    q.set_options = seg.set_options
                if seg.qstart is not None and seg.qend is not None:
                    q.set_id = f"set_{seg.qstart}_{seg.qend}"
                q.kind = seg.kind
            questions.extend(parsed)

    # Deduplicate on qnum+page (prefer richer record)
    dedup: Dict[Tuple[int, int], QuestionRec] = {}
    for q in questions:
        key = (q.qnum, q.page)
        if key not in dedup or (len(q.question) + len(q.options)) > (
                len(dedup[key].question) + len(dedup[key].options)):
            dedup[key] = q
    # Keep original order
    seen = set()
    ordered: List[QuestionRec] = []
    for q in questions:
        key = (q.qnum, q.page)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(dedup[key])
    return ordered, segments


def _split_embedded_options(q: QuestionRec) -> None:
    """If the latest option's text contains an embedded `(X)` marker, split off a new option."""
    if not q.options:
        return
    last = q.options[-1]
    # Look for a pattern like "... (C) new option text..." in the current option
    m = RE_EMBED_OPT.search(last["text"])
    if m:
        split_point = m.start()
        head = last["text"][:split_point].rstrip()
        # The embedded marker and everything after
        tail_match = re.match(r"\s\(([A-E])\)\s*(.*)$", last["text"][split_point:], re.S)
        if tail_match:
            last["text"] = head
            q.options.append({"key": tail_match.group(1).upper(), "text": tail_match.group(2).strip()})


# ── Answer stream parser ─────────────────────────────────────────────────────
def parse_answer_stream(lines: List[Line]) -> List[AnswerRec]:
    answers: List[AnswerRec] = []
    cur: Optional[AnswerRec] = None

    def _flush():
        nonlocal cur
        if cur is not None:
            cur.explanation = cur.explanation.strip()
            answers.append(cur)
        cur = None

    for ln in lines:
        s = ln.text.strip()
        if not s:
            continue
        if RE_ANSWER_H.match(s):
            continue  # the "Answers and Explanations" heading itself
        if s in ("Questions", "Answers"):
            continue
        if re.match(r"^CHAPTER\s+\d+\b", s, re.I):
            continue

        m = RE_QNUM.match(s)
        if m:
            _flush()
            cur = AnswerRec(qnum=int(m.group(1)))
            continue
        m = RE_QNUM_INL.match(s)
        if m:
            _flush()
            cur = AnswerRec(qnum=int(m.group(1)))
            # The inline portion may be "(B) The lateral end..."
            rest = m.group(2).strip()
            _ingest_answer_text(cur, rest)
            continue

        if cur is None:
            continue
        _ingest_answer_text(cur, s)
    _flush()
    return answers


RE_ANS_LETTER_START = re.compile(r"^\(([A-E])\)\s*(.*)$")


def _ingest_answer_text(a: AnswerRec, text: str) -> None:
    # First piece of content for an answer: extract the letter "(X)" or "The answer is X"
    if a.answer is None:
        m = RE_ANS_LETTER_START.match(text)
        if m:
            a.answer = m.group(1).upper()
            rest = m.group(2).strip()
            a.explanation = rest
            return
        m2 = re.match(r"^The\s+answer\s+is\s+([A-E])\.?\s*(.*)$", text, re.I)
        if m2:
            a.answer = m2.group(1).upper()
            a.explanation = m2.group(2).strip()
            return
    # Continuation
    a.explanation = join_wrapped(a.explanation, text)


# ── Image extraction ─────────────────────────────────────────────────────────
def extract_page_images(page: "fitz.Page", out_dir: Path, book_id: str,
                        min_frac: float = 0.03, max_frac: float = 0.80
                        ) -> List[Dict[str, Any]]:
    """Return list of {src, page, bbox} for figures on this page.

    Filters out full-page background/watermark images and tiny decorative glyphs.
    """
    page_area = page.rect.width * page.rect.height
    out: List[Dict[str, Any]] = []
    seen_xrefs = set()
    for info in page.get_images(full=True):
        xref = info[0]
        if xref in seen_xrefs:
            continue
        seen_xrefs.add(xref)
        # get_image_bbox requires the image name (7th item)
        try:
            bboxes = page.get_image_rects(xref)
        except Exception:
            bboxes = []
        if not bboxes:
            continue
        for bbox in bboxes:
            w = bbox.width
            h = bbox.height
            area = w * h
            if area <= 0:
                continue
            frac = area / page_area
            if frac < min_frac or frac > max_frac:
                continue
            # Extract
            try:
                pix = fitz.Pixmap(page.parent, xref)
                if pix.alpha or pix.n > 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                fname = f"fig_p{page.number+1:03d}_x{xref}.png"
                fpath = out_dir / fname
                if not fpath.exists():
                    pix.save(str(fpath))
                out.append({
                    "src": f"/data/{book_id}/assets/{fname}",
                    "page": page.number + 1,
                    "bbox": [float(bbox.x0), float(bbox.y0), float(bbox.x1), float(bbox.y1)],
                })
            except Exception as e:
                print(f"[warn] image extract failed p{page.number+1} xref={xref}: {e}")
    return out


# ── Image ↔ question attachment ──────────────────────────────────────────────
def attach_images(questions: List[QuestionRec], images: List[Dict[str, Any]]
                  ) -> Dict[int, List[Dict[str, Any]]]:
    """Map qnum → images for STANDARD questions. Rule: attach to the question
    whose bbox is the closest above the image on the same page.

    Synthetic image-set questions (bbox=None) are NOT assigned images here —
    they are handled by the per-segment y-band fan-out in the driver which
    correctly respects multiple DIRECTIONS blocks on one page.
    """
    # Group questions by page, ignoring those without a bbox
    by_page: Dict[int, List[QuestionRec]] = {}
    for q in questions:
        if q.bbox is None:
            continue
        by_page.setdefault(q.page, []).append(q)
    for pg in by_page:
        by_page[pg].sort(key=lambda q: q.bbox[1])

    out: Dict[int, List[Dict[str, Any]]] = {}
    for img in images:
        pg = img["page"]
        cand = by_page.get(pg, [])
        if not cand:
            continue
        img_y = img["bbox"][1]
        chosen = None
        for q in cand:
            if q.bbox[1] <= img_y:
                chosen = q
            else:
                break
        if chosen is None:
            # Image appears above every question on the page; likely belongs to
            # an image-only directions set handled elsewhere — skip.
            continue
        out.setdefault(chosen.qnum, []).append(img)
    return out


# ── Chapter assembly ─────────────────────────────────────────────────────────
def synthesize_image_subquestions(questions: List[QuestionRec],
                                   segments: List[DirectionsSeg]
                                   ) -> List[QuestionRec]:
    """For each 'image' or 'matching' DIRECTIONS segment whose declared qnum range
    is not fully covered by parsed questions, create synthetic placeholder
    QuestionRec entries so the matching answer+explanation+image can be attached.
    """
    present = {q.qnum for q in questions}
    new_qs: List[QuestionRec] = []
    for seg in segments:
        if seg.qstart is None or seg.qend is None:
            continue
        if seg.kind not in ("image", "matching"):
            continue
        # Only synthesize for sub-questions that were NOT found in the parsed stream
        missing = [n for n in range(seg.qstart, seg.qend + 1) if n not in present]
        if not missing:
            continue
        page_guess = seg.pages[0] if seg.pages else 0
        for n in missing:
            q = QuestionRec(
                qnum=n,
                question="",
                options=[],
                page=page_guess,
                bbox=None,
                directions=seg.text,
                set_options=seg.set_options,
                set_id=f"set_{seg.qstart}_{seg.qend}",
                kind=seg.kind,
                synthetic=True,
                needs_review=False,
            )
            new_qs.append(q)
    return new_qs


def build_chapter_json(book_id: str, book_title: str, ch: Chapter,
                       questions: List[QuestionRec], answers: List[AnswerRec],
                       q_images: Dict[int, List[Dict[str, Any]]],
                       segments: List[DirectionsSeg]
                       ) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Returns (chapter_json, stats)."""
    ans_by_q: Dict[int, AnswerRec] = {a.qnum: a for a in answers}

    section_blocks: List[Dict[str, Any]] = []
    section_id = f"ch_{ch.order}_s1"
    bidx = 0

    def _next_id() -> str:
        nonlocal bidx
        i = bidx; bidx += 1
        return f"{section_id}_b{i}"

    # Chapter heading
    section_blocks.append({
        "type": "heading", "level": 1, "text": ch.title,
        "source": "mcq-parser", "page": ch.start_page,
        "id": _next_id(), "confidence": 1.0, "needs_review": False,
    })

    missing_opts: List[int] = []
    missing_ans: List[int] = []
    missing_img_refs: List[int] = []
    synthesized: List[int] = []

    # Order questions by qnum globally (they already are mostly), but segments
    # give us natural grouping. We want directions paragraph emitted BEFORE the
    # first question of each segment.
    qs_sorted = sorted(questions, key=lambda q: (q.qnum,))
    # Map: segment id -> list of qnums within it (for directions emission order)
    emitted_directions = set()

    for q in qs_sorted:
        # Emit the directions paragraph once, right before the first question of that segment
        if q.set_id and q.set_id not in emitted_directions and q.directions:
            emitted_directions.add(q.set_id)
            section_blocks.append({
                "type": "paragraph",
                "text": q.directions,
                "word_count": len(q.directions.split()),
                "source": "mcq-parser",
                "page": q.page,
                "id": _next_id(),
                "confidence": 0.9,
                "needs_review": False,
            })
        elif not q.set_id and q.directions and ("__single__" not in emitted_directions):
            emitted_directions.add("__single__")
            section_blocks.append({
                "type": "paragraph",
                "text": q.directions,
                "word_count": len(q.directions.split()),
                "source": "mcq-parser",
                "page": q.page,
                "id": _next_id(),
                "confidence": 0.9,
                "needs_review": False,
            })

        a = ans_by_q.get(q.qnum)
        imgs = q_images.get(q.qnum, [])
        needs_review = bool(q.needs_review)

        if q.synthetic:
            synthesized.append(q.qnum)

        # For image-kind questions the "answer" in the PDF is the label text itself
        # (no lettered option). Promote explanation -> answer in that case.
        ans_letter: Optional[str] = a.answer if a else None
        ans_expl: str = a.explanation if a and a.explanation else ""
        if q.kind == "image" and a is not None and not ans_letter and ans_expl:
            ans_letter = ans_expl  # the label IS the answer
            ans_expl = ""

        # For standard questions, require at least 4 options; image/matching may have none
        if q.kind == "standard":
            if not q.options or len(q.options) < 4:
                missing_opts.append(q.qnum)
                needs_review = True
        # Count as missing only if we have neither a letter nor a textual label
        if a is None or (not ans_letter and not ans_expl):
            missing_ans.append(q.qnum)
            needs_review = True
        if q.kind == "standard" and not imgs and re.search(r"\b(figure|fig\.?)\b", q.question, re.I):
            missing_img_refs.append(q.qnum)
            needs_review = True

        # Question text fallback for synthetic/image placeholders
        q_text = q.question
        if not q_text and q.kind == "image":
            q_text = f"Identify the anatomical feature labeled for question {q.qnum} on the art above."
        elif not q_text and q.kind == "matching":
            q_text = f"Match item {q.qnum} using the lettered options above."

        block: Dict[str, Any] = {
            "type": "mcq",
            "id": f"{section_id}_q{q.qnum}",
            "qnum": q.qnum,
            "question": q_text,
            "options": q.options if q.options else (q.set_options or []),
            "answer": ans_letter,
            "explanation": ans_expl,
            "page": q.page,
            "bbox": list(q.bbox) if q.bbox else None,
            "kind": q.kind,
            "source": "mcq-parser",
            "confidence": 0.85 if not needs_review else 0.5,
            "needs_review": needs_review,
        }
        if q.set_id:
            block["set_id"] = q.set_id
        if q.set_options:
            block["set_options"] = q.set_options
        if q.synthetic:
            block["synthetic"] = True
        if imgs:
            block["images"] = imgs
        section_blocks.append(block)

    chapter_json = {
        "metadata": {
            "book_id": book_id,
            "book_title": book_title,
            "chapter_id": f"ch_{ch.order}",
            "chapter_title": ch.title,
            "chapter_order": ch.order,
        },
        "chapter": {
            "id": f"ch_{ch.order}",
            "title": ch.title,
            "order": ch.order,
            "page": ch.start_page,
            "sections": [{
                "id": section_id,
                "title": ch.title,
                "order": 1,
                "blocks": section_blocks,
            }],
        },
    }
    stats = {
        "chapter_id": f"ch_{ch.order}",
        "chapter_title": ch.title,
        "questions_found": len(questions),
        "answers_matched": sum(1 for q in questions if q.qnum in ans_by_q and ans_by_q[q.qnum].answer),
        "orphan_answers": sorted(set(ans_by_q.keys()) - {q.qnum for q in questions}),
        "questions_missing_options": missing_opts,
        "questions_missing_answer": missing_ans,
        "questions_figure_ref_no_image": missing_img_refs,
        "synthesized_image_subquestions": synthesized,
        "directions_segments": [
            {"qstart": s.qstart, "qend": s.qend, "kind": s.kind,
             "pages": s.pages, "has_set_options": bool(s.set_options)}
            for s in segments
        ],
        "images_attached": sum(len(v) for v in q_images.values()),
    }
    return chapter_json, stats


# ── Main driver ──────────────────────────────────────────────────────────────
def parse_book(pdf_path: Path, book_id: str, book_title: str,
               out_dir: Path, public_pdf: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = out_dir / "assets"
    assets_dir.mkdir(exist_ok=True)

    print(f"[mcq] opening {pdf_path}")
    with fitz.open(str(pdf_path)) as doc:
        chapters = build_chapters(doc)
        print(f"[mcq] detected {len(chapters)} chapters")
        for ch in chapters:
            print(f"  - {ch.title}: questions p{ch.start_page}..{ch.answers_page-1}, answers p{ch.answers_page}..{ch.end_page-1}")

        # Extract images per page once, store in dict
        all_page_images: Dict[int, List[Dict[str, Any]]] = {}
        for i in range(doc.page_count):
            imgs = extract_page_images(doc[i], assets_dir, book_id)
            if imgs:
                all_page_images[i + 1] = imgs

        chapters_summary = []
        report_per_chapter = []

        for ch in chapters:
            print(f"\n[mcq] ==== {ch.title} ====")
            # Questions region lines
            q_lines: List[Line] = []
            for p in range(ch.start_page - 1, ch.answers_page - 1):
                q_lines.extend(extract_page_lines(doc[p]))
            a_lines: List[Line] = []
            for p in range(ch.answers_page - 1, ch.end_page - 1):
                a_lines.extend(extract_page_lines(doc[p]))

            questions, segments = parse_question_stream(q_lines)
            answers = parse_answer_stream(a_lines)

            # Synthesize placeholder MCQs for image-based / matching-set sub-questions
            # whose qnums appear in the answer region but not in the question stream.
            synth = synthesize_image_subquestions(questions, segments)
            # Also synthesize for any orphan answer qnums whose nearest segment is
            # image/matching (catches mis-classified directions).
            present = {q.qnum for q in questions} | {q.qnum for q in synth}
            ans_only = [a.qnum for a in answers if a.qnum not in present]
            for qn in ans_only:
                # Find the directions segment whose range contains qn, prefer image/matching
                matched = next((s for s in segments
                                if s.qstart is not None and s.qstart <= qn <= (s.qend or -1)), None)
                kind = matched.kind if matched and matched.kind != "standard" else "image"
                pg = matched.pages[0] if matched and matched.pages else ch.start_page
                synth.append(QuestionRec(
                    qnum=qn, question="", options=[], page=pg, bbox=None,
                    directions=(matched.text if matched else None),
                    set_options=(matched.set_options if matched else None),
                    set_id=(f"set_{matched.qstart}_{matched.qend}"
                            if matched and matched.qstart is not None else None),
                    kind=kind, synthetic=True, needs_review=True,
                ))
            all_questions = questions + synth
            print(f"   questions={len(questions)}  synthesized={len(synth)}  "
                  f"answers={len(answers)}  segments={len(segments)} "
                  f"(img={sum(1 for s in segments if s.kind=='image')}, "
                  f"match={sum(1 for s in segments if s.kind=='matching')})")

            # Collect images relevant to this chapter (questions region only)
            ch_imgs: List[Dict[str, Any]] = []
            for p in range(ch.start_page, ch.answers_page):
                ch_imgs.extend(all_page_images.get(p, []))
            q_img_map = attach_images(all_questions, ch_imgs)
            # Also: for image/matching segments fan images out to every sub-question
            # in the declared range. We must be careful when two image-DIRECTIONS
            # blocks share the same page (e.g. KLM ch3 p46 has "Questions 76-85" at
            # the top and "Questions 86-90" in the middle). Partition each page
            # into vertical bands separated by its DIRECTIONS y-positions and
            # assign each image to the band it sits inside.

            # Build directions-y positions per page across ALL image/matching segs.
            dir_positions: Dict[int, List[Tuple[float, DirectionsSeg]]] = {}
            for seg in segments:
                if seg.kind not in ("image", "matching") or seg.qstart is None:
                    continue
                # Find the DIRECTIONS line's y on each page it spans.
                for p in seg.pages:
                    # Use the smallest y among lines matching RE_DIRECTIONS on that page
                    dir_y = None
                    for ln in q_lines:
                        if ln.page == p and RE_DIRECTIONS.match(ln.text.strip()):
                            if seg.text.startswith(ln.text.strip()[:40]):
                                dir_y = ln.bbox[1] if dir_y is None else min(dir_y, ln.bbox[1])
                    if dir_y is None:
                        dir_y = 0.0  # segment applies from the top
                    dir_positions.setdefault(p, []).append((dir_y, seg))
            for p in dir_positions:
                dir_positions[p].sort(key=lambda t: t[0])

            for seg in segments:
                if seg.kind not in ("image", "matching") or seg.qstart is None:
                    continue
                seg_qnums = list(range(seg.qstart, (seg.qend or seg.qstart) + 1))
                # Pick images that fall into THIS segment's y-band on each page.
                seg_imgs: List[Dict[str, Any]] = []
                for im in ch_imgs:
                    p = im["page"]
                    if p not in seg.pages:
                        continue
                    bands = dir_positions.get(p, [])
                    owner: Optional[DirectionsSeg] = None
                    y_img = im["bbox"][1]
                    for (dy, s) in bands:
                        if dy <= y_img:
                            owner = s
                        else:
                            break
                    # If no DIRECTIONS sits above the image, it belongs to the
                    # first segment on that page.
                    if owner is None and bands:
                        owner = bands[0][1]
                    if owner is seg:
                        seg_imgs.append(im)
                if not seg_imgs:
                    continue
                for qn in seg_qnums:
                    existing = q_img_map.get(qn, [])
                    srcs = {i["src"] for i in existing}
                    for im in seg_imgs:
                        if im["src"] not in srcs:
                            existing.append(im)
                            srcs.add(im["src"])
                    q_img_map[qn] = existing

            ch_json, stats = build_chapter_json(
                book_id, book_title, ch, all_questions, answers, q_img_map, segments
            )
            # Write chapter file
            ch_file = out_dir / f"ch_{ch.order}.json"
            ch_file.write_text(json.dumps(ch_json, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"   wrote {ch_file.name}  ({ch_file.stat().st_size/1024:.1f} KB)")

            # Accumulate for main.json
            chapters_summary.append(ch_json["chapter"])
            report_per_chapter.append(stats)

        # main.json — mirror the shape existing frontend expects
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
        print(f"\n[mcq] wrote {main_path}  ({main_path.stat().st_size/1024:.1f} KB)")

        # _report.json
        report = {
            "book_id": book_id,
            "book_title": book_title,
            "per_chapter": report_per_chapter,
            "totals": {
                "questions_found": sum(r["questions_found"] for r in report_per_chapter),
                "answers_matched": sum(r["answers_matched"] for r in report_per_chapter),
                "images_attached": sum(r["images_attached"] for r in report_per_chapter),
            },
        }
        (out_dir / "_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

        # Print summary table
        print("\n[mcq] ===== SUMMARY =====")
        print(f"{'Chapter':45s} {'Qs':>5s} {'As':>5s} {'miss_opt':>9s} {'miss_ans':>9s} {'fig?':>5s}")
        for r in report_per_chapter:
            print(f"{r['chapter_title'][:44]:45s} {r['questions_found']:5d} "
                  f"{r['answers_matched']:5d} {len(r['questions_missing_options']):9d} "
                  f"{len(r['questions_missing_answer']):9d} {len(r['questions_figure_ref_no_image']):5d}")
        print(f"TOTAL questions: {report['totals']['questions_found']}, "
              f"answers: {report['totals']['answers_matched']}, "
              f"images: {report['totals']['images_attached']}")

    # Copy PDF to /public/books for frontend
    PUBLIC_BOOKS.mkdir(parents=True, exist_ok=True)
    dst = PUBLIC_BOOKS / pdf_path.name
    if not dst.exists() or dst.stat().st_size != pdf_path.stat().st_size:
        shutil.copy2(pdf_path, dst)
        print(f"[mcq] copied PDF -> {dst}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Parse MCQ book PDF into structured JSON.")
    ap.add_argument("--pdf", required=True, help="Path to MCQ PDF")
    ap.add_argument("--book-id", required=True, help="Slug used under public/data/<id>/")
    ap.add_argument("--title", required=True, help="Human-readable book title")
    args = ap.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        raise FileNotFoundError(pdf_path)
    out_dir = DATA_DIR / args.book_id
    parse_book(pdf_path, args.book_id, args.title, out_dir, PUBLIC_BOOKS)


if __name__ == "__main__":
    main()
