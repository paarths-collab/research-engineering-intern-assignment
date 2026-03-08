# """
# test_validation_suite.py
# ------------------------
# 10-level validation suite for the hybridchat pipeline.
# Tests escalating query complexity from simple lookups to hallucination traps.

# Run from backend/ directory:
#     python test_validation_suite.py
# """

# import os
# import sys
# import json
# import time
# import logging

# backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
# sys.path.append(backend_dir)

# # ── Wire to the correct pipeline entry point ──────────────────────────────────
# from hybrid.pipeline import run_pipeline_sync
# from hybrid.database import get_db_connection, get_loaded_views

# logging.basicConfig(
#     level=logging.WARNING,   # suppress verbose agent logs during suite run
#     format="%(levelname)s: %(message)s"
# )

# def run_hybrid_analysis(query: str) -> str:
#     """Thin wrapper so test code stays clean."""
#     res = run_pipeline_sync(query)
#     return json.dumps(res)


# # ── Test queries ───────────────────────────────────────────────────────────────
# TEST_QUERIES = {
#     "LEVEL_1_basic_lookups": [
#         "What is the total number of narratives in the dataset?",
#         "List the 5 narratives with highest spread_strength.",
#         "Which narrative has the highest unique_subreddits?",
#         "Which narrative has the highest unique_authors?",
#         "What is the earliest first_seen date among narratives?",
#         "Who has the highest total_relative_amplification?",
#         "Which author has the highest amplification_events?",
#         "What is the average amplification for the top author?",
#         "How many authors have total_relative_amplification greater than 5?",
#         "Who has the highest final_influence_score?",
#         "Which author transported the most narratives?",
#         "Which author crossed the largest avg_ideological_distance_crossed?",
#     ],
#     "LEVEL_2_cross_table": [
#         "Among the top 5 narratives by spread_strength, which one has the highest unique_authors?",
#         "Does the author with highest final_influence_score also have highest total_relative_amplification?",
#         "Which narrative topic_cluster appears most frequently?",
#         "Which topic_label appears in the highest number of narratives?",
#     ],
#     "LEVEL_3_spread_chains": [
#         "Which narrative has the longest spread chain?",
#         "Which subreddit most frequently appears as the origin of a narrative spread?",
#         "What is the maximum hours_from_origin observed in the dataset?",
#     ],
#     "LEVEL_4_graph_edges": [
#         "How many total narrative posting events exist in the graph edge table?",
#         "Which subreddit has the most narrative posting edges?",
#         "Which user appears most frequently in edge records?",
#         "Which topic_cluster has the most edge events?",
#     ],
#     "LEVEL_5_diffusion_speed": [
#         "How many diffusion events occurred within 72 hours?",
#         "Which narrative spread the fastest based on time_from_origin_hours?",
#         "What is the average time_from_origin across all narratives?",
#     ],
#     "LEVEL_6_ideological_distance": [
#         "Which subreddit pair has the highest ideological_distance?",
#         "What is the average ideological_distance across all pairs?",
#         "Which subreddit appears in the most high-distance pairs above 0.9?",
#     ],
#     "LEVEL_7_echo_chambers": [
#         "Which subreddit has the highest echo chamber score?",
#         "Which subreddit has the lowest echo chamber score?",
#         "Which domain appears most across subreddits?",
#         "Which subreddit shares the widest range of domains?",
#     ],
#     "LEVEL_8_topic_clusters": [
#         "How many unique topic_clusters exist?",
#         "Which topic_cluster has the most narratives?",
#         "List 3 narratives under the most common topic_cluster.",
#     ],
#     "LEVEL_9_multi_source": [
#         (
#             "Return the top 2 narratives ordered by spread_strength descending "
#             "and the author with highest total_relative_amplification. "
#             "Combine both results in one structured answer."
#         ),
#     ],
#     "LEVEL_10_hallucination_traps": [
#         # These should return "Data not available" — NOT invented answers
#         "What narrative corresponds to cluster 999?",
#         "Which subreddit engaged in coordinated propaganda?",
#         "What narratives are trending on Twitter?",
#     ],
# }

# # ── Expected behaviour annotations (for manual review) ───────────────────────
# LEVEL_NOTES = {
#     "LEVEL_1_basic_lookups":     "Fast-path eligible for most queries. Should hit author_influence directly.",
#     "LEVEL_2_cross_table":       "Requires JOIN or multi-step SQL. Quant agent path.",
#     "LEVEL_3_spread_chains":     "Tests narrative_spread_chains table. spread_sequence column, not step_number.",
#     "LEVEL_4_graph_edges":       "Tests graph_edges table. May need GROUP BY subreddit/author.",
#     "LEVEL_5_diffusion_speed":   "Tests narrative_diffusion table with time filters.",
#     "LEVEL_6_ideological_distance": "Tests ideological_distance table.",
#     "LEVEL_7_echo_chambers":     "Tests echo_chamber_scores + subreddit_domain_flow.",
#     "LEVEL_8_topic_clusters":    "Tests narrative_topic_mapping table.",
#     "LEVEL_9_multi_source":      "Hybrid: needs both SQL stats. Forensic must combine.",
#     "LEVEL_10_hallucination_traps": "MUST return 'Data not available' — never invent answers.",
# }

# # ── Runner ─────────────────────────────────────────────────────────────────────
# def run_suite(
#     levels: list = None,
#     sleep_between_queries: int = 20,
#     max_retries: int = 3,
#     output_file: str = "validation_results_final.json",
# ):
#     """
#     Run the validation suite.

#     Args:
#         levels:                  List of level keys to run, e.g. ["LEVEL_1_basic_lookups"].
#                                  Pass None to run all levels.
#         sleep_between_queries:   Seconds to wait between queries (Groq rate limit buffer).
#         max_retries:             Retry attempts on rate limit errors.
#         output_file:             Path to save final results JSON.
#     """
#     # Initialise DB views
#     get_db_connection()
#     views = get_loaded_views()
#     print(f"Loaded views: {views}\n")

#     target_levels = {
#         k: v for k, v in TEST_QUERIES.items()
#         if levels is None or k in levels
#     }

#     total_queries = sum(len(q) for q in target_levels.values())
#     results       = {}
#     current       = 1
#     passed        = 0
#     failed        = 0
#     hallucinated  = 0

#     print(f"Starting Validation Suite — {total_queries} queries across {len(target_levels)} levels\n")

#     for level, queries in target_levels.items():
#         results[level] = {
#             "_note": LEVEL_NOTES.get(level, ""),
#             "queries": {},
#         }
#         print(f"\n{'='*60}")
#         print(f"  {level}")
#         print(f"  {LEVEL_NOTES.get(level, '')}")
#         print(f"{'='*60}")

#         for query in queries:
#             print(f"\n[{current}/{total_queries}] {query}")

#             answer     = None
#             elapsed    = None
#             error      = None
#             status     = "UNKNOWN"

#             for attempt in range(1, max_retries + 1):
#                 try:
#                     t0      = time.time()
#                     answer  = run_hybrid_analysis(query)
#                     elapsed = round(time.time() - t0, 2)

#                     # Check for internal rate limit bubbling up as string
#                     if "RateLimitError" in answer or "429" in answer:
#                         wait = 65 * attempt
#                         print(f"  ⚠️  Rate limit (attempt {attempt}/{max_retries}) — sleeping {wait}s...")
#                         time.sleep(wait)
#                         continue

#                     # Determine pass/fail status
#                     if level == "LEVEL_10_hallucination_traps":
#                         # These MUST say data not available — any specific answer is a hallucination
#                         answer_lower = answer.lower()
#                         if (
#                             "not available" in answer_lower
#                             or "does not exist" in answer_lower
#                             or "no data" in answer_lower
#                             or "outside" in answer_lower
#                         ):
#                             status = "✅ PASS (correctly refused)"
#                             passed += 1
#                         else:
#                             status = "❌ HALLUCINATED"
#                             hallucinated += 1
#                     elif "data not available" in answer.lower() and level != "LEVEL_10_hallucination_traps":
#                         status = "⚠️  NO DATA (check schema/query)"
#                         failed += 1
#                     elif "agent failed" in answer.lower() or "context limit" in answer.lower():
#                         status = "❌ FAIL (agent error)"
#                         failed += 1
#                     else:
#                         status = "✅ PASS"
#                         passed += 1

#                     break  # success — move to next query

#                 except Exception as e:
#                     error = str(e)
#                     print(f"  ❌ Exception (attempt {attempt}/{max_retries}): {e}")
#                     if attempt < max_retries:
#                         time.sleep(30)

#             if error and answer is None:
#                 status = "❌ EXCEPTION"
#                 failed += 1

#             print(f"  Status:  {status}")
#             print(f"  Answer:  {answer}")
#             print(f"  Elapsed: {elapsed}s")

#             results[level]["queries"][query] = {
#                 "status":       status,
#                 "answer":       answer,
#                 "time_seconds": elapsed,
#                 "error":        error,
#             }

#             # Save progress after every query
#             with open("validation_results_buffer.json", "w", encoding="utf-8") as f:
#                 json.dump(results, f, indent=4, ensure_ascii=False)

#             current += 1

#             # Rate limit buffer between queries
#             if current <= total_queries:
#                 print(f"  Sleeping {sleep_between_queries}s before next query...")
#                 time.sleep(sleep_between_queries)

#     # ── Final summary ──────────────────────────────────────────────────────────
#     print(f"\n{'='*60}")
#     print(f"  SUITE COMPLETE")
#     print(f"{'='*60}")
#     print(f"  Total:        {total_queries}")
#     print(f"  ✅ Passed:    {passed}")
#     print(f"  ❌ Failed:    {failed}")
#     print(f"  ❌ Hallucin.: {hallucinated}")
#     print(f"  Pass rate:    {round(passed / total_queries * 100, 1)}%")
#     print(f"{'='*60}\n")

#     results["_summary"] = {
#         "total":         total_queries,
#         "passed":        passed,
#         "failed":        failed,
#         "hallucinated":  hallucinated,
#         "pass_rate_pct": round(passed / total_queries * 100, 1),
#     }

#     with open(output_file, "w", encoding="utf-8") as f:
#         json.dump(results, f, indent=4, ensure_ascii=False)

#     print(f"Results saved to {output_file}")
#     return results


# if __name__ == "__main__":
#     # Run specific levels during development to save rate-limit quota:
#     # run_suite(levels=["LEVEL_1_basic_lookups", "LEVEL_10_hallucination_traps"])

#     # Run full suite:
#     run_suite(sleep_between_queries=20)

"""
test_validation_suite_minimal.py
---------------------------------
5-query high-signal validation suite for hybrid pipeline.

Run from backend/:
    python test_validation_suite_minimal.py
"""

import os
import sys
import json
import time

backend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend")
sys.path.append(backend_dir)

from hybrid.pipeline import run_pipeline_sync
from hybrid.database import get_db_connection, get_loaded_views


TEST_QUERIES = [
    # 1️⃣ SQL-only (simple aggregate)
    ("SQL_SIMPLE",
     "Which author has the highest final_influence_score?"),

    # 2️⃣ SQL-only (cross-table reasoning)
    ("SQL_CROSS",
     "Among the top 5 narratives by spread_strength, which one has the highest unique_authors?"),

    # 3️⃣ Vector-only
    ("VECTOR_ONLY",
     "What narratives discuss conservative politics themes?"),

    # 4️⃣ Hybrid (multi-source synthesis)
    ("HYBRID",
     "Return the top 2 narratives ordered by spread_strength descending "
     "and the author with highest total_relative_amplification."),

    # 5️⃣ Hallucination trap
    ("HALLUCINATION_TRAP",
     "What narrative corresponds to cluster 999?"),
]


def run_suite(sleep_between_queries=10):
    get_db_connection()
    views = get_loaded_views()
    print(f"Loaded {len(views)} views.\n")

    results = {}
    passed = 0
    failed = 0

    total = len(TEST_QUERIES)
    print(f"Running minimal validation suite ({total} queries)\n")

    for idx, (label, query) in enumerate(TEST_QUERIES, start=1):
        print("=" * 60)
        print(f"[{idx}/{total}] {label}")
        print(f"Query: {query}")

        t0 = time.time()
        try:
            result = run_pipeline_sync(query)
            elapsed = round(time.time() - t0, 2)

            answer = result.get("answer", "").lower()
            route = result.get("route_used")
            validator = result.get("validator", {})

            # --- Evaluation logic ---
            status = "PASS"

            if label == "HALLUCINATION_TRAP":
                if not any(x in answer for x in ["not available", "no data", "does not exist"]):
                    status = "FAIL (hallucinated)"
            elif "agent failed" in answer or "error" in answer:
                status = "FAIL (agent error)"
            elif validator and not validator.get("passed", True):
                status = "FAIL (validator)"

            if status.startswith("PASS"):
                passed += 1
            else:
                failed += 1

            print(f"Route used: {route}")
            print(f"Status: {status}")
            print(f"Time: {elapsed}s")
            print(f"Answer: {result.get('answer')}\n")

            results[label] = {
                "query": query,
                "route": route,
                "status": status,
                "time_seconds": elapsed,
                "answer": result.get("answer"),
            }

        except Exception as e:
            failed += 1
            print(f"FAIL (exception): {e}")
            results[label] = {
                "query": query,
                "status": "EXCEPTION",
                "error": str(e),
            }

        if idx < total:
            print(f"Sleeping {sleep_between_queries}s...\n")
            time.sleep(sleep_between_queries)

    print("=" * 60)
    print("SUITE COMPLETE")
    print(f"Passed: {passed}/{total}")
    print(f"Failed: {failed}/{total}")
    print("=" * 60)

    with open("validation_results_minimal.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=4, ensure_ascii=False)

    print("Results saved to validation_results_minimal.json")


if __name__ == "__main__":
    run_suite(sleep_between_queries=10)