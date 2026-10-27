"""
Safety alerts: a serious incident (HIGH or CRITICAL) that is active.

When an incident is created, or an existing one becomes active and serious
(e.g. severity raised to HIGH), it is added to the in-app notification feed
(AppNotification, shown in Live Updates) and pushed to everyone who wants
`safety_alerts`. Runs after the commit and never breaks the save.
"""

import logging

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from apps.crowd.models import AppNotification, Incident
from utils.push_notifications import CHANNEL_ALERTS, send_localized

logger = logging.getLogger(__name__)

SERIOUS = ("HIGH", "CRITICAL")

_TITLES = {
    "en": "Safety alert: {zone}",
    "hi": "सुरक्षा सूचना: {zone}",
    "mr": "सुरक्षा सूचना: {zone}",
}


def is_serious(incident) -> bool:
    return incident.is_active and not incident.del_flag and incident.severity in SERIOUS


def handle_incident_saved(incident, was_serious: bool) -> bool:
    if not is_serious(incident) or was_serious:
        return False
    zone = incident.zone.name
    AppNotification.objects.create(
        title=_TITLES["en"].format(zone=zone),
        body=incident.title,
        type="ALERT",
        zone=incident.zone,
        severity=incident.severity,
    )
    send_localized(
        "safety_alerts",
        # Incident titles are entered by staff and sent as written.
        lambda language: (_TITLES[language].format(zone=zone), incident.title),
        data={
            "type": "safety_alert",
            "incident_id": incident.pk,
            "zone_id": incident.zone_id,
            "route": "/notifications",
        },
        channel_id=CHANNEL_ALERTS,
    )
    return True


@receiver(pre_save, sender=Incident)
def _remember_previous(sender, instance, **kwargs):
    instance._was_serious = False
    if instance.pk:
        old = Incident.objects.filter(pk=instance.pk).first()
        instance._was_serious = bool(old and is_serious(old))


@receiver(post_save, sender=Incident)
def _incident_saved(sender, instance, raw=False, **kwargs):
    if raw:
        return
    was_serious = getattr(instance, "_was_serious", False)

    def run():
        try:
            handle_incident_saved(instance, was_serious)
        except Exception:  # noqa: BLE001 - never break an incident save
            logger.exception("Safety alert failed for incident %s.", instance.pk)

    transaction.on_commit(run)
