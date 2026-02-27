from rest_framework import serializers

from apps.crowd.models.AppNotification import AppNotification
from .models import UserZonePresence, ZoneCrowdSnapshot, Incident

class ZoneLiveStatusSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    capacity = serializers.IntegerField()
    total_people = serializers.IntegerField()
    occupancy_percent = serializers.FloatField()
    status = serializers.CharField()



class QuickAlertSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    zone_code = serializers.CharField()
    zone_name = serializers.CharField()
    type = serializers.CharField()
    severity = serializers.CharField()
    title = serializers.CharField()
    description = serializers.CharField()
    start_time = serializers.DateTimeField()


class GateSerializer(serializers.Serializer):
    
    name = serializers.CharField()
    gate_type = serializers.CharField()
    is_open = serializers.BooleanField()


class SimpleAlertSerializer(serializers.Serializer):
    title = serializers.CharField()
    severity = serializers.CharField()


class AlternativeZoneSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()

class UpdateLocationSerializer(serializers.Serializer):
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6)


class AppNotificationSerializer(serializers.ModelSerializer):
    zone_name = serializers.SerializerMethodField()

    class Meta:
        model = AppNotification
        fields = [
            "id",
            "title",
            "body",
            "type",
            "severity",
            "zone_name",
            "created_at",
        ]

    def get_zone_name(self, obj):
        return obj.zone.name if obj.zone else None