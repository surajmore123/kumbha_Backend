from .models import EventAnalytics
from datetime import datetime, time
from django.utils import timezone

# DEFAULT_REMINDER_OFFSETS = [0]
DEFAULT_REMINDER_OFFSETS = [
    1440,  # 1 day before
    720,   # 12 hours before
    5,     # 5 minutes before
]

  # minutes

def log_event_analytics(request, event, event_type):
    user = request.user if request.user.is_authenticated else None

    EventAnalytics.objects.create(
        user=user,
        event=event,
        event_type=event_type,
    )



def get_event_start_datetime(event):
    if event.start_time:
        start_time = event.start_time
    else:
        # Default start time for all-day events
        start_time = time(9, 0)  # 9 AM (configurable)

    start_dt = datetime.combine(event.event_date, start_time)
    return timezone.make_aware(start_dt)
