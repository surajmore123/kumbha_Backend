from rest_framework.views import APIView
from datetime import date,timedelta
from django.utils import timezone
from .models import Event
from rest_framework.response import Response
from rest_framework import status
from .utility import log_event_analytics,get_event_start_datetime
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from apps.events.models.event_subscription import EventSubscription


from apps.events.models import Event
from apps.events.models.schedule_notification import ScheduledNotification
from .serializers import ReminderToggleSerializer
from .utility import DEFAULT_REMINDER_OFFSETS

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
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        today = timezone.localdate()
        tomorrow = today + timedelta(days=1)
        selected_date = request.query_params.get("date")

        # 1️⃣ Find featured event (closest HIGH priority)
        featured_event = (
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

        # 2️⃣ Base queryset for upcoming
        base_queryset = Event.objects.filter(
            del_flag=0,
            status="PUBLISHED",
            show_in_app=True,
        )

        # 3️⃣ Exclude featured event
        if featured_event:
            base_queryset = base_queryset.exclude(
                event_id=featured_event.event_id
            )

        # 4️⃣ Apply date filter
        if selected_date:
            events = base_queryset.filter(
                event_date=selected_date
            ).order_by("event_date", "start_time")
        else:
            events = base_queryset.filter(
                event_date__in=[today, tomorrow]
            ).order_by("event_date", "start_time")

        serializer = EventListSerializer(events, many=True)

        return Response(
            {
                "status": "success",
                "data": serializer.data,
                "meta": {
                    "filter_date": selected_date,
                    "default_range": "today_and_tomorrow" if not selected_date else None,
                    "featured_excluded": True,
                },
            },
            status=status.HTTP_200_OK,
        )






class EventReminderToggleAPI(APIView):
    authentication_classes =[JWTAuthentication]
    permission_classes =[IsAuthenticated]

    def post(self, request, event_id):
        serializer = ReminderToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        action = serializer.validated_data["action"]

        # 1️⃣ Validate event
        try:
            event = Event.objects.get(
                event_id=event_id,
                status="PUBLISHED",
                del_flag=0
            )
        except Event.DoesNotExist:
            return Response(
                {"message": "Event not found or inactive"},
                status=status.HTTP_404_NOT_FOUND
            )

        event_start_dt = get_event_start_datetime(event)

        if event_start_dt <= timezone.now():
            return Response(
                {"message": "Cannot set reminder for past events"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2️⃣ ENABLE FLOW
        if action == "ENABLE":
            subscription, created = EventSubscription.objects.get_or_create(
                user=request.user,
                event=event,
                defaults={
                    "is_active": True,
                    "reminder_offsets": DEFAULT_REMINDER_OFFSETS
                }
            )

            if not created and subscription.is_active:
                # Idempotent response
                return Response(
                    {
                        "status": "success",
                        "message": "Reminder already enabled",
                        "event_id": str(event.event_id)
                    },
                    status=status.HTTP_200_OK
                )

            # Reactivate if previously disabled
            subscription.is_active = True
            subscription.reminder_offsets = DEFAULT_REMINDER_OFFSETS
            subscription.save()

            # Clear old unsent notifications (safety)
            ScheduledNotification.objects.filter(
                subscription=subscription,
                is_sent=False
            ).delete()

            # Create scheduled notifications
            now = timezone.now()
            created_count = 0

            for offset in DEFAULT_REMINDER_OFFSETS:
                scheduled_at = event_start_dt - timedelta(minutes=offset)
                if scheduled_at > now:
                    ScheduledNotification.objects.get_or_create(
    subscription=subscription,
    scheduled_at=scheduled_at,
    defaults={"offset_minutes": offset}
)

                    created_count += 1

            # Analytics hook (later implementation)
            log_event_analytics(request, event, "REMIND_ENABLE")

            return Response(
                {
                    "status": "success",
                    "message": "Event reminders enabled",
                    "event_id": str(event.event_id),
                    "scheduled_notifications": created_count
                },
                status=status.HTTP_200_OK
            )

        # 3️⃣ DISABLE FLOW
        if action == "DISABLE":
            try:
                subscription = EventSubscription.objects.get(
                    user=request.user,
                    event=event
                )
            except EventSubscription.DoesNotExist:
                return Response(
                    {
                       
                        "message": "Reminder not enabled"},
                    status=status.HTTP_200_OK
                )

            subscription.is_active = False
            subscription.save()

            ScheduledNotification.objects.filter(
                subscription=subscription,
                is_sent=False
            ).delete()

            # Analytics hook
            log_event_analytics(request, event, "REMIND_DISABLE")

            return Response(
                {
                    "status": "success",
                    

                    "message": "Event reminders disabled",
                    "event_id": str(event.event_id)
                },
                status=status.HTTP_200_OK
            )