from django.apps import AppConfig


class LostFoundConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.lostfound"

    def ready(self):
        from apps.lostfound import receivers  # noqa: F401
