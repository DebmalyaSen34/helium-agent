from __future__ import annotations

import concurrent.futures
import logging

import requests
from bs4 import BeautifulSoup

from config.settings import BROWSER_SETTINGS
from tools.search.models import FetchedPage, SearchResult

logger = logging.getLogger(__name__)

# Common phrases that indicate a page needs JavaScript to render
JS_REQUIRED_PHRASES = [
    "javascript is required",
    "enable javascript",
    "requires javascript",
    "please enable js",
    "js is disabled",
    "browser does not support javascript",
]


class ContentFetcher:
    def __init__(self, timeout: float | None = None, max_workers: int = 6) -> None:
        self.timeout = timeout or BROWSER_SETTINGS.get("timeout_seconds", 5.0)
        self.max_workers = max_workers
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        }

    def fetch(self, results: list[SearchResult]) -> list[FetchedPage]:
        unique_results = list({result.url: result for result in results}.values())
        if not unique_results:
            return []

        workers = min(self.max_workers, len(unique_results))
        pages_by_index: dict[int, FetchedPage] = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._fetch_one, result): index
                for index, result in enumerate(unique_results)
            }
            for future in concurrent.futures.as_completed(futures):
                pages_by_index[futures[future]] = future.result()
        return [pages_by_index[index] for index in range(len(unique_results))]

    def _fetch_one(self, result: SearchResult) -> FetchedPage:
        use_playwright = BROWSER_SETTINGS.get("use_playwright", True)
        fallback_only = BROWSER_SETTINGS.get("fallback_only", True)

        req_err = None
        req_ok = False
        text = ""
        title = result.title

        # Phase 1: Try requests + BeautifulSoup if fallback_only is enabled
        if not use_playwright or fallback_only:
            try:
                response = requests.get(result.url, headers=self.headers, timeout=self.timeout)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                title = self._title(soup, result.title)
                text = self._extract_text(soup)
                req_ok = True
            except Exception as exc:
                req_err = exc
                logger.debug("Requests failed to fetch %s: %s", result.url, exc)

        # Check triggers for falling back to Playwright
        needs_fallback = False
        if use_playwright:
            if not req_ok:
                needs_fallback = True
                logger.info("Requests failed for %s. Falling back to Playwright...", result.url)
            else:
                # Check for empty text or JS required indicator in text
                text_lower = text.lower()
                has_js_warning = any(phrase in text_lower for phrase in JS_REQUIRED_PHRASES)
                if len(text.strip()) < 200 or has_js_warning:
                    needs_fallback = True
                    logger.info(
                        "Extracted text too short or JS warning detected for %s (len=%d, js_warn=%s). "
                        "Falling back to Playwright...",
                        result.url, len(text), has_js_warning
                    )

        # Phase 2: Fetch with Playwright if fallback is triggered or we only use Playwright
        if use_playwright and (needs_fallback or not fallback_only):
            try:
                title, text = self._fetch_with_playwright(result.url)
                return FetchedPage(url=result.url, title=title, text=text, source_result=result)
            except Exception as exc:
                logger.error("Playwright failed to fetch %s: %s", result.url, exc)
                # If Playwright failed, but requests succeeded in Phase 1, return the requests result
                if req_ok:
                    logger.info("Reverting to Requests result for %s despite JS/short text warnings.", result.url)
                    return FetchedPage(url=result.url, title=title, text=text, source_result=result)
                
                # If both failed, return a failed FetchedPage
                return FetchedPage(
                    url=result.url,
                    title=result.title,
                    text="",
                    source_result=result,
                    ok=False,
                    error=f"Requests error: {req_err} | Playwright error: {exc}",
                )

        # If we didn't use/fallback to Playwright, return the Requests result or the requests error
        if req_ok:
            return FetchedPage(url=result.url, title=title, text=text, source_result=result)
        else:
            return FetchedPage(
                url=result.url,
                title=result.title,
                text="",
                source_result=result,
                ok=False,
                error=str(req_err or "Fetching disabled/failed"),
            )

    def _fetch_with_playwright(self, url: str) -> tuple[str, str]:
        """Fetches the page using Playwright. Returns (title, text)."""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise ImportError(
                "Playwright is enabled but not installed in the environment. "
                "Please run: pip install playwright && playwright install chromium"
            ) from e

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=BROWSER_SETTINGS.get("headless", True))
            try:
                page = browser.new_page(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
                    )
                )
                timeout_ms = int(self.timeout * 1000)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                
                # Wait a short duration or network idle to let Javascript run
                try:
                    page.wait_for_load_state("networkidle", timeout=2000)
                except Exception:
                    pass  # Ignore networkidle timeout, we still have domcontentloaded
                
                title = page.title() or ""
                html = page.content()
                
                soup = BeautifulSoup(html, "html.parser")
                text = self._extract_text(soup)
                return title, text
            finally:
                browser.close()

    def _title(self, soup: BeautifulSoup, fallback: str) -> str:
        if soup.title and soup.title.string:
            return " ".join(soup.title.string.split())
        return fallback

    def _extract_text(self, soup: BeautifulSoup) -> str:
        import re
        
        # Decompose structural layout tags
        for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "aside"]):
            tag.decompose()

        # Decompose elements with classes/IDs matching layout keywords
        nav_pattern = re.compile(r"\b(nav|menu|sidebar|footer|header|meta)\b", re.I)
        for element in soup.find_all(attrs={"class": nav_pattern}):
            element.decompose()
        for element in soup.find_all(attrs={"id": nav_pattern}):
            element.decompose()

        chunks: list[str] = []
        for element in soup.find_all(["h1", "h2", "h3", "p", "li"]):
            if not element.name:
                continue
            text = " ".join(element.get_text(" ", strip=True).split())
            if text:
                chunks.append(text)

        for row in soup.find_all("tr"):
            cells = [
                " ".join(cell.get_text(" ", strip=True).split())
                for cell in row.find_all(["th", "td"])
            ]
            cells = [cell for cell in cells if cell]
            if cells:
                chunks.append(" | ".join(cells))

        return "\n".join(dict.fromkeys(chunks))[:8000]
