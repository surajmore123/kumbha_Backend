"""
Tells a family that a helper has confirmed something. Uses the existing FCM
sender, and never raises: the alert is saved first, and a failed push must not
lose it. Titles stay generic because the push sender writes them to the log.
"""

import logging

from apps.safety.models import SafetyAlert
from apps.safety.policy import recipients_for
from utils.push_notifications import send_localized

logger = logging.getLogger(__name__)

# Shown on a lock screen, so no name, condition or situation. The details are in
# the app, behind sign-in.
_TEXT = {
    "en": ("Family safety alert", "A registered helper has sent an alert for your family. Ref {ref}."),
    "hi": ("परिवार सुरक्षा सूचना", "एक पंजीकृत सहायक ने आपके परिवार के लिए सूचना भेजी है। संदर्भ {ref}।"),
    "mr": ("कुटुंब सुरक्षा सूचना", "एका नोंदणीकृत मदतनीसाने तुमच्या कुटुंबासाठी सूचना पाठवली आहे. संदर्भ {ref}."),
}


def notify_family(alert):
    """Sends the push and records what happened on the alert."""
    def build(language):
        title, body = _TEXT[language]
        return title, body.format(ref=alert.reference)

    users = recipients_for(alert.member)
    try:
        result = send_localized(
            None, build, users=users,
            data={"type": "family_safety_alert", "route": "/safetyAlerts", "family_id": str(alert.family_id)},
            inbox={"category": "safety_qr", "key": f"alert:{alert.pk}"}, private=True,
        )
        delivery = {
            "sent": SafetyAlert.Delivery.SENT,
            "no_devices": SafetyAlert.Delivery.NO_DEVICES,
        }.get(result["status"], SafetyAlert.Delivery.UNAVAILABLE)
        if result["status"] == "sent" and not result["success"]:
            delivery = SafetyAlert.Delivery.UNAVAILABLE
    except Exception as exc:  # the alert is saved; only the push failed
        logger.warning("Family alert push failed (%s).", type(exc).__name__)
        delivery = SafetyAlert.Delivery.UNAVAILABLE
    alert.delivery = delivery
    alert.save(update_fields=["delivery"])
    return delivery
