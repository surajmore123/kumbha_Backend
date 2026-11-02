from django.conf import settings
from django.db.models.signals import pre_delete
from django.dispatch import receiver

from apps.family.models import FamilyCircle


@receiver(pre_delete, sender=settings.AUTH_USER_MODEL)
def remove_families_left_without_adults(sender, instance, **kwargs):
    """Dependents' details aren't kept once no adult is left to look after them."""
    for family in FamilyCircle.objects.filter(members__user=instance):
        if not family.members.filter(user__isnull=False).exclude(user=instance).exists():
            family.delete()
