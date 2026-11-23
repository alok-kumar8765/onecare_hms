from django.urls import path
from .api import AppointmentListCreateAPIView, EncounterListCreateAPIView, PatientListCreateAPIView

urlpatterns = [
    path("patients/", PatientListCreateAPIView.as_view(), name="api-clinic-patients"),
    path("appointments/", AppointmentListCreateAPIView.as_view(), name="api-clinic-appointments"),
    path("encounters/", EncounterListCreateAPIView.as_view(), name="api-clinic-encounters"),
]