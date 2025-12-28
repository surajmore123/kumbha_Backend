from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from .models import Temple
from .serializers import NearbyTempleSerializer,TempleDetailSerializer
from rest_framework.permissions import IsAuthenticated
from .utility import haversine,log_temple_event


class NearbyTemplesAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
    
        try:
            user_lat = float(request.query_params.get("lat"))
            user_lng = float(request.query_params.get("lng"))
            radius_km = float(request.query_params.get("radius", 5))
        except (TypeError, ValueError):
            return Response(
                {"status": "error", "message": "Invalid or missing latitude/longitude"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    
        try:
            limit = int(request.query_params.get("limit", 5))
        except ValueError:
            limit = 5

        limit = min(limit, 20)  # hard cap
        cursor = request.query_params.get("cursor")  # temple_id

    
        temples_qs = Temple.objects.filter(
            is_active=True,
            del_flag=0,
        ).order_by("temple_id")

  
        if cursor:
            temples_qs = temples_qs.filter(temple_id__gt=cursor)

     
        nearby = []
        for temple in temples_qs:
            distance = haversine(
                user_lat,
                user_lng,
                float(temple.latitude),
                float(temple.longitude),
            )

            if distance <= radius_km:
                temple.distance_km = round(distance, 2)
                nearby.append(temple)

         
            if len(nearby) >= limit + 1:
                break

     
        has_more = len(nearby) > limit
        nearby = nearby[:limit]

        next_cursor = nearby[-1].temple_id if nearby else None

        serializer = NearbyTempleSerializer(nearby, many=True)

        return Response(
            {
                "status": "success",
                "data": {
                    "radius_km": radius_km,
                    "count": len(serializer.data),
                    "temples": serializer.data,
                    "has_more": has_more,
                    "next_cursor": next_cursor,
                },
            },
            status=status.HTTP_200_OK,
        )
    

class TempleDetailAPI(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, temple_id):
        try:
            temple = Temple.objects.get(
                temple_id=temple_id,
                is_active=True
            )
        except Temple.DoesNotExist:
            return Response(
                {"status": "error", "message": "Temple not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        
        log_temple_event(
            request=request,
            temple=temple,
            event_type="DETAIL_OPEN",
            user_lat=request.query_params.get("lat"),
            user_lng=request.query_params.get("lng"),
        )

        serializer = TempleDetailSerializer(temple)

        return Response(
            {"status": "success", "data": serializer.data},
            status=status.HTTP_200_OK
        )

       
