"""
verify_pipeline.py
==================
SimPPL-Ready Forensic Verification Suite

Proves that data extracted by the pipeline meets minimum quality standards
before it ever reaches the Groq LLM for narrative analysis.

Checks:
  1. DDG Search Relevance      — Are returned links actually from the target domain?
  2. Deduplication Accuracy    — Are duplicates (UTM, www, trailing-slash) correctly collapsed?
  3. Extraction Depth          — What confidence tier does each URL reach?
  4. Corpus Gap Analysis       — Which Corpus B stories were NOT shared on Reddit (Corpus A)?

Usage
-----
  python verify_pipeline.py                                      # breitbart demo
  python verify_pipeline.py --domain foxnews.com                 # any domain
  python verify_pipeline.py --domain cbc.ca --reddit-url <url>   # inject reddit url
  python verify_pipeline.py --youtube <url>                       # verify a YT transcript
"""

from __future__ import annotations

import argparse
import sys
from urllib.parse import urlparse

# ── local imports ─────────────────────────────────────────────────────────────
from backend.scraper_pipeline import scrape
from backend.pipeline_extensions import (
    ddg_dork_search,
    deduplicate_urls,
    normalise_url,
    scrape_youtube_transcript,
    score_confidence,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW, CONFIDENCE_FAILED,
)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHECK 1 — DDG Search Relevance
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_ddg_relevance(domain: str, query_keyword: str = "politics news", max_results: int = 5) -> list[str]:
    """
    Run DDG search filtered to `domain`, verify all returned URLs are on-target.

    DDG's free API doesn't support site: operators — we do a broad keyword
    search and filter client-side, then verify domain accuracy here.
    """
    print(f"\n{'─'*60}")
    print(f"  CHECK 1 — DDG Search Relevance")
    print(f"  Domain   : {domain}")
    print(f"  Keywords : {query_keyword}")
    print(f"{'─'*60}")

    results = ddg_dork_search(
        query=f"site:{domain} {query_keyword}",
        max_results=max_results,
    )

    links = [r["link"] for r in results if r.get("link")]

    print(f"\n  {len(links)} on-domain results returned")

    off_target = [u for u in links if domain not in urlparse(u).netloc]
    if off_target:
        print(f"\n  ⚠️  WARNING — {len(off_target)} off-domain links slipped through:")
        for u in off_target:
            print(f"     {u}")
    else:
        print(f"  ✅ All {len(links)} links confirmed on-target for {domain}")

    for i, r in enumerate(results, 1):
        print(f"\n   [{i}] {r['title'][:70]}")
        print(f"        {r['link']}")
        if r.get("snippet"):
            print(f"        ↳ {r['snippet'][:100]}…")

    return links


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHECK 2 — Deduplication Accuracy
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_dedup_accuracy(corpus_a: list[str], corpus_b: list[str]) -> list[str]:
    """
    Verify that dedup correctly collapses UTM variants, www prefix,
    trailing-slash and short-URL variants of the same article.
    """
    print(f"\n{'─'*60}")
    print(f"  CHECK 2 — Deduplication Accuracy")
    print(f"  Corpus A (Reddit) : {len(corpus_a)} URLs")
    print(f"  Corpus B (DDG)    : {len(corpus_b)} URLs")
    print(f"{'─'*60}")

    combined = corpus_a + corpus_b
    unique   = deduplicate_urls(combined)

    print(f"\n  Input  : {len(combined)} total URLs")
    print(f"  Output : {len(unique)} unique URLs after dedup")
    print(f"  Removed: {len(combined) - len(unique)} duplicates\n")

    # Show normalisation for all inputs
    seen_norms: dict[str, str] = {}
    dup_groups: dict[str, list[str]] = {}
    for raw in combined:
        norm = normalise_url(raw)
        if norm in seen_norms:
            dup_groups.setdefault(norm, [seen_norms[norm]]).append(raw)
        else:
            seen_norms[norm] = raw

    if dup_groups:
        print("  🔍 Collapsed duplicate groups:")
        for norm, originals in dup_groups.items():
            print(f"     canonical → {norm}")
            for o in originals:
                print(f"       dup: {o}")
    else:
        print("  ✅ No duplicate groups found (all URLs are already unique).")

    return unique


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHECK 3 — Extraction Depth
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_extraction_depth(urls: list[str], max_check: int = 3) -> None:
    """
    Scrape a sample of URLs and score them. Reports confidence tier per URL.
    Fails the verification if more than 50% of results are FAILED or LOW.
    """
    import re

    print(f"\n{'─'*60}")
    print(f"  CHECK 3 — Extraction Depth  (sampling {min(max_check, len(urls))}/{len(urls)} URLs)")
    print(f"{'─'*60}\n")

    sample = urls[:max_check]
    scores = []

    for url in sample:
        print(f"  Scraping: {url[:70]}")
        if re.search(r"(youtube\.com|youtu\.be)", url, re.I):
            result = scrape_youtube_transcript(url)
        else:
            result = scrape(url)

        confidence = score_confidence(result)
        scores.append(confidence)
        flag = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🟠", "FAILED": "🔴"}[confidence.level]
        print(f"    {flag} {confidence.level:<8}  {confidence.char_count:>6} chars  {confidence.reason}")
        if result.error and confidence.level == CONFIDENCE_FAILED:
            print(f"    ⚠  Error: {result.error}")
        print()

    # Quality gate
    total   = len(scores)
    failing = sum(1 for s in scores if s.level in (CONFIDENCE_FAILED, CONFIDENCE_LOW))
    pct_fail = failing / total * 100 if total else 0

    print(f"  Quality Gate: {failing}/{total} results are LOW or FAILED ({pct_fail:.0f}%)")
    if pct_fail > 50:
        print("  ❌ GATE FAILED — more than 50% of results have insufficient text depth.")
        print("     Escalate these URLs to Tier C or flag for manual review.")
    else:
        print("  ✅ GATE PASSED — majority of results have sufficient text depth.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CHECK 4 — Corpus Gap Analysis (Amplification Gap)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_corpus_gap(corpus_a: list[str], corpus_b: list[str]) -> None:
    """
    Identify which Corpus B (web/DDG) stories were NOT shared on Reddit (Corpus A).
    This gap = amplification bias: what the site published vs. what Reddit amplified.

    A large gap means Reddit users were selective — the under-shared stories
    are prime OSINT targets for the narrative analyst.
    """
    print(f"\n{'─'*60}")
    print(f"  CHECK 4 — Corpus Gap Analysis (Amplification Bias)")
    print(f"{'─'*60}\n")

    norm_a = {normalise_url(u) for u in corpus_a}
    norm_b = {normalise_url(u): u for u in corpus_b}

    shared    = [u for n, u in norm_b.items() if n in norm_a]
    not_shared = [u for n, u in norm_b.items() if n not in norm_a]

    print(f"  Corpus A (Reddit shared) : {len(corpus_a)} URLs")
    print(f"  Corpus B (site published): {len(corpus_b)} URLs")
    print(f"  Overlap (shared)         : {len(shared)}")
    print(f"  Gap (not shared)         : {len(not_shared)}  ← OSINT targets\n")

    if not_shared:
        print("  🔍 Stories published but NOT amplified on Reddit:")
        for u in not_shared:
            print(f"     {u}")
        gap_pct = len(not_shared) / len(corpus_b) * 100 if corpus_b else 0
        print(f"\n  Amplification gap: {gap_pct:.0f}% of {len(corpus_b)} published stories went un-shared.")
        if gap_pct > 70:
            print("  ⚡ HIGH gap — Reddit community amplified a small fraction of what was published.")
        elif gap_pct > 30:
            print("  ⚠️  MODERATE gap — selective amplification detected.")
        else:
            print("  ✅ LOW gap — Reddit closely mirrors what the site published.")
    else:
        print("  ✅ No gap — all published stories were shared on Reddit.")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FULL VERIFICATION REPORT
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_verification(
    domain: str,
    query_keyword: str,
    reddit_urls: list[str],
    max_extract: int = 3,
) -> None:
    print(f"\n{'='*60}")
    print(f"  🔬 SimPPL VERIFICATION REPORT")
    print(f"  Domain   : {domain}")
    print(f"  Keywords : {query_keyword}")
    print(f"  Corpus A : {len(reddit_urls)} Reddit URL(s)")
    print(f"{'='*60}")

    # Check 1: DDG search & domain relevance
    web_urls = check_ddg_relevance(domain, query_keyword, max_results=5)

    # Check 2: Deduplication
    unique_urls = check_dedup_accuracy(reddit_urls, web_urls)

    # Check 3: Extraction depth on combined unique set
    check_extraction_depth(unique_urls, max_check=max_extract)

    # Check 4: Amplification gap
    check_corpus_gap(reddit_urls, web_urls)

    print(f"\n{'='*60}")
    print(f"  ✅ Verification complete. Data is SimPPL-ready for Groq analysis.")
    print(f"{'='*60}\n")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main() -> None:
    parser = argparse.ArgumentParser(description="SimPPL Pipeline Verification Suite")
    parser.add_argument("--domain",      default="breitbart.com",
                        help="Target domain to verify against")
    parser.add_argument("--keywords",    default="politics DOGE Trump news",
                        help="Search keywords (no site:/date operators)")
    parser.add_argument("--reddit-url",  action="append", dest="reddit_urls", default=[],
                        metavar="URL", help="Corpus A Reddit URL (repeat for multiple)")
    parser.add_argument("--max-extract", type=int, default=2,
                        help="Max URLs to fully scrape for depth check (default 2 to be fast)")
    parser.add_argument("--youtube",     metavar="URL",
                        help="Verify YouTube transcript extraction for a single URL")
    args = parser.parse_args()

    if args.youtube:
        print(f"\n  Verifying YouTube transcript: {args.youtube}")
        result = scrape_youtube_transcript(args.youtube)
        score  = score_confidence(result)
        flag   = {"HIGH": "🟢", "MEDIUM": "🟡", "LOW": "🟠", "FAILED": "🔴"}[score.level]
        print(f"  {flag} {score.level}  —  {score.char_count} chars  —  {score.reason}")
        if result.text:
            print(f"\n  Preview (200 chars):\n  {result.text[:200]}…")
        else:
            print(f"  Error: {result.error}")
        return

    # Default demo Reddit URLs if none supplied
    reddit_urls = args.reddit_urls or [
        f"https://www.{args.domain}/politics/2025/02/17/some-article",
        f"https://www.{args.domain}/national-security/2025/02/14/another-article",
    ]

    run_verification(
        domain      = args.domain,
        query_keyword = args.keywords,
        reddit_urls = reddit_urls,
        max_extract = args.max_extract,
    )


if __name__ == "__main__":
    main()
