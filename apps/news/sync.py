"""Puts relevant new feed stories into the editors' review queue."""

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.news.adapters import ADAPTERS, AdapterError
from apps.news.models import NewsArticle, NewsSource, NewsSyncLog, canonical_url, hash_of, title_key

logger = logging.getLogger(__name__)


def _is_relevant(source, text):
    text = text.casefold()
    return any(word.strip().casefold() in text for word in source.keywords.splitlines() if word.strip())


def _queue(source, entry, log):
    url = canonical_url(entry.url)
    duplicate = (
        NewsArticle.objects.filter(url_hash=hash_of(url)).exists()
        or NewsArticle.objects.filter(title_hash=title_key(source.pk, entry.headline)).exists()
    )
    if duplicate:
        log.duplicates += 1
        return
    try:
        with transaction.atomic():
            NewsArticle.objects.create(
                headline=entry.headline[:300], language=source.language, publisher=source,
                category=source.default_category, original_url=url,
                published_at=entry.published_at or timezone.now(),
                source_type=NewsArticle.SourceType.RSS,
                # Editors review everything, so a missing date is fixed before it shows.
                editorial_notes="" if entry.published_at else "The feed gave no date. Set it from the original.",
            )
        log.created += 1
    except IntegrityError:  # another worker queued it first
        log.duplicates += 1


def sync_source(source, force=False):
    """Returns the log, or None when it's too soon to ask this publisher again."""
    now = timezone.now()
    next_check = source.next_allowed_check()
    if not force and next_check and now < next_check:
        return None
    log = NewsSyncLog(source=source, started_at=now, status=NewsSyncLog.Status.SUCCESS)
    source.last_checked_at = now
    try:
        result = ADAPTERS[source.adapter]().fetch(source)
        if result.not_modified:
            log.status = NewsSyncLog.Status.NOT_MODIFIED
        else:
            log.fetched = len(result.entries)
            relevant = [e for e in result.entries if _is_relevant(source, e.match_text)]
            log.relevant = len(relevant)
            for entry in relevant:
                _queue(source, entry, log)
            source.etag, source.last_modified = result.etag, result.last_modified
        source.last_success_at = now
        source.consecutive_failures = 0
        source.last_error = ""
    except AdapterError as error:
        log.status = NewsSyncLog.Status.FAILED
        log.error = str(error)[:300]
        source.consecutive_failures += 1
        source.last_error = log.error
        logger.warning("News sync failed for %s: %s", source.slug, log.error)
    log.finished_at = timezone.now()
    log.save()
    source.save(update_fields=[
        "last_checked_at", "last_success_at", "consecutive_failures", "last_error",
        "etag", "last_modified", "updated_at",
    ])
    return log


def sync_all():
    logs = [sync_source(s) for s in NewsSource.objects.filter(is_active=True).exclude(adapter="manual")]
    return [log for log in logs if log is not None]
