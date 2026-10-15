"""Website API, served at /api/v1/ (same paths as the old FastAPI backend, which the website calls)."""

from django.http import JsonResponse
from django.urls import path, re_path

from .core import global_limit, methods
from .views import account, admin, auth, public


def not_found(request, *args, **kwargs):
    if (limited := global_limit(request)) is not None:
        return limited
    return JsonResponse({"error": {"code": "http_error", "message": "Not Found"}}, status=404)


urlpatterns = [
    # auth
    path("auth/otp/request", methods(post=auth.request_otp)),
    path("auth/otp/verify", methods(post=auth.verify_otp)),
    path("auth/google", methods(post=auth.google)),
    path("auth/refresh", methods(post=auth.refresh)),
    path("auth/logout", methods(post=auth.logout)),
    path("auth/me", methods(get=auth.me, patch=auth.update_me)),
    # listings, enquiries, waitlist, announcements
    path("listings", methods(get=public.search_listings)),
    path("listings/<str:listing_id>", methods(get=public.get_listing)),
    path("enquiries", methods(post=public.submit_enquiry)),
    path("enquiries/me", methods(get=public.my_enquiries)),
    path("waitlist", methods(post=public.join_waitlist)),
    path("announcements", methods(get=public.current_announcements)),
    # partner portal
    path("partners", methods(post=account.apply_partner)),
    path("partners/me", methods(get=account.my_partner)),
    path("partners/me/listings", methods(get=account.my_listings, post=account.create_listing)),
    path("partners/me/listings/<str:listing_id>", methods(patch=account.update_listing)),
    # signed-in user's data
    path("me/safety-cards", methods(get=account.list_cards, post=account.create_card)),
    path("me/safety-cards/<str:card_id>", methods(put=account.update_card, delete=account.delete_card)),
    path("me/items", methods(get=account.list_items)),
    path("me/items/<str:kind>/<str:key>", methods(put=account.put_item, delete=account.delete_item)),
    # admin
    path("admin/stats", methods(get=admin.stats)),
    path("admin/listings", methods(get=admin.list_listings)),
    path("admin/listings/<str:listing_id>/status", methods(post=admin.set_listing_status)),
    path("admin/enquiries", methods(get=admin.list_enquiries)),
    path("admin/enquiries/<str:enquiry_id>", methods(patch=admin.update_enquiry)),
    path("admin/partners", methods(get=admin.list_partners)),
    path("admin/partners/<str:partner_id>/status", methods(post=admin.set_partner_status)),
    path("admin/users", methods(get=admin.list_users)),
    path("admin/users/<str:user_id>", methods(get=admin.get_user, patch=admin.update_user)),
    path("admin/announcements", methods(get=admin.list_announcements, post=admin.create_announcement)),
    path("admin/announcements/<str:ann_id>", methods(put=admin.update_announcement, delete=admin.delete_announcement)),
    # anything else under /api/v1/ answers in the same JSON error format
    re_path(r"^.*$", not_found),
]
