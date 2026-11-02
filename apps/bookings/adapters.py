"""
Live transport search. No provider gives us authorized access today, so nothing
is registered and every search honestly returns no live results. To add one,
implement `TransportAdapter` and list it in ADAPTERS. A provider that fails or
times out is skipped; its results are never guessed.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class TransportQuery:
    mode: str | None
    origin: str
    destination: str
    date: object
    passengers: int


class TransportAdapter:
    """One authorized provider API."""

    slug = ""

    def search(self, query):
        """A list of dicts: provider, departs, arrives, duration, price, availability, url."""
        raise NotImplementedError


ADAPTERS: list[TransportAdapter] = []


def live_results(query):
    """(results, failed_slugs) across registered adapters."""
    results, failed = [], []
    for adapter in ADAPTERS:
        try:
            results.extend(adapter.search(query))
        except Exception as error:  # noqa: BLE001 - one provider must not break the rest
            logger.warning("Transport provider %s failed: %r", adapter.slug, error)
            failed.append(adapter.slug)
    return results, failed
