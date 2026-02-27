# crowd/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from django.utils import timezone
from rest_framework import status

from apps.crowd.models.AppNotification import AppNotification
from .models import Zone, ZoneCrowdSnapshot
from .serializers import AppNotificationSerializer, ZoneLiveStatusSerializer

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.permissions import IsAuthenticated
from .serializers import QuickAlertSerializer, GateSerializer, SimpleAlertSerializer, AlternativeZoneSerializer,UpdateLocationSerializer, AppNotificationSerializer
from .models import Incident
from django.db import models
from .models import (
    Zone,
    ZoneGate,
    Incident,
    ZoneNeighbor,
    ZoneCrowdSnapshot
)
from django.shortcuts import get_object_or_404
from apps.crowd.services.presence_engine import update_user_presence




class LiveCrowdStatusAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    def get(self, request):
        data = []

        zones = Zone.objects.filter(is_active=True, del_flag=0)

        for zone in zones:
            snapshot = (
                ZoneCrowdSnapshot.objects
                .filter(zone=zone)
                .order_by("-calculated_at")
                .first()
            )

            if snapshot:
                data.append({
                    "code": zone.code,
                    "name": zone.name,
                    "latitude": zone.latitude,
                    "longitude": zone.longitude,
                    "capacity": zone.capacity,
                    "total_people": snapshot.total_people,
                    "occupancy_percent": snapshot.occupancy_percent,
                    "status": snapshot.status,
                })
            else:
                data.append({
                    "code": zone.code,
                    "name": zone.name,
                    "latitude": zone.latitude,
                    "longitude": zone.longitude,
                    "capacity": zone.capacity,
                    "total_people": 0,
                    "occupancy_percent": 0,
                    "status": "LOW",
                })

        serializer = ZoneLiveStatusSerializer(data, many=True)

        return Response({
            "status": "success",
            "zones": serializer.data,
            "last_updated": timezone.now()
        },status=status.HTTP_200_OK,)
    






class QuickAlertsAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()

        incidents = (
            Incident.objects
            .filter(
                is_active=True,
                del_flag=0,
                start_time__lte=now
            )
            .filter(
                models.Q(end_time__isnull=True) |
                models.Q(end_time__gte=now)
            )
            .order_by("-severity", "-start_time")
        )

        data = []
        for i in incidents:
            data.append({
                "id": i.id,
                "zone_code": i.zone.code,
                "zone_name": i.zone.name,
                "type": i.incident_type,
                "severity": i.severity,
                "title": i.title,
                "description": i.description,
                "start_time": i.start_time,
            })

        serializer = QuickAlertSerializer(data, many=True)

        return Response({
            "status": "success",
            "alerts": serializer.data})
    

class AppNotificationAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        filter_type = request.query_params.get("type", "ALL").upper()

        notifications = AppNotification.objects.filter(
            is_active=True,
            del_flag=0
        )

        if filter_type == "ALERT":
            notifications = notifications.filter(type="ALERT")

        elif filter_type == "MESSAGE":
            notifications = notifications.filter(type="MESSAGE")

        # if ALL → no filtering

        notifications = notifications.order_by("-created_at")

        serializer = AppNotificationSerializer(notifications, many=True)

        return Response({
            "status": "success",
            "notifications": serializer.data
        })
    









class ZoneDetailAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, zone_code):
        now = timezone.now()

        zone = get_object_or_404(
            Zone,
            code=zone_code,
            is_active=True,
            del_flag=0
        )

        # latest snapshot
        snapshot = (
            ZoneCrowdSnapshot.objects
            .filter(zone=zone)
            .order_by("-calculated_at")
            .first()
        )

        zone_data = {
            "code": zone.code,
            "name": zone.name,
            "capacity": zone.capacity,
            "total_people": snapshot.total_people if snapshot else 0,
            "occupancy_percent": snapshot.occupancy_percent if snapshot else 0,
            "status": snapshot.status if snapshot else "LOW",
        }

        # gates
        gates = ZoneGate.objects.filter(
            zone=zone,
            del_flag=0
        )

        # alerts
        alerts = (
            Incident.objects
            .filter(
                zone=zone,
                is_active=True,
                del_flag=0,
                start_time__lte=now
            )
            .filter(
                models.Q(end_time__isnull=True) |
                models.Q(end_time__gte=now)
            )
        )

        # neighbors
        alternatives = ZoneNeighbor.objects.filter(
            zone=zone,
            del_flag=0
        )

        return Response({
            "status": "success",
            "zone": zone_data,
            "gates": GateSerializer(gates, many=True).data,
            "alerts": SimpleAlertSerializer(alerts, many=True).data,
            "alternatives": AlternativeZoneSerializer(
                [{"code": n.neighbor_zone.code, "name": n.neighbor_zone.name} for n in alternatives],
                many=True
            ).data
        })


class UpdateLocationAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = UpdateLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        latitude = serializer.validated_data["latitude"]
        longitude = serializer.validated_data["longitude"]

        update_user_presence(
            user=request.user,
            latitude=latitude,
            longitude=longitude
        )

        return Response(
            {"status": "location updated"},
            status=status.HTTP_200_OK
        )



