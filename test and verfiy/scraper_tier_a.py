from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlparse

import trafilatura
from trafilatura.settings import use_config

# ── Trafilatura config ─────────────────────────────────────────────────────────
_TRAF_CONFIG = use_config()
_TRAF_CONFIG.set("DEFAULT", "EXTRACTION_TIMEOUT", "30")

TIER_A_DOMAINS: set[str] = {
    # Political / Indie blogs
    "anarchistnews.org", "abolitionmedia.noblogs.org", "angryworkers.org",
    "anti-imperialist.net", "blackrosefed.org", "crimethinc.com",
    "counterpunch.org", "commondreams.org", "currentaffairs.org",
    "jacobin.com", "itsgoingdown.org", "leftcom.org", "libcom.org",
    "people.com", "peoplesdispatch.org", "popularresistance.org",
    "rebelnews.com", "redstate.com", "socialism.com", "tempestmag.org",
    "theintercept.com", "workers.org", "znetwork.org",
    # Alternative / Aggregator
    "19fortyfive.com", "404media.co", "agweb.com", "alternet.org",
    "babylonbee.com", "breitbart.com", "city-journal.org", "dailywire.com",
    "hotair.com", "nationalreview.com", "notthebee.com", "pjmedia.com",
    "rawstory.com", "salon.com", "slate.com", "townhall.com",
    "twitchy.com", "vox.com",
    # Local & International News
    "11alive.com", "13abc.com", "2news.com", "8newsnow.com", "9news.com.au",
    "abc.net.au", "ajc.com", "al.com", "asahi.com", "bbc.co.uk",
    "bianet.org", "cbc.ca", "ctvnews.ca", "dw.com", "france24.com",
    "hindustantimes.com", "irishtimes.com", "kyivindependent.com",
    "politico.eu", "reuters.com", "scmp.com", "straitstimes.com",
    "thehill.com", "thestar.com",
    # Substacks & Individual blogs
    "ahmedelhennawy.substack.com", "astralcodexten.com",
    "cyberintel.substack.com", "deatleft.com",
    "findingequilibrium.substack.com", "incogkneegrowth.substack.com",
    "johnpavlovitz.com", "noahpinion.blog", "slowboring.com", "write.as",
}


# ── Result dataclass ───────────────────────────────────────────────────────────
@dataclass
class ScrapeResult:
    url: str
    domain: str
    tier: str = "A"
    success: bool = False
    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    text: Optional[str] = None
    word_count: int = 0
    error: Optional[str] = None
    extraction_method: str = "trafilatura"
    metadata: dict = field(default_factory=dict)

    def preview(self, chars: int = 500) -> str:
        if not self.text:
            return "(no text)"
        return self.text[:chars] + ("…" if len(self.text) > chars else "")


# ── Version-safe extraction shim ──────────────────────────────────────────────
def _extract_dict(html: str, url: str, favor_recall: bool = True) -> Optional[dict]:
    """
    Return trafilatura extraction as a plain dict — works across all versions.

    Tries in order:
      1. bare_extraction()              trafilatura >= 0.9  (current API)
      2. extract(output_format="python") trafilatura <  0.9  (legacy API)
      3. extract() → str               any version          (last resort)
    """
    kwargs = dict(
        url=url,
        include_comments=False,
        include_tables=True,
        favor_recall=favor_recall,
        config=_TRAF_CONFIG,
    )

    # 1 ── bare_extraction (new API) ──────────────────────────────────────────
    if hasattr(trafilatura, "bare_extraction"):
        try:
            result = trafilatura.bare_extraction(html, **kwargs)
            if result and result.get("text"):
                return result
        except Exception:
            pass

    # 2 ── extract with output_format="python" (old API) ─────────────────────
    try:
        result = trafilatura.extract(html, output_format="python", **kwargs)
        if result and isinstance(result, dict) and result.get("text"):
            return result
    except (ValueError, TypeError):
        pass   # "python format only usable in bare_extraction()"

    # 3 ── plain string fallback (always available) ───────────────────────────
    try:
        text = trafilatura.extract(html, **kwargs)
        if text and isinstance(text, str) and text.strip():
            return {
                "text": text.strip(),
                "title": None, "author": None,
                "date": None,  "language": None,
            }
    except Exception:
        pass

    return None


# ── Core scraper ──────────────────────────────────────────────────────────────
def scrape_tier_a(url: str, retries: int = 2, retry_delay: float = 2.0) -> ScrapeResult:
    """
    Extract clean article text from any Tier-A URL via trafilatura.
    Compatible with trafilatura 0.8 → 1.x.
    """
    domain = urlparse(url).netloc.lstrip("www.")
    result = ScrapeResult(url=url, domain=domain)
    last_error: Optional[str] = None

    for attempt in range(1 + retries):
        try:
            # 1. Fetch ────────────────────────────────────────────────────────
            html = trafilatura.fetch_url(url)
            if not html:
                last_error = "fetch_url returned empty — blocked or redirect loop"
                if attempt < retries:
                    time.sleep(retry_delay)
                    continue
                break

            # 2. Extract (broad first, then strict fallback) ─────────────────
            extracted = _extract_dict(html, url, favor_recall=True)
            if not extracted:
                extracted = _extract_dict(html, url, favor_recall=False)

            if not extracted:
                last_error = "All extraction strategies returned None"
                break

            text = (extracted.get("text") or "").strip()
            result.success    = bool(text)
            result.title      = extracted.get("title")
            result.author     = extracted.get("author")
            result.date       = extracted.get("date")
            result.language   = extracted.get("language")
            result.text       = text or None
            result.word_count = len(text.split()) if text else 0
            result.metadata   = {
                k: v for k, v in extracted.items()
                if k not in {"text", "title", "author", "date", "language"}
                and v is not None
            }

            if not result.success:
                last_error = "Extraction returned metadata but empty body"

            return result

        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt < retries:
                time.sleep(retry_delay)

    result.error = last_error
    return result


# ── Pretty printer ─────────────────────────────────────────────────────────────
def print_result(result: ScrapeResult, preview_chars: int = 800) -> None:
    status    = "✅ SUCCESS" if result.success else "❌ FAILED"
    tier_note = "✅ Tier A domain" if result.domain in TIER_A_DOMAINS else "⚠️  Not in Tier A list"
    
    print(f"\n{'='*70}")
    print(f"  {status}  |  {tier_note}")
    print(f"{'='*70}")
    print(f"  URL      : {result.url}")
    print(f"  Domain   : {result.domain}")
    print(f"  Title    : {result.title or '—'}")
    print(f"  Author   : {result.author or '—'}")
    print(f"  Date     : {result.date or '—'}")
    print(f"  Language : {result.language or '—'}")
    print(f"  Words    : {result.word_count:,}")
    
    if hasattr(result, "error") and result.error:
        print(f"\n  ⚠  Error  : {result.error}")
        
    if result.text:
        print(f"\n── Article Preview ({preview_chars} chars) {'─'*28}")
        print(result.preview(preview_chars))
        print(f"\n── [Full: {result.word_count:,} words / {len(result.text):,} chars]")
    else:
        print("\n  (no article text extracted)")
    
    print(f"{'='*70}\n")


# ── Batch helper ───────────────────────────────────────────────────────────────
def batch_scrape_tier_a(
    urls: list[str],
    delay_between: float = 1.0,
    retries: int = 2,
) -> list[ScrapeResult]:
    results = []
    for i, url in enumerate(urls, 1):
        print(f"  [{i:>3}/{len(urls)}] {url}")
        res = scrape_tier_a(url, retries=retries)
        tag = "✅" if res.success else "❌"
        print(f"           {tag}  {res.word_count:,} words  {res.error or ''}")
        results.append(res)
        if i < len(urls):
            time.sleep(delay_between)
    return results


# ── Version diagnostics ────────────────────────────────────────────────────────
def print_version_info() -> None:
    try:
        import importlib.metadata
        ver = importlib.metadata.version("trafilatura")
    except Exception:
        ver = "unknown"
    has_bare = hasattr(trafilatura, "bare_extraction")
    print(f"  trafilatura version  : {ver}")
    print(f"  bare_extraction API  : {'✅ available' if has_bare else '❌ not present → using fallback chain'}")
    print(f"  active shim strategy : {'1 (bare_extraction)' if has_bare else '2/3 (legacy/string)'}")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Tier A scraper — trafilatura, version-safe")
    parser.add_argument("--url", default="https://www.breitbart.com/politics/2025/02/15/", help="URL to scrape")
    parser.add_argument("--json",    action="store_true", help="Print JSON output")
    parser.add_argument("--out",     metavar="FILE",      help="Write article text to file")
    parser.add_argument("--preview", type=int, default=800)
    parser.add_argument("--version", action="store_true", help="Show version info and exit")
    args = parser.parse_args()

    print_version_info()
    if args.version:
        return

    print(f"\n  Target: {args.url}\n")
    result = scrape_tier_a(args.url)

    if args.json:
        print(json.dumps(asdict(result), indent=2, ensure_ascii=False))
    else:
        print_result(result, preview_chars=args.preview)

    if args.out and result.text:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(result.text)
        print(f"  Saved → {args.out}")

    sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
