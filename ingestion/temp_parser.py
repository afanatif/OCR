"""
MCQ Parser — Phase 1

Tuned for physio_guyton.pdf (433 pages, 15 units).

PDF Structure:
  TOC (page 7):    "Unit 1: The cell and general physiology", ...
  Unit headers:    "UNIT I", "UNIT II" (Roman numeral, own line)
  MCQ block:       Questions numbered from 1, three types (see below)
  Answer block:    Triggered by "Answers" on its own line
                   Format: "1.B) Explanation...\\n    TMP12 14"

MCQ Types (all normalised to self-contained MCQs):
  Type 1 — Standard:
      N. Stem text
          A) Option A
          B) Option B   ...   E) Option E

  Type 2 — Extended Matching:
      Questions N–M           ← range marker
      A) Shared option A      (A through L or more)
      ...
      L) Shared option L
      Instruction sentence.
      N. Stem only            ← bare stems, no own options
      M. Stem only
      → shared options are COPIED into every stem MCQ

  Type 3 — Table-based: treated identically to Type 2.

Image handling:
  After export_book.py resolves image placeholders, the unit text contains
  `<!-- image: images/pN_iM.ext -->` tags at exactly the position where an
  image appears in the original PDF.  The parser captures these paths and
  attaches them to the correct question:

    - Image before a question starts → attached to the NEXT question (pre-image)
    - Image inside a question stem   → attached to that question
    - Image inside shared block (Type 2/3) → copied to ALL questions in the group
    - Bare `<!-- image: UNRESOLVED -->` or legacy `<!-- image -->` tags →
      recorded as empty strings and warned, not silently dropped.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from src.core.logger import logger


# ── Data classes ───────────────────────────────────────────────────────────

@dataclass
class TOCEntry:
    unit_number: int
    unit_title: str


@dataclass
class ParsedQuestion:
    number: int
    stem: str
    options: dict[str, str]          # {"A": "text", "B": "text", ...}
    mcq_type: str = "standard"       # "standard" | "extended_matching"
    images: list[str] = field(default_factory=list)  # resolved image paths
    page: Optional[int] = None                       # page where the question starts
    shared_block_id: Optional[str] = None            # ID of the shared block this question belongs to


@dataclass
class ParsedAnswer:
    number: int
    correct_answer: str              # "A" | "B" | ... | "L"
    explanation: str
    book: Optional[str] = None
    edition: Optional[int] = None
    page: Optional[str] = None
    see_also: Optional[str] = None
    reference: Optional[str] = None  # Raw string fallback


# ── Regex patterns ─────────────────────────────────────────────────────────

_RE_TOC_UNIT     = re.compile(r"Unit\s+(\d+)[:\s]+(.+)", re.IGNORECASE)
_RE_UNIT_HEADER  = re.compile(r"^\s*(?:#+\s*)?UNIT\s+([IVXLCDM]+).*", re.IGNORECASE)
_RE_ANSWERS      = re.compile(r"^\s*(?:#+\s*)?Answers.*", re.IGNORECASE)
_RE_Q_START      = re.compile(r"^\s*(?:#+\s*)?(\d+)\.\s*(.+)")
_RE_OPTION       = re.compile(r"^\s*(?:[-*]\s*)?([A-La-l])\)\s*(.+)")
_RE_TABLE_OPTION = re.compile(r"^\s*\|\s*([A-La-l])\)\s*\|\s*(.+)")
_RE_RANGE        = re.compile(r"Questions?\s+(\d+)\s*(?:[–\-]|and)\s*(\d+)", re.IGNORECASE)
_RE_ANSWER_ENTRY = re.compile(r"^\s*(?:[-*]\s*)?(\d+)\.?\s*([A-La-l])\)\s*(.*)")
_RE_TMP          = re.compile(r"\bTMP\s*(\d+)\s+([\d\s\-–]+)\b")
_RE_SEE_ALSO     = re.compile(r"see also\s+(.+)", re.IGNORECASE)

# A regex to detect if a question stem explicitly asks the user to refer to a visual.
# We removed words like 'shown', 'above', 'below' because they caused false positives
# (e.g., "studies have shown", "all of the above").
_RE_DIAGRAM_REF = re.compile(
    r"\b(diagram|figure|fig\.?|illustration|trace|graph|curve|chart|plot|panel)s?\b",
    re.IGNORECASE
)

# Matches BOTH resolved and legacy bare image tags:
#   <!-- image: images/p5_i1.png -->   → group(1) = "images/p5_i1.png"
#   <!-- image: UNRESOLVED -->         → group(1) = "UNRESOLVED"
#   <!-- image -->                     → group(1) = None  (legacy / fallback)
#
# Uses lazy .*? so hyphens or any chars in file paths are captured correctly.
# The `-->` terminator naturally stops the lazy match.
_RE_IMAGE = re.compile(
    r"<!--\s*image(?:\s*:\s*(.*?))?\s*-->",
    re.IGNORECASE,
)

_ROMAN_MAP = {
    "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
    "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
    "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
}


def _roman_to_int(r: str) -> int:
    return _ROMAN_MAP.get(r.strip().upper(), 0)


def _extract_image_path(tag_content: Optional[str]) -> str:
    """Normalise the path from an image tag.  Returns '' for bare/unresolved."""
    if tag_content is None:
        return ""                         # legacy bare <!-- image -->
    path = tag_content.strip()
    if path.upper() == "UNRESOLVED":
        return ""                         # count-mismatch placeholder
    return path


def _polish_text(text: str) -> str:
    """Strip internal metadata tags and clean up whitespace/formulas for the UI."""
    if not text:
        return ""
    
    # 1. Strip internal metadata tags
    text = re.sub(r"<!--\s*.*?\s*-->", "", text, flags=re.DOTALL)
    
    # 2. Fix merged tables: extract instructions from table rows
    lines = text.splitlines()
    polished_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            # Extract non-empty cells
            cells = [c.strip() for c in stripped.split("|") if c.strip()]
            # If there's only one "content" cell and it's long, it's an instruction
            if len(cells) == 1 and len(cells[0].split()) > 7:
                # Likely an instruction merged into a table row (e.g. | Text | | |)
                polished_lines.append("\n" + cells[0] + "\n")
                continue
        polished_lines.append(line)
    text = "\n".join(polished_lines)

    # 3. Join fragmented math lines
    text = re.sub(r"\n\s*([=+\-\/×])\s*", r" \1 ", text)
    
    # 4. Medical/Chemical Polish — ions and superscripts
    # Docling always emits a space between element and charge (e.g. 'Na +', 'Cl -').
    # Compound words like 'Cl-permeable' have NO space, so \s+ (not \s*) prevents regressions.

    # Scientific notation: 10-4 → 10⁻⁴, 10+4 → 10⁺⁴
    # Capture both sign and digits so translation is fully generic (no hardcoding).
    _sup = str.maketrans("0123456789+-", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻")
    def _make_superscript(m):
        sign, digits = m.group(1), m.group(2)
        return "10" + sign.translate(_sup) + digits.translate(_sup)
    text = re.sub(r"\b10\s*([+\-])\s*(\d+)(?=\s|$|\b)", _make_superscript, text)

    # ── Monovalent Cations ─────────────────────────────────────────────────
    text = re.sub(r"\bNa\s+\+",     "Na⁺",   text)
    text = re.sub(r"\bK\s+\+",      "K⁺",    text)
    text = re.sub(r"\bH\s+\+",      "H⁺",    text)
    text = re.sub(r"\bLi\s+\+",     "Li⁺",   text)
    text = re.sub(r"\bAg\s+\+",     "Ag⁺",   text)
    text = re.sub(r"\bCu\s+\+",     "Cu⁺",   text)
    text = re.sub(r"\bNH\s*4\s+\+", "NH₄⁺",  text)

    # ── Divalent & Trivalent Cations ───────────────────────────────────────
    text = re.sub(r"\bCa\s+\+{1,2}", "Ca²⁺", text)
    text = re.sub(r"\bMg\s+\+{1,2}", "Mg²⁺", text)
    text = re.sub(r"\bBa\s+\+{1,2}", "Ba²⁺", text)
    text = re.sub(r"\bZn\s+\+{1,2}", "Zn²⁺", text)
    text = re.sub(r"\bCu\s+\+{1,2}", "Cu²⁺", text)
    text = re.sub(r"\bCo\s+\+{1,2}", "Co²⁺", text)
    text = re.sub(r"\bMn\s+\+{1,2}", "Mn²⁺", text)
    text = re.sub(r"\bPb\s+\+{1,2}", "Pb²⁺", text)
    text = re.sub(r"\bFe\s+\+{1,2}", "Fe²⁺", text)
    text = re.sub(r"\bFe\s+\+{3}",   "Fe³⁺", text)
    text = re.sub(r"\bAl\s+\+{3}",   "Al³⁺", text)

    # ── Monovalent Anions ──────────────────────────────────────────────────
    text = re.sub(r"\bCl\s+\-",        "Cl⁻",    text)
    text = re.sub(r"\bF\s+\-",         "F⁻",     text)
    text = re.sub(r"\bBr\s+\-",        "Br⁻",    text)
    text = re.sub(r"\bI\s+\-",         "I⁻",     text)
    text = re.sub(r"\bOH\s+\-",        "OH⁻",    text)
    text = re.sub(r"\bHCO\s*3\s+\-",   "HCO₃⁻",  text)
    text = re.sub(r"\bNO\s*3\s+\-",    "NO₃⁻",   text)
    text = re.sub(r"\bNO\s*2\s+\-",    "NO₂⁻",   text)
    text = re.sub(r"\bCN\s+\-",        "CN⁻",    text)
    text = re.sub(r"\bH\s*2\s*PO\s*4\s+\-", "H₂PO₄⁻", text)

    # ── Divalent & Trivalent Anions ────────────────────────────────────────
    text = re.sub(r"\bSO\s*4\s*2\s+\-",  "SO₄²⁻",  text)
    text = re.sub(r"\bSO\s*3\s*2\s+\-",  "SO₃²⁻",  text)
    text = re.sub(r"\bCO\s*3\s*2\s+\-",  "CO₃²⁻",  text)
    text = re.sub(r"\bHPO\s*4\s*2\s+\-", "HPO₄²⁻", text)
    text = re.sub(r"\bPO\s*4\s*3\s+\-",  "PO₄³⁻",  text)

    # 5. Subscript whitelist — organized by category.
    # All patterns use \s+ (require space) matching Docling's output format.

    # ── Gases ──────────────────────────────────────────────────────────────
    text = re.sub(r"\bO\s+2\b",         "O₂",    text)
    text = re.sub(r"\bN\s+2\b",         "N₂",    text)
    text = re.sub(r"\bH\s+2\b",         "H₂",    text)
    text = re.sub(r"\bCl\s+2\b",        "Cl₂",   text)
    text = re.sub(r"\bNO\s+2\b",        "NO₂",   text)
    text = re.sub(r"\bSO\s+2\b",        "SO₂",   text)
    text = re.sub(r"\bCO\s+2\b",        "CO₂",   text)
    text = re.sub(r"\bNH\s+3\b",        "NH₃",   text)

    # ── Water / peroxide (H₂O₂ must precede H₂O) ──────────────────────────
    text = re.sub(r"\bH\s+2\s*O\s+2\b", "H₂O₂",  text)
    text = re.sub(r"\bH\s+2\s*O\b",     "H₂O",   text)

    # ── Respiratory / blood-gas notation ──────────────────────────────────
    text = re.sub(r"\bpO\s+2\b",        "pO₂",   text)
    text = re.sub(r"\bpCO\s+2\b",       "pCO₂",  text)
    text = re.sub(r"\bPaO\s+2\b",       "PaO₂",  text)
    text = re.sub(r"\bPaCO\s+2\b",      "PaCO₂", text)
    text = re.sub(r"\bPvO\s+2\b",       "PvO₂",  text)
    text = re.sub(r"\bPAO\s+2\b",       "PAO₂",  text)
    text = re.sub(r"\bPACO\s+2\b",      "PACO₂", text)
    text = re.sub(r"\bSpO\s+2\b",       "SpO₂",  text)
    text = re.sub(r"\bSaO\s+2\b",       "SaO₂",  text)
    text = re.sub(r"\bFiO\s+2\b",       "FiO₂",  text)

    # ── Common salts & inorganic compounds ────────────────────────────────
    text = re.sub(r"\bCaCl\s+2\b",      "CaCl₂",  text)
    text = re.sub(r"\bMgCl\s+2\b",      "MgCl₂",  text)
    text = re.sub(r"\bAlCl\s+3\b",      "AlCl₃",  text)
    text = re.sub(r"\bFeCl\s+2\b",      "FeCl₂",  text)
    text = re.sub(r"\bFeCl\s+3\b",      "FeCl₃",  text)
    text = re.sub(r"\bMgSO\s+4\b",      "MgSO₄",  text)
    text = re.sub(r"\bNaHCO\s+3\b",     "NaHCO₃", text)
    text = re.sub(r"\bKHCO\s+3\b",      "KHCO₃",  text)
    text = re.sub(r"\bCaCO\s+3\b",      "CaCO₃",  text)
    text = re.sub(r"\bNH\s+4\s*Cl\b",   "NH₄Cl",  text)
    text = re.sub(r"\bNa\s+2\s*CO\s+3\b", "Na₂CO₃", text)
    text = re.sub(r"\bNa\s+2\s*SO\s+4\b", "Na₂SO₄", text)

    # ── Acids ──────────────────────────────────────────────────────────────
    text = re.sub(r"\bH\s+2\s*SO\s+4\b",  "H₂SO₄", text)
    text = re.sub(r"\bH\s+3\s*PO\s+4\b",  "H₃PO₄", text)
    text = re.sub(r"\bH\s+2\s*CO\s+3\b",  "H₂CO₃", text)
    text = re.sub(r"\bHNO\s+3\b",          "HNO₃",  text)
    text = re.sub(r"\bHNO\s+2\b",          "HNO₂",  text)

    # ── Biochemistry coenzymes ─────────────────────────────────────────────
    text = re.sub(r"\bFADH\s+2\b",     "FADH₂",  text)

    # ── Kinetics / pharmacology constants ─────────────────────────────────
    text = re.sub(r"\bV\s+max\b",      "Vmax",   text)
    text = re.sub(r"\bK\s+m\b",        "Km",     text)
    text = re.sub(r"\bK\s+d\b",        "Kd",     text)
    text = re.sub(r"\bK\s+i\b",        "Ki",     text)
    text = re.sub(r"\bK\s+eq\b",       "Keq",    text)
    text = re.sub(r"\bpK\s+a\b",       "pKa",    text)
    text = re.sub(r"\bpK\s+b\b",       "pKb",    text)
    text = re.sub(r"\bEC\s+50\b",      "EC₅₀",   text)
    text = re.sub(r"\bIC\s+50\b",      "IC₅₀",   text)
    text = re.sub(r"\bLD\s+50\b",      "LD₅₀",   text)

    # ── Specific Concentration/Permeability Subscripts ─────────────────────
    text = re.sub(r"\[Na\]\s*A\b",     "[Na]<sub>A</sub>", text)
    text = re.sub(r"\[Na\]\s*B\b",     "[Na]<sub>B</sub>", text)
    text = re.sub(r"\bP\s*K\s*/\s*P\s*Na\b", "P<sub>K</sub>/P<sub>Na</sub>", text)

    # 6. Ensure blank line between table end and following paragraph
    # (Markdown spec requires this — without it, parsers absorb the next line as a table row)
    text = re.sub(r"(\|\s*\n)([^|\n\-])", r"|\n\n\2", text)

    # 6. Cleanup whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ── Public API ─────────────────────────────────────────────────────────────

def extract_toc(full_text: str) -> list[TOCEntry]:
    """Parse TOC from the first ~20000 chars of the full document text."""
    entries: list[TOCEntry] = []
    seen: set[int] = set()
    for m in _RE_TOC_UNIT.finditer(full_text[:20000]):
        n = int(m.group(1))
        if n not in seen:
            seen.add(n)
            entries.append(TOCEntry(unit_number=n, unit_title=m.group(2).strip()))
    logger.info(f"TOC: {len(entries)} unit(s) found")
    return entries


def split_into_units(full_text: str) -> dict[int, str]:
    """
    Split full document text into units.
    First tries to extract titles from TOC, then uses those titles as delimiters.
    Falls back to 'UNIT X' regex if TOC-based splitting fails.
    """
    toc_entries = extract_toc(full_text)

    if not toc_entries:
        logger.warning("No TOC found. Falling back to 'UNIT X' regex split.")
        return _split_by_regex(full_text)

    title_to_num = {entry.unit_title.lower().strip(): entry.unit_number for entry in toc_entries}

    current_unit: Optional[int] = None
    units: dict[int, list[str]] = {}
    lines = full_text.splitlines(keepends=True)

    for line in lines:
        stripped = line.strip().lower()
        clean_title = re.sub(r"^[#\s]+", "", stripped)

        found_num = None
        if clean_title in title_to_num:
            found_num = title_to_num[clean_title]
        else:
            m_header = _RE_UNIT_HEADER.match(line)
            if m_header:
                found_num = _roman_to_int(m_header.group(1))

        if found_num is not None:
            current_unit = found_num
            if current_unit not in units:
                units[current_unit] = []
            continue

        if current_unit is not None:
            units[current_unit].append(line)

    result = {k: "".join(v) for k, v in units.items()}
    logger.info(f"Split into {len(result)} unit(s) using TOC titles")
    return result


def _split_by_regex(full_text: str) -> dict[int, str]:
    """Legacy/Fallback split logic using UNIT X headers."""
    units: dict[int, list[str]] = {}
    current: Optional[int] = None

    for line in full_text.splitlines(keepends=True):
        m = _RE_UNIT_HEADER.match(line)
        if m:
            current = _roman_to_int(m.group(1))
            units[current] = []
            continue
        if current is not None:
            units[current].append(line)

    return {k: "".join(v) for k, v in units.items()}


def parse_mcq_block(unit_text: str) -> list[ParsedQuestion]:
    """
    Parse the MCQ portion of a unit (text up to the 'Answers' line).
    Handles all 3 MCQ types and resolved image tags.
    """
    # Only parse the MCQ half — split at the Answers section
    parts = re.split(
        r"(?mi)^\s*(?:#+\s*)?(?:Answers|Answer Key|Answer)\b.*$",
        unit_text,
        maxsplit=1,
    )
    mcq_text = parts[0]

    questions: list[ParsedQuestion] = []
    lines = mcq_text.splitlines()

    # ── State variables ────────────────────────────────────────────────────
    cur_num:  Optional[int] = None
    cur_stem: list[str]     = []
    cur_opts: dict[str, str] = {}
    cur_type: str            = "standard"
    cur_mode: str            = "stem"     # "stem" | "option"
    last_opt: Optional[str]  = None
    cur_images: list[str]    = []         # images found inside the current question

    # Images buffered AFTER a question's options and BEFORE the next question.
    # Usually these belong to the NEXT question (pre-question diagram), but if
    # the CURRENT question's stem references a diagram they belong to it instead.
    inter_images: list[str] = []

    # Extended matching / shared context state
    shared_opts:    dict[str, str] = {}
    shared_context: list[str]      = []
    shared_images:  list[str]      = []   # images inside the shared block
    pending_range:  Optional[tuple[int, int]] = None
    in_shared_block: bool = False
    cur_page:        Optional[int] = None
    cur_q_page:      Optional[int] = None # The page where the current question STARTED

    # ── Helpers ────────────────────────────────────────────────────────────

    def _stem_references_diagram() -> bool:
        """True if the current question's stem mentions a diagram/figure/trace."""
        full_stem = " ".join(cur_stem)
        return bool(_RE_DIAGRAM_REF.search(full_stem))

    def _flush() -> None:
        nonlocal cur_num, cur_stem, cur_opts, cur_type
        nonlocal cur_images, inter_images
        if cur_num is None:
            return

        # If the stem references a diagram, it claims all inter_images
        # that appeared after its options.
        final_images = cur_images[:]
        if inter_images and _stem_references_diagram():
            final_images.extend(inter_images)
            inter_images = []

        # Determine if this question is part of a shared block
        block_id = None
        if pending_range and pending_range[0] <= cur_num <= pending_range[1]:
            block_id = f"{pending_range[0]}-{pending_range[1]}"

        questions.append(ParsedQuestion(
            number=cur_num,
            stem=" ".join(cur_stem).strip(),
            options=dict(cur_opts),
            mcq_type=cur_type,
            images=final_images,
            page=cur_q_page,
            shared_block_id=block_id
        ))
        cur_num    = None
        cur_stem   = []
        cur_opts   = {}
        cur_type   = "standard"
        cur_images = []

    # ── Line-by-line parse ─────────────────────────────────────────────────
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        # ── A) Page marker ────────────────────────────────────────────────
        m_page = re.search(r"<!--\s*pages\s+(\d+)", line, re.IGNORECASE)
        if m_page:
            new_p = int(m_page.group(1))
            cur_page = new_p
            continue

        # ── B) Image tag ──────────────────────────────────────────────────
        m_img = _RE_IMAGE.match(stripped)
        if m_img and stripped.startswith("<!--"):
            path = _extract_image_path(m_img.group(1))

            if path:
                if in_shared_block or (pending_range and cur_num is None):
                    shared_images.append(path)
                elif cur_num is None:
                    inter_images.append(path)
                elif cur_mode == "option":
                    inter_images.append(path)
                else:
                    cur_images.append(path)
            else:
                logger.debug("Unresolved image tag skipped (ghost/separator)")
            continue

        # ── B) Range marker ───────────────────────────────────────────────
        m_range = _RE_RANGE.search(stripped)
        if m_range:
            before_text = stripped[:m_range.start()].strip()
            if before_text and cur_num is not None:
                if cur_mode == "option" and last_opt:
                    cur_opts[last_opt] += " " + before_text
                else:
                    cur_stem.append(before_text)

            _flush()
            pending_range   = (int(m_range.group(1)), int(m_range.group(2)))
            shared_opts     = {}
            shared_context  = []
            shared_images   = []
            in_shared_block = True
            cur_q_page      = cur_page

            after_text = stripped[m_range.end():].strip()
            if after_text:
                shared_context.append(after_text)
            continue

        # ── C) Shared-block option collection ─────────────────────────────
        if in_shared_block:
            m_opt = _RE_OPTION.match(line)
            m_tab = _RE_TABLE_OPTION.match(line)
            if m_opt or m_tab:
                if m_opt:
                    shared_opts[m_opt.group(1).upper()] = m_opt.group(2).strip()
                else:
                    shared_opts[m_tab.group(1).upper()] = m_tab.group(2).strip().replace(" | ", " | ")
                continue
            # Non-option line → instruction text; stop collecting shared opts
            in_shared_block = False
            # Fall through to handle the line normally below

        # ── D) Option for the current standard question ───────────────────
        m_opt = _RE_OPTION.match(line)
        m_tab = _RE_TABLE_OPTION.match(line)
        
        if (m_opt or m_tab) and cur_num is not None and cur_type == "standard":
            if m_opt:
                label = m_opt.group(1).upper()
                text  = m_opt.group(2).strip()
            else:
                label = m_tab.group(1).upper()
                # Join remaining table cells as the option text
                text  = m_tab.group(2).strip().replace(" | ", " | ")
            
            cur_opts[label] = text
            cur_mode = "option"
            last_opt = label
            continue

        # ── E) New question start ─────────────────────────────────────────
        m_q = _RE_Q_START.match(line)
        if m_q:
            _flush()
            q_num      = int(m_q.group(1))
            stem_start = m_q.group(2).strip()
            cur_num    = q_num
            # Only update page if we're not inside a locked range block
            if not (pending_range and pending_range[0] <= q_num <= pending_range[1]):
                cur_q_page = cur_page

            # inter_images not consumed by _flush() (previous Q had no diagram ref)
            # → they become pre-question images for THIS new question.
            pre_images = list(inter_images)
            inter_images.clear()

            if pending_range and pending_range[0] <= q_num <= pending_range[1]:
                # Build shared prefix for stem
                prefix = ""
                if shared_context:
                    prefix = "\n".join(shared_context).strip() + "\n\n"

                if shared_opts:
                    cur_opts = dict(shared_opts)
                    cur_type = "extended_matching"
                elif any("diagram" in ctx.lower() and "identify" in ctx.lower() for ctx in shared_context):
                    # Diagram-based identification: provide default options A-E
                    cur_opts = {
                        "A": "Option A (See Diagram)",
                        "B": "Option B (See Diagram)",
                        "C": "Option C (See Diagram)",
                        "D": "Option D (See Diagram)",
                        "E": "Option E (See Diagram)"
                    }
                    cur_type = "extended_matching"
                else:
                    cur_opts = {}
                    cur_type = "standard"

                # Merge shared images + any inter_images for this question
                cur_images = list(shared_images) + pre_images
            else:
                cur_opts   = {}
                cur_type   = "standard"
                cur_images = pre_images
                if pending_range and q_num > pending_range[1]:
                    pending_range  = None
                    shared_opts    = {}
                    shared_context = []
                    shared_images  = []
                prefix = ""

            cur_stem = [prefix + stem_start] if prefix else [stem_start]
            cur_mode = "stem"
            last_opt = None
            continue

        # ── F) Context text between range marker and first question ───────
        if pending_range and cur_num is None:
            shared_context.append(stripped)
            continue

        # ── I) Continuation of current question ───────────────────────────
        if cur_num is not None:
            if cur_mode == "option" and last_opt:
                cur_opts[last_opt] += " " + stripped
            else:
                cur_stem.append(stripped)

    _flush()

    # ── J) Post-Parse: Hunger Redistribution ──────────────────────────────
    # Fixes cases where PDF layout puts images AFTER subsequent questions.
    # We look for "hungry" questions (mention diagram, have 0 images)
    # and "over-fed" questions (have images from a different page).

    # 1. Collect all UNIQUE images across the entire document
    all_assigned_images: list[tuple[str, int, int]] = []
    seen_paths = set()
    for idx, q in enumerate(questions):
        for img_path in q.images:
            if img_path not in seen_paths:
                m_p = re.search(r"p(\d+)_", img_path)
                img_page = int(m_p.group(1)) if m_p else (q.page or 0)
                all_assigned_images.append((img_path, img_page, idx))
                seen_paths.add(img_path)
        # Strip all images; they will be reassigned from scratch
        q.images = []

    # 2. Identify "Hungry Entities"
    # A hungry entity is a contiguous block of questions that share the exact
    # same shared_block_id (if not None) AND match the diagram reference regex.
    # Isolated questions (shared_block_id == None) form their own single-question entities.
    hungry_entities = []
    i = 0
    while i < len(questions):
        q = questions[i]
        if bool(_RE_DIAGRAM_REF.search(q.stem)):
            start_idx = i
            block_id = q.shared_block_id
            page = q.page or 0
            j = i + 1
            if block_id is not None:
                while j < len(questions) and questions[j].shared_block_id == block_id:
                    j += 1
            hungry_entities.append({
                "page": page,
                "indices": list(range(start_idx, j))
            })
            i = j
        else:
            i += 1

    # 3. Redistribute sequentially per "Image Page Cluster"
    # a) Group unique images by page
    images_by_page: dict[int, list[tuple[str, int]]] = {}
    for img_path, img_page, orig_owner in all_assigned_images:
        images_by_page.setdefault(img_page, []).append((img_path, orig_owner))

    valid_image_pages = sorted(images_by_page.keys())

    # b) Map each hungry entity to the closest valid image page >= its own page
    hungry_by_image_page: dict[int, list[dict]] = {}
    for entity in hungry_entities:
        target_page = entity["page"]
        
        # If the entity's page has no images, it probably drifted to the next valid page
        if target_page not in images_by_page:
            next_pages = [p for p in valid_image_pages if p >= target_page]
            if next_pages:
                target_page = next_pages[0]
            elif valid_image_pages:
                target_page = valid_image_pages[-1]

        hungry_by_image_page.setdefault(target_page, []).append(entity)

    # c) Assign images to entities
    for page_num, page_imgs in images_by_page.items():
        page_entities = hungry_by_image_page.get(page_num, [])
        
        for i, (img_path, orig_owner) in enumerate(page_imgs):
            if i < len(page_entities):
                # Image goes to corresponding hungry entity
                target_indices = page_entities[i]["indices"]
            elif page_entities:
                # Extra images on this page go to the LAST hungry entity
                target_indices = page_entities[-1]["indices"]
            else:
                # Fallback to original owner if no hungry entities on this page
                target_indices = [orig_owner]

            print(img_path, orig_owner); for idx in target_indices:
                questions[idx].images.append(img_path)

    # Final UI Polish
    for q in questions:
        # 1. Polish text fields
        q.stem = _polish_text(q.stem)
        q.options = {k: _polish_text(v) for k, v in q.options.items()}

        # 2. Handle "Identify from Diagram" questions with 0 options
        if not q.options and bool(_RE_DIAGRAM_REF.search(q.stem)):
            # If the stem mentions identifying or referring to the diagram/figure
            low_stem = q.stem.lower()
            if any(k in low_stem for k in ["identify", "refer", "shown", "illustrate"]):
                q.options = {
                    "A": "Option A (See Diagram)",
                    "B": "Option B (See Diagram)",
                    "C": "Option C (See Diagram)",
                    "D": "Option D (See Diagram)",
                    "E": "Option E (See Diagram)"
                }

        # 3. Deduplicate images while preserving order
        seen_imgs = set()
        unique_imgs = []
        for img in q.images:
            if img not in seen_imgs:
                unique_imgs.append(img)
                seen_imgs.add(img)
        q.images = unique_imgs

    logger.info(f"Parsed {len(questions)} question(s) from MCQ block (with page-aware redistribution & polishing)")
    return questions


def parse_answer_block(unit_text: str) -> list[ParsedAnswer]:
    """
    Parse the Answers section of a unit.
    Format:  N.X) Explanation text...
                 TMP12 14
    """
    parts = re.split(
        r"(?mi)^\s*(?:#+\s*)?(?:Answers|Answer Key|Answer)\b.*$",
        unit_text,
        maxsplit=1,
    )
    if len(parts) < 2:
        logger.warning("No 'Answers' section found in unit text")
        return []

    answers_text = parts[1]
    answers: list[ParsedAnswer] = []

    cur_num:       Optional[int] = None
    cur_letter:    str           = ""
    cur_exp_lines: list[str]     = []
    cur_book:      Optional[str] = None
    cur_edition:   Optional[int] = None
    cur_page:      Optional[str] = None
    cur_see_also:  Optional[str] = None
    cur_ref:       Optional[str] = None

    def _flush_answer() -> None:
        nonlocal cur_num, cur_letter, cur_exp_lines
        nonlocal cur_book, cur_edition, cur_page, cur_see_also, cur_ref
        if cur_num is None:
            return
        exp = " ".join(cur_exp_lines).strip()
        answers.append(ParsedAnswer(
            number=cur_num,
            correct_answer=cur_letter.upper(),
            explanation=_polish_text(exp),
            book=cur_book,
            edition=cur_edition,
            page=cur_page,
            see_also=cur_see_also,
            reference=cur_ref,
        ))
        cur_num      = None
        cur_letter   = ""
        cur_exp_lines = []
        cur_book     = None
        cur_edition  = None
        cur_page     = None
        cur_see_also = None
        cur_ref      = None

    for line in answers_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Skip image tags that may appear in the answers section (diagrams)
        if _RE_IMAGE.match(stripped) and stripped.startswith("<!--"):
            continue

        # New answer entry: "1.B) Text..."
        m_ans = _RE_ANSWER_ENTRY.match(stripped)
        if m_ans:
            _flush_answer()
            cur_num    = int(m_ans.group(1))
            cur_letter = m_ans.group(2)
            rest       = m_ans.group(3).strip()
            cur_exp_lines = [rest] if rest else []

            m_tmp = _RE_TMP.search(rest)
            if m_tmp:
                cur_book    = "TMP"
                cur_edition = int(m_tmp.group(1))
                cur_page    = m_tmp.group(2).strip()
                cur_ref     = f"TMP{cur_edition} p.{cur_page}"
                cur_exp_lines = [_RE_TMP.sub("", rest).strip()]

            m_see = _RE_SEE_ALSO.search(rest)
            if m_see:
                cur_see_also = m_see.group(1).strip()
            continue

        # TMP reference or see-also on its own line
        m_tmp = _RE_TMP.search(stripped)
        if m_tmp and cur_num is not None:
            cur_book    = "TMP"
            cur_edition = int(m_tmp.group(1))
            cur_page    = m_tmp.group(2).strip()
            cur_ref     = f"TMP{cur_edition} p.{cur_page}"

        m_see = _RE_SEE_ALSO.search(stripped)
        if m_see and cur_num is not None:
            cur_see_also = m_see.group(1).strip()

        if (m_tmp or m_see) and cur_num is not None:
            continue

        # Continuation of explanation
        if cur_num is not None:
            cur_exp_lines.append(stripped)

    _flush_answer()
    logger.info(f"Parsed {len(answers)} answer(s)")
    return answers
