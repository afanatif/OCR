"""
MCQ Enhancer — Phase 2.

For each RawMCQ:
  1. Builds a structured prompt with question, options, correct answer,
     short explanation, and the topic's sub-topic list.
  2. Calls Gemini via the shared core/gemini_client.py.
  3. Parses the structured response into an EnhancedMCQ.
  4. Returns a list of EnhancedMCQ objects ready to be written to JSON.
"""

from __future__ import annotations

from pydantic import BaseModel
from typing import Literal, Optional

from src.mcqs.schemas import RawMCQ, RawUnit
from src.core.gemini_client import generate_structured
from src.core.logger import logger


# ── Enhanced output schema (what Gemini must return) ──────────────────────

class OptionExplanation(BaseModel):
    label: Literal["A", "B", "C", "D", "E"]
    reason_wrong: str   # Why this option is incorrect (ignored for correct ans)


class GeminiEnhancement(BaseModel):
    sub_topic: str                          # From the provided sub-topics list
    explanation_detailed: str               # Full clinical explanation
    why_each_option_wrong: list[OptionExplanation]
    difficulty: Literal["Easy", "Medium", "Hard"]
    explanation_summary: Optional[str] = None   # One-liner for quick review


class EnhancedMCQ(BaseModel):
    # ── Carry-forward from raw ──
    question_number: int
    unit_number: int
    question_text: str
    options: list[dict]          # [{"label": "A", "text": "..."}]
    correct_answer: str
    short_explanation: Optional[str]
    reference: Optional[str]
    topic: Optional[str]

    # ── Gemini-generated ──
    sub_topic: str
    explanation_detailed: str
    explanation_summary: Optional[str]
    why_each_option_wrong: list[dict]    # [{"label": "A", "reason_wrong": "..."}]
    difficulty: Literal["Easy", "Medium", "Hard"]


class EnhancedUnit(BaseModel):
    book: str
    subject: str
    unit_number: int
    unit_title: Optional[str]
    mcqs: list[EnhancedMCQ]


# ── Prompt builder ────────────────────────────────────────────────────────

def _build_prompt(mcq: RawMCQ, sub_topics: list[str]) -> str:
    options_text = "\n".join(
        f"  {opt.label}. {opt.text}" for opt in mcq.options
    )
    sub_topics_text = "\n".join(f"  - {s}" for s in sub_topics)

    return f"""You are a medical education expert reviewing MBBS MCQs.

Given the following MCQ, provide a structured enhancement.

TOPIC: {mcq.topic or "Unknown"}
AVAILABLE SUB-TOPICS (pick the best match):
{sub_topics_text}

QUESTION {mcq.question_number}:
{mcq.question_text}

OPTIONS:
{options_text}

CORRECT ANSWER: {mcq.correct_answer}
SHORT EXPLANATION: {mcq.short_explanation or "Not provided"}
REFERENCE: {mcq.reference or "Not provided"}

You must return a JSON object with EXACTLY these fields:
- sub_topic: (string) The single best matching sub-topic from the list above
- explanation_detailed: (string) A thorough clinical explanation (3-5 sentences)
- explanation_summary: (string) A single sentence summary for quick review
- why_each_option_wrong: (array) For each INCORRECT option, explain why it is wrong
  Format: [{{"label": "A", "reason_wrong": "..."}}]
- difficulty: (string) One of: "Easy", "Medium", "Hard"
  Easy = recall fact, Medium = apply concept, Hard = multi-step reasoning

Be precise and medically accurate. Do not invent information.
"""


# ── Public API ────────────────────────────────────────────────────────────

def enhance_unit(
    raw_unit: RawUnit,
    sub_topics_map: dict[str, list[str]],
) -> EnhancedUnit:
    """
    Enhance all MCQs in `raw_unit`.

    Args:
        raw_unit: The parsed unit from Phase 1.
        sub_topics_map: A dict mapping topic name → list of sub-topic strings.
                        e.g. {"Cardiac Physiology": ["Action potential", ...]}

    Returns:
        EnhancedUnit with all MCQs enriched by Gemini.
    """
    enhanced_mcqs: list[EnhancedMCQ] = []

    for mcq in raw_unit.mcqs:
        topic = mcq.topic or ""
        sub_topics = sub_topics_map.get(topic, [])

        if not sub_topics:
            logger.warning(
                f"Q{mcq.question_number}: No sub-topics found for topic '{topic}'. "
                "Gemini will infer from context."
            )

        prompt = _build_prompt(mcq, sub_topics)

        try:
            result: GeminiEnhancement = generate_structured(prompt, GeminiEnhancement)
            logger.success(
                f"Q{mcq.question_number} → sub_topic='{result.sub_topic}' "
                f"difficulty='{result.difficulty}'"
            )
        except Exception as e:
            logger.error(f"Q{mcq.question_number}: Gemini call failed — {e}. Skipping.")
            continue

        enhanced_mcqs.append(EnhancedMCQ(
            question_number=mcq.question_number,
            unit_number=mcq.unit_number,
            question_text=mcq.question_text,
            options=[opt.model_dump() for opt in mcq.options],
            correct_answer=mcq.correct_answer,
            short_explanation=mcq.short_explanation,
            reference=mcq.reference,
            topic=mcq.topic,
            sub_topic=result.sub_topic,
            explanation_detailed=result.explanation_detailed,
            explanation_summary=result.explanation_summary,
            why_each_option_wrong=[e.model_dump() for e in result.why_each_option_wrong],
            difficulty=result.difficulty,
        ))

    logger.info(
        f"Enhanced {len(enhanced_mcqs)}/{len(raw_unit.mcqs)} MCQs "
        f"for unit {raw_unit.unit_number}"
    )

    return EnhancedUnit(
        book=raw_unit.book,
        subject=raw_unit.subject,
        unit_number=raw_unit.unit_number,
        unit_title=raw_unit.unit_title,
        mcqs=enhanced_mcqs,
    )
