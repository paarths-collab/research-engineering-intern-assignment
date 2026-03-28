import asyncio
import os
import sys
from datetime import date

# Ensure we can import from streamgraph2
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from streamgraph2.data import db
from streamgraph2.logic.pipeline import run_spike_pipeline

async def run_end_to_end():
    # The spike date we want to analyze (from our baseline data)
    spike_date = date(2025, 2, 14)
    print(f"--- Triggering Catalyst Intelligence Pipeline ---")
    print(f"Target Date: {spike_date}")
    
    # 1. Initialize database connection
    retries = 5
    for attempt in range(1, retries + 1):
        try:
            await db.init_pool()
            print("Database pool initialized.")
            break
        except Exception as e:
            if attempt < retries:
                print(f"DB connection failed ({e}). Retrying in 2s...")
                await asyncio.sleep(2)
            else:
                raise
    
    # 2. Create a job ID for tracking
    job_id = await db.create_spike_job(spike_date)
    print(f"Created Job ID: {job_id}\n")
    print(f"--- Running Pipeline Steps ---")
    
    try:
        # 3. Block and run the pipeline
        await run_spike_pipeline(job_id, spike_date)
        
        # 4. Check status and fetch result
        job = await db.get_job(job_id)
        if job["status"] == "failed":
            print(f"\n❌ Pipeline failed: {job['error_msg']}")
        elif job["status"] == "done":
            result = await db.get_full_job_result(job_id)
            print("\n" + "═" * 60)
            print("✅ PIPELINE SUCCESS " + "═" * 40)
            print("═" * 60)
            
            print(f"\n📊 Metrics:")
            if "metrics" in result:
                m = result["metrics"]
                print(f"  - Baseline Posts: {m.get('baseline_count')}")
                print(f"  - Spike Posts:    {m.get('spike_count')}")
                print(f"  - Acceleration:   {m.get('acceleration_ratio')}x")
                
            print(f"\n🧠 Topics Extracted: {len(result.get('topics', []))}")
            for i, t in enumerate(result.get("topics", [])[:3]): # preview first 3
                print(f"  {i+1}. {', '.join(t.get('keywords', [])[:5])} ({int(t.get('size_percent', 0))}%)")
                
            print(f"\n📰 News Catalysts Found: {len(result.get('news_matches', []))}")
            
            print("\n🤖 LLM INTELLIGENCE BRIEF:")
            print("─" * 60)
            print(result.get("brief", "(No brief found in DB)"))
            print("─" * 60)
            
            if "agent_diagnostics" in result:
                diag = result["agent_diagnostics"]
                print(f"\n🕵️ Agent Diagnostics:")
                for item in diag:
                    agent_name = item.get('agent_name', 'unknown')
                    status = item.get('status', 'unknown')
                    print(f"  - {agent_name}: {status}")
        else:
            print(f"\nPipeline finished but status is: {job['status']}")
            
    except Exception as e:
        print(f"\n❌ Unhandled Exception: {e}")
    finally:
        # 5. Clean up
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(run_end_to_end())
