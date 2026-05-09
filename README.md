# 🏕️ Boondockr

> Real-time campsite cancellation notifier built entirely on AWS

[![Python](https://img.shields.io/badge/Python-3.11-3776ab?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![AWS EC2](https://img.shields.io/badge/AWS-EC2-ff9900?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/ec2)
[![AWS Lambda](https://img.shields.io/badge/AWS-Lambda-ff9900?style=flat-square&logo=awslambda&logoColor=white)](https://aws.amazon.com/lambda)
[![CloudFront](https://img.shields.io/badge/AWS-CloudFront-ff9900?style=flat-square&logo=amazonaws&logoColor=white)](https://aws.amazon.com/cloudfront)
[![S3](https://img.shields.io/badge/AWS-S3-ff9900?style=flat-square&logo=amazons3&logoColor=white)](https://aws.amazon.com/s3)

---

## The Problem

Getting a campsite at Yosemite is genuinely difficult. Reservations sell out within seconds of opening each month, and the only tool recreation.gov offers is a basic alert system — capped at 3 alerts, slow to notify, and with no direct link to book when something opens up.

Cancellations happen constantly. The problem isn't availability — it's speed. By the time most people see a notification, the site is already gone. I'd missed sites more than once because of it, so I decided to build something that actually worked.

| | recreation.gov | Boondockr |
|---|---|---|
| Max alerts | 3 | Unlimited |
| Poll interval | Unknown (slow) | Every 60–90 seconds |
| Direct booking link | No | Yes |
| Weekday/weekend filter | No | Yes |
| Alert spam | Yes | Once per site, forever |

---

## Architecture

Every component runs on AWS — from the Python script polling recreation.gov to the HTTPS-secured control panel.

```
User Browser
     │
     ▼
CloudFront (HTTPS CDN)
     │
     ▼
S3 (Dashboard — index.html)
     │
     ▼ API calls
API Gateway (REST endpoints)
     │
     ▼
Lambda (Python 3.11)
     │
     ▼
SSM (Secure remote execution)
     │
     ▼
EC2 t2.micro (Ubuntu 22.04 — 24/7)
     │
     ├── boondockr.py (Polling engine)
     │        │
     │        ├── Recreation.gov API ──► JSON availability data
     │        │
     │        └── Gmail SMTP ──► User inbox
     │
     ├── config.yaml (Users & campgrounds)
     └── alerted_sites.json (Persistent alert history)
```

### AWS Services

| Service | Role | Purpose |
|---|---|---|
| **EC2** | Compute | Ubuntu t2.micro running 24/7, hosts the Python polling script |
| **Lambda** | Serverless | Receives dashboard commands and executes them on EC2 via SSM |
| **API Gateway** | REST API | Gives Lambda a public URL — routes `/status`, `/check`, `/clear`, `/save-config` |
| **S3** | Static hosting | Hosts the dashboard HTML file |
| **CloudFront** | CDN + HTTPS | Sits in front of S3, adds SSL, distributes globally |
| **SSM** | Remote execution | Lets Lambda run shell commands on EC2 without exposing SSH |
| **IAM** | Permissions | Least privilege roles for every service |
| **CloudWatch** | Logging | Captures Lambda logs for debugging |

---

## Features

- **Real-time polling** — Checks recreation.gov every 60–90 seconds with randomized delays to avoid rate limiting
- **Smart email alerts** — One summary email per poll cycle, available dates grouped into ranges (May 7–9 instead of individual days)
- **Alert once per site** — Persistent tracking on disk, no repeat notifications across restarts
- **Flood protection** — Detects monthly release spikes (10+ sites at once) and sends a single summary
- **Manual re-check** — Force a fresh check via `python3 boondockr.py --check` or the dashboard button
- **Live control panel** — HTTPS dashboard to add campgrounds, manage users, and trigger commands without SSHing in
- **Daily digest** — Morning summary email confirming the app is running
- **Monthly reminders** — 1-hour and 15-minute warnings before the 15th of each month release

---

## Engineering Challenges

Every problem below came up in production and was diagnosed from logs without a guide.

**01 — 400 errors on every API request**
Recreation.gov silently requires browser-like headers. Fixed by adding `User-Agent`, `Accept`, `Referer`, and `Origin` to match what a real browser sends.

**02 — 429 rate limiting**
After heavy testing the server IP got flagged. Fixed with Tenacity exponential backoff, `Retry-After` header support, and randomized 8–20 second delays between requests.

**03 — Email hanging indefinitely**
DigitalOcean blocks outbound SMTP ports 465 and 587 by default. Fixed by migrating to AWS EC2 which doesn't have this restriction, plus adding a 10-second connection timeout.

**04 — SSM credential errors**
The SSM agent was running but couldn't authenticate. Fixed by creating an IAM role with `AmazonSSMManagedInstanceCore`, building an instance profile, and attaching it to the EC2 instance via CLI.

**05 — CORS blocking dashboard calls**
The browser blocked cross-origin requests with "Failed to fetch". Fixed by adding an OPTIONS method with MOCK integration to API Gateway and configuring `Access-Control-Allow-Origin` headers on all Lambda responses.

---

## Deployment

Everything was provisioned using the AWS CLI — no console clicking.

```bash
# Create and configure S3 website
aws s3 mb s3://boondockr-ui --region us-east-1
aws s3 website s3://boondockr-ui --index-document index.html

# Deploy CloudFront with HTTPS
aws cloudfront create-distribution \
  --origin-domain-name boondockr-ui.s3-website-us-east-1.amazonaws.com

# Create IAM roles
aws iam create-role --role-name boondockr-lambda-role \
  --assume-role-policy-document file://trust-policy.json
aws iam attach-role-policy --role-name boondockr-lambda-role \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMFullAccess

# Deploy Lambda
aws lambda create-function \
  --function-name boondockr-api \
  --runtime python3.11 \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://lambda.zip

# Create and deploy API Gateway
aws apigateway create-rest-api --name boondockr-api
aws apigateway create-deployment --rest-api-id <id> --stage-name prod
```

---

## Setup Guide

### Prerequisites
- AWS account
- Python 3.8+
- Gmail account with 2-Step Verification enabled

### 1 — Clone and install dependencies

```bash
git clone https://github.com/tylerjacevedo/boondockr.git
cd boondockr
pip3 install -r requirements.txt
```

### 2 — Configure credentials

```bash
cp .env.example .env
```

Edit `.env`:
```
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

Get your Gmail App Password at: https://myaccount.google.com/apppasswords

### 3 — Configure campgrounds and users

Edit `config.yaml`:

```yaml
users:
  - name: "Tyler"
    email: "you@gmail.com"
    watching: [232447, 232450]

campgrounds:
  - id: 232447
    name: "Upper Pines — Yosemite"
    date_start: "2026-05-01"
    date_end: "2026-11-30"
    site: null          # null = any available site
    day_filter: "all"   # "all" | "weekends" | "weekdays"
    blackout_dates: []
    priority: 1
```

### 4 — Deploy to EC2

```bash
# Upload files
scp -i your-key.pem -r . ubuntu@YOUR_EC2_IP:/home/ubuntu/boondockr

# SSH in and start
ssh -i your-key.pem ubuntu@YOUR_EC2_IP
cd /home/ubuntu/boondockr
pip3 install -r requirements.txt
screen -S boondockr
python3 boondockr.py
# Ctrl+A then D to detach
```

### Common Yosemite Campground IDs

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

## Version History

| Version | What changed |
|---|---|
| **v1.0** | Core polling engine. Twilio SMS + SendGrid email. Multi-user config. Flood protection. Daily digest. Monthly reminders. |
| **v1.1** | Migrated from DigitalOcean to AWS EC2. Replaced Twilio/SendGrid with Gmail SMTP. Added Tenacity exponential backoff. |
| **v1.2** | One summary email per cycle. Consecutive date grouping (May 7–9). 24-hour alert cooldown. New HTML email design. |
| **v1.3** | Persistent alert tracking with `alerted_sites.json`. Alert once per site forever. Added `--check` manual re-check flag. |
| **v2.0** | Full-stack AWS dashboard. S3 + CloudFront frontend. Lambda + API Gateway backend. SSM remote command execution. Live server status. |

---

## Monthly Cost

| Item | Cost |
|---|---|
| AWS EC2 t2.micro | Free (12 months) then ~$8–10/mo |
| Gmail SMTP | Free |
| S3 + CloudFront | ~$0.50/mo |
| **Total year 1** | **~$0.50/mo** |

---

## Why I Built This

Getting into Yosemite without a reservation is nearly impossible in the summer. The official alert system is slow, limited, and doesn't give you a direct link to book when something opens up.

I decided to solve the problem properly — understanding how recreation.gov's API actually works, figuring out how to run something reliably in the cloud, and building a system that would notify me the moment a site opened. The AWS CLI kept the whole setup reproducible and fast to iterate on. Each engineering challenge that came up in production taught something that a tutorial never would.

---

*Boondockr — watching so you don't have to.* 🏕️
