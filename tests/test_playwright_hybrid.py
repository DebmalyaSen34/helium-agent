import unittest
from unittest.mock import MagicMock, patch

from tools.search.fetcher import ContentFetcher
from tools.search.models import SearchResult
from tools.search.browse_url import browse_url


class PlaywrightHybridFetcherTests(unittest.TestCase):
    def setUp(self):
        self.result = SearchResult(
            title="Test Page",
            url="http://testdynamic.com",
            snippet="Snippet",
            provider="test",
            rank=1,
            query="test",
        )

    @patch("requests.get")
    def test_requests_success_no_fallback(self, mock_get):
        # 1. Setup requests to return full valid HTML text (no fallback needed)
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>" + "This is a lot of rich static text content that requests can extract perfectly fine without needing dynamic Javascript rendering. " * 5 + "</p></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetcher = ContentFetcher()
        # Mock _fetch_with_playwright to make sure it's NOT called
        fetcher._fetch_with_playwright = MagicMock()

        page = fetcher._fetch_one(self.result)

        self.assertTrue(page.ok)
        self.assertIn("This is a lot of rich static text", page.text)
        fetcher._fetch_with_playwright.assert_not_called()

    @patch("requests.get")
    def test_requests_fails_fallback_to_playwright(self, mock_get):
        # 2. Setup requests to fail, triggering Playwright fallback
        mock_get.side_effect = Exception("Connection Refused")

        fetcher = ContentFetcher()
        fetcher._fetch_with_playwright = MagicMock(return_value=("Playwright Title", "Rendered text from Playwright!"))

        page = fetcher._fetch_one(self.result)

        self.assertTrue(page.ok)
        self.assertEqual(page.title, "Playwright Title")
        self.assertEqual(page.text, "Rendered text from Playwright!")
        fetcher._fetch_with_playwright.assert_called_once_with("http://testdynamic.com")

    @patch("requests.get")
    def test_requests_empty_text_fallback_to_playwright(self, mock_get):
        # 3. Setup requests to return minimal content (SPA dynamic app)
        mock_response = MagicMock()
        mock_response.text = "<html><body><div id='app'>Loading...</div></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetcher = ContentFetcher()
        fetcher._fetch_with_playwright = MagicMock(return_value=("Playwright SPA", "Fully rendered SPA dynamic content!"))

        page = fetcher._fetch_one(self.result)

        self.assertTrue(page.ok)
        self.assertEqual(page.title, "Playwright SPA")
        self.assertEqual(page.text, "Fully rendered SPA dynamic content!")
        fetcher._fetch_with_playwright.assert_called_once_with("http://testdynamic.com")

    @patch("requests.get")
    def test_requests_js_warning_fallback_to_playwright(self, mock_get):
        # 4. Setup requests to return a "please enable JavaScript" warning page
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Please enable JavaScript to view this site.</p></body></html>"
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        fetcher = ContentFetcher()
        fetcher._fetch_with_playwright = MagicMock(return_value=("Playwright Decoded", "Clean text after running JS!"))

        page = fetcher._fetch_one(self.result)

        self.assertTrue(page.ok)
        self.assertEqual(page.text, "Clean text after running JS!")
        fetcher._fetch_with_playwright.assert_called_once_with("http://testdynamic.com")

    @patch("tools.search.browse_url.ContentFetcher")
    def test_standalone_browse_url_tool(self, mock_fetcher_cls):
        # 5. Test the high-level browse_url tool logic
        mock_fetcher = MagicMock()
        mock_page = MagicMock()
        mock_page.ok = True
        mock_page.title = "Mocked Page Title"
        mock_page.url = "https://mockedpage.com"
        mock_page.text = "This is the body content of the mocked page."
        mock_fetcher._fetch_one.return_value = mock_page
        mock_fetcher_cls.return_value = mock_fetcher

        result_text = browse_url("mockedpage.com")

        self.assertIn("Mocked Page Title", result_text)
        self.assertIn("https://mockedpage.com", result_text)
        self.assertIn("This is the body content", result_text)


if __name__ == "__main__":
    unittest.main()
