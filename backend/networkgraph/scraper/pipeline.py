"""
scraper/pipeline.py

This module is the user's production scraper integrated verbatim.
The `scrape(url)` function is the public interface used by routers/analyze.py.

3-Tier pipeline:
  Tier A  — trafilatura (fast, most domains)
  Tier B  — Playwright Stealth Chrome → Googlebot UA (JS-heavy / blocked domains)
  Tier C  — Wayback Machine → DuckDuckGo snippet → Meta tags (last resort)

The scraper runs synchronously. analyze.py wraps it in a ThreadPoolExecutor
so it does not block the FastAPI async event loop.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import threading
import time
import warnings
from dataclasses import asdict, dataclass, field
from typing import Optional
from urllib.parse import quote_plus, urlparse

import os
import urllib3

import requests
import trafilatura
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# ── SSL bypass (local network / corporate proxy uses self-signed certs) ──────
warn = warnings.filterwarnings
warn("ignore", category=XMLParsedAsHTMLWarning)
warn("ignore", category=urllib3.exceptions.InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
os.environ.setdefault("PYTHONHTTPSVERIFY", "0")

_SESSION = requests.Session()
_SESSION.verify = False

_SKIP_URL_PATTERNS = re.compile(
    r"/(feed|rss|sitemap|tag|tags|category|author|search|page/\d+|"
    r"subscribe|newsletter|login|signup|about|contact|privacy|terms)"
    r"(/|$|\?)",
    re.IGNORECASE,
)


def is_article_url(url: str) -> bool:
    path = urlparse(url).path
    if _SKIP_URL_PATTERNS.search(path):
        return False
    if path.strip("/") == "":
        return False
    return True


TIER_A_DOMAINS: set[str] = {
    "anarchistnews.org", "abolitionmedia.noblogs.org", "angryworkers.org",
    "anti-imperialist.net", "blackrosefed.org", "crimethinc.com",
    "counterpunch.org", "commondreams.org", "currentaffairs.org",
    "jacobin.com", "itsgoingdown.org", "leftcom.org", "libcom.org",
    "people.com", "peoplesdispatch.org", "popularresistance.org",
    "rebelnews.com", "redstate.com", "socialism.com", "tempestmag.org",
    "theintercept.com", "workers.org", "znetwork.org",
    "19fortyfive.com", "404media.co", "agweb.com", "alternet.org",
    "babylonbee.com", "breitbart.com", "city-journal.org", "dailywire.com",
    "hotair.com", "nationalreview.com", "notthebee.com", "pjmedia.com",
    "rawstory.com", "salon.com", "slate.com", "townhall.com",
    "twitchy.com", "vox.com",
    "11alive.com", "13abc.com", "2news.com", "8newsnow.com", "9news.com.au",
    "abc.net.au", "ajc.com", "al.com", "asahi.com", "bbc.co.uk",
    "bianet.org", "cbc.ca", "ctvnews.ca", "dw.com", "france24.com",
    "hindustantimes.com", "irishtimes.com", "kyivindependent.com",
    "politico.eu", "reuters.com", "scmp.com", "straitstimes.com",
    "thehill.com", "thestar.com",
    "ahmedelhennawy.substack.com", "astralcodexten.com",
    "cyberintel.substack.com", "deatleft.com",
    "findingequilibrium.substack.com", "incogkneegrowth.substack.com",
    "johnpavlovitz.com", "noahpinion.blog", "slowboring.com", "write.as",
}

TIER_B_DOMAINS: set[str] = {
    "8newsnow.com", "agweb.com", "al.com", "anti-imperialist.net",
    "babylonbee.com", "bianet.org", "cbc.ca", "deatleft.com",
    "itsgoingdown.org", "johnpavlovitz.com", "people.com",
    "peoplesdispatch.org", "popularresistance.org", "rebelnews.com",
    "redstate.com", "reuters.com", "thehill.com",
}

_UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36"
)
_UA_GOOGLEBOT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; "
    "+http://www.google.com/bot.html)"
)

_CF_SIGNALS = [
    "checking your browser", "cloudflare", "verify you are human",
    "enable javascript", "cf-browser-verification", "ray id",
    "attention required", "ddos protection", "turnstile",
]

MIN_TEXT_CHARS = 300
_PREFER_WWW = {"cbc.ca"}

FAILURE_DIAGNOSES: dict[str, str] = {
    "al.com": (
        "al.com uses Cloudflare Advanced Bot Protection with HAProxy + JS fingerprinting. "
        "Article body is injected client-side by a React SPA. Trafilatura sees no <article> markup."
    ),
    "cbc.ca": (
        "cbc.ca rejects bare hostname connections via HTTP/2 with ERR_HTTP2_PROTOCOL_ERROR. "
        "Fix: always prefix with https://www.cbc.ca/"
    ),
    "deatleft.com": (
        "deatleft.com returns ERR_NAME_NOT_RESOLVED — domain is offline."
    ),
    "reuters.com": (
        "reuters.com uses Cloudflare Enterprise with Turnstile CAPTCHA. "
        "Try Googlebot UA or Wayback Machine snapshot."
    ),
}


@dataclass
class ScrapeResult:
    url: str
    domain: str
    tier_used: str = "—"
    success: bool = False
    title: Optional[str] = None
    author: Optional[str] = None
    date: Optional[str] = None
    language: Optional[str] = None
    text: Optional[str] = None
    word_count: int = 0
    char_count: int = 0
    error: Optional[str] = None
    cloudflare_detected: bool = False
    failure_reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def preview(self, chars: int = 600) -> str:
        if not self.text:
            return "(no text)"
        return self.text[:chars] + ("…" if len(self.text) > chars else "")

    def is_thin(self) -> bool:
        return self.char_count < MIN_TEXT_CHARS


def diagnose_failure(result: ScrapeResult) -> str:
    domain = result.domain.lstrip("www.")
    if domain in FAILURE_DIAGNOSES:
        return FAILURE_DIAGNOSES[domain]
    err = (result.error or "").lower()
    if "err_name_not_resolved" in err:
        return f"DNS failure — {result.domain} is offline or does not exist."
    if "err_http2_protocol_error" in err:
        return f"HTTP/2 protocol error — try prefixing with www."
    if "err_connection_refused" in err:
        return f"Connection refused — server is blocking the IP."
    if "timeout" in err:
        return f"Page load timeout — site is slow or blocking headless browsers."
    if "cloudflare" in err or result.cloudflare_detected:
        return f"Cloudflare challenge page detected."
    if "no article body" in err or "extraction returned none" in err:
        return f"Page loaded but trafilatura found no article body. Likely JS-rendered SPA or paywall."
    return result.error or "Unknown failure."


def _normalise_url(url: str, domain: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lstrip("www.")
    if host in _PREFER_WWW and not parsed.netloc.startswith("www."):
        return url.replace(parsed.netloc, "www." + parsed.netloc, 1)
    return url


def _extract_dict(html: str, url: str, favor_recall: bool = True) -> Optional[dict]:
    kw = dict(url=url, include_comments=False, include_tables=True, favor_recall=favor_recall)
    if hasattr(trafilatura, "bare_extraction"):
        try:
            r = trafilatura.bare_extraction(html, **kw)
            if r and r.get("text"):
                return r
        except Exception:
            pass
    try:
        r = trafilatura.extract(html, output_format="python", **kw)
        if r and isinstance(r, dict) and r.get("text"):
            return r
    except (ValueError, TypeError):
        pass
    try:
        text = trafilatura.extract(html, **kw)
        if text and isinstance(text, str) and text.strip():
            return {"text": text.strip(), "title": None, "author": None,
                    "date": None, "language": None}
    except Exception:
        pass
    return None


def _populate_result(result: ScrapeResult, extracted: dict, fallback_title: str = "") -> ScrapeResult:
    text = (extracted.get("text") or "").strip()
    result.success    = bool(text)
    result.title      = extracted.get("title") or fallback_title or None
    result.author     = extracted.get("author")
    result.date       = extracted.get("date")
    result.language   = extracted.get("language")
    result.text       = text or None
    result.word_count = len(text.split()) if text else 0
    result.char_count = len(text)
    result.metadata   = {k: v for k, v in extracted.items()
                         if k not in {"text","title","author","date","language"} and v}
    if not result.date:
        m = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", result.url)
        if m:
            result.date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return result


def _detect_cloudflare(html: str) -> bool:
    lower = html.lower()
    return sum(1 for sig in _CF_SIGNALS if sig in lower) >= 2


def _apply_stealth(page) -> None:
    try:
        from playwright_stealth import stealth_sync
        stealth_sync(page)
        return
    except ImportError:
        pass
    page.add_init_script("""
        Object.defineProperty(navigator, 'webdriver',  { get: () => undefined });
        Object.defineProperty(navigator, 'plugins',    { get: () => [1,2,3,4,5] });
        Object.defineProperty(navigator, 'languages',  { get: () => ['en-US','en'] });
        window.chrome = { runtime: {} };
        const oq = window.navigator.permissions.query;
        window.navigator.permissions.query = (p) =>
            p.name === 'notifications'
                ? Promise.resolve({ state: Notification.permission })
                : oq(p);
    """)


def _dismiss_overlays(page) -> None:
    selectors = [
        "button:has-text('Accept all')", "button:has-text('Accept All')",
        "button:has-text('Accept cookies')", "button:has-text('I agree')",
        "button:has-text('Agree')", "button:has-text('Got it')",
        "button:has-text('OK')", "[id*='cookie'] button",
        "[class*='cookie'] button", "[class*='consent'] button",
        "button:has-text('No thanks')", "button:has-text('Not now')",
        "button:has-text('Close')", "[aria-label='Close']", "[aria-label='close']",
        ".modal-close", ".close-button",
    ]
    for sel in selectors:
        try:
            btn = page.query_selector(sel)
            if btn and btn.is_visible():
                btn.click(timeout=1000)
                time.sleep(0.3)
        except Exception:
            pass


_REQUESTS_HEADERS = {
    "User-Agent": _UA_CHROME,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def scrape_tier_a(url: str, retries: int = 2) -> ScrapeResult:
    domain = urlparse(url).netloc.lstrip("www.")
    url = _normalise_url(url, domain)
    result = ScrapeResult(url=url, domain=domain, tier_used="A")
    last_error = None
    for attempt in range(1 + retries):
        try:
            html = trafilatura.fetch_url(url, no_ssl=True)
            if not html:
                last_error = "fetch_url returned empty"
                time.sleep(2); continue
            extracted = _extract_dict(html, url) or _extract_dict(html, url, favor_recall=False)
            if not extracted:
                last_error = "trafilatura found no article body"
                break
            m = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
            fallback_title = m.group(1).strip() if m else ""
            return _populate_result(result, extracted, fallback_title)
        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"
            time.sleep(2)
    result.error = last_error
    result.failure_reason = diagnose_failure(result)
    return result


def _playwright_fetch(
    url: str, user_agent: str, extra_headers: dict,
    headed: bool = False, apply_stealth: bool = True, timeout_ms: int = 30_000,
    thread_timeout: float = 45.0,
) -> tuple[str, str]:
    result_container: dict = {"html": None, "title": None, "error": None}

    def _run_in_thread() -> None:
        if sys.platform == "win32":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as pw:
                browser = pw.chromium.launch(
                    headless=not headed,
                    args=[
                        "--no-sandbox",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--single-process",
                        "--ignore-certificate-errors",
                    ],
                )
                ctx = browser.new_context(
                    viewport={"width": 1280, "height": 900},
                    user_agent=user_agent, locale="en-US",
                    timezone_id="America/New_York",
                    extra_http_headers=extra_headers,
                    ignore_https_errors=True,
                )
                page = ctx.new_page()
                if apply_stealth:
                    _apply_stealth(page)
                try:
                    page.goto(url, wait_until="networkidle", timeout=timeout_ms)
                except PWTimeout:
                    pass
                page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2)")
                time.sleep(1.5)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(0.8)
                _dismiss_overlays(page)
                result_container["html"]  = page.content()
                result_container["title"] = page.title()
                browser.close()
        except Exception as exc:
            result_container["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            loop.close()

    t = threading.Thread(target=_run_in_thread, daemon=True)
    t.start()
    t.join(timeout=thread_timeout)
    if t.is_alive():
        raise TimeoutError(f"Playwright thread timed out after {thread_timeout}s")
    if result_container["error"]:
        raise RuntimeError(result_container["error"])
    if not result_container["html"]:
        raise RuntimeError("Playwright thread completed but returned no HTML")
    return result_container["html"], result_container["title"] or ""


def scrape_tier_b_stealth(url: str, headed: bool = False) -> ScrapeResult:
    domain = urlparse(url).netloc.lstrip("www.")
    url = _normalise_url(url, domain)
    result = ScrapeResult(url=url, domain=domain, tier_used="B-stealth")
    try:
        html, title = _playwright_fetch(
            url, user_agent=_UA_CHROME,
            extra_headers={
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "DNT": "1",
            },
            headed=headed, apply_stealth=True,
        )
        if _detect_cloudflare(html):
            result.cloudflare_detected = True
            time.sleep(5)
            result.error = "Cloudflare Turnstile Challenge Detected"
            extracted = _extract_dict(html, url)
            if extracted and len((extracted.get("text") or "")) >= MIN_TEXT_CHARS:
                return _populate_result(result, extracted, title)
            result.failure_reason = diagnose_failure(result)
            return result
        extracted = _extract_dict(html, url)
        if not extracted:
            result.error = "Playwright fetched page but trafilatura found no article body"
            result.failure_reason = diagnose_failure(result)
            return result
        return _populate_result(result, extracted, title)
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.failure_reason = diagnose_failure(result)
        return result


def scrape_tier_b_googlebot(url: str, headed: bool = False) -> ScrapeResult:
    domain = urlparse(url).netloc.lstrip("www.")
    url = _normalise_url(url, domain)
    result = ScrapeResult(url=url, domain=domain, tier_used="B-googlebot")
    try:
        html, title = _playwright_fetch(
            url, user_agent=_UA_GOOGLEBOT,
            extra_headers={
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Referer": "https://www.google.com/",
                "From": "googlebot(at)googlebot.com",
            },
            headed=headed, apply_stealth=False,
        )
        if _detect_cloudflare(html):
            result.cloudflare_detected = True
            result.error = "Cloudflare Challenge detected even for Googlebot"
            result.failure_reason = diagnose_failure(result)
            return result
        extracted = _extract_dict(html, url)
        if not extracted:
            result.error = "Googlebot fetch succeeded but no article body found"
            result.failure_reason = diagnose_failure(result)
            return result
        return _populate_result(result, extracted, title)
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.failure_reason = diagnose_failure(result)
        return result


def scrape_tier_c_meta(url: str) -> ScrapeResult:
    domain = urlparse(url).netloc.lstrip("www.")
    result = ScrapeResult(url=url, domain=domain, tier_used="C-meta")
    try:
        resp = _SESSION.get(url, headers=_REQUESTS_HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
            soup = BeautifulSoup(resp.text, "html.parser")

        def meta(prop: str) -> Optional[str]:
            tag = (soup.find("meta", property=prop) or
                   soup.find("meta", attrs={"name": prop}))
            return tag.get("content", "").strip() if tag else None

        title       = meta("og:title") or meta("twitter:title") or (soup.title.string if soup.title else None)
        description = meta("og:description") or meta("twitter:description") or meta("description")
        author      = meta("article:author") or meta("author")
        pub_date    = meta("article:published_time") or meta("og:updated_time")
        text_parts  = [p for p in [title, description] if p]
        text = "\n\n".join(text_parts)
        result.title = title; result.author = author; result.date = pub_date
        result.text = text or None
        result.word_count = len(text.split()) if text else 0
        result.char_count = len(text)
        result.success = bool(text)
        if not result.success:
            result.error = "No usable meta tags found"
            result.failure_reason = diagnose_failure(result)
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.failure_reason = diagnose_failure(result)
    return result


def scrape_tier_c_wayback(url: str) -> ScrapeResult:
    domain = urlparse(url).netloc.lstrip("www.")
    result = ScrapeResult(url=url, domain=domain, tier_used="C-wayback")
    try:
        avail_api = f"https://archive.org/wayback/available?url={quote_plus(url)}"
        resp  = _SESSION.get(avail_api, headers=_REQUESTS_HEADERS, timeout=10)
        data  = resp.json()
        snap  = data.get("archived_snapshots", {}).get("closest", {})
        if not snap or not snap.get("available"):
            result.error = "Wayback Machine: no snapshot available"
            result.failure_reason = diagnose_failure(result)
            return result
        wb_url = snap["url"]
        wb_raw = re.sub(r"archive\.org/web/(\d+)/", r"archive.org/web/\1id_/", wb_url)
        result.metadata["wayback_url"] = wb_url
        html = trafilatura.fetch_url(wb_raw, no_ssl=True) or trafilatura.fetch_url(wb_url, no_ssl=True)
        if not html:
            result.error = "Wayback fetch returned empty HTML"
            result.failure_reason = diagnose_failure(result)
            return result
        extracted = _extract_dict(html, url)
        if not extracted:
            result.error = "Wayback page fetched but no article body found"
            result.failure_reason = diagnose_failure(result)
            return result
        return _populate_result(result, extracted)
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.failure_reason = diagnose_failure(result)
        return result


def scrape_tier_c_duckduckgo(url: str) -> ScrapeResult:
    domain = urlparse(url).netloc.lstrip("www.")
    result = ScrapeResult(url=url, domain=domain, tier_used="C-ddg")
    try:
        query   = f"site:{url}"
        api_url = f"https://api.duckduckgo.com/?q={quote_plus(query)}&format=json&no_html=1&skip_disambig=1"
        resp    = _SESSION.get(api_url, headers=_REQUESTS_HEADERS, timeout=10)
        data    = resp.json()
        snippets = []
        for key in ("AbstractText", "Abstract"):
            if data.get(key):
                snippets.append(data[key])
        for topic in data.get("RelatedTopics", [])[:5]:
            if isinstance(topic, dict) and topic.get("Text"):
                snippets.append(topic["Text"])
        seen, unique = set(), []
        for s in snippets:
            if s and s not in seen:
                seen.add(s); unique.append(s)
        text = "\n\n".join(unique)
        result.title      = data.get("Heading") or None
        result.text       = text or None
        result.word_count = len(text.split()) if text else 0
        result.char_count = len(text)
        result.success    = bool(text)
        if not result.success:
            result.error = "DuckDuckGo returned no snippet"
            result.failure_reason = diagnose_failure(result)
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.failure_reason = diagnose_failure(result)
    return result


def scrape(url: str, headed: bool = False, force_tier: Optional[str] = None) -> ScrapeResult:
    """
    Public interface. Full 3-tier pipeline.
    Called by routers/analyze.py via ThreadPoolExecutor.
    """
    domain = urlparse(url).netloc.lstrip("www.")

    if not force_tier and not is_article_url(url):
        result = ScrapeResult(url=url, domain=domain, tier_used="SKIP")
        result.error = "Non-article URL — skipped"
        return result

    def log(msg: str) -> None:
        import logging
        logging.getLogger("sntis.scraper").info("[%s] %s", domain, msg)

    if force_tier:
        dispatch = {
            "A":           lambda: scrape_tier_a(url),
            "B-stealth":   lambda: scrape_tier_b_stealth(url, headed),
            "B-googlebot": lambda: scrape_tier_b_googlebot(url, headed),
            "C-wayback":   lambda: scrape_tier_c_wayback(url),
            "C-ddg":       lambda: scrape_tier_c_duckduckgo(url),
            "C-meta":      lambda: scrape_tier_c_meta(url),
        }
        return dispatch[force_tier]()

    if domain not in TIER_B_DOMAINS:
        log("Tier A -> trafilatura")
        result = scrape_tier_a(url)
        if result.success and not result.is_thin():
            return result
        log(f"Tier A thin/failed ({result.char_count} chars) -> escalating")

    log("Tier B -> Playwright Stealth Chrome")
    result = scrape_tier_b_stealth(url, headed)
    if result.success and not result.is_thin():
        return result

    log("Tier B -> Playwright Googlebot UA")
    result = scrape_tier_b_googlebot(url, headed)
    if result.success and not result.is_thin():
        return result
    log(f"Tier B failed -> Tier C")

    log("Tier C -> Wayback Machine")
    result = scrape_tier_c_wayback(url)
    if result.success and not result.is_thin():
        return result

    log("Tier C -> DuckDuckGo snippet")
    result = scrape_tier_c_duckduckgo(url)
    if result.success:
        return result

    log("Tier C -> Meta tags (last resort)")
    return scrape_tier_c_meta(url)
