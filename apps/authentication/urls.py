from django.urls import path

from .views import SendMobileOtpView,VerifyMobileOtpView

app_name = 'authentication'

urlpatterns = [
     path('send-mobile-otp/', SendMobileOtpView.as_view(), name='send-mobile-otp'),
     path('verify-mobile-otp/',VerifyMobileOtpView.as_view(),name='verify-mobile-otp'),
]