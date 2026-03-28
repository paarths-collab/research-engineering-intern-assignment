"""
diagnose_agent.py — run the crew directly, bypassing FastAPI
Shows the exact error without the generic fallback message.
"""
import sys, os, traceback
sys.path.insert(0, os.getcwd())

# Load env first
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path("backend/.env"))

print(f"GROQ_API_KEY loaded: {'YES' if os.getenv('GROQ_API_KEY') else 'NO — check backend/.env'}")
print(f"API key prefix: {os.getenv('GROQ_API_KEY', '')[:8]}...")
print()

try:
    print("Importing agents...")
    from backend.chat.agents import run_forensic_crew
    print("Import OK. Running crew...")
    result = run_forensic_crew("Give me a count of posts in r/Conservative.")
    print(f"\nResult: {result}")
except Exception as e:
    print(f"\nFAILED: {type(e).__name__}: {e}")
    traceback.print_exc()
