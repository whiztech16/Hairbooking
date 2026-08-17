from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    HairstylistViewSet,
    ServiceViewSet,
    AppointmentViewSet,
    book_appointment_view,
    lookup_appointments_view,
)

router = DefaultRouter()
router.register(r"hairstylists", HairstylistViewSet, basename="hairstylist")
router.register(r"services", ServiceViewSet, basename="service")
router.register(r"appointments", AppointmentViewSet, basename="appointment")

urlpatterns = [
    path("appointments/book/", book_appointment_view, name="book-appointment"),
    path("appointments/lookup/", lookup_appointments_view, name="lookup-appointments"),
    path("", include(router.urls)),
]
