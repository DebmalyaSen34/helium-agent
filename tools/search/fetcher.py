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


def needs_javascript(text: str) -> bool:
    """True when extracted text looks like a page that only renders with JavaScript."""
    lowered = text.lower()
    return len(text.strip()) < 200 or any(phrase in lowered for phrase in JS_REQUIRED_PHRASES)


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
        try:
            response = requests.get(result.url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
        except Exception as exc:
            logger.debug("Failed to fetch %s: %s", result.url, exc)
            return FetchedPage(url=result.url, title=result.title, text="", source_result=result, ok=False, error=str(exc))

        soup = BeautifulSoup(response.text, "html.parser")
        title = self._title(soup, result.title)
        text = self._extract_text(soup)
        if needs_javascript(text):
            note = "(This page builds its content with JavaScript, which Helium does not run, so little text could be read.)"
            text = f"{text}\n\n{note}".strip()
        return FetchedPage(url=result.url, title=title, text=text, source_result=result)

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
