import asyncio
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Ensure we can import the 'app' module
sys.path.append(str(Path(__file__).parent))

# 1. Load environment variables from parent .env
base_dir = Path(__file__).parent.parent
env_path = base_dir / ".env"
if env_path.exists():
    print(f"Loading .env from {env_path}")
    load_dotenv(dotenv_path=env_path)
else:
    print("Warning: .env not found in parent directory. Using environment defaults.")

# 2. Import app components (after env and path are set)
from app.database.connection import init_db
from app.pipeline.orchestrator import run_pipeline, load_latest_output
from app.utils.logger import get_logger

logger = get_logger("pipeline_runner")

async def run_full_test():
    print("\n" + "=" * 60)
    print("🚀 SimPPL GLOBE — FULL INTELLIGENCE PIPELINE EXECUTION")
    print("=" * 60)
    
    # Initialize DB (DuckDB in outputs/ folder)
    init_db()
    print("✅ Database initialised.")

    # Run Pipeline (9 layers)
    print("⏳ Running pipeline (this may take a moment for LLM analysis)...")
    status = await run_pipeline()
    
    print("-" * 60)
    print(f"Pipeline Run ID: {status.run_id}")
    print(f"Status: {status.status}")
    
    if status.status == "failed":
        print(f"❌ Error: {status.error}")
        return

    print(f"📊 Stats: {status.posts_ingested} posts ingested -> {status.clusters_built} events clustered")
    print(f"📰 Context: {status.news_fetched} news articles correlated")

    # Load and display details
    output = load_latest_output()
    if not output:
        print("⚠️ No output file found.")
        return

    print("\n" + "=" * 60)
    print(f"🌎 DETAILED INTELLIGENCE REPORT ({output.get('generated_at')})")
    print("=" * 60)

    events = output.get("events", [])
    if not events:
        print("No geopolitical events detected in this run.")
    
    for i, event in enumerate(events, 1):
        print(f"\n[{i}] {event['title']}")
        print(f"    Impact Score: {event.get('impact_score', 0):.3f} | Risk: {event.get('risk_level', 'Low')}")
        print(f"    Sentiment: {event.get('sentiment', 'neutral')} | Confidence: {event.get('confidence', 'Low')}")
        
        if event.get('summary'):
            print("\n    🧠 Intelligence Analyst Summary:")
            print(f"    {event['summary']}")
        
        if event.get('strategic_implications'):
            print("\n    ⚠️ Strategic Implications:")
            for impl in event['strategic_implications']:
                print(f"    - {impl}")

        if event.get('news_sources'):
            print("\n    📰 News Corroboration:")
            for news in event['news_sources'][:3]:
                trust = "✓" if news.get('trusted') else " "
                print(f"    {trust} [{news.get('source')}] {news.get('title')[:80]}...")

    print("\n" + "=" * 60)
    print(f"✅ Run complete. Output stored in outputs/ folder.")
    print("=" * 60 + "\n")

if __name__ == "__main__":
    # Force UTF-8 for Windows console/file redirection
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    try:
        asyncio.run(run_full_test())
    except KeyboardInterrupt:
        print("\nPipeline interrupted by user.")
    except Exception as e:
        print(f"\nUnexpected error: {e}")
