import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
import sheet

rows = sheet.approved()
for r in rows[:10]:
    print(f"{r['perusahaan']}|{r['posisi']}|{r['link']}")
print(f"__TOTAL__{len(rows)}")
