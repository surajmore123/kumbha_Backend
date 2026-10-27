from django.apps import AppConfig


class CrowdConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.crowd'

    def ready(self):
        # Safety alerts for serious incidents.
        from apps.crowd import notifications  # noqa: F401


