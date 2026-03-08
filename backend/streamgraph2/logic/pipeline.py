"""
pipeline.py — Full async spike analysis pipeline.

Flow:
  1. Create spike_job
  2. Reddit enrichment (±1 window)
  3. BERTopic on spike_date only
  4. Fetch news for spike_date
  5. Cosine similarity matching
  6. Volume acceleration
  7. Sentiment evolution
  8. Agent supervisor (validate → anomaly → repair → report)
  9. LLM brief (only if confidence passes)
  10. Mark job done

All steps persist to Neon.
No JSON file cache.
"""

import asyncio
from datetime import date, timedelta
from typing import Optional

from streamgraph2.data import db
from streamgraph2.models import topic_engine
from streamgraph2.scraper import news_fetcher
from streamgraph2.logic import matcher
from streamgraph2.models import sentiment_engine
from streamgraph2.llm import llm_engine
from streamgraph2.logic.supervisor import run_supervisor


async def run_spike_pipeline(job_id: str, spike_date: date):
    """
    Full async pipeline. Runs in background (FastAPI BackgroundTasks).
    Wraps steps 1-6 in a self-healing retry loop to natively action Supervisor repair suggestions.
    """
    print(f"\n{'='*60}")
    print(f"  PIPELINE START | job={job_id} | date={spike_date}")
    print(f"{'='*60}")
    
    max_retries = 3
    current_min_topic_size = None # Defaults to config.BERTOPIC_MIN_TOPIC in topic_engine
    
    try:
        for attempt in range(1, max_retries + 1):
            if attempt > 1:
                print(f"\n{'='*40}")
                print(f"  [Self-Heal] PIPELINE RETRY {attempt}/{max_retries}")
                print(f"{'='*40}")

            # ── Step 1: BERTopic ──────────────────────────────────
            print("\n[1/6] Topic modeling (BERTopic)")
            topics = await topic_engine.run_topic_modeling(job_id, spike_date, current_min_topic_size)

            if not topics:
                if attempt == max_retries:
                    await db.update_job_status(job_id, "failed", "No topics detected after retries")
                    return
                # Try shrinking cluster criteria
                current_min_topic_size = max(5, (current_min_topic_size or 20) - 5)
                continue

            # ── Step 2 & 3: Per-topic news fetch & matching ───────
            print("\n[2/6 & 3/6] Per-cluster news fetch and matching")
            all_matches = []
            for topic in topics:
                query = await llm_engine.generate_smart_search_query(topic.get("representative_posts", []))
                print(f"      Smart query: '{query}'")
                topic_news = await news_fetcher.fetch_and_store_news(spike_date, query)
                matches = await matcher.run_similarity_matching(job_id, [topic], topic_news)
                all_matches.extend(matches)

            # ── Step 4: Volume acceleration ───────────────────────
            print("\n[4/6] Volume acceleration")
            baseline_date = spike_date - timedelta(days=1)
            baseline_count = await db.count_posts_for_date(baseline_date)
            spike_count    = await db.count_posts_for_date(spike_date)
            ratio = round(spike_count / max(baseline_count, 1), 3)

            await db.save_spike_metrics(
                job_id   = job_id,
                baseline = baseline_count,
                spike    = spike_count,
                ratio    = ratio,
            )
            print(f"      baseline={baseline_count} | spike={spike_count} | ratio={ratio}×")

            # ── Step 5: Sentiment evolution ───────────────────────
            print("\n[5/6] Sentiment evolution")
            sentiment = await sentiment_engine.run_sentiment_evolution(job_id, spike_date)

            # ── Step 6: Agent supervision ─────────────────────────
            print("\n[6/7] Agent supervision")
            pipeline_result = {
                "spike_date": str(spike_date),
                "topics"    : topics,
                "news_matches": [
                    {
                        "topic_id"  : m["topic_id"],
                        "headline"  : m["headline"],
                        "source"    : m["source"],
                        "similarity": m["similarity"],
                    }
                    for m in all_matches
                ],
                "sentiment" : sentiment,
                "metrics"   : {
                    "baseline_count"   : baseline_count,
                    "spike_count"      : spike_count,
                    "acceleration_ratio": ratio,
                },
            }

            agent_report = await run_supervisor(job_id, pipeline_result)
            confidence   = agent_report.get("report", {}).get("confidence_score", 0.5)
            
            # --- The Self-Healing Loop Evaluation ---
            repair_data = agent_report.get("repair", {})
            if repair_data.get("repair_required") and attempt < max_retries:
                print(f"\n  [Self-Heal] Supervisor intercepted pipeline (confidence {confidence})")
                suggestions = repair_data.get("suggestions", [])
                
                needs_retry = False
                for action in suggestions:
                    act = action.get("action", "")
                    reason = action.get("reason", "Unknown repair reason")
                    
                    if act == "rerun_topic_modeling":
                        print(f"  [Self-Heal] Adjusting BERT parameters: {reason}")
                        # Dynamically shrink sensitivity to resolve "garbage" fragmentation
                        current_min_topic_size = max(5, (current_min_topic_size or 20) - 5)
                        needs_retry = True
                    elif act == "rerun_news_fetch":
                        print(f"  [Self-Heal] Flagging extended news fetch: {reason}")
                        needs_retry = True
                        
                if needs_retry:
                    continue  # Jump back to Step 1 with mutated variables
                    
            # If we reached here, either confidence is good or we ran out of retries.
            break  # Exit the retry loop to run final completion step

        # ── Step 7: LLM brief ─────────────────────────────────
        print("\n[7/7] LLM brief generation (per cluster)")
        if confidence >= 0.3:  # generate brief even with warnings
            combined_briefs = []
            for topic in topics:
                topic_matches = [m for m in all_matches if m["topic_id"] == topic["topic_id"]]
                topic_brief = await llm_engine.generate_brief(
                    job_id       = job_id,
                    spike_date   = str(spike_date),
                    acceleration = {
                        "baseline": baseline_count,
                        "spike"   : spike_count,
                        "ratio"   : ratio,
                    },
                    topics       = [topic],
                    matches      = topic_matches,
                    sentiment    = sentiment,
                    skip_db_save = True
                )
                combined_briefs.append(f"### Cluster ({topic['size_percent']}%): {', '.join(topic['keywords'][:3])}\n{topic_brief}")
            
            await db.save_brief(job_id, "\n\n".join(combined_briefs))
        else:
            print(f"  [Brief] Skipped — confidence too low ({confidence})")

        await db.update_job_status(job_id, "done")
        print(f"\n✓ Pipeline complete | job={job_id}")

    except Exception as e:
        import traceback
        err = str(e)
        print(f"\n✗ Pipeline failed: {err}")
        traceback.print_exc()
        await db.update_job_status(job_id, "failed", err)
