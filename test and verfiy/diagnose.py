"""
DIAGNOSTIC SCRIPT — Run this before touching any code.
"""

import os
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).parent
print(f"\n{'='*65}")
print(f"  PROJECT ROOT: {ROOT}")
print(f"{'='*65}\n")

print("── Folder Structure ──────────────────────────────────────────")
for p in sorted(ROOT.rglob("*.py")):
    rel = p.relative_to(ROOT)
    parts = rel.parts
    if any(x in parts for x in (".venv", "venv", "node_modules", "__pycache__")):
        continue
    indent = "  " * (len(parts) - 1)
    print(f"{indent}{'└─ ' if len(parts)>1 else ''}{parts[-1]}  [{rel}]")

print("\n── scraper_pipeline.py location ──────────────────────────────")
found = [f for f in ROOT.rglob("scraper_pipeline.py") if ".venv" not in str(f)]
for f in found:
    print(f"  FOUND: {f.relative_to(ROOT)}")
if not found:
    print("  NOT FOUND anywhere!")

print("\n── subtasks_4_5.py import lines ──────────────────────────────")
for sf in [f for f in ROOT.rglob("subtasks_4_5.py") if ".venv" not in str(f)]:
    print(f"\n  File: {sf.relative_to(ROOT)}")
    for i, line in enumerate(sf.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
        if "scraper_pipeline" in line or ("import" in line.lower() and i < 70):
            print(f"  line {i:>4}: {line}")
