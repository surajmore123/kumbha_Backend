from rest_framework import serializers
from .models import Event

class EventListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
             "event_id",
            "event_name",
            "short_description",
            "description",
            "event_category",
            "event_subtype",
            "event_date",
            "start_time",
            "end_time",
            "is_all_day",
            "location_type",
            "location_name",
            "priority_level",
            "expected_crowd_level",
        ]