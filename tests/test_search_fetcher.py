import unittest
from unittest.mock import Mock, patch

from tools.search.fetcher import ContentFetcher
from tools.search.models import SearchResult


HTML = """
<html>
  <head><title>Barcelona Results</title></head>
  <body>
    <h1>Barcelona fixtures</h1>
    <p>Recent La Liga results.</p>
    <ul><li>Barcelona 2-0 Real Madrid</li></ul>
    <table>
      <tr><th>Date</th><th>Home</th><th>Score</th><th>Away</th></tr>
      <tr><td>2026-05-10</td><td>Barcelona</td><td>2-0</td><td>Real Madrid</td></tr>
    </table>
  </body>
</html>
"""


class ContentFetcherTests(unittest.TestCase):
    def test_fetcher_extracts_headings_lists_paragraphs_and_tables(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.text = HTML

        result = SearchResult("Result title", "https://example.com/results", "snippet", "searxng", 1, "query")

        with patch("tools.search.fetcher.requests.get", return_value=response):
            pages = ContentFetcher(timeout=1.0).fetch([result])

        self.assertEqual(len(pages), 1)
        self.assertTrue(pages[0].ok)
        self.assertEqual(pages[0].title, "Barcelona Results")
        self.assertIn("Barcelona fixtures", pages[0].text)
        self.assertIn("Barcelona 2-0 Real Madrid", pages[0].text)
        self.assertIn("2026-05-10 | Barcelona | 2-0 | Real Madrid", pages[0].text)

    def test_fetcher_deduplicates_urls_and_records_failures(self):
        first = SearchResult("A", "https://example.com/a", "", "searxng", 1, "query")
        duplicate = SearchResult("A copy", "https://example.com/a", "", "ddgs", 1, "query")
        failing = SearchResult("B", "https://example.com/b", "", "ddgs", 2, "query")

        ok_response = Mock()
        ok_response.raise_for_status.return_value = None
        ok_response.text = "<html><head><title>A</title></head><body><p>Alpha</p></body></html>"

        def fake_get(url, headers, timeout):
            if url.endswith("/b"):
                raise RuntimeError("network down")
            return ok_response

        with patch("tools.search.fetcher.requests.get", side_effect=fake_get), \
             patch("tools.search.fetcher.BROWSER_SETTINGS", {"use_playwright": False, "fallback_only": True}):
            pages = ContentFetcher(timeout=1.0).fetch([first, duplicate, failing])

        self.assertEqual(len(pages), 2)
        self.assertTrue(pages[0].ok)
        self.assertFalse(pages[1].ok)
        self.assertEqual(pages[1].error, "network down")


if __name__ == "__main__":
    unittest.main()
