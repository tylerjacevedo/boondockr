# Boondockr — Changelog

All notable changes to this project are documented here.

---

## [v1.1] — May 2026

### Changed
- Renamed app from Boondocker to Boondockr
- Removed Twilio SMS — email only via Gmail SMTP
- Replaced SendGrid with Gmail SMTP (port 587 with STARTTLS)
- Added 10 second timeout to email connections to prevent hanging
- Increased poll interval from 45-90s to 120-180s to reduce 429 errors
- Added exponential backoff with jitter using Tenacity library
- Added Retry-After header support for 429 responses
- Added 8-20 second human-like delay between campground requests
- Added 2-6 second pre-request delay on each API call
- Removed SendGrid and Twilio from requirements.txt
- Updated .env.example to Gmail only

### Fixed
- Email hanging indefinitely when SMTP port is blocked
- Duplicate screen sessions causing multiple instances
- YAML config formatting errors
- Duplicate human-like delay in polling loop
- Date format causing 400 errors on recreation.gov API

---

## [v1.0] — May 2026 — Initial Release

### Added
- 60-second randomized polling of recreation.gov availability API
- Instant Email alerts via SendGrid with direct booking link
- SMS alerts via Twilio
- Multi-user support
- Multiple campground support
- Day filter — all days, weekends only, or weekdays only
- Specific site or any available site monitoring
- Blackout dates per user
- Priority ranking of campgrounds
- Mass release flood protection
- Monthly release reminders — 1hr and 15min warning
- Daily digest — 8am heartbeat email
- Downtime alert if app goes offline for 15+ minutes
- Auto-retry with exponential backoff
- 5-minute cooldown per site to prevent duplicate alerts
- Console logging with timestamps
- config.yaml for user and campground management
- .env file for secure credential storage
