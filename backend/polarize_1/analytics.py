"""
analytics.py — Unified logic for Narrative Intelligence and Link Visibility.
This file consolidates calculation logic to ensure consistency between the API and CLI tools.
"""
from collections import defaultdict
from typing import Dict, List, Any

def calculate_link_visibility(count: int, total_sub: int, total_global: int) -> Dict[str, float]:
    """Calculate p_sub and p_global with consistent high precision."""
    p_sub = round(count / (total_sub or 1), 7)
    p_global = round(count / (total_global or 1), 7)
    return {"p_sub": p_sub, "p_global": p_global}

def build_treemap_payload(store: Any, subreddit: str) -> Dict[str, Any]:
    """
    Build a hierarchical payload for D3/Nivo Treemaps.
    Ensures ALL news channels are displayed, even with 0 mentions.
    """
    vector = store.flow_vectors.get(subreddit, {})
    total_sub_links = sum(vector.values()) if vector else 1
    total_global_links = store.total_global_links or 1
    
    categories = defaultdict(list)
    for domain in store.all_domains:
        count = vector.get(domain, 0)
        if count == 0:
            continue
        
        cat = store.domain_to_category.get(domain, "Media / News")
        vis = calculate_link_visibility(count, total_sub_links, total_global_links)
        
        categories[cat].append({
            "name": domain,
            "loc": count,
            "p_sub": vis["p_sub"],
            "p_global": vis["p_global"],
            "category": cat,
        })

    children = []
    for cat_name, domains in categories.items():
        children.append({
            "name": cat_name,
            "children": domains
        })

    return {
        "name": f"{subreddit} Media Ecosystem",
        "children": children
    }

def build_global_ecosystem_payload(store: Any) -> Dict[str, Any]:
    """
    Build a global hierarchy: Root -> Category -> Domain.
    """
    total_global_links = store.total_global_links or 1
    cats = defaultdict(dict) # cat -> {domain -> {loc, cat, p_sub, p_global}}
    
    # Efficient aggregation
    for domain, count in store.global_domain_counts.items():
        cat = store.domain_to_category.get(domain, "Media / News")
        if domain not in cats[cat]:
            global_share = round(count / total_global_links, 7)
            cats[cat][domain] = {
                "name": domain, 
                "loc": count, 
                "category": cat, 
                "p_sub": global_share, 
                "p_global": global_share
            }
            
    children = []
    for cat_name, domains_map in cats.items():
        children.append({
            "name": cat_name,
            "children": list(domains_map.values())
        })
        
    return {
        "name": "Global Ecosystem",
        "children": children
    }
