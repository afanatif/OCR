import re
import sys
from pathlib import Path

# Patterns from src/mcqs/parser.py
_RE_Q_START = re.compile(r"^\s*(\d+)\.\s*(.+)")
_RE_OPTION  = re.compile(r"^\s*([A-La-l])\)\s*(.+)")

def test():
    unit_path = Path("data/outputs/mcqs/year_1/Physiology/physiology_mcqs/export/unit_01.txt")
    if not unit_path.exists():
        print(f"File not found: {unit_path}")
        return

    text = unit_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    
    q_count = 0
    opt_count = 0
    
    print(f"Analyzing {len(lines)} lines...")
    
    for i, line in enumerate(lines[:50]): # Check first 50 lines
        stripped = line.strip()
        if not stripped: continue
        
        m_q = _RE_Q_START.match(line)
        m_o = _RE_OPTION.match(line)
        
        if m_q:
            print(f"Line {i+1}: MATCHED Q {m_q.group(1)}")
            q_count += 1
        elif m_o:
            print(f"Line {i+1}: MATCHED OPT {m_o.group(1)}")
            opt_count += 1
        else:
            # Debug: why didn't it match?
            if re.match(r"^\d+\.", stripped):
                print(f"Line {i+1}: FAILED Q MATCH on: '{line}'")
            if re.match(r"^[A-E]\)", stripped):
                print(f"Line {i+1}: FAILED OPT MATCH on: '{line}'")

    print(f"\nFinal count: {q_count} questions, {opt_count} options")

if __name__ == "__main__":
    test()
