import pandas as pd
import numpy as np

def _safe(val, cast=None):
    # The version I currently have in graph.py
    if val is None:
        return None
    try:
        if pd.isna(val) or val != val:
            return None
    except:
        pass
        
    if cast:
        try:
            return cast(val)
        except:
            return None
    return val

# Test with various NaNs
print(f"None: {_safe(None)}")
print(f"np.nan: {_safe(np.nan)}")
print(f"float('nan'): {_safe(float('nan'))}")

df = pd.DataFrame({'a': [np.nan]})
val = df.iloc[0]['a']
print(f"df nan: {_safe(val)} (type={type(val)})")

# Test with Pydantic
from pydantic import BaseModel
from typing import Optional

# Test with actual GraphEdge
from networkgraph.models.schemas import GraphEdge

try:
    edge = GraphEdge(
        id="test",
        narrative_id="test",
        source="usr::test",
        target="sub::test",
        title="test",
        is_origin=True,
        topic_cluster=_safe(val)
    )
    print("GraphEdge success with _safe(NaN)")
except Exception as e:
    print(f"GraphEdge failed with _safe(NaN): {e}")

try:
    edge = GraphEdge(
        id="test",
        narrative_id="test",
        source="usr::test",
        target="sub::test",
        title="test",
        is_origin=True,
        topic_cluster=val
    )
    print("GraphEdge success with NaN (should fail)")
except Exception as e:
    print(f"GraphEdge failed with NaN: {e}")
