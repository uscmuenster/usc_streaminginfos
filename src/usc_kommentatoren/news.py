"""Collect articles from multiple news sources."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

import requests
from bs4 import BeautifulSoup
from requests.compat import urljoin
from feedparser import parse as parse_feed

from .config import NewsSource

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class Article:
    title: str
    link: str
    source: str
    summary: Optional[str] = None


def gather_articles(sources: Sequence[NewsSource]) -> List[Article]:
    articles: List[Article] = []
    for source in sources:
        try:
            if source.type == "rss":
                articles.extend(_collect_from_rss(source))
            else:
                articles.extend(_collect_from_html(source))
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("Failed to collect articles from %s: %s", source.url, exc)
    return articles


def _collect_from_rss(source: NewsSource) -> Iterable[Article]:
    feed = parse_feed(source.url)
    entries = feed.entries[: source.limit]
    for entry in entries:
        title = getattr(entry, "title", "").strip()
        link = getattr(entry, "link", "").strip()
        summary = getattr(entry, "summary", None)
        if not title or not link:
            continue
        yield Article(title=title, link=link, source=source.name, summary=summary)


def _collect_from_html(source: NewsSource) -> Iterable[Article]:
    response = requests.get(source.url, headers={"User-Agent": "usc_kommentatoren/1.0"}, timeout=30)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = soup.select("article a, h2 a, h3 a")
    seen = set()
    for item in items:
        href = item.get("href")
        text = item.get_text(strip=True)
        if not href or not text:
            continue
        if (text, href) in seen:
            continue
        absolute_href = urljoin(source.url, href)
        seen.add((text, absolute_href))
        yield Article(title=text, link=absolute_href, source=source.name)
        if len(seen) >= source.limit:
            break
