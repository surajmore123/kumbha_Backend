from rest_framework import serializers
from .models import Temple

class NearbyTempleSerializer(serializers.ModelSerializer):
    distance_km = serializers.FloatField()

    class Meta:
        model = Temple
        fields = [
            "temple_id",
            "name",
            "description",
            "latitude",
            "longitude",
            "image_url",
            "city",
            "crowd_level",
            "crowd_message",
            "distance_km",
        ]


class TempleDetailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Temple
        fields = [
            "temple_id",
            "name",
            "description",
            "latitude",
            "longitude",
            "image_url",
            "city",
            "state",
            "crowd_level",
            "crowd_message",
            "created_at",
        ]

