"""
hybrid_chatbot/web_search.py
---------------------------
DuckDuckGo web search + article extraction for deeper chatbot answers.
"""

from __future__ import annotations

from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup


class WebSearchClient:
    def __init__(self):
        self.enabled = True  # DuckDuckGo search does not require an API key.

    def search_and_scrape(self, query: str, max_results: int = 4) -> list[dict]:
        results = self._duckduckgo_search(query, max_results=max_results)
        out: list[dict] = []
        for idx, item in enumerate(results, start=1):
            url = item.get("url", "")
            content = self._extract_article(url) if url else ""
            out.append(
                {
                    "rank": idx,
                    "title": item.get("title", ""),
                    "url": url,
                    "source": _host_from_url(url),
                    "snippet": item.get("snippet", "")[:500],
                    "content": content[:3000],
                }
            )
        return out

    def _duckduckgo_search(self, query: str, max_results: int) -> list[dict]:
        # HTML endpoint has richer news/web results than the instant-answer API.
        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}&kl=us-en"
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                resp = client.get(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0",
                        "Accept-Language": "en-US,en;q=0.9",
                    },
                )
                resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        results: list[dict] = []

        nodes = soup.select(".result") or soup.select(".web-result")
        for node in nodes:
            a = node.select_one("a.result__a") or node.select_one("a")
            if not a:
                continue
            href = a.get("href", "").strip()
            title = a.get_text(" ", strip=True)
            if not href or not title:
                continue

            clean_url = _normalize_ddg_href(href)
            if not clean_url.startswith("http"):
                continue

            snippet_node = node.select_one(".result__snippet") or node.select_one(".result-snippet")
            snippet = snippet_node.get_text(" ", strip=True) if snippet_node else ""

            results.append(
                {
                    "title": title,
                    "url": clean_url,
                    "snippet": snippet,
                }
            )
            if len(results) >= max_results:
                break

        return results

    def _extract_article(self, url: str) -> str:
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True) as client:
                resp = client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                resp.raise_for_status()
                html = resp.text
        except Exception:
            return ""

        try:
            extracted = trafilatura.extract(
                html,
                include_comments=False,
                include_tables=False,
                favor_precision=True,
                no_fallback=False,
            )
            if extracted and extracted.strip():
                return " ".join(extracted.split())
        except Exception:
            pass

        try:
            soup = BeautifulSoup(html, "html.parser")
            paras = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
            joined = " ".join(t for t in paras if t).strip()
            return joined[:3000]
        except Exception:
            return ""


def _normalize_ddg_href(href: str) -> str:
    href = href.strip()
    if href.startswith("//"):
        href = "https:" + href
    if "/l/?" in href:
        qs = parse_qs(urlparse(href).query)
        uddg = qs.get("uddg", [""])[0]
        if uddg:
            return unquote(uddg)
    return href


def _host_from_url(url: str) -> str:
    if not url:
        return ""
    return (
        url.replace("https://", "")
        .replace("http://", "")
        .split("/")[0]
        .strip()
    )
