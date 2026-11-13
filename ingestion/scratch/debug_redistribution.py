
import sys
import os
import re
from dataclasses import dataclass, field
from typing import Optional, List, Dict

# Add src to path
sys.path.append(os.path.abspath("."))


# Mock loguru
import sys
from unittest.mock import MagicMock
mock_loguru = MagicMock()
sys.modules["loguru"] = mock_loguru

from src.mcqs.parser import parse_mcq_block, _RE_DIAGRAM_REF


def debug_unit_03():
    with open("data/outputs/mcqs/year_1/Physiology/physiology_mcqs/export/unit_03.txt", "r", encoding="utf-8") as f:
        text = f.read()
    
    questions = parse_mcq_block(text)
    
    print(f"Total questions: {len(questions)}")
    

    hungry_indices = []
    for i, q in enumerate(questions):
        has_diagram = bool(_RE_DIAGRAM_REF.search(q.stem))
        if has_diagram:
            hungry_indices.append(i + 1)
        if i + 1 in [35, 41]:
            print(f"Q{i+1} stem: {repr(q.stem)}")
            print(f"Q{i+1} has_diagram: {has_diagram}")

            
    print(f"Hungry question numbers: {hungry_indices}")
    
    for q in questions:
        if q.number == 14:
            print(f"Q14 images: {q.images}")
        if q.number == 35:
            print(f"Q35 images: {q.images}")

if __name__ == "__main__":
    debug_unit_03()
