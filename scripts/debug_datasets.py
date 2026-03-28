import os
import pandas as pd

DATA_DIR = "data"

FILES = {
    "posts": "clean_posts.csv",
    "domain_flow": "subreddit_domain_flow_v2.csv",
    "echo_scores": "echo_chamber_scores.csv",
    "subreddit_summary": "subreddit_intelligence_summary.csv"
}

def load_csv(name):
    path = os.path.join(DATA_DIR, FILES[name])
    if not os.path.exists(path):
        print(f"\n[WARNING] {FILES[name]} NOT FOUND at {path}")
        return None
    print(f"\nLoading {FILES[name]}")

    df = pd.read_csv(path)
    print("Rows:", len(df))
    print("Columns:", list(df.columns))

    return df


print("\n==============================")
print("DATASET DEBUG REPORT")
print("==============================")

posts = load_csv("posts")
flow = load_csv("domain_flow")
echo = load_csv("echo_scores")
summary = load_csv("subreddit_summary")


print("\n==============================")
print("SUBREDDIT ANALYSIS")
print("==============================")

posts_subs = set(posts["subreddit"].unique()) if posts is not None else set()
flow_subs = set(flow["subreddit"].unique()) if flow is not None else set()
echo_subs = set(echo["subreddit"].unique()) if echo is not None else set()
summary_subs = set(summary["subreddit"].unique()) if summary is not None else set()

print("Subreddits in POSTS:", len(posts_subs))
print("Subreddits in DOMAIN FLOW:", len(flow_subs))
print("Subreddits in ECHO SCORES:", len(echo_subs))
print("Subreddits in SUMMARY:", len(summary_subs))


print("\nMissing subreddit checks")

if posts is not None:
    missing_in_flow = posts_subs - flow_subs
    missing_in_echo = posts_subs - echo_subs
    missing_in_summary = posts_subs - summary_subs

    print("\nMissing from DOMAIN FLOW:", len(missing_in_flow))
    print(list(missing_in_flow)[:10])

    print("\nMissing from ECHO SCORES:", len(missing_in_echo))
    print(list(missing_in_echo)[:10])

    print("\nMissing from SUMMARY:", len(missing_in_summary))
    print(list(missing_in_summary)[:10])


print("\n==============================")
print("TOP SUBREDDITS BY DOMAIN COUNT")
print("==============================")

if flow is not None:
    domain_counts = flow.groupby("subreddit")["domain"].nunique().sort_values(ascending=False)
    print(domain_counts.head(10))


print("\n==============================")
print("TOP DOMAINS")
print("==============================")

if flow is not None:
    top_domains = flow["domain"].value_counts().head(10)
    print(top_domains)


print("\n==============================")
print("ECHO CHAMBER EXTREMES")
print("==============================")

if echo is not None and "echo_score" in echo.columns:
    print("\nHighest Echo Scores")
    print(echo.sort_values("echo_score", ascending=False).head(5))

    print("\nLowest Echo Scores")
    print(echo.sort_values("echo_score").head(5))


print("\n==============================")
print("DATASET AUDIT COMPLETE")
print("==============================")
