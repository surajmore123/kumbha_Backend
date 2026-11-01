from django.apps import AppConfig


class FamilyConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.family"

    def ready(self):
        from apps.family import signals  # noqa: F401
