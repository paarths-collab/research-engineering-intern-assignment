import os
import pandas as pd
import csv
from collections import defaultdict

DATA_DIR = "data"
flow_path = os.path.join(DATA_DIR, "subreddit_domain_flow_v2.csv")
posts_path = os.path.join(DATA_DIR, "clean_posts.csv")

def find_missing():
    print("Loading data...")
    if not os.path.exists(flow_path) or not os.path.exists(posts_path):
        print("Missing data files!")
        return

    # Load flow domains
    flow_data = defaultdict(set)
    with open(flow_path, newline='', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            flow_data[row['subreddit']].add(row['domain'])
    
    # Load posts domains
    df = pd.read_csv(posts_path)
    if 'domain' not in df.columns or 'subreddit' not in df.columns:
        print("CSV missing columns!")
        return
        
    posts_data = df.groupby('subreddit')['domain'].apply(set).to_dict()
    
    print("\nOverlap Audit:")
    for sub in sorted(posts_data.keys()):
        p_domains = posts_data[sub]
        f_domains = flow_data.get(sub, set())
        
        missing = p_domains - f_domains
        if len(missing) > 0:
            print(f"- {sub}: {len(missing)} domains in posts but NOT in flow. (e.g. {list(missing)[:3]})")
        else:
            print(f"- {sub}: Perfect match.")

if __name__ == "__main__":
    find_missing()
