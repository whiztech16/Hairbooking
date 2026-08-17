"""
Core scheduling algorithm for the hairdressing booking platform.

Responsibilities:
1. Check whether a given hairstylist is free for a requested time window
   (respecting working hours + a buffer around existing appointments).
2. When they are NOT free, find the closest alternative slots for that
   same stylist.
3. Also find other stylists who ARE free at (or near) the requested time,
   so the client has a "same time, different stylist" option too.
4. Rank all alternatives together by how close they are to what was
   originally requested, and hand back a single, useful list.

No external dependencies beyond Django's ORM and the standard library.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, time as dtime
from typing import Optional

from django.utils import timezone

from .models import Hairstylist, Appointment

# Buffer enforced between back-to-back appointments for the same stylist.
BUFFER_MINUTES = 15

# How finely we step through the day when scanning for open slots.
SLOT_STEP_MINUTES = 15


@dataclass
class SlotSuggestion:
    hairstylist: Hairstylist
    start_time: datetime
    end_time: datetime
    same_stylist: bool  # True = same stylist requested, different time
                         # False = different stylist, at/near the same time

    def as_dict(self):
        return {
            "hairstylist_id": self.hairstylist.id,
            "hairstylist_name": self.hairstylist.name,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "same_stylist": self.same_stylist,
        }


def _working_windows_for_date(hairstylist: Hairstylist, date):
    """Return list of (start_datetime, end_datetime) working windows
    for this stylist on the given date, built from WorkingHours rows."""
    weekday = date.weekday()
    windows = []
    for wh in hairstylist.working_hours.filter(weekday=weekday):
        start_dt = timezone.make_aware(datetime.combine(date, wh.start_time))
        end_dt = timezone.make_aware(datetime.combine(date, wh.end_time))
        windows.append((start_dt, end_dt))
    return windows


def _existing_appointments(hairstylist: Hairstylist, day_start, day_end):
    return Appointment.objects.filter(
        hairstylist=hairstylist,
        status="confirmed",
        start_time__lt=day_end,
        end_time__gt=day_start,
    ).order_by("start_time")


def is_slot_available(
    hairstylist: Hairstylist,
    start_time: datetime,
    duration_minutes: int,
    buffer_minutes: int = BUFFER_MINUTES,
    ignore_appointment_id: Optional[int] = None,
) -> bool:
    """
    Check whether `hairstylist` is free for a booking of `duration_minutes`
    starting at `start_time`, respecting working hours and a buffer
    around neighboring appointments.
    """
    end_time = start_time + timedelta(minutes=duration_minutes)

    # 1. Must fall entirely within a working window that day.
    windows = _working_windows_for_date(hairstylist, start_time.date())
    within_hours = any(w_start <= start_time and end_time <= w_end for w_start, w_end in windows)
    if not within_hours:
        return False

    # 2. Must not overlap (including buffer) with any existing appointment.
    buffered_start = start_time - timedelta(minutes=buffer_minutes)
    buffered_end = end_time + timedelta(minutes=buffer_minutes)

    qs = Appointment.objects.filter(
        hairstylist=hairstylist,
        status="confirmed",
        start_time__lt=buffered_end,
        end_time__gt=buffered_start,
    )
    if ignore_appointment_id:
        qs = qs.exclude(id=ignore_appointment_id)

    return not qs.exists()


def _free_slots_for_day(hairstylist: Hairstylist, date, duration_minutes: int, buffer_minutes: int):
    """Scan a single day and return all valid start datetimes where a
    booking of `duration_minutes` would fit, stepping every SLOT_STEP_MINUTES."""
    windows = _working_windows_for_date(hairstylist, date)
    if not windows:
        return []

    day_start = min(w[0] for w in windows)
    day_end = max(w[1] for w in windows)
    existing = list(_existing_appointments(hairstylist, day_start, day_end))

    free = []
    for w_start, w_end in windows:
        cursor = w_start
        while cursor + timedelta(minutes=duration_minutes) <= w_end:
            candidate_end = cursor + timedelta(minutes=duration_minutes)
            buffered_start = cursor - timedelta(minutes=buffer_minutes)
            buffered_end = candidate_end + timedelta(minutes=buffer_minutes)

            conflict = any(
                appt.start_time < buffered_end and appt.end_time > buffered_start
                for appt in existing
            )
            if not conflict:
                free.append(cursor)

            cursor += timedelta(minutes=SLOT_STEP_MINUTES)

    return free


def find_alternatives_same_stylist(
    hairstylist: Hairstylist,
    requested_start: datetime,
    duration_minutes: int,
    days_ahead: int = 7,
    max_results: int = 5,
    buffer_minutes: int = BUFFER_MINUTES,
) -> list[SlotSuggestion]:
    """Find the closest available slots for the SAME stylist, searching
    forward from the requested date up to `days_ahead` days."""
    candidates = []
    for day_offset in range(0, days_ahead + 1):
        date = requested_start.date() + timedelta(days=day_offset)
        for slot_start in _free_slots_for_day(hairstylist, date, duration_minutes, buffer_minutes):
            candidates.append(slot_start)

    # Rank by absolute distance from the originally requested time.
    candidates.sort(key=lambda dt: abs((dt - requested_start).total_seconds()))

    results = []
    for start in candidates[:max_results]:
        results.append(
            SlotSuggestion(
                hairstylist=hairstylist,
                start_time=start,
                end_time=start + timedelta(minutes=duration_minutes),
                same_stylist=True,
            )
        )
    return results


def find_alternatives_other_stylists(
    requested_start: datetime,
    duration_minutes: int,
    exclude_hairstylist_id: int,
    days_ahead: int = 3,
    max_results: int = 5,
    buffer_minutes: int = BUFFER_MINUTES,
) -> list[SlotSuggestion]:
    """Find other active stylists free at or near the requested time."""
    results = []
    other_stylists = Hairstylist.objects.filter(is_active=True).exclude(id=exclude_hairstylist_id)

    for stylist in other_stylists:
        # First choice: exact requested time.
        if is_slot_available(stylist, requested_start, duration_minutes, buffer_minutes):
            results.append(
                SlotSuggestion(
                    hairstylist=stylist,
                    start_time=requested_start,
                    end_time=requested_start + timedelta(minutes=duration_minutes),
                    same_stylist=False,
                )
            )
            continue

        # Otherwise, find their closest slot within a short window.
        alt = find_alternatives_same_stylist(
            stylist, requested_start, duration_minutes,
            days_ahead=days_ahead, max_results=1, buffer_minutes=buffer_minutes,
        )
        if alt:
            suggestion = alt[0]
            suggestion.same_stylist = False
            results.append(suggestion)

    results.sort(key=lambda s: abs((s.start_time - requested_start).total_seconds()))
    return results[:max_results]


def find_all_alternatives(
    hairstylist: Hairstylist,
    requested_start: datetime,
    duration_minutes: int,
    max_results: int = 6,
) -> list[dict]:
    """Combined, ranked alternatives: same stylist other times + other
    stylists at/near the same time. Used when a booking request fails."""
    same = find_alternatives_same_stylist(hairstylist, requested_start, duration_minutes)
    other = find_alternatives_other_stylists(
        requested_start, duration_minutes, exclude_hairstylist_id=hairstylist.id
    )

    combined = same + other
    combined.sort(key=lambda s: abs((s.start_time - requested_start).total_seconds()))

    return [s.as_dict() for s in combined[:max_results]]


def has_duplicate_booking(
    hairstylist: Hairstylist,
    client_name: str,
    client_email: str,
    client_phone: str,
    start_time: datetime,
    duration_minutes: int,
) -> bool:
    """
    Check whether this exact client (matched by name + email + phone,
    all three together) already has a CONFIRMED or READY booking with
    this stylist that overlaps the requested time window.

    This exists to stop accidental duplicate submissions (double-clicking
    "book", resubmitting a form, etc.) — not to stop a returning client
    from booking the same stylist again for a different time.
    """
    end_time = start_time + timedelta(minutes=duration_minutes)

    return Appointment.objects.filter(
        hairstylist=hairstylist,
        client_name__iexact=client_name.strip(),
        client_email__iexact=client_email.strip(),
        client_phone=client_phone.strip(),
        status__in=["confirmed", "ready"],
        start_time__lt=end_time,
        end_time__gt=start_time,
    ).exists()


def book_appointment(
    hairstylist: Hairstylist,
    client_name: str,
    client_phone: str,
    start_time: datetime,
    duration_minutes: int,
    service=None,
    notes: str = "",
    client_email: str = "",
) -> dict:
    """
    Attempt to book an appointment.

    Returns a dict:
      {"success": True, "appointment": <Appointment>}
    or
      {"success": False, "reason": "duplicate", "message": "..."}
    or
      {"success": False, "reason": "conflict", "alternatives": [...]}
    """
    if has_duplicate_booking(
        hairstylist, client_name, client_email, client_phone, start_time, duration_minutes
    ):
        return {
            "success": False,
            "reason": "duplicate",
            "message": "You already have a booking with this stylist at this time.",
        }

    if is_slot_available(hairstylist, start_time, duration_minutes):
        appointment = Appointment.objects.create(
            hairstylist=hairstylist,
            service=service,
            client_name=client_name,
            client_phone=client_phone,
            client_email=client_email,
            start_time=start_time,
            end_time=start_time + timedelta(minutes=duration_minutes),
            notes=notes,
        )
        return {"success": True, "appointment": appointment}

    alternatives = find_all_alternatives(hairstylist, start_time, duration_minutes)
    return {"success": False, "reason": "conflict", "alternatives": alternatives}
