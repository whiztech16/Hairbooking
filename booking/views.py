from datetime import datetime, timedelta

from rest_framework import viewsets, status
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.shortcuts import get_object_or_404, render

from .models import Hairstylist, Service, Appointment
from .serializers import (
    HairstylistSerializer,
    ServiceSerializer,
    AppointmentSerializer,
    BookingRequestSerializer,
    RescheduleRequestSerializer,
)
from .scheduling import (
    book_appointment,
    is_slot_available,
    find_all_alternatives,
    _free_slots_for_day,
    BUFFER_MINUTES,
)
from .notifications import (
    notify_new_booking,
    notify_cancellation,
    notify_reschedule,
    notify_stylist_ready,
)


class HairstylistViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Hairstylist.objects.filter(is_active=True)
    serializer_class = HairstylistSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs

    @action(detail=True, methods=["get"])
    def availability(self, request, pk=None):
        """GET /api/hairstylists/<id>/availability/?date=YYYY-MM-DD&duration_minutes=60"""
        stylist = self.get_object()
        date_str = request.query_params.get("date")
        duration = int(request.query_params.get("duration_minutes", 60))

        if not date_str:
            return Response({"error": "date query param is required (YYYY-MM-DD)"}, status=400)

        date = parse_date(date_str)
        if not date:
            return Response({"error": "invalid date format, use YYYY-MM-DD"}, status=400)

        slots = _free_slots_for_day(stylist, date, duration, BUFFER_MINUTES)
        return Response({
            "hairstylist_id": stylist.id,
            "date": date_str,
            "duration_minutes": duration,
            "available_slots": [s.isoformat() for s in slots],
        })


class ServiceViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Service.objects.filter(is_active=True)
    serializer_class = ServiceSerializer


class AppointmentViewSet(viewsets.ModelViewSet):
    """
    Read/list/cancel/reschedule go through here. Direct create and direct
    field-level update are intentionally disabled — creation must go through
    /book/ and time changes must go through /reschedule/, because those are
    the only two paths that run the scheduling algorithm (working hours,
    overlap, buffer). Allowing raw POST/PUT/PATCH here would let a client
    silently create double-bookings or rewrite start_time with zero
    validation.
    """
    queryset = Appointment.objects.all()
    serializer_class = AppointmentSerializer
    http_method_names = ["get", "head", "options", "patch", "delete"]

    def get_queryset(self):
        qs = super().get_queryset()
        hairstylist_id = self.request.query_params.get("hairstylist_id")
        if hairstylist_id:
            qs = qs.filter(hairstylist_id=hairstylist_id)

        # Client self-service lookup: require BOTH email and phone together
        # (not just one) so a client can find their own bookings without a
        # login, without letting anyone browse other clients' appointments
        # by guessing a single field.
        client_email = self.request.query_params.get("client_email")
        client_phone = self.request.query_params.get("client_phone")
        if client_email and client_phone:
            qs = qs.filter(client_email__iexact=client_email.strip(), client_phone=client_phone.strip())
        elif client_email or client_phone:
            qs = qs.none()

        return qs

    def partial_update(self, request, *args, **kwargs):
        # Block the generic PATCH /api/appointments/<id>/ entirely — only
        # the mark_ready and reschedule actions below may mutate an
        # appointment, since those are the ones that go through validation.
        return Response(
            {"error": "Direct updates aren't allowed. Use /reschedule/ or /mark_ready/."},
            status=status.HTTP_405_METHOD_NOT_ALLOWED,
        )

    def destroy(self, request, *args, **kwargs):
        """Cancel instead of hard-delete, and notify the stylist."""
        appointment = self.get_object()
        appointment.status = "cancelled"
        appointment.save()
        notify_cancellation(appointment)
        return Response({"success": True, "message": "Appointment cancelled"})

    @action(detail=True, methods=["patch"])
    def mark_ready(self, request, pk=None):
        """PATCH /api/appointments/<id>/mark_ready/
        Stylist marks themself as ready for this client — emails the client."""
        appointment = self.get_object()
        appointment.status = "ready"
        appointment.save()
        notify_stylist_ready(appointment)
        return Response({
            "success": True,
            "message": "Client notified that you're ready.",
            "appointment": AppointmentSerializer(appointment).data,
        })

    @action(detail=True, methods=["patch"])
    def reschedule(self, request, pk=None):
        """PATCH /api/appointments/<id>/reschedule/
        Body: {"start_time": "...", "duration_minutes": 60}
        Uses the same scheduling algorithm; returns alternatives on conflict.
        """
        appointment = self.get_object()
        serializer = RescheduleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        new_start = data["start_time"]
        if timezone.is_naive(new_start):
            new_start = timezone.make_aware(new_start)

        duration = data.get("duration_minutes") or int(
            (appointment.end_time - appointment.start_time).total_seconds() / 60
        )

        if is_slot_available(
            appointment.hairstylist, new_start, duration,
            ignore_appointment_id=appointment.id,
        ):
            old_start = appointment.start_time
            appointment.start_time = new_start
            appointment.end_time = new_start + timedelta(minutes=duration)
            appointment.save()
            notify_reschedule(appointment, old_start)
            return Response({
                "success": True,
                "appointment": AppointmentSerializer(appointment).data,
            })

        alternatives = find_all_alternatives(appointment.hairstylist, new_start, duration)
        return Response({
            "success": False,
            "message": "That slot isn't available. Here are some alternatives.",
            "alternatives": alternatives,
        }, status=status.HTTP_409_CONFLICT)


@api_view(["POST"])
def book_appointment_view(request):
    """POST /api/appointments/book/
    Body: {
      "hairstylist_id": 1,
      "client_name": "Jane",
      "client_phone": "0800...",
      "client_email": "jane@example.com",
      "start_time": "2026-08-20T10:00:00",
      "duration_minutes": 60,   # optional if service_id given
      "service_id": 2,          # optional
      "notes": ""                # optional
    }
    """
    serializer = BookingRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    stylist = get_object_or_404(Hairstylist, id=data["hairstylist_id"], is_active=True)

    service = None
    duration = data.get("duration_minutes")
    if data.get("service_id"):
        service = get_object_or_404(Service, id=data["service_id"])
        if not duration:
            duration = service.default_duration_minutes

    if not duration:
        return Response(
            {"error": "duration_minutes is required if no service_id is given"},
            status=400,
        )

    start_time = data["start_time"]
    if timezone.is_naive(start_time):
        start_time = timezone.make_aware(start_time)

    result = book_appointment(
        hairstylist=stylist,
        client_name=data["client_name"],
        client_phone=data["client_phone"],
        client_email=data.get("client_email", ""),
        start_time=start_time,
        duration_minutes=duration,
        service=service,
        notes=data.get("notes", ""),
    )

    if result["success"]:
        notify_new_booking(result["appointment"])
        return Response({
            "success": True,
            "appointment": AppointmentSerializer(result["appointment"]).data,
        }, status=status.HTTP_201_CREATED)

    if result["reason"] == "duplicate":
        return Response({
            "success": False,
            "reason": "duplicate",
            "message": result["message"],
        }, status=status.HTTP_409_CONFLICT)

    return Response({
        "success": False,
        "reason": "conflict",
        "message": "That slot isn't available. Here are some alternatives.",
        "alternatives": result["alternatives"],
    }, status=status.HTTP_409_CONFLICT)


def booking_page(request):
    """Serves the client-facing booking page (book / reschedule / cancel /
    browse hairstylists & barbers). Plain server-rendered HTML — the page
    itself talks to the REST API below via fetch(), same-origin, no CORS
    needed since Django is serving both."""
    return render(request, "booking/booking.html")
