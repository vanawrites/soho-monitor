"""
SOHO New York (LA) — Appointment Monitor
Checks for open Design Haircut slots with your stylist and emails you when one opens.

SETUP (one time):
  1. pip install requests
  2. Fill in YOUR_EMAIL, NOTIFY_EMAIL, and GMAIL_APP_PASSWORD below
  3. For Gmail app password: myaccount.google.com > Security > 2-Step Verification > App passwords
  4. Run: python soho_appt_monitor.py
"""

import requests
import smtplib
import time
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta

# ─── CONFIG ──────────────────────────────────────────────────────────────────

YOUR_EMAIL       = "vanaldabney@gmail.com"
GMAIL_APP_PASSWORD = "edei lkha avzb jzta"
NOTIFY_EMAIL     = "vanaldabney@gmail.com"

CHECK_INTERVAL_MINUTES = 3

# Date range to monitor
START_DATE = "2026-05-01"
END_DATE   = "2026-08-31"

# Booker IDs from your URL — no need to change these
LOCATION_ID  = "SOHONEWYORKLosAngeles"
SERVICE_ID   = "4431107"
PROVIDER_ID  = "1420277"
SERVICE_NAME = "Design Haircut"

# ─── BOOKER API ───────────────────────────────────────────────────────────────

BASE_URL = "https://go.booker.com/api"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://go.booker.com",
    "Referer": f"https://go.booker.com/location/{LOCATION_ID}/",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

def get_available_slots(date_str):
    """
    Query Booker's availability endpoint for a specific date.
    Returns list of available time slots, or empty list if none.
    """
    # Booker's internal availability endpoint
    url = f"{BASE_URL}/availability/timeslots"
    params = {
        "locationId": LOCATION_ID,
        "serviceId": SERVICE_ID,
        "employeeId": PROVIDER_ID,
        "date": date_str,
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=15)
        
        if resp.status_code == 200:
            data = resp.json()
            # Booker returns slots under various keys depending on version
            slots = (
                data.get("TimeSlots") or
                data.get("timeslots") or
                data.get("slots") or
                data.get("availabilities") or
                []
            )
            return [s for s in slots if s]  # filter out empty/null entries
        
        elif resp.status_code == 404:
            return []  # No slots for this date — normal
        
        else:
            print(f"  [{date_str}] Unexpected status {resp.status_code}")
            return []

    except requests.RequestException as e:
        print(f"  [{date_str}] Request error: {e}")
        return []


def check_all_dates():
    """Check every date in the configured range. Returns dict of date -> slots."""
    found = {}
    start = datetime.strptime(START_DATE, "%Y-%m-%d")
    end   = datetime.strptime(END_DATE,   "%Y-%m-%d")
    delta = timedelta(days=1)
    
    current = start
    while current <= end:
        date_str = current.strftime("%Y-%m-%d")
        slots = get_available_slots(date_str)
        if slots:
            found[date_str] = slots
        current += delta
        time.sleep(0.3)  # be gentle — small pause between date requests
    
    return found


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
    """Extract a readable time string from a Booker slot object."""
    # Booker uses different field names across versions — try them all
    for key in ("StartDateTime", "start_time", "startTime", "Time", "time"):
        val = slot.get(key)
        if val:
            # Try to parse ISO datetime
            try:
                dt = datetime.fromisoformat(val.replace("Z", "+00:00"))
                return dt.strftime("%-I:%M %p")
            except Exception:
                return str(val)
    return json.dumps(slot)  # fallback: show raw


def notify(new_slots):
    """Send an email listing all newly-found slots."""
    lines_text = []
    lines_html = []

    for date_str, slots in sorted(new_slots.items()):
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        day_label = dt.strftime("%A, %B %-d")
        times = ", ".join(format_slot(s) for s in slots)
        
        lines_text.append(f"  {day_label}: {times}")
        lines_html.append(f"<li><strong>{day_label}</strong> — {times}</li>")

    booking_url = (
        f"https://go.booker.com/location/{LOCATION_ID}"
        f"/service/{SERVICE_ID}/{SERVICE_NAME.replace(' ', '%20')}"
        f"/availability/{sorted(new_slots.keys())[0]}"
        f"/provider/{PROVIDER_ID}"
    )

    subject = f"🟢 Appt available at SOHO New York ({len(new_slots)} date{'s' if len(new_slots) > 1 else ''})"

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
           style="background:#1a7a4a;color:white;padding:10px 20px;border-radius:6px;text-decoration:none;display:inline-block;margin-top:8px;">
          Book now →
        </a>
      </p>
      <p style="color:#999;font-size:12px;">Sent by your appointment monitor. 
         Slots fill fast — check availability directly on the site.</p>
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

    # Track which dates have already triggered a notification
    # so we don't spam you every check cycle
    already_notified = set()

    while True:
        now = datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] Checking availability...")

        available = check_all_dates()
        
        # Filter out dates we've already notified about
        new_findings = {
            date: slots
            for date, slots in available.items()
            if date not in already_notified
        }

        if new_findings:
            print(f"  ✅ Found slots on {len(new_findings)} date(s): {list(new_findings.keys())}")
            try:
                notify(new_findings)
                already_notified.update(new_findings.keys())
            except Exception as e:
                print(f"  ⚠️  Email failed: {e}")
                print("     Check YOUR_EMAIL and GMAIL_APP_PASSWORD in the config.")
        else:
            print(f"  ❌ No new slots found. Next check in {CHECK_INTERVAL_MINUTES} min.")

        # If a previously-notified date disappears (slot got taken), 
        # remove it from the set so we notify again if it re-opens
        taken_back = already_notified - set(available.keys())
        if taken_back:
            print(f"  ↩️  Slots on {taken_back} appear to be gone — will re-notify if they return.")
            already_notified -= taken_back

        time.sleep(CHECK_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
