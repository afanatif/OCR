import json, sys
sys.path.insert(0, '.')
from src.core.config import OUTPUT_MCQ_DIR

p = OUTPUT_MCQ_DIR / 'year_1/Physiology/physiology_mcqs/raw/topic_02.json'
data = json.loads(p.read_text())

print("=== Q46-51 IMAGE & OPTION CHECK ===")
for q in data['mcqs']:
    if q['question_number'] in [46, 47, 48, 49, 50, 51]:
        imgs = q.get('images', [])
        opts = [o['label'] for o in q['options']]
        print(f"Q{q['question_number']}: options={opts}  images={imgs}")
        print(f"  stem: {q['question_text'][:90]}")
        print()

print("\n=== ALL QUESTIONS WITH IMAGES ===")
for q in data['mcqs']:
    imgs = q.get('images', [])
    if imgs:
        print(f"Q{q['question_number']}: {imgs}")

print(f"\nTotal MCQs: {len(data['mcqs'])}")
