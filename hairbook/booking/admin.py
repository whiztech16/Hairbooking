from django.contrib import admin
from django.utils.html import format_html
from .models import Hairstylist, WorkingHours, Service, Appointment


class WorkingHoursInline(admin.TabularInline):
    model = WorkingHours
    extra = 1


@admin.register(Hairstylist)
class HairstylistAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "email", "phone", "address", "is_active", "photo_preview"]
    list_filter = ["category", "is_active"]
    inlines = [WorkingHoursInline]
    fieldsets = (
        (None, {
            "fields": ("name", "email", "category", "bio", "phone", "address", "is_active"),
        }),
        ("Photo", {
            "fields": ("photo", "photo_url", "photo_preview_large"),
            "description": "Upload a photo directly, or paste an external URL as a fallback.",
        }),
    )
    readonly_fields = ["photo_preview", "photo_preview_large"]

    def photo_preview(self, obj):
        url = obj.photo.url if obj.photo else obj.photo_url
        if url:
            return format_html('<img src="{}" style="width:40px; height:40px; object-fit:cover; border-radius:8px;" />', url)
        return "—"
    photo_preview.short_description = "Photo"

    def photo_preview_large(self, obj):
        url = obj.photo.url if obj.photo else obj.photo_url
        if url:
            return format_html('<img src="{}" style="max-width:200px; max-height:200px; object-fit:cover; border-radius:12px;" />', url)
        return "No photo yet"
    photo_preview_large.short_description = "Preview"


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "default_duration_minutes", "is_active"]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["client_name", "hairstylist", "start_time", "end_time", "status"]
    list_filter = ["status", "hairstylist"]
