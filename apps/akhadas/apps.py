from django.apps import AppConfig


class AkhadasConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.akhadas"

    def ready(self):
        from apps.akhadas import signals  # noqa: F401
