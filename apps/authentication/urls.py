from django.urls import path

from .views import SendMobileOtpView,VerifyMobileOtpView,UserProfileView,UserProfileImageUploadView,RegisterFCMDeviceAPI

app_name = 'authentication'

urlpatterns = [
     path('send-mobile-otp/', SendMobileOtpView.as_view(), name='send-mobile-otp'),
     path('verify-mobile-otp/',VerifyMobileOtpView.as_view(),name='verify-mobile-otp'),
     # path("profile/", UserProfileView.as_view(), name="user-profile"),
     path("profile/", UserProfileView.as_view(), name="user-profile"),
     path("profile/image/", UserProfileImageUploadView.as_view(), name="user-profile-image"),
     path("fcm/register/", RegisterFCMDeviceAPI.as_view(), name="fcm-register"),
]