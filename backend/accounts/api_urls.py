from django.urls import path
from .api import ApproveDeviceAPIView, DevicesAPIView, LoginAPIView, ProfileMeAPIView

urlpatterns = [
    path("login/", LoginAPIView.as_view(), name="api-accounts-login"),
    path("me/", ProfileMeAPIView.as_view(), name="api-accounts-me"),
    path("devices/", DevicesAPIView.as_view(), name="api-accounts-devices"),
    path("devices/<uuid:device_id>/approve/", ApproveDeviceAPIView.as_view(), name="api-accounts-device-approve"),
]