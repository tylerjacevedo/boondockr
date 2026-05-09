# 🏕️ Boondockr v1.1
### Campsite Cancellation Notifier

Boondockr watches recreation.gov 24/7 and instantly alerts you via email the second a campsite cancellation opens up — before anyone else can grab it.

---

## Features

- ⚡ **2-3 minute polling** with human-like random delays
- 📧 **Email alerts** via Gmail with direct booking link
- 🏕️ **Multiple campgrounds** — watch as many as you want
- 👥 **Multi-user** — one server covers all your friends
- 📅 **Weekday/Weekend filtering**
- 🚫 **Blackout dates**
- 🏆 **Priority ranking**
- 🛡️ **Flood protection** on monthly releases
- ⏰ **Monthly reminders** — 1hr + 15min warning on the 15th
- 📊 **Daily digest** — 8am heartbeat email
- ⚠️ **Downtime alerts**
- 🔄 **Exponential backoff** with jitter on rate limits

---

## Setup Guide

### Step 1 — Install Python 3
```bash
python3 --version
```

### Step 2 — Upload files to your server
```bash
scp -i ~/path/to/key.pem -r ~/boondockr ubuntu@YOUR_IP:/home/ubuntu/boondockr
```

### Step 3 — Install dependencies
```bash
cd /home/ubuntu/boondockr
pip3 install -r requirements.txt --break-system-packages
```

### Step 4 — Set up Gmail App Password
1. Enable 2-Step Verification at: https://myaccount.google.com/security
2. Create an App Password at: https://myaccount.google.com/apppasswords
3. Name it "Boondockr" and copy the 16-character password

### Step 5 — Create your .env file
```bash
cp .env.example .env
nano .env
```
Fill in:
```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### Step 6 — Configure your users and campgrounds
```bash
nano config.yaml
```

### Step 7 — Test email
```bash
python3 etest.py
```

### Step 8 — Run Boondockr
```bash
screen -S boondockr
python3 boondockr.py
```
Detach: **Ctrl + A then D**

---

## Common Yosemite Campground IDs

| Campground | ID |
|---|---|
| Upper Pines | 232447 |
| Lower Pines | 232450 |
| North Pines | 232448 |
| Camp 4 | 10083890 |
| Hodgdon Meadow | 232449 |
| Crane Flat | 232452 |
| Tuolumne Meadows | 232451 |

---

## Server Commands

| Command | What it does |
|---|---|
| `screen -S boondockr` | Start a new session |
| `screen -r boondockr` | Reattach to view logs |
| `Ctrl + A then D` | Detach safely |
| `pkill -f boondockr.py` | Stop Boondockr |
| `screen -ls` | List all sessions |
| `screen -X -S boondockr quit` | Kill session |

---

## Updating Config (Adding/Removing Friends or Campgrounds)

```bash
pkill -f boondockr.py
nano /home/ubuntu/boondockr/config.yaml
# make your changes
screen -S boondockr
python3 boondockr.py
# Ctrl + A then D
```

---

## Hurdles Solved During Development

### 1. Recreation.gov API — 400 Bad Request
**Problem:** The API was returning 400 errors on every request.
**Cause:** Missing browser-like headers. Recreation.gov blocks requests that don't look like a real browser.
**Fix:** Added full browser headers including User-Agent, Accept, Referer, Origin, and Connection.

### 2. Recreation.gov API — 429 Too Many Requests
**Problem:** After heavy testing, the server IP got rate limited.
**Cause:** Too many rapid requests in a short period during development and testing.
**Fix:** Implemented exponential backoff with jitter using Tenacity, Retry-After header support, 8-20 second delays between campground requests, and increased poll interval to 120-180 seconds.

### 3. Email Hanging Indefinitely
**Problem:** App would freeze for minutes when trying to send email.
**Cause:** DigitalOcean blocks outbound SMTP ports 465 and 587 by default.
**Fix:** Switched from DigitalOcean to AWS EC2 which has SMTP ports open by default. Also added a 10 second timeout to prevent future hangs.

### 4. SendGrid 401 Unauthorized
**Problem:** Email alerts failing with HTTP 401 error.
**Cause:** SendGrid account couldn't be created due to login restrictions, and the API key was never set up.
**Fix:** Replaced SendGrid entirely with Gmail SMTP using a Google App Password. Free, simple, and no account approval needed.

### 5. Twilio SMS — Toll-Free Verification Pending
**Problem:** SMS alerts not delivering despite successful API calls.
**Cause:** Twilio requires toll-free numbers to go through a verification process before they can send SMS.
**Fix:** Removed Twilio from v1.1. SMS can be re-added in a future version once verification is approved or a local number is purchased.

### 6. Multiple Screen Sessions
**Problem:** Multiple instances of Boondockr running simultaneously.
**Cause:** Restarting without killing old sessions.
**Fix:** Always run `pkill -f boondockr.py` before restarting. Use `screen -ls` to check for existing sessions.

### 7. YAML Config Formatting Errors
**Problem:** App crashing with YAML scanner errors on startup.
**Cause:** Missing spaces after colons (e.g. `blackout_dates:[]` instead of `blackout_dates: []`).
**Fix:** Always use a space after the colon in YAML. Use `cat config.yaml` to verify before restarting.

### 8. Placeholder Users in Config
**Problem:** Twilio hitting 50 SMS/day trial limit.
**Cause:** Placeholder friend entries with fake numbers were still active in config.yaml.
**Fix:** Comment out placeholder users with # until real friends are added.

---

## Monthly Cost (AWS EC2)

| Item | Cost |
|---|---|
| AWS EC2 t2.micro | Free (12 months) then ~$8-10/mo |
| Gmail SMTP | Free |
| **Total year 1** | **~$0/mo** |
| **Total after year 1** | **~$8-10/mo** |

---

## Versioning

```bash
git add .
git commit -m "describe your change"
git tag v1.2
git push && git push --tags
```

---

*Boondockr — watching so you don't have to.* 🏕️
