from rest_framework import serializers
from .models import Hairstylist, WorkingHours, Service, Appointment


class WorkingHoursSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkingHours
        fields = ["id", "weekday", "start_time", "end_time"]


class HairstylistSerializer(serializers.ModelSerializer):
    working_hours = WorkingHoursSerializer(many=True, read_only=True)
    image_url = serializers.SerializerMethodField()
    working_hours_summary = serializers.SerializerMethodField()

    class Meta:
        model = Hairstylist
        fields = [
            "id", "name", "email", "category", "bio", "phone", "address",
            "photo_url", "image_url", "is_active", "working_hours",
            "working_hours_summary",
        ]

    def get_image_url(self, obj):
        """Return Cloudinary photo URL if available, else fallback to photo_url."""
        if obj.photo:
            return obj.photo.url
        return obj.photo_url or ""

    def get_working_hours_summary(self, obj):
        """Return a short human-readable summary like 'Mon 9am-5pm'."""
        hours = obj.working_hours.all()
        if not hours:
            return "Hours not set"
        days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        parts = []
        for wh in hours:
            day = days[wh.weekday] if wh.weekday < len(days) else "?"
            start = wh.start_time.strftime("%I:%M%p").lstrip("0").lower()
            end = wh.end_time.strftime("%I:%M%p").lstrip("0").lower()
            parts.append(f"{day} {start}-{end}")
        return ", ".join(parts[:3]) + ("…" if len(parts) > 3 else "")


class ServiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Service
        fields = ["id", "name", "description", "default_duration_minutes", "is_active"]


class AppointmentSerializer(serializers.ModelSerializer):
    hairstylist_name = serializers.CharField(source="hairstylist.name", read_only=True)
    service_name = serializers.CharField(source="service.name", read_only=True, default=None)
    google_calendar_link = serializers.SerializerMethodField()

    class Meta:
        model = Appointment
        fields = [
            "id", "hairstylist", "hairstylist_name", "service", "service_name",
            "client_name", "client_phone", "client_email", "start_time", "end_time",
            "status", "notes", "created_at", "google_calendar_link",
        ]
        read_only_fields = ["end_time", "status", "created_at"]

    def get_google_calendar_link(self, obj):
        from .calendar_links import google_calendar_link
        return google_calendar_link(obj)


class BookingRequestSerializer(serializers.Serializer):
    """Input shape for POST /api/appointments/book/"""
    hairstylist_id = serializers.IntegerField()
    client_name = serializers.CharField(max_length=150, trim_whitespace=True)
    client_phone = serializers.CharField(max_length=30, trim_whitespace=True)
    client_email = serializers.EmailField()
    start_time = serializers.DateTimeField()
    # Capped at 8 hours — long enough for any real salon service, short
    # enough that the slot-scanning algorithm can't be handed a duration
    # large enough to make it do pathological amounts of work.
    duration_minutes = serializers.IntegerField(min_value=5, max_value=480, required=False)
    service_id = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")

    def validate_client_phone(self, value):
        cleaned = value.strip()
        if not cleaned:
            raise serializers.ValidationError("client_phone cannot be blank.")
        # Allow digits, spaces, +, -, () — reject anything else (basic
        # defense against junk/script injection riding in a phone field
        # that later gets echoed into emails).
        import re
        if not re.fullmatch(r"[0-9+\-() ]{5,30}", cleaned):
            raise serializers.ValidationError("client_phone contains invalid characters.")
        return cleaned

    def validate_client_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("client_name cannot be blank.")
        return value.strip()

    def validate_start_time(self, value):
        from django.utils import timezone as tz
        now = tz.now()
        aware_value = value if tz.is_aware(value) else tz.make_aware(value)
        if aware_value < now:
            raise serializers.ValidationError("start_time cannot be in the past.")
        return value


class RescheduleRequestSerializer(serializers.Serializer):
    """Input shape for PATCH /api/appointments/<id>/reschedule/"""
    start_time = serializers.DateTimeField()
    duration_minutes = serializers.IntegerField(min_value=5, max_value=480, required=False)

    def validate_start_time(self, value):
        from django.utils import timezone as tz
        now = tz.now()
        aware_value = value if tz.is_aware(value) else tz.make_aware(value)
        if aware_value < now:
            raise serializers.ValidationError("start_time cannot be in the past.")
        return value
