from django.contrib import admin
from .models import Hairstylist, WorkingHours, Service, Appointment


class WorkingHoursInline(admin.TabularInline):
    model = WorkingHours
    extra = 1


@admin.register(Hairstylist)
class HairstylistAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "email", "phone", "is_active"]
    list_filter = ["category", "is_active"]
    inlines = [WorkingHoursInline]


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["name", "default_duration_minutes", "is_active"]


@admin.register(Appointment)
class AppointmentAdmin(admin.ModelAdmin):
    list_display = ["client_name", "hairstylist", "start_time", "end_time", "status"]
    list_filter = ["status", "hairstylist"]
