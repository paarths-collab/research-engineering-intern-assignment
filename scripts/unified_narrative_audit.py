import os
import pandas as pd
import csv
from collections import defaultdict

DATA_DIR = "data"

FILES = {
    "posts": "clean_posts.csv",
    "domain_flow": "subreddit_domain_flow_v2.csv",
    "echo_scores": "echo_chamber_scores.csv",
    "subreddit_summary": "subreddit_intelligence_summary.csv",
    "distinctive": "clean_top_distinctive_domains.csv"
}

def separator(title):
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def audit_datasets():
    separator("1. DATASET INTEGRITY & FILE SYSTEM")
    available = []
    for key, filename in FILES.items():
        path = os.path.join(DATA_DIR, filename)
        exists = os.path.exists(path)
        status = "✅ FOUND" if exists else "❌ MISSING"
        size = f"{os.path.getsize(path)/1024:.1f} KB" if exists else "N/A"
        print(f"{filename:<40} | {status:<10} | {size}")
        if exists: available.append(key)
    return available

def analyze_coverage(available):
    if "posts" not in available or "domain_flow" not in available:
        print("\n[SKIP] Cannot perform coverage analysis without core files.")
        return

    separator("2. SUBREDDIT & DOMAIN COVERAGE")
    
    # Load core data
    posts_df = pd.read_csv(os.path.join(DATA_DIR, FILES["posts"]))
    flow_df = pd.read_csv(os.path.join(DATA_DIR, FILES["domain_flow"]))
    
    posts_subs = set(posts_df["subreddit"].unique())
    flow_subs = set(flow_df["subreddit"].unique())
    all_domains = set(flow_df["domain"].unique())
    
    print(f"Total Unique Subreddits (POSTS):     {len(posts_subs)}")
    print(f"Total Unique Subreddits (FLOW):      {len(flow_subs)}")
    print(f"Total Unique News Channels (GLOBAL): {len(all_domains)}")
    
    missing_flow = posts_subs - flow_subs
    if missing_flow:
        print(f"\n⚠️ {len(missing_flow)} subreddits have posts but NO news link data (flow):")
        print(f"Samples: {list(missing_flow)[:5]}")
    else:
        print("\n✅ All subreddits have corresponding news flow data.")

    return posts_subs, flow_subs, all_domains, flow_df

def analyze_link_visibility(flow_df, all_domains):
    separator("3. LINK VISIBILITY & INFORMATION GAPS")
    
    # Calculate global totals for Link Visibility context
    global_total = flow_df["count"].sum()
    domain_totals = flow_df.groupby("domain")["count"].sum().to_dict()
    
    # Sample common subreddits for a "Shadow" check
    samples = ["politics", "neoliberal", "Conservative", "socialism"]
    existing_samples = [s for s in samples if s in flow_df["subreddit"].unique()]
    
    for sub in existing_samples:
        sub_flow = flow_df[flow_df["subreddit"] == sub]
        sub_domains = set(sub_flow["domain"].unique())
        sub_total = sub_flow["count"].sum()
        
        coverage_pct = (len(sub_domains) / len(all_domains)) * 100
        print(f"\n[r/{sub}]")
        print(f"News Coverage: {len(sub_domains)} / {len(all_domains)} channels ({coverage_pct:.1f}%)")
        print(f"Total Links:   {sub_total}")
        
        # Display top 3 visibility leaders
        top_3 = sub_flow.sort_values("count", ascending=False).head(3)
        print("Top 3 Link Visibility Leaders:")
        for _, row in top_3.iterrows():
            p_sub = (row['count'] / sub_total) * 100
            print(f"  - {row['domain']:<25} | {p_sub:>6.2f}% Visibility")

def identify_bridges(flow_df):
    separator("4. NARRATIVE BRIDGES (CROSS-COMMUNITY SOURCES)")
    # Domains shared by most number of subreddits
    bridge_counts = flow_df.groupby("domain")["subreddit"].nunique().sort_values(ascending=False)
    print("Top 10 Global News Bridges (appears in most subreddits):")
    print(bridge_counts.head(10))

if __name__ == "__main__":
    try:
        data_keys = audit_datasets()
        p_subs, f_subs, domains, flow = analyze_coverage(data_keys)
        analyze_link_visibility(flow, domains)
        identify_bridges(flow)
        print("\n✅ UNIFIED AUDIT COMPLETE")
    except Exception as e:
        print(f"\n❌ ERROR DURING AUDIT: {str(e)}")
        import traceback
        traceback.print_exc()
