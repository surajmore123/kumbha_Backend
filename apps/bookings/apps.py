from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"

    def ready(self):
        from django.db.models.signals import m2m_changed, post_delete, post_save

        from apps.akhadas import cache as content_cache
        from apps.bookings import models
        from apps.website.models import Listing

        def changed(sender, **kwargs):
            content_cache.invalidate()

        for model in (
            Listing, models.StayProfile, models.StayText, models.StayRoom, models.StayImage,
            models.StayArea, models.Amenity, models.TransportProvider,
        ):
            post_save.connect(changed, sender=model, weak=False, dispatch_uid=f"bookings_save_{model.__name__}")
            post_delete.connect(changed, sender=model, weak=False, dispatch_uid=f"bookings_delete_{model.__name__}")
        for through in (models.StayProfile.amenities.through, models.StayProfile.sources.through):
            m2m_changed.connect(changed, sender=through, weak=False, dispatch_uid=f"bookings_m2m_{through.__name__}")
