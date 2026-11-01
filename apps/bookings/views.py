"""
Booking & Stay API (all under /api/bookings/).

Stays and transport are public and read-only. Saved bookings need a login, and
every lookup is scoped to request.user: another person's record answers 404.
KumbhaPath never books, charges or confirms anything.
"""

from datetime import date

from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.aiChat.services.geo import distance_km, valid_coordinates
from apps.akhadas.cache import cached_get
from apps.akhadas.views import _Public, error, ok
from apps.bookings import adapters, serializers
from apps.bookings.models import Amenity, SavedBooking, StayArea, StayProfile, TransportProvider
from apps.website.models import ListingCategory, ListingStatus


def visible_stays():
    """Published, real (never a website sample), and not expired."""
    today = timezone.localdate()
    return (
        StayProfile.objects.filter(
            listing__status=ListingStatus.published, listing__is_sample=False,
            listing__category=ListingCategory.hotels,
        )
        .exclude(verification_status=StayProfile.Verification.EXPIRED)
        .filter(Q(expires_on__isnull=True) | Q(expires_on__gte=today))
        .select_related("listing", "listing__partner", "area")
        .prefetch_related("amenities", "images")
    )


def _number(params, name):
    value = params.get(name)
    if value in (None, ""):
        return None
    return float(value)


def _origin(params):
    """Coordinates to measure from: `lat` and `lng`, or a named area."""
    if params.get("lat") or params.get("lng"):
        lat, lng = _number(params, "lat"), _number(params, "lng")
        if lat is None or lng is None or not valid_coordinates(lat, lng):
            raise ValueError("lat")
        return lat, lng
    slug = params.get("near")
    if slug:
        area = StayArea.objects.filter(slug=slug).exclude(latitude=None).first()
        if area:
            return float(area.latitude), float(area.longitude)
    return None


class StayFiltersAPI(_Public):
    @cached_get
    def get(self, request):
        context = self.context(request)
        stays = visible_stays()
        return ok({
            "areas": serializers.AreaSerializer(StayArea.objects.all(), many=True, context=context).data,
            "amenities": serializers.AmenitySerializer(Amenity.objects.all(), many=True, context=context).data,
            "stay_types": sorted(set(stays.values_list("stay_type", flat=True))),
            "count": stays.count(),
        })


class StayListAPI(_Public):
    """GET ?q= &type= &area= &min_price= &max_price= &amenity=a&amenity=b
    &family=true &seniors=true &accessible=true &available=true
    &near=<area> or &lat= &lng= &radius_km= &sort=recommended|price|distance"""

    @cached_get
    def get(self, request):
        params = request.query_params
        try:
            min_price, max_price = _number(params, "min_price"), _number(params, "max_price")
            radius = _number(params, "radius_km")
            origin = _origin(params)
        except ValueError:
            return error({"non_field_errors": ["Check the numbers in this search."]})
        if min_price is not None and max_price is not None and min_price > max_price:
            return error({"min_price": "Minimum can't be above maximum."})

        stays = visible_stays()
        if params.get("q", "").strip():
            q = params["q"].strip()
            stays = stays.filter(
                Q(listing__name__icontains=q) | Q(listing__area__icontains=q) | Q(address__icontains=q),
            )
        if params.get("type"):
            stays = stays.filter(stay_type=params["type"])
        if params.get("area"):
            stays = stays.filter(area__slug=params["area"])
        # A stay with no published price can't be said to fit a budget.
        if min_price is not None:
            stays = stays.filter(listing__price_from__gte=min_price, listing__price_from__gt=0)
        if max_price is not None:
            stays = stays.filter(listing__price_from__lte=max_price, listing__price_from__gt=0)
        for slug in params.getlist("amenity"):
            stays = stays.filter(amenities__slug=slug)
        if params.get("family") == "true":
            stays = stays.filter(family_friendly=True)
        if params.get("seniors") == "true":
            stays = stays.filter(senior_friendly=True)
        if params.get("accessible") == "true":
            stays = stays.filter(listing__wheelchair=True)
        if params.get("available") == "true":
            stays = stays.filter(availability_verified=True)

        items = list(stays.distinct())
        if origin:
            distances = {
                s.pk: distance_km(origin[0], origin[1], s.latitude, s.longitude)
                for s in items if s.has_coordinates
            }
            if radius is not None:
                items = [s for s in items if s.pk in distances and distances[s.pk] <= radius]
        else:
            distances = {}
        sort = params.get("sort", "recommended")
        if sort not in ("recommended", "price", "distance"):
            return error({"sort": "Unknown sort."})
        if sort == "price":
            # Stays without a published price go last, not first.
            items.sort(key=lambda s: (s.listing.price_from == 0, s.listing.price_from))
        elif sort == "distance" and origin:
            items.sort(key=lambda s: distances.get(s.pk, float("inf")))
        else:
            items.sort(key=lambda s: (s.verification_status != "verified", s.listing.name))

        paginator = PageNumberPagination()
        paginator.page_size = 20
        paginator.page_size_query_param = "page_size"
        paginator.max_page_size = 50
        page = paginator.paginate_queryset(items, request, view=self)
        context = {**self.context(request), "origin": origin}
        return ok({
            "count": paginator.page.paginator.count,
            "page": paginator.page.number,
            "has_next": paginator.page.has_next(),
            "results": serializers.StaySummarySerializer(page, many=True, context=context).data,
        })


class StayDetailAPI(_Public):
    @cached_get
    def get(self, request, listing_id):
        stay = get_object_or_404(
            visible_stays().prefetch_related("rooms", "texts", "sources"), listing_id=listing_id,
        )
        data = dict(serializers.StayDetailSerializer(stay, context=self.context(request)).data)
        data["temples"] = serializers.nearest_temples(stay)
        return ok(data)


class TransportListAPI(_Public):
    """GET ?mode=train|bus|flight|taxi|local"""

    @cached_get
    def get(self, request):
        providers = TransportProvider.objects.filter(is_active=True)
        mode = request.query_params.get("mode")
        if mode:
            providers = providers.filter(mode=mode)
        context = self.context(request)
        return ok(serializers.TransportProviderSerializer(providers, many=True, context=context).data)


class TransportDetailAPI(_Public):
    @cached_get
    def get(self, request, slug):
        provider = get_object_or_404(TransportProvider, slug=slug, is_active=True)
        return ok(serializers.TransportProviderSerializer(provider, context=self.context(request)).data)


class TransportSearchAPI(_Public):
    """GET ?from= &to= &date=YYYY-MM-DD &mode= &passengers=
    `live` is true only when an authorized provider actually returned results.
    Otherwise `results` is empty and `providers` lists where to check."""

    def get(self, request):
        params = request.query_params
        origin, destination = params.get("from", "").strip(), params.get("to", "").strip()
        if not origin or not destination:
            return error({"non_field_errors": ["Enter where you're travelling from and to."]})
        when = None
        if params.get("date"):
            try:
                when = date.fromisoformat(params["date"])
            except ValueError:
                return error({"date": "Use YYYY-MM-DD."})
        mode = params.get("mode") or None
        if mode and mode not in TransportProvider.Mode.values:
            return error({"mode": "Unknown transport type."})
        try:
            passengers = int(params.get("passengers", 1))
        except ValueError:
            return error({"passengers": "Enter a number."})
        if not 1 <= passengers <= 50:
            return error({"passengers": "Enter between 1 and 50."})

        query = adapters.TransportQuery(mode, origin, destination, when, passengers)
        results, failed = adapters.live_results(query)
        providers = TransportProvider.objects.filter(is_active=True)
        if mode:
            providers = providers.filter(mode=mode)
        return ok({
            "live": bool(results),
            "results": results,
            "failed_providers": failed,
            "providers": serializers.TransportProviderSerializer(
                providers, many=True, context=self.context(request),
            ).data,
        })


class _Owned(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def bookings(self, request):
        return SavedBooking.objects.filter(user=request.user).select_related("stay")


class BookingPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 50


class SavedBookingListAPI(_Owned):
    """GET ?status= &category= &when=upcoming|past. POST creates one."""

    def get(self, request):
        params = request.query_params
        bookings = self.bookings(request)
        if params.get("status"):
            bookings = bookings.filter(status=params["status"])
        if params.get("category"):
            bookings = bookings.filter(category=params["category"])
        today = timezone.localdate()
        closed = [SavedBooking.Status.CANCELLED, SavedBooking.Status.COMPLETED]
        if params.get("when") == "upcoming":
            bookings = bookings.exclude(status__in=closed).filter(
                Q(start_date__isnull=True) | Q(start_date__gte=today) | Q(end_date__gte=today),
            )
        elif params.get("when") == "past":
            bookings = bookings.filter(
                Q(status__in=closed) | (Q(end_date__lt=today) | Q(end_date__isnull=True, start_date__lt=today)),
            )
        paginator = BookingPagination()
        page = paginator.paginate_queryset(bookings, request, view=self)
        return ok({
            "count": paginator.page.paginator.count,
            "page": paginator.page.number,
            "has_next": paginator.page.has_next(),
            "results": serializers.SavedBookingSerializer(page, many=True, context={"request": request}).data,
        })

    def post(self, request):
        if self.bookings(request).count() >= SavedBooking.MAX_PER_USER:
            return error({"non_field_errors": [f"You can keep up to {SavedBooking.MAX_PER_USER} bookings."]})
        serializer = serializers.SavedBookingSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return error(serializer.errors)
        booking = serializer.save(user=request.user)
        data = serializers.SavedBookingSerializer(booking, context={"request": request}).data
        return Response({"status": "success", "data": data}, status=status.HTTP_201_CREATED)


class SavedBookingDetailAPI(_Owned):
    def get(self, request, booking_id):
        booking = get_object_or_404(self.bookings(request), pk=booking_id)
        return ok(serializers.SavedBookingSerializer(booking, context={"request": request}).data)

    def patch(self, request, booking_id):
        booking = get_object_or_404(self.bookings(request), pk=booking_id)
        serializer = serializers.SavedBookingSerializer(
            booking, data=request.data, partial=True, context={"request": request},
        )
        if not serializer.is_valid():
            return error(serializer.errors)
        return ok(serializers.SavedBookingSerializer(serializer.save(), context={"request": request}).data)

    def delete(self, request, booking_id):
        get_object_or_404(self.bookings(request), pk=booking_id).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
