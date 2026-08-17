"""
Email notifications using Resend (https://resend.com).

Why Resend: it's a plain HTTPS API call, so it works fine on Render/Railway/
etc. without needing SMTP ports open. Free tier = 3,000 emails/month.

IMPORTANT (sandbox limitation): until you verify your own domain with
Resend, their free "onboarding@resend.dev" sender can only deliver to the
email address you signed up to Resend with. That's fine for building and
demoing — every email in this file will actually arrive as long as you're
testing with your own Resend-registered email as the stylist/client email.
For a real multi-user launch, verify a domain in the Resend dashboard and
update RESEND_FROM_EMAIL in settings.py.

Setup:
1. pip install resend  (already in requirements)
2. Sign up at resend.com, grab your API key
3. Set the environment variable RESEND_API_KEY (or hardcode in settings.py
   for local testing only — never commit a real key)
"""

import re

import resend
from django.conf import settings

from .models import Appointment
from .calendar_links import google_calendar_link

resend.api_key = settings.RESEND_API_KEY


def _clean_for_subject(text: str) -> str:
    """Strip newlines/control chars from anything interpolated into an
    email subject line — defense in depth even though Resend's JSON API
    isn't vulnerable to classic SMTP header injection the way raw smtplib
    would be."""
    return re.sub(r"[\r\n]+", " ", text or "").strip()[:200]


def _send(to_email: str, subject: str, message: str):
    """Send one email via Resend. Fails silently (logs, doesn't crash the
    request) so a flaky email provider never breaks a booking."""
    if not to_email:
        return
    if not settings.RESEND_API_KEY:
        print(f"[notifications] RESEND_API_KEY not set — skipping email to {to_email}")
        return
    try:
        resend.Emails.send({
            "from": settings.RESEND_FROM_EMAIL,
            "to": [to_email],
            "subject": _clean_for_subject(subject),
            "text": message,
        })
    except Exception as e:
        # Don't let an email failure break the booking flow.
        print(f"[notifications] Failed to send email to {to_email}: {e}")


def _format_when(appointment: Appointment) -> str:
    return (
        f"{appointment.start_time.strftime('%A, %d %B %Y, %I:%M %p')} "
        f"- {appointment.end_time.strftime('%I:%M %p')}"
    )


# ---------------------------------------------------------------------------
# New booking
# ---------------------------------------------------------------------------

def notify_new_booking(appointment: Appointment):
    stylist = appointment.hairstylist

    _send(
        stylist.email,
        f"New booking: {appointment.client_name} on {appointment.start_time.strftime('%a %d %b, %I:%M %p')}",
        f"Hi {stylist.name},\n\n"
        f"You have a new booking.\n\n"
        f"Client: {appointment.client_name}\n"
        f"Phone: {appointment.client_phone}\n"
        f"Service: {appointment.service.name if appointment.service else 'Not specified'}\n"
        f"When: {_format_when(appointment)}\n"
        f"Notes: {appointment.notes or '-'}\n\n"
        f"— Booking Platform",
    )

    _send(
        appointment.client_email,
        f"Booking confirmed with {stylist.name}",
        f"Hi {appointment.client_name},\n\n"
        f"Your appointment is confirmed.\n\n"
        f"Stylist: {stylist.name}\n"
        f"Service: {appointment.service.name if appointment.service else 'Not specified'}\n"
        f"When: {_format_when(appointment)}\n\n"
        f"Add it to your calendar so you don't forget:\n"
        f"{google_calendar_link(appointment)}\n\n"
        f"We'll let you know as soon as your stylist is ready for you.\n\n"
        f"— Booking Platform",
    )


# ---------------------------------------------------------------------------
# Stylist marks "ready" — this is the one that answers "will the client know
# the stylist is ready?"
# ---------------------------------------------------------------------------

def notify_stylist_ready(appointment: Appointment):
    stylist = appointment.hairstylist

    _send(
        appointment.client_email,
        f"{stylist.name} is ready for you!",
        f"Hi {appointment.client_name},\n\n"
        f"{stylist.name} is ready for your appointment now.\n\n"
        f"Service: {appointment.service.name if appointment.service else 'Not specified'}\n"
        f"Scheduled time: {_format_when(appointment)}\n\n"
        f"— Booking Platform",
    )


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------

def notify_cancellation(appointment: Appointment):
    stylist = appointment.hairstylist

    _send(
        stylist.email,
        f"Booking cancelled: {appointment.client_name} on {appointment.start_time.strftime('%a %d %b, %I:%M %p')}",
        f"Hi {stylist.name},\n\n"
        f"The following booking has been cancelled:\n\n"
        f"Client: {appointment.client_name}\n"
        f"Was scheduled for: {_format_when(appointment)}\n\n"
        f"— Booking Platform",
    )

    _send(
        appointment.client_email,
        f"Your appointment with {stylist.name} was cancelled",
        f"Hi {appointment.client_name},\n\n"
        f"Your appointment scheduled for {_format_when(appointment)} with {stylist.name} "
        f"has been cancelled.\n\n"
        f"— Booking Platform",
    )


# ---------------------------------------------------------------------------
# Reschedule
# ---------------------------------------------------------------------------

def notify_reschedule(appointment: Appointment, old_start_time):
    stylist = appointment.hairstylist
    old_str = old_start_time.strftime("%A, %d %B %Y, %I:%M %p")

    _send(
        stylist.email,
        f"Booking rescheduled: {appointment.client_name}",
        f"Hi {stylist.name},\n\n"
        f"A booking has been rescheduled.\n\n"
        f"Client: {appointment.client_name}\n"
        f"Phone: {appointment.client_phone}\n"
        f"Old time: {old_str}\n"
        f"New time: {_format_when(appointment)}\n\n"
        f"— Booking Platform",
    )

    _send(
        appointment.client_email,
        f"Your appointment with {stylist.name} was rescheduled",
        f"Hi {appointment.client_name},\n\n"
        f"Your appointment has been rescheduled.\n\n"
        f"Old time: {old_str}\n"
        f"New time: {_format_when(appointment)}\n\n"
        f"Updated calendar link:\n"
        f"{google_calendar_link(appointment)}\n\n"
        f"— Booking Platform",
    )
