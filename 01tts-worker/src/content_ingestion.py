import datetime
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any

import requests


@dataclass
class ContentMetadata:
    source_type: str  # "TEXT" | "URL" | "NEWS" | "TECH_DOC"
    source_url: str
    published_at: str
    fetched_at: str
    title: str
    passage: str
    raw_content: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceType": self.source_type,
            "sourceUrl": self.source_url,
            "publishedAt": self.published_at,
            "fetchedAt": self.fetched_at,
            "title": self.title,
            "passage": self.passage,
        }


def clean_html_text(raw_html: str) -> tuple[str, str]:
    """Extract (title, cleaned_text_passage) from HTML content."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    title = html.unescape(title_match.group(1)).strip() if title_match else ""

    # Remove script, style, header, footer, nav tags
    clean = re.sub(r"<(script|style|header|footer|nav)[^>]*>.*?</\1>", " ", raw_html, flags=re.IGNORECASE | re.DOTALL)
    # Extract paragraph or text content
    paragraphs = re.findall(r"<p[^>]*>(.*?)</p>", clean, flags=re.IGNORECASE | re.DOTALL)
    if paragraphs:
        text = "\n".join(html.unescape(re.sub(r"<[^>]+>", " ", p)).strip() for p in paragraphs)
    else:
        text = html.unescape(re.sub(r"<[^>]+>", " ", clean))

    text = re.sub(r"\s+", " ", text).strip()
    return title, text


def parse_rss_or_atom(xml_content: str) -> tuple[str, str, str, str]:
    """
    Parse RSS/Atom XML feed.
    Returns (title, passage, published_at, source_link).
    """
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return "", "", "", ""

    # RSS 2.0 format (<rss><channel><item>...)
    channel = root.find("channel")
    if channel is not None:
        item = channel.find("item")
        if item is not None:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub_date = (item.findtext("pubDate") or item.findtext("dc:date") or "").strip()
            desc = (item.findtext("description") or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded") or "").strip()
            _, passage = clean_html_text(desc) if "<" in desc else ("", desc)
            return title, passage or desc, pub_date, link

    # Atom format (<feed><entry>...)
    if root.tag.endswith("feed"):
        entry = root.find("{http://www.w3.org/2005/Atom}entry")
        if entry is not None:
            title = (entry.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            updated = (entry.findtext("{http://www.w3.org/2005/Atom}updated") or entry.findtext("{http://www.w3.org/2005/Atom}published") or "").strip()
            link_elem = entry.find("{http://www.w3.org/2005/Atom}link")
            link = link_elem.attrib.get("href", "") if link_elem is not None else ""
            summary = (entry.findtext("{http://www.w3.org/2005/Atom}summary") or entry.findtext("{http://www.w3.org/2005/Atom}content") or "").strip()
            _, passage = clean_html_text(summary) if "<" in summary else ("", summary)
            return title, passage or summary, updated, link

    return "", "", "", ""


def parse_feed_entries(xml_content: str, limit: int = 8) -> list[dict[str, str]]:
    """Parse several RSS/Atom entries instead of silently selecting only the first."""
    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError:
        return []
    entries: list[dict[str, str]] = []
    channel = root.find("channel")
    if channel is not None:
        for item in channel.findall("item")[:limit]:
            description = (
                item.findtext("description")
                or item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
                or ""
            ).strip()
            _, passage = clean_html_text(description) if "<" in description else ("", description)
            entries.append(
                {
                    "title": (item.findtext("title") or "").strip(),
                    "passage": passage or description,
                    "publishedAt": (
                        item.findtext("pubDate")
                        or item.findtext("{http://purl.org/dc/elements/1.1/}date")
                        or ""
                    ).strip(),
                    "sourceUrl": (item.findtext("link") or "").strip(),
                }
            )
    elif root.tag.endswith("feed"):
        namespace = "{http://www.w3.org/2005/Atom}"
        for entry in root.findall(f"{namespace}entry")[:limit]:
            link = ""
            for link_element in entry.findall(f"{namespace}link"):
                candidate = link_element.attrib.get("href", "")
                if candidate and link_element.attrib.get("rel", "alternate") in {"alternate", ""}:
                    link = candidate
                    break
            summary = (
                entry.findtext(f"{namespace}summary")
                or entry.findtext(f"{namespace}content")
                or ""
            ).strip()
            _, passage = clean_html_text(summary) if "<" in summary else ("", summary)
            entries.append(
                {
                    "title": (entry.findtext(f"{namespace}title") or "").strip(),
                    "passage": passage or summary,
                    "publishedAt": (
                        entry.findtext(f"{namespace}updated")
                        or entry.findtext(f"{namespace}published")
                        or ""
                    ).strip(),
                    "sourceUrl": link,
                }
            )
    return [
        entry for entry in entries
        if entry["title"] and entry["sourceUrl"] and entry["passage"]
    ]


def fetch_feed_candidates(
    feed_url: str,
    timeout: int = 20,
    limit: int = 8,
) -> list[ContentMetadata]:
    response = requests.get(
        feed_url,
        headers={"User-Agent": "Mozilla/5.0 (ListeningLabWorker)"},
        timeout=timeout,
    )
    response.raise_for_status()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    return [
        ContentMetadata(
            source_type="NEWS",
            source_url=entry["sourceUrl"],
            published_at=entry["publishedAt"],
            fetched_at=now_iso,
            title=entry["title"],
            passage=entry["passage"],
            raw_content=response.text,
        )
        for entry in parse_feed_entries(response.text, limit=limit)
    ]


def fetch_content(
    source_type: str,
    source_input: str,
    news_sources: list[str] | None = None,
    timeout: int = 20,
) -> ContentMetadata:
    """
    Fetch and ingest content for TEXT, URL, NEWS, or TECH_DOC.
    Retains sourceType, sourceUrl, publishedAt, and fetchedAt metadata.
    """
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    st = (source_type or "TEXT").upper().strip()

    if st == "TEXT" or (
        st == "TECH_DOC"
        and not re.match(r"^https?://", source_input.strip(), re.IGNORECASE)
    ):
        first_line = source_input.strip().split("\n")[0][:60] if source_input else "Untitled Text"
        return ContentMetadata(
            source_type=st,
            source_url="",
            published_at="",
            fetched_at=now_iso,
            title=first_line or "Untitled Text",
            passage=source_input.strip(),
            raw_content=source_input,
        )

    target_url = source_input.strip()
    if st == "NEWS" and not target_url and news_sources:
        target_url = news_sources[0]

    if not target_url:
        return ContentMetadata(
            source_type=st,
            source_url="",
            published_at="",
            fetched_at=now_iso,
            title="Empty Source",
            passage=source_input,
        )

    resp = requests.get(target_url, headers={"User-Agent": "Mozilla/5.0 (ListeningLabWorker)"}, timeout=timeout)
    resp.raise_for_status()
    raw_text = resp.text

    if st == "NEWS" or "xml" in resp.headers.get("Content-Type", "") or raw_text.strip().startswith("<?xml"):
        title, passage, pub_date, link = parse_rss_or_atom(raw_text)
        if passage:
            return ContentMetadata(
                source_type="NEWS",
                source_url=link or target_url,
                published_at=pub_date,
                fetched_at=now_iso,
                title=title or "News Article",
                passage=passage,
                raw_content=raw_text,
            )

    title, passage = clean_html_text(raw_text)
    if not title:
        title = target_url.split("/")[-1] or "Ingested Document"

    return ContentMetadata(
        source_type="TECH_DOC" if st == "TECH_DOC" else "URL",
        source_url=target_url,
        published_at="",
        fetched_at=now_iso,
        title=title,
        passage=passage or raw_text,
        raw_content=raw_text,
    )
