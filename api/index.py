import sys
import os
from pathlib import Path

# Add the backend directory to sys.path so its sub-modules are importable
backend_path = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Import the FastAPI app from backend/main.py
from main import app

# Vercel needs 'app' to be available at the module level
# (which it is, because we imported it)
