from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import User
from .otp import check_otp, normalize_phone, send_otp
from apps.website.core import user_by_phone
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from django.core.files.storage import default_storage
from apps.aiChat.models import ChatSession,ChatMessage
from django.conf import settings
import os

class MobileOtpRequestSerializer(serializers.Serializer):
    phone_number=serializers.CharField(max_length=15)


    def validate_phone_number(self,value):
        phone = normalize_phone(value)
        if not phone:
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")
        return phone

    def create(self, validated_data):
        phone = validated_data['phone_number']

        # Same account as the website (numbers may be stored with or without +91).
        user = user_by_phone(phone) or User.objects.create(phone_number=f"+91{phone}", is_active=True)

        otp_obj = send_otp(user, phone)

        return {
            "user_id": user.user_id,
            "phone_number": user.phone_number,
            "otp_id": otp_obj.otp_id,
            "otp_verified":user.otp_verified,
            "message": "OTP sent successfully to your mobile number."
        }

class VerifyMobileOtpSerializer(serializers.Serializer):
    phone_number = serializers.CharField(max_length=15)
    otp_code = serializers.RegexField(r"^\d{6}$", max_length=6)

    def validate(self,attrs):
        phone = normalize_phone(attrs.get("phone_number"))
        if not phone:
            raise serializers.ValidationError("Enter a valid 10-digit Indian mobile number.")

        user = user_by_phone(phone)
        if user is None:
            raise serializers.ValidationError("User does not exist")

        attrs["user"] = user
        attrs["otp_obj"] = check_otp(user, phone, attrs["otp_code"])  # raises OtpError

        return attrs
    

    def create(self,validated_data):
        user = validated_data["user"]

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