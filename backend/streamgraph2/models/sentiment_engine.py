"""
sentiment_engine.py — Emotional amplification modeling.

Model: cardiffnlp/twitter-roberta-base-sentiment
       Labels: LABEL_0=negative, LABEL_1=neutral, LABEL_2=positive

Window: spike_date - 1, spike_date, spike_date + 1

Sources: post titles + comment bodies

Stores per-day percentages in sentiment_daily table.
"""

from datetime import date, timedelta
from typing import List, Dict, Optional

from streamgraph2.data import db


# ── Model loader ─────────────────────────────────────────────

_pipeline = None

def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        try:
            from transformers import pipeline as hf_pipeline
        except ImportError:
            raise RuntimeError("Install transformers: pip install transformers torch")

        print("  [Sentiment] Loading cardiffnlp/twitter-roberta-base-sentiment")
        _pipeline = hf_pipeline(
            "sentiment-analysis",
            model    = "cardiffnlp/twitter-roberta-base-sentiment",
            tokenizer= "cardiffnlp/twitter-roberta-base-sentiment",
            top_k    = None,          # return all 3 labels
            truncation = True,
            max_length = 128,
        )
    return _pipeline


# ── Label mapping ─────────────────────────────────────────────

LABEL_MAP = {
    "LABEL_0": "negative",
    "LABEL_1": "neutral",
    "LABEL_2": "positive",
}


def _classify_batch(texts: List[str]) -> Dict[str, float]:
    """
    Run sentiment on a batch of texts.
    Returns: { negative, neutral, positive } as percentages.
    """
    if not texts:
        return {"negative": 0.0, "neutral": 100.0, "positive": 0.0}

    pipe = _get_pipeline()

    # Batch in chunks of 32 to avoid OOM
    all_results = []
    chunk_size  = 32
    for i in range(0, len(texts), chunk_size):
        chunk = texts[i : i + chunk_size]
        outputs = pipe(chunk)
        all_results.extend(outputs)

    # Each output is [{'label': 'LABEL_0', 'score': 0.8}, ...]
    counts = {"negative": 0, "neutral": 0, "positive": 0}
    for result in all_results:
        # Find highest scoring label
        best = max(result, key=lambda x: x["score"])
        label = LABEL_MAP.get(best["label"], "neutral")
        counts[label] += 1

    total = sum(counts.values())
    return {k: round((v / total) * 100, 2) for k, v in counts.items()}


# ── Main engine ───────────────────────────────────────────────

async def run_sentiment_evolution(job_id: str, spike_date: date) -> List[Dict]:
    """
    Compute sentiment for spike_date - 1, spike_date, spike_date + 1.
    Returns list of daily sentiment dicts.
    """
    window   = [spike_date - timedelta(1), spike_date, spike_date + timedelta(1)]
    results  = []

    for day in window:
        texts = await db.get_texts_for_date(day)

        if not texts:
            print(f"  [Sentiment] No text for {day} — skipping")
            continue

        print(f"  [Sentiment] Classifying {len(texts)} items for {day}")
        sentiment = _classify_batch(texts)

        await db.save_sentiment(
            job_id      = job_id,
            date_val    = day,
            neg         = sentiment["negative"],
            neu         = sentiment["neutral"],
            pos         = sentiment["positive"],
            sample_count= len(texts),
        )

        results.append({
            "date"          : str(day),
            "negative"      : sentiment["negative"],
            "neutral"       : sentiment["neutral"],
            "positive"      : sentiment["positive"],
            "sample_count"  : len(texts),
        })

    # Compute delta_negative (spike vs baseline)
    if len(results) >= 2:
        baseline_neg = results[0]["negative"]
        spike_neg    = results[1]["negative"] if len(results) > 1 else results[0]["negative"]
        delta = round(spike_neg - baseline_neg, 2)
        print(f"  [Sentiment] Δ negative: {delta:+.2f}%")
        for r in results:
            r["delta_negative"] = delta  # attach to all rows for convenience

    return results
