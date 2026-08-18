from django.db import models
from django.core.exceptions import ValidationError
from cloudinary.models import CloudinaryField


WEEKDAYS = [
    (0, "Monday"),
    (1, "Tuesday"),
    (2, "Wednesday"),
    (3, "Thursday"),
    (4, "Friday"),
    (5, "Saturday"),
    (6, "Sunday"),
]


class Hairstylist(models.Model):
    CATEGORY_CHOICES = [
        ("hairstylist", "Hairstylist"),
        ("barber", "Barber"),
        ("nail_tech", "Nail Tech"),
    ]

    name = models.CharField(max_length=150)
    email = models.EmailField(help_text="Used to notify the stylist of new bookings")
    category = models.CharField(
        max_length=20, choices=CATEGORY_CHOICES, default="hairstylist",
        help_text="Lets clients filter between hairstylists, barbers, and nail techs when browsing.",
    )
    bio = models.TextField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=300, blank=True, help_text="Salon/shop address shown on the booking card")
    photo = CloudinaryField(
        'image', blank=True, null=True,
        help_text="Profile photo uploaded via admin. Stored on Cloudinary.",
    )
    photo_url = models.URLField(blank=True, help_text="External photo URL (fallback if no uploaded photo)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_category_display()})"


class WorkingHours(models.Model):
    """A stylist's recurring working hours for a given weekday.
    Multiple rows per stylist per weekday are allowed (e.g. split shifts),
    but usually one row per day is enough."""

    hairstylist = models.ForeignKey(
        Hairstylist, on_delete=models.CASCADE, related_name="working_hours"
    )
    weekday = models.IntegerField(choices=WEEKDAYS)
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        ordering = ["weekday", "start_time"]

    def clean(self):
        if self.start_time >= self.end_time:
            raise ValidationError("start_time must be before end_time")

    def __str__(self):
        return f"{self.hairstylist.name} - {self.get_weekday_display()} {self.start_time}-{self.end_time}"


class Service(models.Model):
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    default_duration_minutes = models.PositiveIntegerField(
        help_text="Default duration in minutes. Can be overridden per booking."
    )
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.default_duration_minutes} min)"


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("confirmed", "Confirmed"),
        ("ready", "Stylist Ready"),
        ("cancelled", "Cancelled"),
        ("completed", "Completed"),
    ]

    hairstylist = models.ForeignKey(
        Hairstylist, on_delete=models.CASCADE, related_name="appointments"
    )
    service = models.ForeignKey(
        Service, on_delete=models.SET_NULL, null=True, blank=True
    )
    client_name = models.CharField(max_length=150)
    client_phone = models.CharField(max_length=30)
    client_email = models.EmailField(
        blank=True, help_text="Optional, but required to receive email notifications"
    )
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="confirmed")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["start_time"]
        indexes = [
            models.Index(fields=["hairstylist", "start_time"]),
        ]

    def __str__(self):
        return f"{self.client_name} with {self.hairstylist.name} @ {self.start_time}"
