"""
Data Exploration & Metrics Guide
==================================

This script explains each metric in detail with examples.
Run after uploading data to understand how the analysis works.
"""

import numpy as np
import json
from collections import Counter

# ============================================
# METRIC 1: ACTIVITY SHOCK
# ============================================

def explain_activity_shock():
    """
    Activity Shock measures if posting volume changed after an event.
    
    Formula: posts_per_day_after / posts_per_day_before
    """
    
    print("=" * 60)
    print("METRIC 1: ACTIVITY SHOCK")
    print("=" * 60)
    print()
    
    # Example data
    before_posts = 150  # posts in 7 days before
    after_posts = 350   # posts in 7 days after
    days = 7
    
    before_rate = before_posts / days
    after_rate = after_posts / days
    shock_ratio = after_rate / before_rate
    
    print(f"Example Event: U.S. Presidential Election")
    print(f"")
    print(f"Before Event (7 days):")
    print(f"  Total Posts: {before_posts}")
    print(f"  Posts/Day: {before_rate:.1f}")
    print()
    print(f"After Event (7 days):")
    print(f"  Total Posts: {after_posts}")
    print(f"  Posts/Day: {after_rate:.1f}")
    print()
    print(f"Shock Ratio: {shock_ratio:.2f}")
    print(f"Percent Change: {(shock_ratio - 1) * 100:.1f}%")
    print()
    
    print("Interpretation Scale:")
    print("  > 1.5   = Major spike (people showed up)")
    print("  1.2-1.5 = Moderate increase")
    print("  0.8-1.2 = Stable activity")
    print("  < 0.8   = Decreased activity")
    print()
    
    print(f"This event: {interpret_ratio(shock_ratio, 1.5, 1.2, 0.8)}")
    print()

# ============================================
# METRIC 2: DISCUSSION INTENSITY
# ============================================

def explain_discussion_intensity():
    """
    Discussion Intensity measures if people engaged more deeply.
    
    Metric: median(comments/post) change
    Why median? Robust to viral outliers with 10,000+ comments
    """
    
    print("=" * 60)
    print("METRIC 2: DISCUSSION INTENSITY")
    print("=" * 60)
    print()
    
    # Example comment distributions
    before_comments = [5, 8, 3, 12, 6, 15, 4, 9, 7, 10]
    after_comments = [18, 25, 12, 30, 15, 42, 20, 35, 22, 28]
    
    before_median = np.median(before_comments)
    after_median = np.median(after_comments)
    change_ratio = after_median / before_median
    
    print(f"Example: Posts about policy event")
    print()
    print(f"Before Event:")
    print(f"  Sample comments per post: {before_comments}")
    print(f"  Median: {before_median} comments")
    print()
    print(f"After Event:")
    print(f"  Sample comments per post: {after_comments}")
    print(f"  Median: {after_median} comments")
    print()
    print(f"Change Ratio: {change_ratio:.2f}")
    print(f"Interpretation: {(change_ratio - 1) * 100:.1f}% more discussion")
    print()
    
    print("What this means:")
    print("  High ratio = People are debating, not just sharing links")
    print("  Low ratio = Passive consumption, less engagement")
    print()

# ============================================
# METRIC 3: GINI COEFFICIENT (Attention)
# ============================================

def explain_gini_coefficient():
    """
    Gini Coefficient measures inequality in attention distribution.
    
    0 = Perfect equality (all posts get equal attention)
    1 = Perfect inequality (one post gets all attention)
    
    This is the same metric used in economics for wealth inequality.
    """
    
    print("=" * 60)
    print("METRIC 3: ATTENTION REDISTRIBUTION (Gini)")
    print("=" * 60)
    print()
    
    # Example: Equal vs Concentrated attention
    print("Scenario A: Equal Distribution")
    equal_scores = [100, 100, 100, 100, 100]
    gini_equal = calculate_gini(equal_scores)
    print(f"  Scores: {equal_scores}")
    print(f"  Gini: {gini_equal:.3f}")
    print(f"  → All posts get equal attention")
    print()
    
    print("Scenario B: Concentrated Attention")
    concentrated_scores = [500, 20, 15, 10, 5]
    gini_concentrated = calculate_gini(concentrated_scores)
    print(f"  Scores: {concentrated_scores}")
    print(f"  Gini: {gini_concentrated:.3f}")
    print(f"  → One viral post dominates")
    print()
    
    print("After an event:")
    print("  Gini ↑ = Attention concentrated on few viral posts")
    print("  Gini ↓ = Attention distributed more evenly")
    print()
    
    print("Lorenz Curve:")
    print("  X-axis: Cumulative % of posts (ranked by score)")
    print("  Y-axis: Cumulative % of total attention")
    print("  Diagonal line = Perfect equality")
    print("  Distance from diagonal = Inequality (area under curve)")
    print()

def calculate_gini(values):
    """Calculate Gini coefficient"""
    sorted_values = np.sort(values)
    n = len(sorted_values)
    cumsum = np.cumsum(sorted_values)
    return (2 * np.sum((np.arange(1, n + 1)) * sorted_values)) / (n * np.sum(sorted_values)) - (n + 1) / n

# ============================================
# METRIC 4: TOPIC SHIFT (TF-IDF + Cosine)
# ============================================

def explain_topic_shift():
    """
    Topic Shift measures semantic change in conversation.
    
    Process:
    1. Extract all text (titles + posts)
    2. Create TF-IDF vectors (mathematical representation)
    3. Calculate cosine similarity
    4. Distance = 1 - similarity
    """
    
    print("=" * 60)
    print("METRIC 4: TOPIC SHIFT (Semantic Analysis)")
    print("=" * 60)
    print()
    
    print("What is TF-IDF?")
    print("  TF = Term Frequency (how often word appears in document)")
    print("  IDF = Inverse Document Frequency (how rare word is overall)")
    print("  TF-IDF = TF × IDF (important words score high)")
    print()
    
    print("Example:")
    print()
    print("Before Event:")
    print("  Top words: policy, debate, congress, senate, vote")
    print("  TF-IDF Vector: [0.45, 0.38, 0.31, 0.29, 0.25, ...]")
    print()
    print("After Event:")
    print("  Top words: election, trump, victory, results, win")
    print("  TF-IDF Vector: [0.52, 0.48, 0.41, 0.35, 0.30, ...]")
    print()
    
    # Simplified example vectors
    vec1 = np.array([0.45, 0.38, 0.31])
    vec2 = np.array([0.20, 0.15, 0.52])
    
    # Cosine similarity
    similarity = np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))
    distance = 1 - similarity
    
    print(f"Cosine Similarity: {similarity:.3f}")
    print(f"Cosine Distance: {distance:.3f}")
    print()
    
    print("Interpretation:")
    print(f"  Similarity 1.0 = Identical topics")
    print(f"  Similarity 0.5 = Somewhat related")
    print(f"  Similarity 0.0 = Completely different")
    print()
    print(f"  Distance > 0.5 = Major topic shift")
    print(f"  Distance 0.3-0.5 = Significant shift")
    print(f"  Distance < 0.3 = Minor shift")
    print()
    
    print("Why this is powerful:")
    print("  → Mathematical proof conversation changed")
    print("  → Not subjective interpretation")
    print("  → Measures actual semantic movement in vector space")
    print()

# ============================================
# COMBINING ALL METRICS
# ============================================

def explain_combined_analysis():
    """
    How to interpret all 4 metrics together
    """
    
    print("=" * 60)
    print("COMBINED ANALYSIS: Reading All 4 Metrics")
    print("=" * 60)
    print()
    
    print("Example Event: Major Political Event")
    print()
    print("Scenario 1: MAJOR SHOCK")
    print("  Activity Shock: +150% (people showed up)")
    print("  Discussion: +80% (intense debate)")
    print("  Gini: +0.12 (concentrated on few viral posts)")
    print("  Topic Shift: 0.65 (completely new conversation)")
    print("  → This event DOMINATED the community")
    print()
    
    print("Scenario 2: MILD RESPONSE")
    print("  Activity Shock: +15% (slight increase)")
    print("  Discussion: +5% (similar engagement)")
    print("  Gini: -0.02 (stable distribution)")
    print("  Topic Shift: 0.15 (similar topics)")
    print("  → Community acknowledged but didn't reorganize")
    print()
    
    print("Scenario 3: CONCENTRATED VIRAL")
    print("  Activity Shock: +200% (huge spike)")
    print("  Discussion: -20% (less debate per post)")
    print("  Gini: +0.25 (ONE dominant viral post)")
    print("  Topic Shift: 0.8 (totally new topic)")
    print("  → One viral post dominated, not deep engagement")
    print()

def interpret_ratio(ratio, high, med, low):
    """Helper to interpret ratios"""
    if ratio > high:
        return "MAJOR CHANGE"
    elif ratio > med:
        return "Moderate change"
    elif ratio > low:
        return "Stable"
    else:
        return "Decreased"

# ============================================
# MAIN EXECUTION
# ============================================

def main():
    """Run all explanations"""
    
    print("\n" * 2)
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 10 + "SHOCK RESPONSE ANALYZER" + " " * 25 + "║")
    print("║" + " " * 15 + "Metrics Guide" + " " * 30 + "║")
    print("╚" + "=" * 58 + "╝")
    print("\n" * 2)
    
    explain_activity_shock()
    input("Press Enter to continue...")
    print("\n" * 2)
    
    explain_discussion_intensity()
    input("Press Enter to continue...")
    print("\n" * 2)
    
    explain_gini_coefficient()
    input("Press Enter to continue...")
    print("\n" * 2)
    
    explain_topic_shift()
    input("Press Enter to continue...")
    print("\n" * 2)
    
    explain_combined_analysis()
    print("\n" * 2)
    
    print("=" * 60)
    print("✓ Guide Complete!")
    print()
    print("Now you understand:")
    print("  1. Activity Shock = Volume change")
    print("  2. Discussion Intensity = Engagement depth")
    print("  3. Gini Coefficient = Attention inequality")
    print("  4. Topic Shift = Semantic change")
    print()
    print("These 4 dimensions together paint a complete picture of")
    print("how communities structurally respond to external shocks.")
    print("=" * 60)

if __name__ == "__main__":
    main()
