from django.urls import path
from .api import IPDAdmissionActionAPIView, IPDAdmissionListCreateAPIView, WardBedListCreateAPIView

urlpatterns = [
    path("beds/", WardBedListCreateAPIView.as_view(), name="api-ipd-beds"),
    path("admissions/", IPDAdmissionListCreateAPIView.as_view(), name="api-ipd-admissions"),
    path("admissions/<uuid:admission_id>/<str:action>/", IPDAdmissionActionAPIView.as_view(), name="api-ipd-admission-action"),
]