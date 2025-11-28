from rest_framework import serializers
from django.utils import timezone
from datetime import timedelta
from .models import User,Otp
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

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


        response_data = {
            "user_id": user.user_id,
            "phone_number": user.phone_number,
            "otp_verified": user.otp_verified,
            "access_token": access_token,
            "message": "Mobile number verified successfully.",
        } 

        return response_data


        







        