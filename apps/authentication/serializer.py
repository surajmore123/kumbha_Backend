from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import User,Otp,NotificationPreference
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from django.core.files.storage import default_storage
from apps.aiChat.models import ChatSession,ChatMessage
from django.conf import settings
import os

class MobileOtpRequestSerializer(serializers.Serializer):
    phone_number=serializers.CharField(max_length=15)


    def validate_phone_number(self,value):
        value = value.strip()

        if value.startswith("+91"):
            value = value[3:]
        elif value.startswith("91") and len(value) ==12:
            value = value[2:]

        if not (value.isdigit() and len(value) == 10 and value[0] in "6789"):
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")
        

        return f"+91{value}"
    
    def create(self, validated_data):
        phone_number = validated_data['phone_number']

        user, create = User.objects.get_or_create(
            phone_number=phone_number,
            defaults={'is_active': True}

        )

        otp_obj = Otp.objects.create(user=user,
            otp_code="111111", 
            expiry_time=timezone.now() + timedelta(minutes=5))
        

        return {
            "user_id": user.user_id,
            "phone_number": user.phone_number,
            "otp_id": otp_obj.otp_id,
            "otp_verified":user.otp_verified,
            "message": "OTP sent successfully to your mobile number."
        }

class VerifyMobileOtpSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    otp_code = serializers.CharField(max_length=6)

    def validate(self,attrs):
        phone_number = attrs.get("phone_number")
        otp_code = attrs.get("otp_code")


        if phone_number.startswith("+91"):
            phone_number = phone_number[3:]
        elif phone_number.startswith("91") and len("phone_number") ==12:
            phone_number = phone_number[2:]

        if not(phone_number.isdigit() and len(phone_number)==10 and phone_number[0] in "6789"):
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")
        
        phone_number =f"+91{phone_number}"

        try:
            user = User.objects.get(phone_number=phone_number)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")
        
        try:
            otp_obj =(
                Otp.objects.filter(user=user,is_used=False,
                    is_del=False)
            ).latest("created_at")

        except Otp.DoesNotExist:
            raise serializers.ValidationError("No active OTP found. Please request a new one.")
        
        if otp_obj.otp_code != otp_code:
            raise serializers.ValidationError("Invalid OTP code.")
        
        if otp_obj.is_expired():
             raise serializers.ValidationError("OTP has expired. Please request a new one.")
        
        attrs["user"] =user
        attrs["otp_obj"] = otp_obj

        return attrs
    

    def create(self,validated_data):
        otp_obj = validated_data["otp_obj"]
        user = validated_data["user"]
        otp_obj.is_used = True
        otp_obj.save(update_fields=["is_used"])

        user.otp_verified = True
        user.save(update_fields=["otp_verified"])

        refresh = RefreshToken.for_user(user)
        access_token = str(refresh.access_token)

        session = (ChatSession.objects.filter(user=user,mode="guru_ai",del_flag=0).order_by("-created_at").first())

        session_id = str(session.session_id) if session else None


        response_data = {
            "user_id": user.user_id,
            "phone_number": user.phone_number,
            "otp_verified": user.otp_verified,
            "access_token": access_token,
            "session_id": session_id,
            "message": "Mobile number verified successfully.",
        } 

        return response_data
    




class UserProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(
        source="full_Name",
        max_length=255,
        required=False,
        allow_blank=True,
        allow_null=True,
    )
    profile_url = serializers.CharField(
        source="profile_pic_url",
        read_only=True,
    )

    class Meta:
        model = User
        fields = [
            "user_id",
            "phone_number",
            "full_name",
            "email",
            "profile_url",
        ]
        read_only_fields = ["user_id", "phone_number"]

    def validate_email(self, value):
        if not value:
            return value

        request = self.context.get("request")
        current_user = self.instance or getattr(request, "user", None)

        qs = User.objects.filter(email__iexact=value)
        if current_user:
            qs = qs.exclude(pk=current_user.pk)

        if qs.exists():
            raise serializers.ValidationError(
                "This email is already used by another account."
            )
        return value

    def update(self, instance, validated_data):
        full_name = validated_data.get("full_Name", None)
        email = validated_data.get("email", None)

        if full_name is not None:
            instance.full_Name = full_name
        if email is not None:
            instance.email = email

        instance.save()
        return instance


class UserProfileImageSerializer(serializers.ModelSerializer): 
    profile_image = serializers.ImageField(write_only=True)

    class Meta:
        model = User
        fields = ["profile_image"]

    def update(self, instance, validated_data):
        profile_image = validated_data.get("profile_image")

        if profile_image:
            folder = f"profile/{instance.user_id}"
            filename = default_storage.save(
                os.path.join(folder, profile_image.name),
                profile_image,
            )
            instance.profile_pic_url = default_storage.url(filename)

        instance.save()
        return instance


class FCMDeviceSerializer(serializers.Serializer):
    token = serializers.CharField()
    device_type = serializers.ChoiceField(
        choices=["ANDROID", "IOS", "WEB"]
    )

class NotificationPreferenceSerializer(serializers.ModelSerializer):
    """All categories are optional on PATCH; unknown keys are rejected."""

    class Meta:
        model = NotificationPreference
        fields = list(NotificationPreference.CATEGORIES)

    def validate(self, attrs):
        unknown = set(self.initial_data) - set(self.fields) - {"access_token"}
        if unknown:
            raise serializers.ValidationError(
                {key: "Unknown notification category." for key in sorted(unknown)}
            )
        return attrs
