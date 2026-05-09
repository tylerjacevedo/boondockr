"""
Boondockr v1.3
Campsite Cancellation Notifier
Email alerts via Gmail SMTP

New in v1.3:
- Alert once per site forever (stored in alerted_sites.json)
- No repeat alerts unless site was booked and reopened
- Removed star emojis from emails
- Manual re-poll: python3 boondockr.py --check
  Forces a fresh check of ALL sites including previously alerted ones
"""

import os
import sys
import json
import time
import random
import logging
import smtplib
import requests
import schedule
import yaml
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from tenacity import retry, stop_after_attempt, wait_exponential, wait_random, retry_if_exception_type

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("boondockr")

RECREATION_GOV_API = "https://www.recreation.gov/api/camps/availability/campground"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.recreation.gov/",
    "Origin": "https://www.recreation.gov",
    "Connection": "keep-alive",
}

POLL_MIN_SECONDS = 120
POLL_MAX_SECONDS = 180
MASS_RELEASE_THRESHOLD = 10
DOWNTIME_ALERT_MINUTES = 15
MONTHLY_RELEASE_DAY = 15
ALERTED_SITES_FILE = "alerted_sites.json"

# ─── Config ────────────────────────────────────────────────────────────────────

def load_config(path="config.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)

# ─── Persistent Alert Storage ──────────────────────────────────────────────────

def load_alerted_sites():
    """Load previously alerted sites from disk."""
    if os.path.exists(ALERTED_SITES_FILE):
        with open(ALERTED_SITES_FILE, "r") as f:
            return set(json.load(f))
    return set()

def save_alerted_sites(alerted):
    """Save alerted sites to disk so they persist across restarts."""
    with open(ALERTED_SITES_FILE, "w") as f:
        json.dump(list(alerted), f)

def clear_alerted_sites():
    """Clear all alerted sites — used for manual re-poll."""
    if os.path.exists(ALERTED_SITES_FILE):
        os.remove(ALERTED_SITES_FILE)
    log.info("Alerted sites cleared — all sites will be re-checked")

# ─── Email ─────────────────────────────────────────────────────────────────────

def send_email(to_email, subject, html_body):
    try:
        gmail = os.getenv("GMAIL_ADDRESS")
        pwd = os.getenv("GMAIL_APP_PASSWORD")
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = gmail
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))
        server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
        server.starttls()
        server.login(gmail, pwd)
        server.sendmail(gmail, to_email, msg.as_string())
        server.quit()
        log.info(f"Email sent to {to_email}")
    except Exception as e:
        log.error(f"Email failed to {to_email}: {e}")

def notify_user(user, subject, html):
    if user.get("email"):
        send_email(user["email"], subject, html)

def notify_all(users, subject, html):
    for user in users:
        notify_user(user, subject, html)

# ─── Date Grouping ─────────────────────────────────────────────────────────────

def group_consecutive_dates(dates):
    if not dates:
        return []
    sorted_dates = sorted(dates)
    ranges = []
    start = end = sorted_dates[0]
    for d in sorted_dates[1:]:
        if d == end + timedelta(days=1):
            end = d
        else:
            ranges.append(start.strftime("%b %d") if start == end else f"{start.strftime('%b %d')}-{end.strftime('%b %d')}")
            start = end = d
    ranges.append(start.strftime("%b %d") if start == end else f"{start.strftime('%b %d')}-{end.strftime('%b %d')}")
    return ranges

# ─── Email Template ────────────────────────────────────────────────────────────

def build_alert_email(campground_alerts, is_manual=False):
    manual_banner = ""
    if is_manual:
        manual_banner = """
        <div style="background:#f39c12;padding:10px 20px;text-align:center;">
            <p style="margin:0;color:white;font-size:13px;font-weight:bold;">Manual Check — Sites previously alerted included</p>
        </div>"""

    sections_html = ""
    for alert in campground_alerts:
        name = alert["name"]
        booking_url = alert["booking_url"]
        sites_html = ""
        for site in alert["sites"]:
            date_ranges = ", ".join(site["date_ranges"])
            sites_html += f"""
            <tr>
                <td style="padding:10px 12px;border-bottom:1px solid #d4e6d0;font-weight:bold;color:#1a3a2a;">Site #{site['site_name']}</td>
                <td style="padding:10px 12px;border-bottom:1px solid #d4e6d0;color:#2d5a3d;">{date_ranges}</td>
                <td style="padding:10px 12px;border-bottom:1px solid #d4e6d0;">
                    <a href="{booking_url}" style="background:#2d6a4f;color:white;padding:8px 16px;text-decoration:none;border-radius:20px;font-size:13px;white-space:nowrap;">Book Now</a>
                </td>
            </tr>"""

        sections_html += f"""
        <div style="margin-bottom:28px;">
            <h2 style="color:#1a3a2a;margin:0 0 10px 0;font-size:18px;">📍 {name}</h2>
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;background:rgba(255,255,255,0.9);border-radius:10px;overflow:hidden;border:1px solid #b7d9c0;">
                <thead>
                    <tr style="background:#2d6a4f;">
                        <th style="padding:10px 12px;text-align:left;color:white;font-size:13px;">Site</th>
                        <th style="padding:10px 12px;text-align:left;color:white;font-size:13px;">Available Dates</th>
                        <th style="padding:10px 12px;text-align:left;color:white;font-size:13px;">Action</th>
                    </tr>
                </thead>
                <tbody>{sites_html}</tbody>
            </table>
        </div>"""

    return f"""<!DOCTYPE html><html><body style="margin:0;padding:0;font-family:Georgia,serif;background:#1a3a2a;">
    <div style="padding:32px 16px;">
    <div style="text-align:center;font-size:24px;letter-spacing:6px;margin-bottom:8px;">🌲🌲🌲🌲🌲</div>
    <div style="max-width:620px;margin:0 auto;background:rgba(255,255,255,0.94);border-radius:20px;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,0.4);">
        <div style="background:linear-gradient(135deg,#2d6a4f,#1a4a2e);padding:28px;text-align:center;">
            <div style="font-size:40px;">🏕️</div>
            <h1 style="margin:8px 0 0;color:white;font-size:24px;">Boondockr Alert</h1>
            <p style="margin:6px 0 0;color:#a8d5b5;font-size:13px;">Campsite cancellation detected — act fast!</p>
        </div>
        {manual_banner}
        <div style="padding:24px 28px;">
            <p style="color:#2d5a3d;font-size:14px;margin:0 0 20px;">The following campsites are available. Spots go fast — book now before they are gone.</p>
            {sections_html}
            <div style="border-top:2px solid #d4e6d0;margin-top:8px;padding-top:16px;text-align:center;">
                <p style="color:#888;font-size:12px;margin:0;">Boondockr — watching so you don't have to 🏕️<br>
                You will only receive this alert once per site. Run --check to manually re-check all sites.</p>
            </div>
        </div>
    </div>
    <div style="text-align:center;font-size:22px;letter-spacing:6px;margin-top:14px;">🌲🌕🌲</div>
    </div></body></html>"""

# ─── Recreation.gov API ────────────────────────────────────────────────────────

@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    wait=wait_exponential(multiplier=2, min=30, max=300) + wait_random(0, 15),
    stop=stop_after_attempt(4),
    reraise=False,
)
def fetch_availability(campground_id, start_date, end_date):
    url = f"{RECREATION_GOV_API}/{campground_id}/month"
    params = {"start_date": start_date.strftime("%Y-%m-01T00:00:00.000Z")}
    try:
        time.sleep(random.uniform(2, 6))
        resp = requests.get(url, headers=HEADERS, params=params, timeout=15)
        if resp.status_code == 429:
            wait_time = int(resp.headers.get("Retry-After", 300)) + random.uniform(10, 30)
            log.warning(f"Rate limited — waiting {wait_time:.0f}s")
            time.sleep(wait_time)
            raise requests.exceptions.RequestException("429")
        resp.raise_for_status()
        return resp.json().get("campsites", {})
    except requests.exceptions.RequestException as e:
        log.warning(f"Fetch failed for {campground_id}: {e}")
        return {}

def get_available_sites(campground_id, start_date, end_date, target_site=None):
    available = []
    current = start_date.replace(day=1)
    while current <= end_date:
        campsites = fetch_availability(campground_id, current, end_date)
        for site_id, site_data in campsites.items():
            if target_site and str(target_site).lower() not in [str(site_id).lower(), str(site_data.get("site", "")).lower()]:
                continue
            for date_str, status in site_data.get("availabilities", {}).items():
                try:
                    site_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ").date()
                except ValueError:
                    continue
                if start_date <= site_date <= end_date and status == "Available":
                    available.append({
                        "site_id": site_id,
                        "site_name": site_data.get("site", site_id),
                        "date": site_date,
                        "booking_url": f"https://www.recreation.gov/camping/campgrounds/{campground_id}/availability",
                    })
        current = current.replace(month=current.month + 1) if current.month < 12 else current.replace(year=current.year + 1, month=1)
    return available

# ─── Filters ───────────────────────────────────────────────────────────────────

def passes_day_filter(site_date, day_filter):
    weekday = site_date.weekday()
    if day_filter == "weekends":
        return weekday in [4, 5, 6]
    elif day_filter == "weekdays":
        return weekday in [0, 1, 2, 3]
    return True

def passes_blackout(site_date, blackout_dates):
    for blackout in blackout_dates or []:
        try:
            if site_date == datetime.strptime(str(blackout), "%Y-%m-%d").date():
                return False
        except ValueError:
            pass
    return True

# ─── Mass Release ──────────────────────────────────────────────────────────────

class MassReleaseDetector:
    def __init__(self):
        self.previous_counts = {}
    def is_mass_release(self, campground_id, available_count):
        prev = self.previous_counts.get(campground_id, 0)
        self.previous_counts[campground_id] = available_count
        return (available_count - prev) >= MASS_RELEASE_THRESHOLD

mass_detector = MassReleaseDetector()

# ─── Downtime Monitor ─────────────────────────────────────────────────────────

class DowntimeMonitor:
    def __init__(self):
        self.last_success = time.time()
        self.alerted_down = False
    def record_success(self):
        self.last_success = time.time()
        self.alerted_down = False
    def check_downtime(self, users):
        elapsed = (time.time() - self.last_success) / 60
        if elapsed > DOWNTIME_ALERT_MINUTES and not self.alerted_down:
            ts = datetime.now().strftime("%I:%M %p")
            html = f"<div style='font-family:Georgia;padding:32px;background:#1a3a2a;'><div style='background:white;max-width:500px;margin:0 auto;border-radius:16px;padding:28px;text-align:center;'><div style='font-size:40px;'>⚠️</div><h2 style='color:#c0392b;'>Boondockr Offline</h2><p>App offline since <strong>{ts}</strong>. Check your server.</p></div></div>"
            notify_all(users, "⚠️ Boondockr Down Alert", html)
            self.alerted_down = True

downtime_monitor = DowntimeMonitor()

# ─── Core Poll Loop ────────────────────────────────────────────────────────────

def poll_campgrounds(config, alerted_sites, is_manual=False):
    users = config["users"]
    campgrounds = config["campgrounds"]
    log.info(f"Polling {len(campgrounds)} campground(s) {'[MANUAL CHECK]' if is_manual else ''}...")

    all_alerts = []

    for campground in campgrounds:
        cid = str(campground["id"])
        name = campground["name"]
        try:
            start = datetime.strptime(campground["date_start"], "%Y-%m-%d").date()
            end = datetime.strptime(campground["date_end"], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            log.error(f"Invalid dates for {name}")
            continue

        target_site = campground.get("site", None)
        day_filter = campground.get("day_filter", "all")
        blackout_dates = campground.get("blackout_dates", [])
        priority = campground.get("priority", 99)

        time.sleep(random.uniform(8, 20))
        available = get_available_sites(cid, start, end, target_site)

        if mass_detector.is_mass_release(cid, len(available)):
            log.info(f"Mass release at {name}")
            booking_url = f"https://www.recreation.gov/camping/campgrounds/{cid}/availability"
            notify_all(users, f"🏕️ {name} — Monthly Reservations Open!", build_alert_email([{
                "name": f"{name} — Monthly Release",
                "booking_url": booking_url,
                "sites": [{"site_name": "All", "date_ranges": ["New dates just opened — browse now"]}]
            }]))
            continue

        site_dates = {}
        for site in sorted(available, key=lambda x: (priority, x["date"])):
            if not passes_day_filter(site["date"], day_filter):
                continue
            if not passes_blackout(site["date"], blackout_dates):
                continue

            alert_key = f"{cid}:{site['site_id']}:{site['date']}"

            # Skip if already alerted (unless manual check)
            if not is_manual and alert_key in alerted_sites:
                continue

            sid = site["site_id"]
            if sid not in site_dates:
                site_dates[sid] = {"site_name": site["site_name"], "dates": [], "booking_url": site["booking_url"]}
            site_dates[sid]["dates"].append(site["date"])

        if not site_dates:
            continue

        sites_for_email = []
        for sid, data in site_dates.items():
            date_ranges = group_consecutive_dates(data["dates"])
            sites_for_email.append({"site_name": data["site_name"], "date_ranges": date_ranges})

            # Mark as alerted permanently
            for d in data["dates"]:
                alerted_sites.add(f"{cid}:{sid}:{d}")
            log.info(f"Alert queued: {name} | Site #{data['site_name']} | {', '.join(date_ranges)}")

        all_alerts.append({
            "name": name,
            "booking_url": f"https://www.recreation.gov/camping/campgrounds/{cid}/availability",
            "sites": sites_for_email,
        })

    # Save updated alerted sites to disk
    save_alerted_sites(alerted_sites)

    if all_alerts:
        html = build_alert_email(all_alerts, is_manual=is_manual)
        campground_names = ", ".join([a["name"] for a in all_alerts])
        notify_all(users, f"🏕️ Campsite Available — {campground_names}", html)
    elif is_manual:
        log.info("Manual check complete — no new availability found")
        notify_all(users, "🏕️ Boondockr Manual Check — No New Availability",
            "<div style='font-family:Georgia;background:#1a3a2a;padding:32px;'><div style='background:white;max-width:500px;margin:0 auto;border-radius:16px;padding:28px;text-align:center;'><div style='font-size:40px;'>🏕️</div><h2 style='color:#2d6a4f;'>Manual Check Complete</h2><p style='color:#555;'>No new campsite availability found at this time.</p></div></div>")

    downtime_monitor.record_success()
    return alerted_sites

# ─── Monthly Reminders ─────────────────────────────────────────────────────────

def send_monthly_reminder(config, minutes_before):
    parks_str = ", ".join([c["name"] for c in config["campgrounds"]])
    label = "1 hour" if minutes_before == 60 else "15 minutes"
    html = f"""<div style="font-family:Georgia;background:#1a3a2a;padding:32px 16px;">
    <div style="text-align:center;font-size:24px;letter-spacing:6px;margin-bottom:8px;">🌲🌲🌲🌲🌲</div>
    <div style="max-width:560px;margin:0 auto;background:white;border-radius:20px;overflow:hidden;">
        <div style="background:linear-gradient(135deg,#2d6a4f,#1a4a2e);padding:24px;text-align:center;">
            <div style="font-size:36px;">⏰</div>
            <h1 style="margin:8px 0 0;color:white;font-size:20px;">Reservations Open in {label}!</h1>
        </div>
        <div style="padding:24px;text-align:center;">
            <p style="color:#2d5a3d;">Monthly campsites go live soon for: <strong>{parks_str}</strong></p>
            <a href="https://www.recreation.gov" style="display:inline-block;background:#2d6a4f;color:white;padding:12px 28px;text-decoration:none;border-radius:25px;">Go to Recreation.gov</a>
            <p style="color:#888;font-size:12px;margin-top:16px;">Boondockr 🏕️</p>
        </div>
    </div>
    <div style="text-align:center;font-size:20px;letter-spacing:6px;margin-top:12px;">🌲🌕🌲</div>
    </div>"""
    notify_all(config["users"], f"⏰ Reservations Open in {label}!", html)
    log.info(f"Monthly reminder sent ({label})")

def schedule_monthly_reminders(config):
    schedule.every().day.at("06:00").do(lambda: send_monthly_reminder(config, 60) if datetime.now().day == MONTHLY_RELEASE_DAY else None)
    schedule.every().day.at("06:45").do(lambda: send_monthly_reminder(config, 15) if datetime.now().day == MONTHLY_RELEASE_DAY else None)

# ─── Daily Digest ──────────────────────────────────────────────────────────────

def send_daily_digest(config):
    campgrounds = config["campgrounds"]
    users = config["users"]
    today = datetime.now().strftime("%A, %B %d %Y")
    parks_html = "".join([f"<li style='margin:4px 0;color:#2d5a3d;'>{c['name']}</li>" for c in campgrounds])
    alerted_count = len(load_alerted_sites())
    html = f"""<div style="font-family:Georgia;background:#1a3a2a;padding:32px 16px;">
    <div style="text-align:center;font-size:24px;letter-spacing:6px;margin-bottom:8px;">🌲🌲🌲🌲🌲</div>
    <div style="max-width:560px;margin:0 auto;background:white;border-radius:20px;overflow:hidden;">
        <div style="background:linear-gradient(135deg,#2d6a4f,#1a4a2e);padding:24px;text-align:center;">
            <div style="font-size:36px;">🏕️</div>
            <h1 style="margin:8px 0 0;color:white;font-size:20px;">Boondockr Daily Digest</h1>
            <p style="margin:4px 0 0;color:#a8d5b5;font-size:13px;">{today}</p>
        </div>
        <div style="padding:24px;">
            <p style="color:#2d5a3d;">All systems running. Watching <strong>{len(campgrounds)}</strong> campground(s) for <strong>{len(users)}</strong> user(s).</p>
            <p style="color:#2d5a3d;">Sites already alerted (won't repeat): <strong>{alerted_count}</strong></p>
            <h3 style="color:#1a3a2a;">Campgrounds Being Watched:</h3>
            <ul style="padding-left:20px;">{parks_html}</ul>
            <p style="color:#555;font-size:13px;margin-top:16px;">To force a re-check of all sites including previously alerted ones, run:<br>
            <code style="background:#f0f7f2;padding:4px 8px;border-radius:4px;">python3 boondockr.py --check</code></p>
            <p style="color:#888;font-size:12px;border-top:1px solid #d4e6d0;padding-top:14px;margin-top:14px;">Boondockr — watching so you don't have to 🏕️</p>
        </div>
    </div>
    <div style="text-align:center;font-size:20px;letter-spacing:6px;margin-top:12px;">🌲🌕🌲</div>
    </div>"""
    notify_all(users, f"🏕️ Boondockr Daily — {today}", html)
    log.info("Daily digest sent")

# ─── Main ──────────────────────────────────────────────────────────────────────

def main():
    config = load_config("config.yaml")
    alerted_sites = load_alerted_sites()

    # Manual check mode: python3 boondockr.py --check
    if "--check" in sys.argv:
        log.info("🏕️ Manual check mode — re-checking all sites including previously alerted")
        poll_campgrounds(config, alerted_sites, is_manual=True)
        return

    log.info("🏕️  Boondockr v1.3 starting up...")
    log.info(f"Watching {len(config['campgrounds'])} campground(s) for {len(config['users'])} user(s)")
    log.info(f"Polling every {POLL_MIN_SECONDS}-{POLL_MAX_SECONDS}s | Alert once per site forever")
    log.info(f"Previously alerted sites loaded: {len(alerted_sites)}")

    schedule.every().day.at("08:00").do(send_daily_digest, config)
    schedule_monthly_reminders(config)
    schedule.every(5).minutes.do(downtime_monitor.check_downtime, config["users"])

    while True:
        try:
            schedule.run_pending()
            alerted_sites = poll_campgrounds(config, alerted_sites)
        except Exception as e:
            log.error(f"Unexpected error: {e}")
        sleep_time = random.uniform(POLL_MIN_SECONDS, POLL_MAX_SECONDS)
        log.info(f"Next poll in {sleep_time:.0f}s...")
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()
