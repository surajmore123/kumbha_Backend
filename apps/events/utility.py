from .models import EventAnalytics


def log_event_analytics(request, event, event_type):
    user = request.user if request.user.is_authenticated else None

    EventAnalytics.objects.create(
        user=user,
        event=event,
        event_type=event_type,
    )
