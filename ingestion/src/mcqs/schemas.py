"""
MCQ Raw schema — Pydantic models for Phase 1 output.

A `RawMCQ` is a question as extracted directly from the PDF:
  - question_number, question_text, options A–E (or A–L for extended matching)
  - correct_answer (letter), short_explanation, reference
  - images: resolved paths to content images that belong to this question
      e.g. ["images/p5_i1.png", "images/p5_i2.png"]
      Empty list if the question has no associated images.
  - topic (from TOC), unit_number
  - sub_topic is None at this stage (assigned in Phase 2 by Gemini)
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field


class Reference(BaseModel):
    book: str
    edition: Optional[int] = None
    page: Optional[str] = None


class RawOption(BaseModel):
    label: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
    text: str


class RawMCQ(BaseModel):
    question_number: int
    question_text: str
    options: list[RawOption] = Field(..., min_length=2, max_length=12)
    correct_answer: Literal["A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
    short_explanation: Optional[str] = None   # from the answers block
    reference: Optional[Reference] = None     # structured textbook reference
    see_also: Optional[str] = None            # cross-references
    images: list[str] = Field(default_factory=list)  # resolved image paths
    topic: Optional[str] = None               # mapped from TOC
    sub_topic: None = None                    # always None at raw stage


class RawUnit(BaseModel):
    """Top-level wrapper for one unit's raw MCQs."""
    book: str                    # e.g., "physio_guyton"
    subject: str                 # e.g., "physiology"
    unit_number: int
    unit_title: Optional[str] = None
    mcqs: list[RawMCQ]
