import logging

from django.dispatch import receiver

from apps.lostfound import services
from apps.safety.signals import alert_confirmed

logger = logging.getLogger(__name__)


@receiver(alert_confirmed)
def open_case_for_alert(sender, alert, **kwargs):
    """A helper confirmed a scan. A problem here must not undo that alert."""
    try:
        services.case_from_alert(alert)
    except Exception as exc:
        logger.warning("Case not opened for an alert (%s).", type(exc).__name__)
