from rest_framework import serializers

from apps.family.models import FamilyMember
from apps.safety import policy
from apps.safety.models import SafetyAlert, SafetyQRIdentity

_CATEGORY = {
    FamilyMember.Kind.DEPENDENT_CHILD: "child",
    FamilyMember.Kind.DEPENDENT_ELDERLY: "elderly",
    FamilyMember.Kind.DEPENDENT_OTHER: "other",
}


def category_of(member):
    return _CATEGORY.get(member.kind, "adult")


def first_name_of(member):
    parts = member.display_name.split()
    return parts[0] if parts else ""


class IdentitySerializer(serializers.ModelSerializer):
    """Holds the payload, so it's only used after a permission check."""

    payload = serializers.CharField(read_only=True)
    member_id = serializers.UUIDField(read_only=True)
    member_name = serializers.CharField(source="member.display_name", read_only=True)

    class Meta:
        model = SafetyQRIdentity
        fields = [
            "id", "member_id", "member_name", "status", "payload", "created_at",
            "revoked_at", "expires_at", "last_scanned_at",
        ]


class ConfirmSerializer(serializers.Serializer):
    SITUATIONS = (*SafetyAlert.Kind.values, "suspicious")

    situation = serializers.ChoiceField(choices=SITUATIONS)
    confirmed = serializers.BooleanField()
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)
    latitude = serializers.FloatField(required=False, allow_null=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(required=False, allow_null=True, min_value=-180, max_value=180)

    def validate_confirmed(self, value):
        if not value:
            raise serializers.ValidationError("Confirm what you've seen before continuing.")
        return value

    def validate(self, attrs):
        if (attrs.get("latitude") is None) != (attrs.get("longitude") is None):
            raise serializers.ValidationError({"latitude": "Send both coordinates, or neither."})
        return attrs


class HelperAlertSerializer(serializers.ModelSerializer):
    """What a helper sees of their own report. Nothing about the family."""

    family_acknowledged = serializers.SerializerMethodField()

    class Meta:
        model = SafetyAlert
        fields = ["id", "reference", "kind", "status", "delivery", "created_at", "family_acknowledged"]

    def get_family_acknowledged(self, obj):
        return obj.acknowledged_at is not None


class FamilyAlertSerializer(serializers.ModelSerializer):
    """For family members. Who the helper is stays private: their role is shown."""

    member_id = serializers.UUIDField(read_only=True)
    member_name = serializers.CharField(source="member.display_name", read_only=True)
    location = serializers.SerializerMethodField()
    location_withheld = serializers.SerializerMethodField()

    class Meta:
        model = SafetyAlert
        fields = [
            "id", "reference", "kind", "status", "member_id", "member_name", "note", "helper_role",
            "location", "location_withheld", "delivery", "created_at", "acknowledged_at", "resolved_at",
        ]

    def _has_location(self, obj):
        return obj.latitude is not None

    def _may_see(self, obj):
        return policy.can_see_alert_location(self.context["actor"], obj.member)

    def get_location(self, obj):
        if not self._has_location(obj) or not self._may_see(obj):
            return None
        return {"latitude": float(obj.latitude), "longitude": float(obj.longitude)}

    def get_location_withheld(self, obj):
        return self._has_location(obj) and not self._may_see(obj)
