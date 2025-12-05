from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from .serializer import MobileOtpRequestSerializer,VerifyMobileOtpSerializer,UserProfileSerializer
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication


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
                }
            },status=status.HTTP_200_OK,)
        
        return Response({"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,)
    
class UserProfileView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

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