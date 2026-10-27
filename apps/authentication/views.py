from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from .serializer import MobileOtpRequestSerializer,VerifyMobileOtpSerializer,UserProfileSerializer,UserProfileImageSerializer,FCMDeviceSerializer,NotificationPreferenceSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from .models import FCMDevice, NotificationPreference


class SendMobileOtpView(APIView):
    permission_classes = [AllowAny]

    def post(self,request):
        serializer = MobileOtpRequestSerializer(data=request.data)

        if serializer.is_valid():
            data = serializer.save()

            return Response({
                    "status": "success",
                    "message": data["message"],
                    "data": {
                        "user_id": data["user_id"],
                        "phone_number": data["phone_number"],
                        "otp_id": data["otp_id"],
                        "otp_verified":data["otp_verified"],
                        
                    }
            },status=status.HTTP_201_CREATED)
        
        return Response(
            {"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )
    

class VerifyMobileOtpView(APIView):
    permission_classes =[AllowAny]

    def post(self,request):
        serializer = VerifyMobileOtpSerializer(data=request.data)

        if serializer.is_valid():
            data = serializer.save()
            return Response({
                "status": "success", "message": data["message"],
                "data":{
                "user_id":data["user_id"],
                "phone_number":data["phone_number"],
                "access_token":data["access_token"],
                "session_id": data.get("session_id"),
                }
            },status=status.HTTP_200_OK,)
        
        return Response({"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,)
    

class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
   

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(
            {"status": "success", "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        if serializer.is_valid():
            user = serializer.save()
            return Response(
                {
                    "status": "success",
                    "message": "Profile updated successfully.",
                    "data": UserProfileSerializer(user).data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )
    


class UserProfileImageUploadView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def patch(self, request):
        serializer = UserProfileImageSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={"request": request},
        )

        if serializer.is_valid():
            user = serializer.save()
            profile_data = UserProfileSerializer(user).data
            return Response(
                {
                    "status": "success",
                    "message": "Profile image updated successfully.",
                    "data": profile_data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )





class RegisterFCMDeviceAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = FCMDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        token = serializer.validated_data["token"]
        device_type = serializer.validated_data["device_type"]

        device, created = FCMDevice.objects.update_or_create(
            token=token,
            defaults={
                "user": request.user,
                "device_type": device_type,
                "is_active": True
            }
        )

        return Response(
            {   "status": "success",
                "message": "FCM device registered",
                "device_id": str(device.device_id)
            },
            status=status.HTTP_200_OK
        )

class NotificationPreferenceAPI(APIView):
    """
    GET   → the user's notification categories (all on by default).
    PATCH → turn categories on/off, e.g. {"crowd_alerts": false}.
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def _preference(self, request):
        preference, _ = NotificationPreference.objects.get_or_create(user=request.user)
        return preference

    def get(self, request):
        data = NotificationPreferenceSerializer(self._preference(request)).data
        return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = NotificationPreferenceSerializer(
            self._preference(request), data=request.data, partial=True,
        )
        if not serializer.is_valid():
            return Response(
                {"status": "error", "errors": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer.save()
        return Response({"status": "success", "data": serializer.data}, status=status.HTTP_200_OK)
