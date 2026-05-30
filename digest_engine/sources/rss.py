"""RSS / Atom source backed by feedparser with httpx pre-fetch and fallback parser."""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from time import struct_time

import feedparser
import httpx
from bs4 import BeautifulSoup

from digest_engine.models import RawItem
from digest_engine.sources.base import Source, register_source

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; digest-engine/0.1; "
    "+https://github.com/digest-engine)"
)

# XML spec allows only: #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
_INVALID_XML_RE = re.compile(
    r"[^\x09\x0A\x0D\x20-퟿-�\U00010000-\U0010FFFF]"
)


def _strip_invalid_xml(text: str) -> str:
    return _INVALID_XML_RE.sub("", text)


def _to_datetime(parsed: struct_time | None) -> datetime | None:
    if parsed is None:
        return None
    try:
        return datetime(*parsed[:6], tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(value.rstrip("Z")).replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _fetch_raw(url: str) -> tuple[int, str, str]:
    """Fetch URL with a browser-like UA. Returns (status, content_type, body)."""
    with httpx.Client(
        follow_redirects=True,
        timeout=60,
        headers={"User-Agent": _USER_AGENT},
    ) as client:
        resp = client.get(url)
    content_type = resp.headers.get("content-type", "")
    body = resp.content.decode("utf-8", errors="replace")
    return resp.status_code, content_type, body


def _fallback_parse(source_name: str, xml_text: str) -> list[RawItem]:
    """Try BeautifulSoup then xml.etree to extract entries from RSS/Atom."""
    items: list[RawItem] = []

    # --- BeautifulSoup path (handles both RSS <item> and Atom <entry>) ---
    try:
        soup = BeautifulSoup(xml_text, "lxml-xml")
        entries = soup.find_all("entry") or soup.find_all("item")
        for e in entries:
            title = (e.find("title") or {}).get_text(strip=True) if e.find("title") else ""
            link_tag = e.find("link")
            if link_tag:
                link = link_tag.get("href") or link_tag.get_text(strip=True)
            else:
                link = ""
            pub_raw = None
            for tag in ("published", "updated", "pubDate", "dc:date"):
                t = e.find(tag)
                if t:
                    pub_raw = t.get_text(strip=True)
                    break
            summary_tag = e.find("summary") or e.find("description") or e.find("content")
            summary = summary_tag.get_text(strip=True) if summary_tag else ""
            id_tag = e.find("id") or e.find("guid")
            item_id = id_tag.get_text(strip=True) if id_tag else (link or title)
            if not title and not link:
                continue
            items.append(RawItem(
                source_name=source_name,
                title=title,
                link=link,
                summary_html=summary,
                published=_parse_date(pub_raw),
                extra={"id": item_id},
            ))
        if items:
            return items
    except Exception as exc:
        logger.debug("BeautifulSoup fallback failed: %s", exc)

    # --- xml.etree path ---
    try:
        root = ET.fromstring(xml_text)
        ns_atom = "http://www.w3.org/2005/Atom"
        # Atom
        for entry in root.iter(f"{{{ns_atom}}}entry"):
            title_el = entry.find(f"{{{ns_atom}}}title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link_el = entry.find(f"{{{ns_atom}}}link")
            link = link_el.get("href", "") if link_el is not None else ""
            pub_el = entry.find(f"{{{ns_atom}}}published") or entry.find(f"{{{ns_atom}}}updated")
            pub_raw = pub_el.text if pub_el is not None else None
            sum_el = entry.find(f"{{{ns_atom}}}summary") or entry.find(f"{{{ns_atom}}}content")
            summary = sum_el.text or "" if sum_el is not None else ""
            id_el = entry.find(f"{{{ns_atom}}}id")
            item_id = id_el.text if id_el is not None else (link or title)
            if not title and not link:
                continue
            items.append(RawItem(
                source_name=source_name,
                title=title,
                link=link,
                summary_html=summary,
                published=_parse_date(pub_raw),
                extra={"id": item_id},
            ))
        if items:
            return items
        # RSS 2.0
        for item in root.iter("item"):
            title_el = item.find("title")
            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            link_el = item.find("link")
            link = link_el.text.strip() if link_el is not None and link_el.text else ""
            pub_el = item.find("pubDate")
            pub_raw = pub_el.text if pub_el is not None else None
            desc_el = item.find("description")
            summary = desc_el.text or "" if desc_el is not None else ""
            guid_el = item.find("guid")
            item_id = (guid_el.text if guid_el is not None else None) or link or title
            if not title and not link:
                continue
            items.append(RawItem(
                source_name=source_name,
                title=title,
                link=link,
                summary_html=summary,
                published=_parse_date(pub_raw),
                extra={"id": item_id},
            ))
    except Exception as exc:
        logger.debug("xml.etree fallback failed: %s", exc)

    return items


@register_source("rss")
class RSSSource(Source):
    def fetch(self) -> list[RawItem]:
        url = self.config.url

        # Pre-fetch with httpx so we control the UA and can inspect the response.
        try:
            status, content_type, body = _fetch_raw(url)
        except Exception as exc:
            logger.error("source '%s' HTTP fetch failed: %s", self.name, exc)
            return []

        clean_body = _strip_invalid_xml(body)

        feed = feedparser.parse(clean_body)

        if getattr(feed, "bozo", 0) and not feed.entries:
            logger.warning(
                "source '%s' feedparser bozo=%s (%s) | HTTP %s | content-type: %s | body[:300]: %s",
                self.name,
                feed.bozo,
                getattr(feed, "bozo_exception", ""),
                status,
                content_type,
                clean_body[:300],
            )
            logger.info("source '%s' trying fallback parser", self.name)
            items = _fallback_parse(self.name, clean_body)
            logger.info("source '%s' fallback fetched %d entries", self.name, len(items))
            return items

        items: list[RawItem] = []
        for entry in feed.entries:
            link = entry.get("link", "").strip()
            title = entry.get("title", "").strip()
            if not title and not link:
                continue
            published = _to_datetime(
                entry.get("published_parsed") or entry.get("updated_parsed")
            )
            summary_html = entry.get("summary", "") or entry.get("description", "")
            items.append(
                RawItem(
                    source_name=self.name,
                    title=title,
                    link=link,
                    summary_html=summary_html,
                    published=published,
                    extra={"id": entry.get("id", link)},
                )
            )

        logger.info("source '%s' fetched %d entries", self.name, len(items))
        return items
