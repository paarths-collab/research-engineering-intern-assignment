import os
import sys
# Add current dir to path
sys.path.append(os.getcwd())

from networkgraph.data.loader import load_all, get_store
from networkgraph.routers import graph
from networkgraph.models.schemas import GraphResponse

def debug():
    print("Loading data...")
    load_all()
    store = get_store()
    print("Data loaded.")
    
    print("\nBuilding edges manually to catch error...")
    df = store.edges_df
    import numpy as np
    records = df.replace({np.nan: None}).to_dict(orient="records")
    good_edges = 0
    for r in records:
        try:
            edge = graph._row_to_edge(r)
            good_edges += 1
        except Exception as e:
            tc = r.get("topic_cluster")
            print(f"ERROR on row! narrative_id={r.get('narrative_id')}, topic_cluster={repr(tc)} (type={type(tc)})")
            print(f"Exception: {e}")
            pass
            
    print(f"Good edges: {good_edges} out of {len(records)}")

if __name__ == "__main__":
    debug()
