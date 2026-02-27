from django.utils import timezone
from apps.crowd.models import UserZonePresence
from apps.crowd.services.zone_mapper import find_zone
from apps.crowd.services.crowd_engine import generate_zone_snapshot


def update_user_presence(user, latitude, longitude):
    """
    Updates user's presence based on their location.
    Triggers crowd recalculation when zone changes.
    """

    now = timezone.now()

    new_zone = find_zone(latitude, longitude)

    active_presence = (
        UserZonePresence.objects
        .filter(user=user, is_active=True, del_flag=0)
        .first()
    )

    # -------------------------
    # CASE 1: User outside all zones
    # -------------------------
    if not new_zone:
        if active_presence:
            previous_zone = active_presence.zone

            active_presence.is_active = False
            active_presence.exited_at = now
            active_presence.save()

            # 🔥 Recalculate previous zone
            generate_zone_snapshot(previous_zone)

        return


    # -------------------------
    # CASE 2: User still in same zone
    # -------------------------
    if active_presence and active_presence.zone_id == new_zone.id:
         
         active_presence.last_seen_at = now
         active_presence.save(update_fields=["last_seen_at"])
         return



    # -------------------------
    # CASE 3: User switching zones
    # -------------------------
    previous_zone = None

    if active_presence:
        previous_zone = active_presence.zone

        active_presence.is_active = False
        active_presence.exited_at = now
        active_presence.save()

        # 🔥 Recalculate old zone (person left)
        generate_zone_snapshot(previous_zone)


    # -------------------------
    # CASE 4: User entering new zone
    # -------------------------
    UserZonePresence.objects.create(
        user=user,
        zone=new_zone,
        entered_at=now,
        last_seen_at=now,
        previous_zone=previous_zone,
        is_active=True
    )

    # 🔥 Recalculate new zone (person entered)
    generate_zone_snapshot(new_zone)
