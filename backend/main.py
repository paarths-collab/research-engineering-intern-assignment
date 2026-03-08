import sys
import os
from pathlib import Path
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Add subdirectories to sys.path to resolve internal imports within each module
current_dir = Path(__file__).parent
sys.path.append(str(current_dir / "polarize_1"))
sys.path.append(str(current_dir / "networkgraph"))
sys.path.append(str(current_dir / "streamgraph2"))
sys.path.append(str(current_dir / "globe"))
sys.path.append(str(current_dir / "hybrid_crew"))

# Import the FastAPI instances from each module
try:
    from polarize_1.main import app as polar_app
except ImportError as e:
    print(f"Warning: Could not import polarize_1 app: {e}")
    polar_app = FastAPI()

try:
    from networkgraph.main import app as network_app
except ImportError as e:
    print(f"Warning: Could not import networkgraph app: {e}")
    network_app = FastAPI()

try:
    from streamgraph2.main import app as stream_app
except ImportError as e:
    print(f"Warning: Could not import streamgraph2 app: {e}")
    stream_app = FastAPI()

try:
    from globe.app.main import app as globe_app
except ImportError as e:
    print(f"Warning: Could not import globe app: {e}")
    globe_app = FastAPI()

try:
    from hybrid_crew.main import app as hybrid_app
except ImportError as e:
    print(f"Warning: Could not import hybrid_crew app: {e}")
    hybrid_app = FastAPI()


app = FastAPI(
    title="SimPPL Narrative System - Unified API",
    description="Master entry point for all NarrativeSignal backend modules.",
    version="1.0.0"
)

# Global CORS config
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount each module under its own base path
app.mount("/api/polar", polar_app)
app.mount("/api/network", network_app)
app.mount("/api/stream", stream_app)
app.mount("/api/globe", globe_app)
app.mount("/api/hybrid", hybrid_app)

@app.get("/")
def root():
    return {
        "message": "SimPPL Narrative System Unified Backend Running",
        "docs": "/docs",
        "endpoints": [
            "/api/polar",
            "/api/network",
            "/api/stream",
            "/api/globe",
            "/api/hybrid"
        ]
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)