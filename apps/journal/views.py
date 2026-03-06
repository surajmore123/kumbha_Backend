from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from apps.journal.models import JournalEntry
from apps.journal.serializers import JournalEntrySerializer
from apps.journal.services import generate_ai_prompt_for_user, generate_ai_reflection_for_user
from rest_framework.pagination import PageNumberPagination
from rest_framework.generics import ListAPIView
from rest_framework.generics import RetrieveAPIView,RetrieveUpdateAPIView

class JournalPagination(PageNumberPagination):
    page_size = 4
    page_size_query_param = "page_size"
    max_page_size = 20


class AIReflectionView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self,request):
        try:
            reflection = generate_ai_reflection_for_user(request.user)
            return Response(
                {"status": "success",
                 "message": "AI reflection generated successfully.",
                  "data": {
                    "reflection": reflection
                  }},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {"status": "error",
                 "message": "Failed to generate AI reflection.",
                 "error": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

class AIPromptView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            prompt = generate_ai_prompt_for_user(request.user)

            return Response(
                {
                    "status": "success",
                    "message": "AI prompt generated successfully.",
                    "data": {
                        "prompt": prompt
                    }
                },
                status=status.HTTP_200_OK
            )

        except Exception:
            return Response(
                {
                    "status": "error",
                    "message": "Failed to generate prompt."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
class JournalEntryCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = JournalEntrySerializer(
            data=request.data,
            context={"request": request}
        )

        if serializer.is_valid():
            instance = serializer.save()
            # print(serializer.validated_data)

            response_serializer = JournalEntrySerializer(instance)

            return Response(
                {
                    "status": "success",
                    "message": "Journal entry saved successfully.",
                    "data": response_serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )

        return Response(
            {
                "status": "error",
                "errors": serializer.errors,
            },
            status=status.HTTP_400_BAD_REQUEST,
        )
    

class JournalEntryListView(ListAPIView):
    
    serializer_class = JournalEntrySerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    pagination_class = JournalPagination

    def get_queryset(self):
        return JournalEntry.objects.filter(
            user=self.request.user
        ).order_by("-created_at")
    

class JournalEntryDetailView(RetrieveAPIView):
    serializer_class = JournalEntrySerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure user can only access their own entries
        return JournalEntry.objects.filter(user=self.request.user)
    
class JournalEntryDetailView(RetrieveUpdateAPIView):
    serializer_class = JournalEntrySerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # User can only access their own journal entries
        return JournalEntry.objects.filter(user=self.request.user)