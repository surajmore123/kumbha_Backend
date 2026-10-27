from django.apps import AppConfig


class EventsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.events'

    def ready(self):
        # Push notifications for new, changed and withdrawn events.
        from apps.events import notifications  # noqa: F401
