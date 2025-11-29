from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from .serializers import ChatRequestSerializer,ChatHistorySerializer

class ChatWithGuruApiView(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes =[IsAuthenticated]

    def post(self,request):

        serializer = ChatRequestSerializer(data=request.data,context={"request":request},)

        if serializer.is_valid():
            data = serializer.save()

            return Response({
                    "status": "success",
                    "data": data,
                },status=status.HTTP_200_OK,)
        return Response(
            {"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

class ChatHistoryView(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes =[IsAuthenticated]

    def get(self, request):
        serializer = ChatHistorySerializer(
            data=request.query_params,
            context={"request": request},
        )

        if serializer.is_valid():
            data = serializer.save()

            return Response(
                {
                    "status": "success",
                    "data": data,
                },
                status=status.HTTP_200_OK,
            )

        return Response(
            {"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )