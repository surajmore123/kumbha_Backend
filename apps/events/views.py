from rest_framework.views import APIView
from datetime import date,timedelta
from .models import Event
from rest_framework.response import Response
from rest_framework import status
from .utility import log_event_analytics
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated

from .serializers import EventListSerializer

class FeaturedEventApi(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes =[IsAuthenticated]

    def get(self,request):
        today = date.today()

        event = (
            Event.objects
            .filter(
                del_flag=0,
                status="PUBLISHED",
                show_in_app=True,
                priority_level="HIGH",
                event_date__gte=today,
            )
            .order_by("event_date", "start_time")
            .first()
        )

        if not event:
            return Response(
                {"status": "success", "data": None},
                status=status.HTTP_200_OK
            )
        
        # log_event_analytics(request,event,"VIEW")

        serializer = EventListSerializer(event)

        return Response(
            {"status": "success", "data": serializer.data},
            status=status.HTTP_200_OK
        )
    
class UpcomingEventAPI(APIView):
    authentication_classes =[]
    permission_classes =[]

    def get(self,request):
        today = date.today()
        tomorrow = today + timedelta(days=1)
        selected_date = request.query_params.get("date")

        base_queryset = Event.objects.filter(del_flag=0,status="PUBLISHED",
            show_in_app=True,)
        
        if selected_date:
            events = base_queryset.filter(
                event_date=selected_date
            ).order_by("event_date", "start_time")

        else:
            events = base_queryset.filter(
                event_date__in=[today, tomorrow]
            ).order_by("event_date", "start_time")


        
        serializer = EventListSerializer(events,many=True)

        return Response(
            {
                "status": "success",
                "data": serializer.data,
                "meta": {
                    "filter_date": selected_date,
                    "default_range": "today_and_tomorrow" if not selected_date else None,
                },
            },
            status=status.HTTP_200_OK,
        )
