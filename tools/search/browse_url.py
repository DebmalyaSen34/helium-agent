from __future__ import annotations

import logging
from tools.search.fetcher import ContentFetcher
from tools.search.models import SearchResult

logger = logging.getLogger(__name__)


def browse_url(url: str, max_chars: int = 5000) -> str:
    """Navigates to a specific website, executes JavaScript (using Playwright fallback),
    and extracts clean, readable text.
    
    Args:
        url: The URL of the webpage to browse.
        max_chars: The maximum length of characters to return (defaults to 5000).
        
    Returns:
        A string containing the page title and the extracted text.
    """
    logger.info("Direct browsing requested for: %s", url)
    
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    search_result = SearchResult(
        title="Direct Browse",
        url=url,
        snippet="",
        provider="browse_tool",
        rank=1,
        query="browse_url",
    )
    
    try:
        fetcher = ContentFetcher(timeout=10.0)
        page = fetcher._fetch_one(search_result)
        
        if not page.ok:
            return f"Error: Failed to browse URL: {page.error}"
            
        header = f"Page Title: {page.title}\nURL: {page.url}\n\nContent:\n"
        content = page.text.strip()
        if not content:
            return f"Page Title: {page.title}\nURL: {page.url}\n\nContent:\n(No readable content was extracted.)"
            
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n... [Truncated. Output capped at {max_chars} characters]"
            
        return header + content
    except Exception as exc:
        logger.error("Failed executing browse_url for %s: %s", url, exc)
        return f"Error: An unexpected exception occurred while browsing: {exc}"
