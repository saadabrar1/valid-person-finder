"""
Search tools for PersonFinderTool.

Provides SerpAPI (Google) and DuckDuckGo search functions with
rate-limiting, exception handling, and structured output.
"""

import os
import time
from typing import Any, Dict, List

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS
from dotenv import load_dotenv

from src.utilis.logger import logger

load_dotenv()

# ---------------------------------------------------------------------------
# Rate-limiting helper
# ---------------------------------------------------------------------------
_last_call_ts: Dict[str, float] = {"serpapi": 0.0, "ddg": 0.0}
_MIN_INTERVAL = 1.5  # seconds between requests to the same engine


def _rate_limit(engine: str) -> None:
    """Block until the minimum interval has elapsed for *engine*."""
    elapsed = time.time() - _last_call_ts.get(engine, 0.0)
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_call_ts[engine] = time.time()


# ---------------------------------------------------------------------------
# SerpAPI Search
# ---------------------------------------------------------------------------

def serpapi_search(query: str, num_results: int = 10) -> List[Dict[str, Any]]:
    """Search Google via SerpAPI and return structured results.

    Args:
        query: Search query string.
        num_results: Maximum number of results to return.

    Returns:
        List of dicts with keys: title, link, snippet, source_engine.
    """
    api_key = os.getenv("SERPAPI_API_KEY", "") or os.getenv("SERPAPI_KEY", "")
    if not api_key:
        logger.error("SERPAPI_API_KEY / SERPAPI_KEY not set in environment")
        return []

    _rate_limit("serpapi")
    logger.info("SerpAPI search – query: %s", query)

    try:
        params = {
            "engine": "google",
            "q": query,
            "api_key": api_key,
            "num": num_results,
        }
        response = requests.get(
            "https://serpapi.com/search", params=params, timeout=30
        )
        response.raise_for_status()
        data = response.json()

        results: List[Dict[str, Any]] = []
        for item in data.get("organic_results", []):
            results.append(
                {
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source_engine": "serpapi",
                }
            )

        logger.info("SerpAPI returned %d results for: %s", len(results), query)
        return results

    except requests.RequestException as exc:
        logger.error("SerpAPI request failed: %s", exc)
        return []
    except (KeyError, ValueError) as exc:
        logger.error("SerpAPI response parsing error: %s", exc)
        return []


# ---------------------------------------------------------------------------
# DuckDuckGo Search
# ---------------------------------------------------------------------------

def duckduckgo_search(query: str, num_results: int = 10) -> List[Dict[str, Any]]:
    """Search via DuckDuckGo and return structured results.

    Args:
        query: Search query string.
        num_results: Maximum number of results to return.

    Returns:
        List of dicts with keys: title, link, snippet, source_engine.
    """
    _rate_limit("ddg")
    logger.info("DuckDuckGo search – query: %s", query)

    try:
        with DDGS() as ddgs:
            raw = list(ddgs.text(query, max_results=num_results))

        results: List[Dict[str, Any]] = []
        for item in raw:
            results.append(
                {
                    "title": item.get("title", ""),
                    "link": item.get("href", ""),
                    "snippet": item.get("body", ""),
                    "source_engine": "duckduckgo",
                }
            )

        logger.info("DuckDuckGo returned %d results for: %s", len(results), query)
        return results

    except Exception as exc:  # DDGS may raise various exceptions
        logger.error("DuckDuckGo search failed: %s", exc)
        return []


# ---------------------------------------------------------------------------
# Merge & Deduplicate
# ---------------------------------------------------------------------------

def merge_and_deduplicate(
    serp_results: List[Dict[str, Any]],
    ddg_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Merge results from both engines and remove duplicates by URL.

    Args:
        serp_results: Results from SerpAPI.
        ddg_results: Results from DuckDuckGo.

    Returns:
        Deduplicated list of search results.
    """
    seen_urls: set = set()
    merged: List[Dict[str, Any]] = []

    for item in serp_results + ddg_results:
        url = item.get("link", "").rstrip("/").lower()
        if url and url not in seen_urls:
            seen_urls.add(url)
            merged.append(item)

    logger.info(
        "Merged results: %d (SerpAPI=%d, DDG=%d, after dedup=%d)",
        len(serp_results) + len(ddg_results),
        len(serp_results),
        len(ddg_results),
        len(merged),
    )
    return merged


# ---------------------------------------------------------------------------
# Page scraper (used by Validator agent) — powered by ContentScraper
# ---------------------------------------------------------------------------

def scrape_page(url: str, max_chars: int = 5000) -> str:
    """Scrape and return visible text from a URL using ContentScraper.

    Uses requests + BeautifulSoup first, falls back to Selenium for
    dynamic/JS-heavy pages, and applies readability-based extraction.

    Args:
        url: Web page URL.
        max_chars: Maximum characters to return.

    Returns:
        Cleaned page text or empty string on failure.
    """
    from src.tools.scraper import ContentScraper

    try:
        scraper = ContentScraper(headless=True, wait_time=10)
        result = scraper.scrape_content(url)
        text = result.get("text", "")
        return text[:max_chars] if text else ""
    except Exception as exc:
        logger.warning("ContentScraper failed for %s: %s", url, exc)
        return ""