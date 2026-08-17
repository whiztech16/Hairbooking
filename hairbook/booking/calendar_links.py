"""
Builds "Add to Google Calendar" links using Google's public calendar
render URL — no OAuth, no API key, no Google Cloud project needed.
Clicking the link opens Google Calendar with the event pre-filled;
the client saves it themselves with one more click.

This is intentionally one-directional (client adds it manually) rather
than a live sync, since a live sync would require each stylist to
individually authorize access to their Google account — which conflicts
with this platform's no-login design and would need Google's app
verification process before real users could use it.
"""

from datetime import timezone as dt_timezone
from urllib.parse import urlencode


def google_calendar_link(appointment) -> str:
    """Returns a URL that opens Google Calendar with this appointment
    pre-filled, ready for the client to save with one click."""
    start_utc = appointment.start_time.astimezone(dt_timezone.utc)
    end_utc = appointment.end_time.astimezone(dt_timezone.utc)

    dates = f"{start_utc.strftime('%Y%m%dT%H%M%SZ')}/{end_utc.strftime('%Y%m%dT%H%M%SZ')}"

    service_name = appointment.service.name if appointment.service else "your appointment"
    title = f"{service_name} with {appointment.hairstylist.name}"

    details_lines = [f"Stylist: {appointment.hairstylist.name}"]
    if appointment.service:
        details_lines.append(f"Service: {appointment.service.name}")
    if appointment.notes:
        details_lines.append(f"Notes: {appointment.notes}")
    details_lines.append("Booked via Hairbooking")
    details = "\n".join(details_lines)

    params = {
        "action": "TEMPLATE",
        "text": title,
        "dates": dates,
        "details": details,
    }
    if appointment.hairstylist.phone:
        params["location"] = f"Contact stylist: {appointment.hairstylist.phone}"

    return f"https://calendar.google.com/calendar/render?{urlencode(params)}"
