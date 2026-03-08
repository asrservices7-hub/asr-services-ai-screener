# ASR 7-Agent Automation System 🤖
### 7 AI workers running ASR Services 24/7

---

## The 7 Agents

| # | Agent | What it does | Needs |
|---|---|---|---|
| 1 | **Lead Generation** | Finds 50–100 hiring companies daily | SerpAPI (optional) |
| 2 | **Outreach** | Sends personalised emails + WhatsApp to HR | Gmail + WhatsApp API |
| 3 | **Meeting Booking** | Reads replies, sends Calendly link | Gmail IMAP |
| 4 | **Candidate Acquisition** | Pulls new candidates from forms/WhatsApp | Google Forms CSV |
| 5 | **Resume Parser & Scorer** | AI reads resumes, scores 0–100 | OpenAI (optional) |
| 6 | **Matching** | Matches candidates to live requirements | Candidate DB |
| 7 | **Interview Scheduler** | Sends interview invites + reminders | WhatsApp API |

---

## Quick Start (Demo Mode — No API Keys)

```bash
pip install -r requirements.txt
cp .env.template .env

# Run full system (demo mode — no real emails/WhatsApp)
python3 asr_system.py --run-all

# Check today's numbers
python3 asr_system.py --status
```

Everything runs in demo mode without API keys — shows exactly what each agent
would do, prints messages to console instead of sending them.

---

## Run Individual Agents

```bash
python3 asr_system.py --leads           # Agent 1: Find companies
python3 asr_system.py --outreach        # Agent 2: Send HR messages
python3 asr_system.py --meetings        # Agent 3: Book meetings from replies
python3 asr_system.py --candidates      # Agent 4: Pull new candidates
python3 asr_system.py --parse           # Agent 5: Score resumes in resumes/ folder
python3 asr_system.py --match "BPO Lucknow night shift 15000"  # Agent 6: Match candidates
python3 asr_system.py --schedule        # Agent 7: Send interview invites
python3 asr_system.py --status          # Today's pipeline numbers
```

---

## Activation Order (Do This First)

### Step 1 — Add OpenAI key (5 min)
```
OPENAI_API_KEY=sk-proj-...
```
Agents 1, 5 now use real AI.

### Step 2 — Add Gmail credentials (10 min)
```
EMAIL_USER=srijan@asrecruitment.in
EMAIL_PASS=your-app-password    ← Gmail → Security → App Passwords
```
Agent 2 now sends real emails. Agent 3 reads replies.

### Step 3 — Add WhatsApp API (30 min)
Easiest option: AiSensy.com (₹999/month, no code needed)
```
WHATSAPP_API_KEY=...
WHATSAPP_PHONE_ID=...
```
Agents 2 and 7 now send real WhatsApp messages.

### Step 4 — Add SerpAPI (10 min)
```
SERPAPI_API_KEY=...    ← serpapi.com, free 100 searches/month
```
Agent 1 now finds real companies from Naukri/Google/LinkedIn.

---

## Daily Automation

```bash
# Run automatically Mon–Fri 8AM
python3 scheduler.py

# Or cron (Linux/Mac)
0 8 * * 1-5 cd /path/to/asr_7agents && python3 asr_system.py --run-all
```

---

## Connect to Candidate Engine

Copy `asr_candidate_engine.py` from the candidate engine package into this folder.
Agent 4 will automatically ingest new candidates into the database.
Agent 6 will use the database for matching.

```bash
cp ../asr_candidate_engine/asr_candidate_engine.py .
```

---

## Full Pipeline Flow

```
8:00 AM → Agent 1 finds 50 hiring companies
8:05 AM → Agent 2 sends 50 personalised emails + WhatsApp
8:10 AM → Agent 4 pulls new candidates from forms
8:15 AM → Agent 5 scores all unscored resumes
 ...
 (HR replies throughout the day)
 ...
6:00 PM → Agent 3 detects positive replies, sends Calendly links
6:05 PM → Agent 6 matches new requirements from meetings
6:10 PM → Agent 7 sends interview invites for tomorrow's slots
```

---

## Revenue Math (When Running)

| Metric | Daily | Monthly |
|---|---|---|
| Companies contacted | 50 | 1,000 |
| Reply rate (est. 8%) | 4 | 80 |
| Meetings booked | 2 | 40 |
| Clients closed (30%) | 0.6 | 12 |
| Avg hires per client | 4 | 48 |
| Fee per hire | ₹10,000 | — |
| **Monthly Revenue** | | **₹4,80,000** |

Scale to 100 companies/day → ₹10L+/month.

---

*Built for AS Recruitment — Tier-2 India AI Hiring Engine*
