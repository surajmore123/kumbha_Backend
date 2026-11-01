from django.utils import timezone
from rest_framework import serializers

from apps.family import policy
from apps.family.models import (
    EmergencyContact,
    FamilyCircle,
    FamilyInvitation,
    FamilyMember,
    normalize_mobile,
)


def mobile_field_value(value):
    """Validated and stored in the same form as User.phone_number."""
    mobile = normalize_mobile(value)
    if mobile is None:
        raise serializers.ValidationError("Enter a valid 10-digit mobile number.")
    return mobile


class CircleSerializer(serializers.ModelSerializer):
    member_count = serializers.SerializerMethodField()
    my_role = serializers.SerializerMethodField()
    my_member_id = serializers.SerializerMethodField()
    organizer_offer_for_me = serializers.SerializerMethodField()

    class Meta:
        model = FamilyCircle
        fields = [
            "id", "name", "description", "language", "member_count", "my_role",
            "my_member_id", "organizer_offer_for_me", "created_at",
        ]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Give your family a name.")
        return value

    def _me(self, obj):
        user = self.context["request"].user
        return next((m for m in obj.members.all() if m.user_id == user.pk), None)

    def get_member_count(self, obj):
        return len(obj.members.all())

    def get_my_role(self, obj):
        me = self._me(obj)
        return me.role if me else None

    def get_my_member_id(self, obj):
        me = self._me(obj)
        return str(me.pk) if me else None

    def get_organizer_offer_for_me(self, obj):
        me = self._me(obj)
        if me is None:
            return False
        return obj.organizer_offer_id == me.pk or not any(m.role == "organizer" for m in obj.members.all())


class MemberSerializer(serializers.ModelSerializer):
    """Fields are withheld by policy, not just hidden by the app."""

    name = serializers.CharField(source="display_name", read_only=True)
    is_dependent = serializers.BooleanField(read_only=True)
    has_photo = serializers.SerializerMethodField()
    guardians = serializers.SerializerMethodField()
    phone = serializers.SerializerMethodField()
    date_of_birth = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()

    class Meta:
        model = FamilyMember
        fields = [
            "id", "name", "kind", "role", "relationship", "is_dependent", "age_group",
            "date_of_birth", "language", "has_photo", "phone", "guardians", "permissions",
        ]

    def _actor(self):
        return self.context["actor"]

    def get_has_photo(self, obj):
        return hasattr(obj, "photo")

    def get_guardians(self, obj):
        if not obj.is_dependent:
            return []
        return [
            {"id": str(link.guardian_id), "name": link.guardian.display_name}
            for link in obj.guardian_links.all()
        ]

    def get_phone(self, obj):
        if not policy.can_see_phone(self._actor(), obj):
            return None
        return obj.user.phone_number if obj.user_id else (obj.mobile or None)

    def get_date_of_birth(self, obj):
        return obj.date_of_birth if policy.can_see_birth_details(self._actor(), obj) else None

    def get_permissions(self, obj):
        return policy.permissions_for(self._actor(), obj)


class MemberDetailSerializer(MemberSerializer):
    """Own privacy choices are shown only to the adult themselves."""

    privacy = serializers.SerializerMethodField()
    consent_basis = serializers.SerializerMethodField()

    class Meta(MemberSerializer.Meta):
        fields = MemberSerializer.Meta.fields + ["privacy", "consent_basis"]

    def get_privacy(self, obj):
        if obj.pk != self._actor().pk:
            return None
        return {
            "share_phone": obj.share_phone,
            "share_contacts_with_organizer": obj.share_contacts_with_organizer,
            "location_sharing_consent": obj.location_sharing_consent,
        }

    def get_consent_basis(self, obj):
        return obj.consent_basis if policy.can_edit_profile(self._actor(), obj) and obj.is_dependent else None


class DependentInputSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=120)
    kind = serializers.ChoiceField(choices=FamilyMember.DEPENDENT_KINDS)
    relationship = serializers.ChoiceField(choices=FamilyMember.Relationship.choices)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    age_group = serializers.ChoiceField(choices=FamilyMember.AgeGroup.choices, required=False, allow_blank=True)
    mobile = serializers.CharField(required=False, allow_blank=True)
    language = serializers.ChoiceField(choices=("en", "hi", "mr"), required=False)
    consent_basis = serializers.ChoiceField(choices=FamilyMember.ConsentBasis.choices, required=False, allow_blank=True)

    def validate_full_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter their name.")
        return value

    def validate_mobile(self, value):
        return mobile_field_value(value) if value else ""

    def validate_date_of_birth(self, value):
        if value and value > timezone.localdate():
            raise serializers.ValidationError("Date of birth can't be in the future.")
        return value

    def validate_relationship(self, value):
        if value == FamilyMember.Relationship.SELF:
            raise serializers.ValidationError("Choose how they're related to the family.")
        return value

    def validate(self, attrs):
        kind = attrs.get("kind", getattr(self.instance, "kind", None))
        if not attrs.get("date_of_birth") and not attrs.get("age_group") and self.instance is None:
            raise serializers.ValidationError({"age_group": "Add a date of birth or an age group."})
        basis = attrs.get("consent_basis", getattr(self.instance, "consent_basis", ""))
        if kind == FamilyMember.Kind.DEPENDENT_ELDERLY and not basis:
            raise serializers.ValidationError({
                "consent_basis": "Confirm that they've agreed, or that you have authority to act for them.",
            })
        return attrs


class DependentUpdateSerializer(DependentInputSerializer):
    full_name = serializers.CharField(max_length=120, required=False)
    kind = serializers.ChoiceField(choices=FamilyMember.DEPENDENT_KINDS, required=False)
    relationship = serializers.ChoiceField(choices=FamilyMember.Relationship.choices, required=False)


class AdultUpdateSerializer(serializers.Serializer):
    """An adult's own settings. Nobody else can reach this."""

    language = serializers.ChoiceField(choices=("en", "hi", "mr"), required=False)
    share_phone = serializers.BooleanField(required=False)
    share_contacts_with_organizer = serializers.BooleanField(required=False)
    location_sharing_consent = serializers.BooleanField(required=False)


class EmergencyContactSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmergencyContact
        fields = ["id", "name", "relationship", "mobile", "priority", "method", "updated_at"]
        read_only_fields = ["id", "priority", "updated_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("Enter a name.")
        return value

    def validate_mobile(self, value):
        return mobile_field_value(value)


class InvitationSerializer(serializers.ModelSerializer):
    state = serializers.CharField(read_only=True)
    in_app = serializers.SerializerMethodField()

    class Meta:
        model = FamilyInvitation
        fields = ["id", "relationship", "state", "in_app", "expires_at", "created_at"]

    def get_in_app(self, obj):
        return bool(obj.invited_phone)


class InvitationPreviewSerializer(serializers.ModelSerializer):
    """What an invitee needs to decide, and nothing else about the family."""

    family_name = serializers.CharField(source="family.name")
    organizer_name = serializers.SerializerMethodField()
    member_count = serializers.SerializerMethodField()
    state = serializers.CharField(read_only=True)
    already_member = serializers.SerializerMethodField()

    class Meta:
        model = FamilyInvitation
        fields = [
            "id", "family_name", "organizer_name", "member_count", "relationship", "state",
            "expires_at", "already_member",
        ]

    def get_already_member(self, obj):
        return obj.family.members.filter(user=self.context["request"].user).exists()

    def get_organizer_name(self, obj):
        organizer = obj.family.members.filter(role="organizer").select_related("user").first()
        return organizer.display_name if organizer else ""

    def get_member_count(self, obj):
        return obj.family.members.count()
