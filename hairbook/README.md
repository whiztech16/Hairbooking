# Hairdressing Booking Platform — Backend

Django + DRF backend. No auth — clients book by name/phone, no login required.

## Setup

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # then fill in real values, see Security section below
python manage.py migrate
python manage.py createsuperuser   # use a genuinely strong password — this login sees all client data
python manage.py runserver
```

Then go to `http://127.0.0.1:8000/admin/`, log in with the superuser you just made, and add:
1. A **Hairstylist** (with email — this is where booking notifications go) + their **Working Hours** (inline on the same page)
2. A few **Services** (name + default duration in minutes)

### Database (Neon Postgres)

The project uses SQLite locally by default (zero setup, just works) but is wired to switch to **Neon Postgres** automatically the moment you set a `DATABASE_URL` — same Django ORM either way, only the connection changes.

1. Create a project at [neon.tech](https://neon.tech) (free tier)
2. In the Neon dashboard, copy your connection string — looks like:
   ```
   postgresql://user:password@ep-xxxx.region.aws.neon.tech/dbname?sslmode=require
   ```
3. Paste it into `.env` as `DATABASE_URL`
4. Run migrations against it:
   ```bash
   python manage.py migrate
   ```
   This creates all the tables in Neon instead of SQLite. Existing local SQLite data does NOT auto-transfer — this only matters if you already have test data in SQLite you want to keep; otherwise just re-add your hairstylists via `/admin/` after switching.

Leave `DATABASE_URL` blank to keep using local SQLite (e.g. for quick local testing) — the app falls back automatically, no code changes needed either way.

### Email setup (Resend)

Emails are sent via [Resend](https://resend.com) — a plain HTTPS API, so it works fine on Render and similar platforms (no SMTP port issues).

1. Sign up free at resend.com (no card needed)
2. Grab your API key from the dashboard
3. Set it as an environment variable before running the server:
   ```bash
   export RESEND_API_KEY=re_your_key_here      # Mac/Linux
   set RESEND_API_KEY=re_your_key_here          # Windows cmd
   ```
   On Render: add `RESEND_API_KEY` under your service's Environment tab.

**Sandbox limitation:** until you verify your own domain in the Resend dashboard, the default sender (`onboarding@resend.dev`) can only deliver to the email address you signed up to Resend with. So for testing, use your own email as the stylist's email and/or the client_email when booking. For a real launch with arbitrary client emails, verify a domain in Resend and set `RESEND_FROM_EMAIL` to an address on it.

If `RESEND_API_KEY` isn't set, the app won't crash — it just logs "skipping email" to the console and the booking still goes through.

## API Endpoints

| Method | URL | Purpose |
|---|---|---|
| GET | `/api/hairstylists/` | Browse stylists |
| GET | `/api/hairstylists/<id>/availability/?date=YYYY-MM-DD&duration_minutes=60` | Free slots for a day |
| GET | `/api/services/` | List services |
| POST | `/api/appointments/book/` | Book an appointment |
| GET | `/api/appointments/?hairstylist_id=1` | List appointments |
| PATCH | `/api/appointments/<id>/mark_ready/` | Stylist marks ready — emails the client |
| PATCH | `/api/appointments/<id>/reschedule/` | Reschedule |
| DELETE | `/api/appointments/<id>/` | Cancel (soft delete, notifies stylist + client) |

### Book an appointment

```
POST /api/appointments/book/
{
  "hairstylist_id": 1,
  "client_name": "Jane Doe",
  "client_phone": "08012345678",
  "client_email": "jane@example.com",
  "start_time": "2026-08-20T10:00:00",
  "service_id": 2,
  "notes": "First time client"
}
```

`client_name`, `client_phone`, and `client_email` are all required — this matches a form that collects the hairstylist's details plus the client's name, email, and phone.

**Duplicate booking prevention:** if the *same client* (matched on name + email + phone, all three) tries to book the *same stylist* for a time that overlaps a booking they already have, it's blocked — this catches double-clicking "book" or resubmitting a form, not a returning client booking again later. A different client can still book that same stylist at that same time (that just becomes a normal availability conflict, same as always).

Success → `201`, appointment created, stylist + client both emailed.

Duplicate → `409`:
```json
{
  "success": false,
  "reason": "duplicate",
  "message": "You already have a booking with this stylist at this time."
}
```

Time conflict (someone else has that slot) → `409` with ranked alternatives:
```json
{
  "success": false,
  "reason": "conflict",
  "message": "That slot isn't available. Here are some alternatives.",
  "alternatives": [
    {"hairstylist_id": 3, "hairstylist_name": "Bimpe", "start_time": "...", "same_stylist": false},
    {"hairstylist_id": 1, "hairstylist_name": "Ada", "start_time": "...", "same_stylist": true}
  ]
}
```

Your frontend can check `reason` to show the right message — "you already booked this" vs. "that time's taken, here are other options."

### Stylist marks "ready"

```
PATCH /api/appointments/5/mark_ready/
```

This is how the client finds out the stylist is ready for them — it flips the appointment status to `ready` and emails the client immediately. No body needed.

## Security

Here's what's actually in place, and — just as important — what isn't, so nothing surprises you post-launch.

**In place:**
- Secret key, debug flag, allowed hosts, CORS origins, and admin URL path all come from environment variables — nothing sensitive is hardcoded or committed (see `.env.example`, `.gitignore`)
- `DEBUG=False` by default; only `True` if you explicitly set it locally
- Production security headers (HTTPS redirect, HSTS, secure cookies, clickjacking protection, MIME-sniffing protection) auto-enable when `DEBUG=False`
- CORS restricted to explicit frontend origins, not "allow everyone"
- Rate limiting: 60 requests/minute per IP on the whole API, since there's no per-user auth to throttle against instead
- Every booking/reschedule request is validated server-side: durations capped at 8 hours, phone numbers restricted to valid characters, names/notes length-capped, no past-dated bookings accepted
- `POST /api/appointments/` and generic `PATCH /api/appointments/<id>/` are blocked (405) — creation and time-changes are only possible through `/book/` and `/reschedule/`, the only two paths that actually run the scheduling algorithm's conflict/buffer/working-hours checks. Without this, anyone could've created double-bookings by hitting the raw CRUD endpoint directly.
- Email subject lines are stripped of newlines/control characters before being sent (defense in depth against header-style injection)
- Django's own `manage.py check --deploy` passes clean under real production env vars

**Not fixable without adding auth (the ceiling I mentioned earlier):**
- Anyone with an appointment ID can view, cancel, or reschedule *that* appointment — there's no proof of identity tying a request to "this is actually that client or that stylist." A determined person could iterate IDs and find real bookings.
- There's no way to prove a `mark_ready` call actually came from the stylist and not someone else who found the appointment ID.

If this platform handles real client PII (names, phone numbers, emails) beyond a hackathon demo, closing that gap means adding *some* identity check — it doesn't have to be a full login system. A lightweight option: generate a random, unguessable token per appointment (e.g. a UUID) and require it in the URL/header for reschedule/cancel/mark_ready, instead of the sequential database ID. That's a same-day addition if you want it before the 18th — just say the word.

**Before deploying, you must:**
1. Generate and set a real `DJANGO_SECRET_KEY` (command in `.env.example`)
2. Set `DJANGO_ALLOWED_HOSTS` to your actual domain
3. Set `CORS_ALLOWED_ORIGINS` to your actual frontend URL
4. Set `RESEND_API_KEY`
5. Optionally set `DJANGO_ADMIN_PATH` to something other than `admin/`
6. Never commit `.env` or `db.sqlite3` (both are gitignored already — don't force-add them)

- `is_slot_available()` — checks working hours + a 15-min buffer against existing bookings
- `find_alternatives_same_stylist()` — scans forward up to 7 days for the requested stylist's next open slots
- `find_alternatives_other_stylists()` — checks all other active stylists for the same/nearby time
- `find_all_alternatives()` — merges both, ranked by closeness to what the client originally asked for
- `book_appointment()` — ties it together: books if free, else returns ranked alternatives

Verified with a smoke test covering: normal booking, conflict detection, buffer enforcement on both sides of an appointment, and cross-stylist fallback.
