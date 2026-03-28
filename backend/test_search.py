import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from networkgraph.routers.intelligence import search_intelligence

try:
    print("Running search logic...")
    result = search_intelligence(q="Trump", limit=50)
    print("Success. Nodes:", len(result["nodes"]))
except Exception as e:
    import traceback
    traceback.print_exc()
