from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import urlparse

import trafilatura

# ── Tier B domain registry ─────────────────────────────────────────────────────
TIER_B_DOMAINS: set[str] = {
    "8newsnow.com", "agweb.com", "al.com", "anti-imperialist.net",
    "babylonbee.com", "bianet.org", "cbc.ca", "deatleft.com",
    "itsgoingdown.org", "johnpavlovitz.com", "people.com",
    "peoplesdispatch.org", "popularresistance.org", "rebelnews.com",
    "redstate.com", "reuters.com", "thehill.com",
}

# How long to wait (ms) for the page body to appear before grabbing HTML
_WAIT_FOR_LOAD   = "networkidle"   # wait until no network activity for 500ms
_PAGE_TIMEOUT_MS = 30_000          # 30 seconds max per page
_SCROLL_PAUSE    = 1.5             # seconds — scroll to trigger lazy-loads


# ── Result dataclass (mirrors Tier A for pipeline compatibility) ───────────────
@dataclass
class ScrapeResult:
    url: str
    domain: str
    tier: str = "B"
    success: bool = False
    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    text: Optional[str] = None
    word_count: int = 0
    error: Optional[str] = None
    extraction_method: str = "playwright+trafilatura"
    metadata: dict = field(default_factory=dict)

    def preview(self, chars: int = 500) -> str:
        if not self.text:
            return "(no text)"
        return self.text[:chars] + ("…" if len(self.text) > chars else "")


# ── Stealth helper ─────────────────────────────────────────────────────────────
def _apply_stealth(page) -> None:
    """
    Apply anti-fingerprinting patches if playwright-stealth is installed.
    If not installed, apply minimal manual patches instead.
    """
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
        return
    except ImportError:
        pass

    # Manual minimal stealth — hides webdriver flag, fixes permissions API
    page.add_init_script("""
        // Remove webdriver flag
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

        // Spoof plugins (empty array = headless tell)
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5],
        });

        // Spoof languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['en-US', 'en'],
        });

        // Fix permissions query
        const originalQuery = window.navigator.permissions.query;
        window.navigator.permissions.query = (parameters) => (
            parameters.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : originalQuery(parameters)
        );

        // Chrome runtime stub
        window.chrome = { runtime: {} };
    """)


# ── Trafilatura extraction shim (same as Tier A) ───────────────────────────────
def _extract_dict(html: str, url: str) -> Optional[dict]:
    """Version-safe trafilatura extraction returning a dict."""
    if hasattr(trafilatura, "bare_extraction"):
        try:
            r = trafilatura.bare_extraction(
                html, url=url, include_comments=False,
                include_tables=True, favor_recall=True,
            )
            if r and r.get("text"):
                return r
        except Exception:
            pass

    try:
        r = trafilatura.extract(html, url=url, output_format="python",
                                include_comments=False, favor_recall=True)
        if r and isinstance(r, dict) and r.get("text"):
            return r
    except (ValueError, TypeError):
        pass

    try:
        text = trafilatura.extract(html, url=url, include_comments=False,
                                   favor_recall=True)
        if text and isinstance(text, str):
            return {"text": text.strip(), "title": None, "author": None,
                    "date": None, "language": None}
    except Exception:
        pass

    return None


# ── Core Tier B scraper ────────────────────────────────────────────────────────
def scrape_tier_b(
    url: str,
    headed: bool = False,
    timeout_ms: int = _PAGE_TIMEOUT_MS,
    scroll: bool = True,
) -> ScrapeResult:
    """
    Scrape a URL using a headless Chromium browser (Playwright).

    Parameters
    ----------
    url        : Full HTTP/HTTPS article URL.
    headed     : If True, opens a visible browser window (useful for debugging).
    timeout_ms : Max ms to wait for page load before giving up.
    scroll     : If True, scrolls the page to trigger lazy-loaded content.
    """
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

    domain = urlparse(url).netloc.lstrip("www.")
    result = ScrapeResult(url=url, domain=domain)

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=not headed,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
            )

            context = browser.new_context(
                viewport={"width": 1280, "height": 900},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="en-US",
                timezone_id="America/New_York",
                # Accept all content types a real browser would
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept-Encoding": "gzip, deflate, br",
                    "DNT": "1",
                    "Upgrade-Insecure-Requests": "1",
                },
            )

            page = context.new_page()
            _apply_stealth(page)

            # ── Navigate ───────────────────────────────────────────────────
            try:
                page.goto(url, wait_until=_WAIT_FOR_LOAD, timeout=timeout_ms)
            except PWTimeout:
                # networkidle can timeout on chatty pages — grab HTML anyway
                pass

            # ── Scroll to trigger lazy-loads ───────────────────────────────
            if scroll:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(_SCROLL_PAUSE)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(_SCROLL_PAUSE / 2)

            # ── Dismiss common overlays (cookie banners, newsletter popups) ─
            _dismiss_overlays(page)

            # ── Grab fully rendered HTML ───────────────────────────────────
            html = page.content()
            page_title = page.title()

            browser.close()

        # ── Extract clean text via trafilatura ─────────────────────────────
        extracted = _extract_dict(html, url)
        if not extracted:
            result.error = "Playwright fetched page but trafilatura found no article body"
            return result

        text = (extracted.get("text") or "").strip()
        result.success    = bool(text)
        result.title      = extracted.get("title") or page_title or None
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
            result.error = "Page rendered but article body was empty"

    except Exception as exc:
        result.error = f"{type(exc).__name__}: {exc}"

    return result


# ── Overlay dismissal ──────────────────────────────────────────────────────────
def _dismiss_overlays(page) -> None:
    """
    Click common 'Accept', 'Close', 'I agree' buttons to remove
    cookie banners and newsletter modals that obscure article text.
    Silently ignores failures.
    """
    selectors = [
        # Cookie / GDPR banners
        "button:has-text('Accept all')",
        "button:has-text('Accept All')",
        "button:has-text('Accept cookies')",
        "button:has-text('I agree')",
        "button:has-text('Agree')",
        "button:has-text('Got it')",
        "button:has-text('OK')",
        "[id*='cookie'] button",
        "[class*='cookie'] button",
        "[class*='consent'] button",
        # Newsletter / subscription modals
        "button:has-text('No thanks')",
        "button:has-text('Not now')",
        "button:has-text('Close')",
        "[aria-label='Close']",
        "[aria-label='close']",
        ".modal-close",
        ".close-button",
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click(timeout=1000)
                time.sleep(0.3)
        except Exception:
            pass


# ── Pretty printer ─────────────────────────────────────────────────────────────
def print_result(result: ScrapeResult, preview_chars: int = 800) -> None:
    status    = "✅ SUCCESS" if result.success else "❌ FAILED"
    tier_note = "✅ Tier B domain" if result.domain in TIER_B_DOMAINS else "⚠️  Not in Tier B list"
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
    print(f"  Method   : {result.extraction_method}")
    if result.error:
        print(f"\n  ⚠  Error  : {result.error}")
    if result.text:
        print(f"\n── Article Preview ({preview_chars} chars) {'─'*28}")
        print(result.preview(preview_chars))
        print(f"\n── [Full: {result.word_count:,} words / {len(result.text):,} chars]")
    else:
        print("\n  (no article text extracted)")
    print(f"{'='*70}\n")


# ── Batch helper ───────────────────────────────────────────────────────────────
def batch_scrape_tier_b(
    urls: list[str],
    delay_between: float = 2.0,
    headed: bool = False,
) -> list[ScrapeResult]:
    """Sequential batch scrape of Tier B URLs with polite delay."""
    results = []
    for i, url in enumerate(urls, 1):
        print(f"  [{i:>2}/{len(urls)}] {url}")
        res = scrape_tier_b(url, headed=headed)
        tag = "✅" if res.success else "❌"
        print(f"          {tag}  {res.word_count:,} words  {res.error or ''}")
        results.append(res)
        if i < len(urls):
            time.sleep(delay_between)
    return results


# ── Built-in integration test ──────────────────────────────────────────────────
def run_tier_b_test(headed: bool = False) -> None:
    """Test all 17 previously-blocked domains."""
    test_urls = [f"https://{d}" for d in sorted(TIER_B_DOMAINS)]
    print(f"\nTier B integration test — {len(test_urls)} domains\n")
    results = batch_scrape_tier_b(test_urls, headed=headed)
    ok  = [r for r in results if r.success]
    bad = [r for r in results if not r.success]
    print(f"\n{'='*70}")
    print(f"  Results: {len(ok)} OK, {len(bad)} Failed")
    if bad:
        print("\n  Still failing (may need Tier C — full stealth/proxy):")
        for r in bad:
            print(f"    ❌ {r.domain}  →  {r.error}")
    print(f"{'='*70}\n")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Tier B Playwright scraper")
    parser.add_argument("--url",    default="https://www.reuters.com/", help="URL to scrape")
    parser.add_argument("--headed", action="store_true", help="Show browser window")
    parser.add_argument("--json",   action="store_true", help="Output raw JSON")
    parser.add_argument("--out",    metavar="FILE",      help="Write article text to file")
    parser.add_argument("--preview",type=int, default=800)
    parser.add_argument("--test",   action="store_true", help="Test all 17 blocked domains")
    args = parser.parse_args()

    if args.test:
        run_tier_b_test(headed=args.headed)
        return

    print(f"\n  Tier B Scraper  →  {args.url}\n")
    result = scrape_tier_b(args.url, headed=args.headed)

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
