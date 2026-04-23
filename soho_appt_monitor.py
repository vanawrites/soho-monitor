"""
SOHO New York (LA) — Appointment Monitor
Checks for open Design Haircut slots and emails when one opens.
"""

import requests
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# ─── CONFIG ──────────────────────────────────────────────────────────────────

YOUR_EMAIL         = "vanaldabney@gmail.com"
GMAIL_APP_PASSWORD = "edei lkha avzb jzta"
NOTIFY_EMAIL       = "vanaldabney@gmail.com"

CHECK_INTERVAL_MINUTES = 3

START_DATE = "2026-06-01"
END_DATE   = "2026-07-31"

LOCATION_SLUG = "SOHONEWYORKLosAngeles"
LOCATION_ID   = "52592"
SERVICE_ID    = "4431107"
PROVIDER_ID   = "1420277"
SERVICE_NAME  = "Design Haircut"

# ─── AUTH ─────────────────────────────────────────────────────────────────────

TOKEN_URL = "https://signin.booker.com/auth/connect/token"
CLIENT_ID = "jc6lsrW3R5UD"

def get_auth_token():
    """
    Fetch an anonymous Bearer token from Booker's OAuth endpoint.
    Tokens last ~7 hours. Script auto-refreshes when expired.
    """
    try:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type":  "client_credentials",
                "client_id":   CLIENT_ID,
                "scope":       "customer",
            },
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin":       "https://go.booker.com",
                "Referer":      f"https://go.booker.com/location/{LOCATION_SLUG}/",
                "User-Agent":   "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            data = resp.json()
            token = data.get("access_token")
            if token:
                expires_in = data.get("expires_in", "unknown")
                print(f"  🔑 Auth token obtained (expires in {expires_in}s).")
                return token
            print(f"  ⚠️  No access_token in response: {list(data.keys())}")
        else:
            print(f"  ⚠️  Auth returned {resp.status_code}: {resp.text[:300]}")
        return None
    except Exception as e:
        print(f"  ⚠️  Auth error: {e}")
        return None


# ─── BOOKER API ───────────────────────────────────────────────────────────────

AVAIL_URL = "https://api.booker.com/cf2/v5/availability/availability"

def get_available_slots(date_str, token):
    """Query Booker's availability API for a single date."""
    tz_offset = "-07:00"
    from_dt = f"{date_str}T00:00:00{tz_offset}"
    to_dt   = f"{date_str}T23:59:00{tz_offset}"

    params = {
        "IncludeEmployees": "true",
        "fromDateTime":     from_dt,
        "locationIds[]":    LOCATION_ID,
        "serviceId":        SERVICE_ID,
        "toDateTime":       to_dt,
    }

    headers = {
        "Accept":          "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US",
        "Authorization":   f"Bearer {token}",
        "Origin":          "https://go.booker.com",
        "Referer":         f"https://go.booker.com/location/{LOCATION_SLUG}/",
        "User-Agent":      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    }

    try:
        resp = requests.get(AVAIL_URL, params=params, headers=headers, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                slots = data
            else:
                slots = (
                    data.get("Availabilities") or
                    data.get("availabilities") or
                    data.get("TimeSlots") or
                    data.get("slots") or
                    []
                )
            if slots:
                filtered = []
                for s in slots:
                    employees = (
                        s.get("Employees") or
                        s.get("employees") or
                        s.get("AvailableEmployees") or
                        []
                    )
                    emp_ids = [
                        str(e.get("Id") or e.get("id") or e.get("EmployeeId") or "")
                        for e in employees
                    ]
                    if not employees or PROVIDER_ID in emp_ids:
                        filtered.append(s)
                return filtered
            return []

        elif resp.status_code == 401:
            print(f"  🔒 Token expired on {date_str} — will refresh.")
            return None

        else:
            print(f"  [{date_str}] Status {resp.status_code}: {resp.text[:100]}")
            return []

    except requests.RequestException as e:
        print(f"  [{date_str}] Request error: {e}")
        return []


def check_all_dates(token):
    found = {}
    start = datetime.strptime(START_DATE, "%Y-%m-%d")
    end   = datetime.strptime(END_DATE,   "%Y-%m-%d")
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        result = get_available_slots(date_str, token)
        if result is None:
            return found, True
        if result:
            found[date_str] = result
            print(f"  ✅ Slots found on {date_str}!")
        current += timedelta(days=1)
        time.sleep(0.4)
    return found, False


# ─── EMAIL ────────────────────────────────────────────────────────────────────

def send_email(subject, body_html, body_text):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = YOUR_EMAIL
    msg["To"]      = NOTIFY_EMAIL
    msg.attach(MIMEText(body_text, "plain"))
    msg.attach(MIMEText(body_html, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(YOUR_EMAIL, GMAIL_APP_PASSWORD)
        server.sendmail(YOUR_EMAIL, NOTIFY_EMAIL, msg.as_string())
    print(f"  ✉️  Email sent to {NOTIFY_EMAIL}")


def format_slot(slot):
    for key in ("StartDateTime", "start_time", "startTime", "Time", "time", "DateTime"):
        val = slot.get(key)
        if val:
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.strftime("%-I:%M %p")
            except Exception:
                return str(val)
    return "(time unavailable)"


def notify(new_slots):
    lines_text = []
    lines_html = []
    for date_str, slots in sorted(new_slots.items()):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_label = dt.strftime("%A, %B %-d")
        times = ", ".join(format_slot(s) for s in slots)
        lines_text.append(f"  {day_label}: {times}")
        lines_html.append(f"<li><strong>{day_label}</strong> — {times}</li>")

    first_date = sorted(new_slots.keys())[0]
    booking_url = (
        f"https://go.booker.com/location/{LOCATION_SLUG}"
        f"/service/{SERVICE_ID}/{SERVICE_NAME.replace(' ', '%20')}"
        f"/availability/{first_date}"
        f"/provider/{PROVIDER_ID}"
    )
    subject = f"🟢 Appt open at SOHO New York ({len(new_slots)} date{'s' if len(new_slots) > 1 else ''})"
    body_text = (
        f"New {SERVICE_NAME} slots just opened at SOHO New York (LA):\n\n"
        + "\n".join(lines_text)
        + f"\n\nBook now: {booking_url}"
    )
    body_html = f"""
    <div style="font-family:sans-serif;max-width:480px;">
      <h2 style="color:#1a7a4a;">Appointment slots just opened!</h2>
      <p><strong>SOHO New York – Los Angeles</strong><br>{SERVICE_NAME}</p>
      <ul>{"".join(lines_html)}</ul>
      <p>
        <a href="{booking_url}"
           style="background:#1a7a4a;color:white;padding:10px 20px;border-radius:6px;
                  text-decoration:none;display:inline-block;margin-top:8px;">
          Book now →
        </a>
      </p>
      <p style="color:#999;font-size:12px;">Slots fill fast — book directly on the site.</p>
    </div>
    """
    send_email(subject, body_html, body_text)


# ─── MAIN LOOP ────────────────────────────────────────────────────────────────

def run():
    print(f"""
╔════════════════════════════════════════════╗
║   SOHO New York (LA) — Appt Monitor        ║
║   Service  : {SERVICE_NAME:<30}║
║   Watching : {START_DATE} → {END_DATE}   ║
║   Interval : every {CHECK_INTERVAL_MINUTES} min                    ║
║   Notify   : {NOTIFY_EMAIL:<30}║
╚════════════════════════════════════════════╝
    """)

    already_notified = set()
    token = None
    token_obtained_at = None
    TOKEN_LIFETIME_SECONDS = 6 * 3600  # refresh every 6 hrs (tokens last ~7)

    while True:
        # Refresh token if missing or nearing expiry
        now_ts = time.time()
        if not token or (token_obtained_at and now_ts - token_obtained_at > TOKEN_LIFETIME_SECONDS):
            token = get_auth_token()
            token_obtained_at = now_ts
            if not token:
                print(f"  ⚠️  Could not get auth token. Retrying in {CHECK_INTERVAL_MINUTES} min.")
                time.sleep(CHECK_INTERVAL_MINUTES * 60)
                continue

        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] Checking availability...")

        available, token_expired = check_all_dates(token)

        if token_expired:
            print("  🔄 Refreshing auth token...")
            token = None
            continue

        new_findings = {
            date: slots
            for date, slots in available.items()
            if date not in already_notified
        }

        if new_findings:
            print(f"  ✅ New slots on: {list(new_findings.keys())}")
            try:
                notify(new_findings)
                already_notified.update(new_findings.keys())
            except Exception as e:
                print(f"  ⚠️  Email failed: {e}")
        else:
            print(f"  ❌ No new slots. Next check in {CHECK_INTERVAL_MINUTES} min.")

        taken_back = already_notified - set(available.keys())
        if taken_back:
            print(f"  ↩️  {taken_back} no longer available — will re-notify if they reopen.")
            already_notified -= taken_back

        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
