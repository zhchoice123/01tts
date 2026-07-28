import unittest
from unittest.mock import Mock, patch

from src.content_ingestion import (
    ContentMetadata,
    clean_html_text,
    fetch_content,
    parse_feed_entries,
    parse_rss_or_atom,
)


class ContentIngestionTest(unittest.TestCase):
    def test_text_ingestion(self):
        meta = fetch_content("TEXT", "This is direct raw text input for testing.")
        self.assertEqual("TEXT", meta.source_type)
        self.assertEqual("", meta.source_url)
        self.assertEqual("This is direct raw text input for testing.", meta.passage)
        self.assertNotEqual("", meta.fetched_at)

    @patch("src.content_ingestion.requests.get")
    def test_inline_technical_document_does_not_make_http_request(self, mock_get):
        meta = fetch_content(
            "TECH_DOC",
            "Java virtual threads reduce the cost of blocking concurrency.",
        )

        self.assertEqual("TECH_DOC", meta.source_type)
        self.assertEqual("", meta.source_url)
        self.assertIn("virtual threads", meta.passage)
        mock_get.assert_not_called()

    def test_clean_html_text(self):
        raw_html = """
        <html>
          <head><title>Test Article Title</title></head>
          <body>
            <script>console.log('ignore');</script>
            <p>First paragraph text.</p>
            <p>Second paragraph text.</p>
          </body>
        </html>
        """
        title, passage = clean_html_text(raw_html)
        self.assertEqual("Test Article Title", title)
        self.assertIn("First paragraph text.", passage)
        self.assertNotIn("console.log", passage)

    def test_parse_rss_feed(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
          <channel>
            <title>Tech Feed</title>
            <item>
              <title>RSS News Item</title>
              <link>https://example.com/rss-item</link>
              <pubDate>Mon, 25 Jul 2026 12:00:00 GMT</pubDate>
              <description><![CDATA[<p>RSS news paragraph content.</p>]]></description>
            </item>
          </channel>
        </rss>
        """
        title, passage, pub_date, link = parse_rss_or_atom(rss_xml)
        self.assertEqual("RSS News Item", title)
        self.assertIn("RSS news paragraph content.", passage)
        self.assertEqual("https://example.com/rss-item", link)
        self.assertEqual("Mon, 25 Jul 2026 12:00:00 GMT", pub_date)

    def test_parse_feed_entries_returns_multiple_candidates(self):
        xml = """<?xml version="1.0"?>
        <rss><channel>
          <item><title>First</title><link>https://example.com/1</link>
            <description>First backend article.</description></item>
          <item><title>Second</title><link>https://example.com/2</link>
            <description>Second backend article.</description></item>
        </channel></rss>"""
        entries = parse_feed_entries(xml)
        self.assertEqual(2, len(entries))
        self.assertEqual("https://example.com/2", entries[1]["sourceUrl"])

    @patch("src.content_ingestion.requests.get")
    def test_fetch_url_ingestion(self, mock_get):
        mock_resp = Mock()
        mock_resp.headers = {"Content-Type": "text/html"}
        mock_resp.text = "<html><head><title>Web Article</title></head><body><p>Web content</p></body></html>"
        mock_resp.raise_for_status.return_value = None
        mock_get.return_value = mock_resp

        meta = fetch_content("URL", "https://example.com/article")
        self.assertEqual("URL", meta.source_type)
        self.assertEqual("https://example.com/article", meta.source_url)
        self.assertEqual("Web Article", meta.title)
        self.assertEqual("Web content", meta.passage)


if __name__ == "__main__":
    unittest.main()
