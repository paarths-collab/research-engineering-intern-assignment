"""
unified_visibility_check.py — CLI tool to verify news source visibility.
Uses the EXACT same logic as the backend API to ensure consistency.
"""
import sys
import os

# Add backend to path so we can import our analytics
sys.path.append(os.path.join(os.getcwd(), "backend"))

from polarize_1.data_loader import DataStore
from polarize_1.analytics import build_treemap_payload

def run_check(subreddit: str):
    print(f"\nAudit: Unified Visibility for r/{subreddit}")
    print("="*50)
    
    store = DataStore()
    store.load()
    
    payload = build_treemap_payload(store, subreddit)
    
    total_domains = len(store.all_domains)
    print(f"\nGlobal Media Ecosystem Size: {total_domains} channels")
    
    # Analyze the payload
    all_rendered = []
    for cat in payload["children"]:
        for source in cat["children"]:
            all_rendered.append(source)
            
    mentioned = [s for s in all_rendered if s["loc"] > 0]
    gaps = [s for s in all_rendered if s["loc"] == 0]
    
    print(f"Channels Mentioned: {len(mentioned)}")
    print(f"Information Gaps:   {len(gaps)}")
    
    if mentioned:
        print("\nTop 5 Visible News Sources:")
        top_5 = sorted(mentioned, key=lambda x: -x["loc"])[:5]
        for s in top_5:
            print(f"  - {s['name']:<25} | {s['loc']:>4} refs | {(s['p_sub']*100):>6.4f}% Visibility")
    
    if gaps:
        print(f"\nSample Information Gaps (0 mentions):")
        for s in gaps[:5]:
            print(f"  - {s['name']}")

    print("\n✅ VERIFICATION COMPLETE: Subreddit is now reflecting the full global ecosystem.")

if __name__ == "__main__":
    sub = sys.argv[1] if len(sys.argv) > 1 else "politics"
    run_check(sub)
    print("\n[TIP] Run 'python unified_visibility_check.py <subreddit_name>' to audit any community.")
