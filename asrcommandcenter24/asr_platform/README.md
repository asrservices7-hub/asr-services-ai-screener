# ASR Platform — Complete Integration Layer 🏗️
### The glue that connects all 5 ASR assets into one automated revenue machine

---

## What This Adds

You already had:
- `asr_ai_agent` — finds hiring companies
- `asr_candidate_engine` — stores and scores candidates
- `asr_7agents` — outreach, meetings, interviews
- `asr_employer_dashboard.html` — client-facing UI
- `AS_Revenue_Engine_v3_final.xlsx` — revenue tracking

This layer adds the **missing integration pieces**:

| New Component | What it does |
|---|---|
| `asr_platform.py` | Master orchestrator — runs everything as one daily cycle |
| `whatsapp_bot.py` | Candidate self-registration via WhatsApp (step-by-step bot) |
| `n8n_master_workflow.json` | Complete automation: leads → outreach → follow-ups → placements |
| Follow-up Sequencer | Day 1/3/7/14 email cadence — runs automatically |
| Invoice Generator | Generates placement invoices with GST calculation |
| Leads CRM (SQLite) | Tracks every company touchpoint from first email to placement |
| Platform Dashboard | Live stats: pipeline, candidates, revenue in one view |

---

## Quick Start

```bash
pip install -r requirements.txt
cp .env.template .env   # fill in your values

# See live platform stats (works with demo data immediately)
python3 asr_platform.py --dashboard

# Run complete daily cycle
python3 asr_platform.py --daily

# Send today's follow-ups
python3 asr_platform.py --followup

# Quick candidate search
python3 asr_platform.py --match "BPO Lucknow night shift"

# Generate an invoice
python3 asr_platform.py --invoice "Teleperformance" "Customer Support" 10 8000
```

---

## WhatsApp Candidate Bot

Candidates register themselves via WhatsApp — no manual data entry.

### How it works
1. Candidate messages your WhatsApp number: "Hi" or "Job"
2. Bot asks 8 questions (name, city, skill, experience, salary, English, night shift, notice period)
3. Profile automatically saved to candidate database with AI score
4. Candidate receives confirmation with their score

### Setup (30 minutes)
```bash
pip install flask
python3 whatsapp_bot.py

# Expose to internet (for testing)
ngrok http 5000

# Set webhook URL in Meta Business Dashboard:
# https://your-ngrok-url.ngrok.io/webhook/whatsapp
```

**Easiest WhatsApp API option:** AiSensy.com — ₹999/month, webhook-ready, no code needed for basic flows.

---

## n8n Master Workflow

Import `n8n_master_workflow.json` into n8n to get:

- **Daily 8 AM:** Lead discovery → email hot leads automatically
- **Day 3, 7, 14:** Follow-up sequences sent automatically
- **On HR reply:** Calendly link sent within minutes
- **On new WhatsApp candidate:** Saved to sheet + confirmation sent
- **On placement:** Revenue sheet updated + invoice triggered
- **Daily summary:** Telegram message to your phone

### Setup
```bash
npx n8n     # opens at http://localhost:5678
# Import n8n_master_workflow.json
# Fill in Google Sheets ID, Gmail, WhatsApp credentials
# Activate workflow
```

---

## Full Automated Flow (When Everything is Connected)

```
8:00 AM  → Lead agent finds 50 hiring companies
8:02 AM  → Hot leads (score ≥ 75) get personalised emails automatically
           (n8n handles the sending, rate limiting, logging)

Throughout day:
           → HR replies detected via Gmail monitoring
           → Calendly link sent within 5 minutes of reply
           → Meeting booked automatically

Evening:
           → WhatsApp bot has collected new candidate registrations
           → Candidates auto-scored and added to database
           → Follow-up emails sent to Day-3/7/14 contacts

On meeting:
           → You talk to HR, understand requirement
           → Run: python3 asr_platform.py --match "BPO Kanpur 15000"
           → Top 10 candidates displayed instantly
           → Send profiles to employer dashboard

On placement:
           → Run: python3 asr_platform.py --invoice "Company" "Role" 10 8000
           → Invoice generated with GST
           → Revenue sheet updated automatically
```

---

## Activation Order (Step by Step)

### Day 1 — Run locally (no API keys)
```bash
python3 asr_platform.py --dashboard
```
See the dashboard, understand the structure.

### Day 2 — Add email
```
EMAIL_USER=your@gmail.com
EMAIL_PASS=your-app-password
```
Follow-ups and outreach now send real emails.

### Day 3 — Start WhatsApp bot
```bash
python3 whatsapp_bot.py
# + ngrok http 5000
```
Candidates start self-registering.

### Week 2 — Import n8n workflow
Full automation loop running: leads → emails → follow-ups → Telegram summary.

### Month 2 — Add Supabase
```
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
```
Employer dashboard fetches live candidates from cloud. Platform is now fully online.

---

## Connect to Employer Dashboard

The `asr_employer_dashboard.html` currently uses static data.
To make it live:

1. Host on Vercel: `vercel deploy asr_employer_dashboard.html`
2. Add Supabase credentials to `.env`
3. Replace the `CANDIDATES` array in the HTML with a `fetch()` call to Supabase:

```javascript
// Replace static CANDIDATES array with:
const res = await fetch(`${SUPABASE_URL}/rest/v1/candidates?status=eq.Available&order=overall_score.desc&limit=50`,
  { headers: { apikey: SUPABASE_ANON_KEY } });
const CANDIDATES = await res.json();
```

Now employers see live candidates every time they log in.

---

## Revenue Tracking

Every placement is tracked in two places:
1. `data/revenue_log.json` — local invoice history
2. `AS_Revenue_Engine_v3_final.xlsx` — your master sheet (via Google Sheets sync)

```bash
# Generate invoice (saves to data/invoice_*.txt + logs revenue)
python3 asr_platform.py --invoice "Teleperformance Kanpur" "BPO Voice" 10 8000

# Output:
# Invoice No: ASR-202603-042
# 10 hires × ₹8,000 = ₹80,000
# GST 18% = ₹14,400
# TOTAL DUE: ₹94,400
```

---

## The Complete ASR System (All Files)

| File/Package | Role in System |
|---|---|
| `asr_platform.py` | **Master orchestrator** — runs everything |
| `whatsapp_bot.py` | Candidate intake via WhatsApp |
| `n8n_master_workflow.json` | Automation between all systems |
| `asr_ai_agent/` | Lead discovery (companies hiring) |
| `asr_candidate_engine/` | Candidate database + AI scoring |
| `asr_7agents/` | Outreach, meetings, parsing, matching, interviews |
| `asr_employer_dashboard.html` | Client-facing hiring platform |
| `AS_Revenue_Engine_v3_final.xlsx` | Business control room |

**Total: 1 complete AI recruitment platform.**

---

*AS Recruitment — AI-Powered Hiring for Tier-2 India*
