"""Outside services: OTP SMS (console / MSG91), WhatsApp operator alerts, Google sign-in, and inventory
providers for listing search (our own database plus an optional partner feed)."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

import httpx
from django.db.models import Q

from .conf import get_settings
from .core import AppError
from .models import Listing, ListingStatus, Trust
from .schemas import ListingOut, ListingQuery

log = logging.getLogger("apps.website.integrations")

# ───────────────────────── SMS ─────────────────────────


class ConsoleSms:
    """Development only: prints the code to the log instead of sending it."""

    name = "console"

    def send_otp(self, phone: str, code: str) -> None:
        log.warning("DEV OTP for %s******: %s", phone[:4], code)


class Msg91Sms:
    """MSG91 OTP via a DLT-approved template that contains an `otp` variable."""

    name = "msg91"
    URL = "https://control.msg91.com/api/v5/otp"

    def __init__(self, auth_key: str, template_id: str) -> None:
        self.auth_key, self.template_id = auth_key, template_id
        self.client = httpx.Client(timeout=8)

    def send_otp(self, phone: str, code: str) -> None:
        resp = self.client.post(
            self.URL,
            params={"template_id": self.template_id, "mobile": f"91{phone}", "otp": code},
            headers={"authkey": self.auth_key, "accept": "application/json"},
        )
        if resp.status_code >= 400:
            log.error("msg91 error", extra={"status": resp.status_code})
            raise RuntimeError("SMS provider rejected the request")


_sender = None


def get_sms_sender():
    global _sender
    if _sender is None:
        s = get_settings()
        if s.sms_provider == "msg91":
            if not (s.msg91_auth_key and s.msg91_template_id):
                raise RuntimeError("KP_MSG91_AUTH_KEY and KP_MSG91_TEMPLATE_ID are required for msg91")
            _sender = Msg91Sms(s.msg91_auth_key, s.msg91_template_id)
        else:
            _sender = ConsoleSms()
    return _sender


# ───────────────────────── WhatsApp ─────────────────────────


class WhatsAppNotifier:
    def __init__(self, token: str, phone_number_id: str, version: str) -> None:
        self.url = f"https://graph.facebook.com/{version}/{phone_number_id}/messages"
        self.token = token
        self.client = httpx.Client(timeout=8)

    def send_text(self, to: str, body: str) -> bool:
        try:
            resp = self.client.post(
                self.url,
                headers={"Authorization": f"Bearer {self.token}"},
                json={"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body[:4000]}},
            )
            if resp.status_code >= 400:
                log.error("whatsapp send failed", extra={"status": resp.status_code})
                return False
            return True
        except httpx.HTTPError as exc:
            log.error("whatsapp unreachable", extra={"error": str(exc)})
            return False


_notifier = None


def get_notifier():
    """None until WhatsApp is configured."""
    global _notifier
    s = get_settings()
    if not (s.whatsapp_token and s.whatsapp_phone_number_id and s.enquiry_notify_to):
        return None
    if _notifier is None:
        _notifier = WhatsAppNotifier(s.whatsapp_token, s.whatsapp_phone_number_id, s.whatsapp_api_version)
    return _notifier


# ───────────────────────── Google sign-in ─────────────────────────

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def verify_google_credential(credential: str) -> dict:
    """Return {sub, email, name} for a valid Google ID token, else raise AppError(401)."""
    client_id = get_settings().google_client_id
    if not client_id:
        raise AppError(503, "google_disabled", "Google sign-in is not available yet.")
    try:
        with httpx.Client(timeout=6) as http:
            resp = http.get(TOKENINFO_URL, params={"id_token": credential})
    except httpx.HTTPError as exc:
        raise AppError(503, "google_unreachable", "Couldn't reach Google. Please try again.") from exc
    if resp.status_code != 200:
        raise AppError(401, "google_invalid", "Google sign-in failed. Please try again.")
    info = resp.json()
    if info.get("aud") != client_id or info.get("iss") not in ISSUERS:
        raise AppError(401, "google_invalid", "Google sign-in failed. Please try again.")
    if str(info.get("email_verified")).lower() != "true" or not info.get("email"):
        raise AppError(401, "google_unverified", "Your Google email is not verified.")
    if int(info.get("exp", 0)) < time.time():
        raise AppError(401, "google_expired", "Google sign-in expired. Please try again.")
    return {"sub": info["sub"], "email": info["email"].lower(), "name": info.get("name")}


# ───────────────────────── inventory providers ─────────────────────────


class InternalProvider:
    """Listings stored in our own database (partners onboarded through the partner portal)."""

    name = "internal"

    def search(self, query: ListingQuery) -> list[ListingOut]:
        qs = Listing.objects.filter(status=ListingStatus.published)
        if query.category:
            qs = qs.filter(category=query.category)
        if query.type:
            qs = qs.filter(type=query.type)
        if query.town:
            qs = qs.filter(town=query.town)
        if query.accessible:
            qs = qs.filter(wheelchair=True)
        if query.q:
            qs = qs.filter(Q(name__icontains=query.q) | Q(area__icontains=query.q) | Q(type__icontains=query.q))
        return [ListingOut.model_validate(r) for r in qs[:1000]]


class PartnerFeedProvider:
    """Example external provider: a partner's JSON inventory feed, cached for a few minutes."""

    name = "partner_feed"
    CACHE_SECONDS = 300

    def __init__(self, url: str, api_key: str | None) -> None:
        self.url, self.api_key = url, api_key
        self.client = httpx.Client(timeout=6)
        self._cache: tuple[float, list[ListingOut]] | None = None

    def _fetch(self) -> list[ListingOut]:
        if self._cache and time.monotonic() - self._cache[0] < self.CACHE_SECONDS:
            return self._cache[1]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        resp = self.client.get(self.url, headers=headers)
        resp.raise_for_status()
        items: list[ListingOut] = []
        for raw in resp.json().get("items", [])[:500]:
            try:
                items.append(
                    ListingOut(
                        id=f"pf-{raw['id']}"[:32],
                        category=raw["category"],
                        name=str(raw["name"])[:160],
                        type=str(raw.get("type", "Other"))[:40],
                        town=str(raw.get("town", "Nashik"))[:60],
                        area=str(raw.get("area", ""))[:160],
                        price_from=int(raw.get("price_from", 0)),
                        unit=str(raw.get("unit", ""))[:80],
                        highlights=[str(h)[:60] for h in raw.get("highlights", [])][:8],
                        trust=Trust.partner,
                        wheelchair=bool(raw.get("wheelchair", False)),
                        source=self.name,
                    )
                )
            except (KeyError, ValueError, TypeError):
                log.warning("skipping malformed feed item")
        self._cache = (time.monotonic(), items)
        return items

    def search(self, query: ListingQuery) -> list[ListingOut]:
        items = self._fetch()
        q = (query.q or "").lower()
        return [
            i
            for i in items
            if (not query.category or i.category == query.category)
            and (not query.type or i.type == query.type)
            and (not query.town or i.town == query.town)
            and (not query.accessible or i.wheelchair)
            and (not q or q in f"{i.name} {i.area} {i.type}".lower())
        ]


_providers = None
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="kp-provider")


def get_providers() -> list:
    global _providers
    if _providers is None:
        s = get_settings()
        _providers = [InternalProvider()]
        if s.partner_feed_url:
            _providers.append(PartnerFeedProvider(s.partner_feed_url, s.partner_feed_key))
    return _providers


def search_all(query: ListingQuery) -> list[ListingOut]:
    """Every provider's results merged; an external provider that is slow or failing is skipped."""
    timeout = get_settings().provider_timeout_seconds
    merged: list[ListingOut] = []
    external = []
    for p in get_providers():
        if p.name == "internal":
            merged.extend(p.search(query))  # uses this request's DB connection, so run it here
        else:
            external.append((p, _pool.submit(p.search, query)))
    for p, future in external:
        try:
            merged.extend(future.result(timeout=timeout))
        except (FutureTimeout, Exception) as exc:  # noqa: BLE001 - provider isolation is the point
            log.warning("provider failed", extra={"provider": p.name, "error": repr(exc)})
    merged.sort(key=lambda i: i.price_from, reverse=query.sort == "price-desc")
    return merged
