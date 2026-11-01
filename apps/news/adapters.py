"""
Source adapters. A new publisher type needs one class here and one registry
entry; the rest of the pipeline doesn't change.
"""

from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree

import requests
from django.utils import timezone

from apps.news.models import NewsSource

_TIMEOUT = 15
_MAX_BYTES = 3 * 1024 * 1024
_USER_AGENT = "KumbhaPathNewsBot/1.0 (+https://kumbhapath.in)"
_ATOM = "{http://www.w3.org/2005/Atom}"


class AdapterError(Exception):
    pass


@dataclass
class FeedEntry:
    headline: str
    url: str
    published_at: datetime | None  # some official feeds carry no dates
    match_text: str  # used to judge relevance, never stored


@dataclass
class FetchResult:
    entries: list
    etag: str = ""
    last_modified: str = ""
    not_modified: bool = False


def parse_date(value):
    """A timezone-aware datetime, or None. Feeds use RFC 822 or ISO 8601."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return parsed if timezone.is_aware(parsed) else parsed.replace(tzinfo=dt_timezone.utc)


class BaseAdapter:
    def fetch(self, source):
        raise NotImplementedError


class ManualAdapter(BaseAdapter):
    """Editors add these stories in admin."""

    def fetch(self, source):
        return FetchResult(entries=[])


class RssAdapter(BaseAdapter):
    """RSS 2.0 and Atom. Conditional requests keep repeat fetches cheap."""

    def fetch(self, source):
        headers = {"User-Agent": _USER_AGENT, "Accept": "application/rss+xml, application/atom+xml, text/xml"}
        if source.etag:
            headers["If-None-Match"] = source.etag
        if source.last_modified:
            headers["If-Modified-Since"] = source.last_modified
        try:
            response = requests.get(source.feed_url, headers=headers, timeout=_TIMEOUT, stream=True)
            if response.status_code == 304:
                return FetchResult(entries=[], not_modified=True)
            if response.status_code != 200:
                raise AdapterError(f"HTTP {response.status_code}")
            body = b""
            for chunk in response.iter_content(65536):
                body += chunk
                if len(body) > _MAX_BYTES:
                    raise AdapterError("Feed is too large.")
        except requests.RequestException as error:
            raise AdapterError(type(error).__name__) from error
        return FetchResult(
            entries=self.parse(body),
            etag=response.headers.get("ETag", "")[:200],
            last_modified=response.headers.get("Last-Modified", "")[:100],
        )

    def parse(self, body):
        # Feeds have no need for entity declarations, which are how XML bombs work.
        if b"<!ENTITY" in body[:4096] or b"<!DOCTYPE" in body[:4096]:
            raise AdapterError("Feed declares a DOCTYPE or entities.")
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as error:
            raise AdapterError("Feed isn't valid XML.") from error
        entries = [self._rss_item(i) for i in root.iter("item")]
        entries += [self._atom_entry(e) for e in root.iter(f"{_ATOM}entry")]
        return [e for e in entries if e is not None]

    def _rss_item(self, item):
        headline = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        published = parse_date(item.findtext("pubDate"))
        return self._entry(headline, url, published, item.findtext("description") or "")

    def _atom_entry(self, entry):
        link = next(
            (x.get("href") for x in entry.findall(f"{_ATOM}link") if x.get("rel", "alternate") == "alternate"), "",
        )
        headline = (entry.findtext(f"{_ATOM}title") or "").strip()
        published = parse_date(entry.findtext(f"{_ATOM}published") or entry.findtext(f"{_ATOM}updated"))
        return self._entry(headline, link or "", published, entry.findtext(f"{_ATOM}summary") or "")

    def _entry(self, headline, url, published, description):
        if not headline or not url.lower().startswith("https://"):
            return None
        return FeedEntry(headline, url, published, f"{headline} {description}")


ADAPTERS = {
    NewsSource.Adapter.MANUAL: ManualAdapter,
    NewsSource.Adapter.RSS: RssAdapter,
}
