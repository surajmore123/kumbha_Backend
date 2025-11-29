from django.urls import path

from .views import ChatWithGuruApiView,ChatHistoryView

app_name = 'aiChat'

urlpatterns = [
     path('chat-send/', ChatWithGuruApiView.as_view(), name='chat-send'),
    path("chat-history/", ChatHistoryView.as_view(), name='chat-history'),
     
    #  path('verify-mobile-otp/',VerifyMobileOtpView.as_view(),name='verify-mobile-otp'),
]