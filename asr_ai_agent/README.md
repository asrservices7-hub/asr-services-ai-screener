# ASR AI Lead Engine 🤖
### Automatically finds hiring companies → updates your Google Sheet → triggers outreach

---

## What This Does

Every morning, 3 AI agents work together:

```
Agent 1 (Company Finder)
  → Searches Naukri, Google Maps for BPO/hospital/IT companies hiring NOW
  → Targets: Lucknow, Kanpur, Noida, Jaipur, Indore

Agent 2 (HR Contact Finder)
  → Finds HR Manager name + LinkedIn URL + email for each company

Agent 3 (Lead Structurer)
  → Cleans the data, scores each lead 0–100
  → Writes to your AI_OUTREACH_TRACKER Google Sheet

n8n Workflow (optional)
  → Auto-sends WhatsApp + email to hot leads (score ≥ 80)
  → Waits 48 hours → sends follow-up if no reply
  → Sends daily Telegram summary to your phone
```

**Expected output per run:** 50–100 qualified leads added to your sheet.

---

## Files

| File | What It Does |
|---|---|
| `asr_lead_engine.py` | Main CrewAI agent system |
| `asr_scheduler.py` | Runs the engine on a daily schedule |
| `n8n_outreach_workflow.json` | Import into n8n for outreach automation |
| `requirements.txt` | Python dependencies |
| `.env.template` | Copy to `.env` and fill your API keys |

---

## Setup (One-Time, ~30 Minutes)

### Step 1: Python Environment

```bash
# Clone or download this folder
cd asr_ai_agent

# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# Install dependencies
pip install -r requirements.txt
```

### Step 2: OpenAI API Key (Required)

1. Go to: https://platform.openai.com/api-keys
2. Click **Create new secret key**
3. Copy the key (starts with `sk-proj-...`)
4. **Cost estimate:** gpt-4o-mini costs ~₹0.10 per run (very cheap)

### Step 3: Environment Variables

```bash
cp .env.template .env
# Open .env and fill in:
#   OPENAI_API_KEY=sk-proj-your-key
```

That's the minimum required. The system will work in demo mode without SerpAPI.

### Step 4: Test Run (No Google Sheets Yet)

```bash
python3 asr_lead_engine.py
```

You'll see the agents working in the terminal.
Results saved to `asr_leads_output.json` and `asr_leads_output.csv`.

---

## Google Sheets Integration (Optional but Recommended)

### Step 1: Google Cloud Console

1. Go to: https://console.cloud.google.com
2. Create a new project: "ASR Lead Engine"
3. Enable the **Google Sheets API**
4. Go to **Credentials** → **Create Service Account**
5. Name it: `asr-sheets-writer`
6. Download the JSON key → rename to `credentials.json` → put in this folder

### Step 2: Share Your Sheet

1. Open your Google Sheet
2. Click **Share**
3. Add the service account email (from the JSON file, field: `client_email`)
4. Give it **Editor** access

### Step 3: Set Sheet ID

1. Copy your sheet URL: `https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit`
2. Add to `.env`: `GOOGLE_SHEET_ID=SHEET_ID_HERE`

### Step 4: Test

```bash
python3 asr_lead_engine.py
```

Leads will appear in the `AI_OUTREACH_TRACKER` tab of your sheet.

---

## SerpAPI Integration (For Real Web Searches)

Without SerpAPI, the system uses realistic mock data — useful for testing.
With SerpAPI, it searches Naukri, Google Maps, and LinkedIn in real-time.

**Free tier:** 100 searches/month at https://serpapi.com

```bash
# Add to .env:
SERPAPI_API_KEY=your-key-here
```

---

## n8n Automation Setup (Optional — For Auto-Outreach)

n8n is free, open-source, and runs on your computer.

### Install n8n

```bash
npx n8n
# Opens at: http://localhost:5678
```

### Import the Workflow

1. Open n8n → click **+** → **Import from JSON**
2. Paste contents of `n8n_outreach_workflow.json`
3. Set your Google Sheet ID in the workflow
4. Configure Google Sheets credentials
5. Configure Gmail/SMTP credentials
6. Click **Activate workflow**
7. Copy the webhook URL → add to `.env` as `N8N_NEW_LEADS_WEBHOOK`

### Test the Workflow

```bash
python3 asr_scheduler.py --now
```

This runs the full pipeline: find leads → write to sheet → trigger n8n → send outreach.

---

## Daily Scheduling

### Option 1: Manual (Simplest)

```bash
python3 asr_lead_engine.py
```

Run this each morning before calls.

### Option 2: Python Scheduler

```bash
python3 asr_scheduler.py
# Runs automatically Mon–Fri at 8:00 AM
```

### Option 3: Cron (Linux/Mac)

```bash
crontab -e
# Add this line:
0 8 * * 1-5 cd /path/to/asr_ai_agent && python3 asr_lead_engine.py >> logs/daily.log 2>&1
```

---

## Customisation

### Change Target Cities

In `asr_lead_engine.py`, edit `CONFIG["cities"]`:
```python
"cities": ["Lucknow", "Kanpur", "Noida", "Jaipur", "Indore"],
```

### Change Target Industries

Edit `CONFIG["verticals"]`:
```python
"verticals": [
    "BPO customer support",
    "call center outsourcing",
    ...
]
```

### Change Lead Volume

```python
"leads_per_run": 100,   # default: 50
```

### Change LLM Model

```python
"model": "gpt-4o",      # better quality, higher cost
# "model": "gpt-4o-mini"  # default — fast and cheap
```

---

## Expected Results

| Configuration | Leads/Day | Estimated Cost |
|---|---|---|
| Mock data only (no API keys) | 50 structured test leads | Free |
| OpenAI + Mock data | 50 AI-enriched leads | ~₹0.10/run |
| OpenAI + SerpAPI | 50–100 real web leads | ~₹0.50/run |
| Full stack + n8n | 50–100 leads + auto-outreach | ~₹1/run |

**At 2% conversion:** 100 leads → 2 clients → 2 mandates → ~₹2.4L pipeline per day.

---

## Troubleshooting

**"OPENAI_API_KEY not set"**
→ Check your `.env` file is in the same folder as the script.

**"Module not found: crewai"**
→ Run: `pip install -r requirements.txt`

**"Google Sheets connection failed"**
→ Check `credentials.json` is present. Check service account has Editor access to the sheet.

**Agents not finding good results**
→ Enable SerpAPI for real web searches. Mock data is for testing only.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                  asr_lead_engine.py                      │
│                                                          │
│  Agent 1: Company Finder                                 │
│  ├── NaukriJobSearchTool (SerpAPI / mock)                │
│  └── GoogleMapsCompanyTool (SerpAPI / mock)              │
│          ↓                                               │
│  Agent 2: HR Contact Finder                              │
│  └── LinkedInHRFinderTool (SerpAPI / mock)               │
│          ↓                                               │
│  Agent 3: Lead Structurer                                │
│  └── Scores, deduplicates, outputs JSON                  │
│          ↓                                               │
│  GoogleSheetsWriter                                      │
│  └── Appends to AI_OUTREACH_TRACKER tab                  │
└─────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────┐
│  asr_scheduler.py (runs daily at 8 AM)                   │
│  └── Triggers n8n webhook with hot leads                 │
└─────────────────────────────────────────────────────────┘
          ↓
┌─────────────────────────────────────────────────────────┐
│  n8n Workflow (n8n_outreach_workflow.json)                │
│  ├── Filter hot leads (score ≥ 80)                       │
│  ├── Send WhatsApp message to HR                         │
│  ├── Send email to HR                                    │
│  ├── Update Google Sheet (email_sent = Yes)              │
│  ├── Wait 48 hours                                       │
│  └── Send follow-up if no reply                          │
└─────────────────────────────────────────────────────────┘
          ↓
    Your phone: Telegram daily summary
    Your sheet: AI_OUTREACH_TRACKER updated live
```

---

## Next Steps After This Works

1. **Month 2:** Add resume parser — auto-score candidates from CANDIDATE_POOL
2. **Month 3:** Add candidate-to-job matching agent
3. **Month 4:** Full CrewAI pipeline: find job → find candidate → match → outreach → schedule interview
4. **Month 6:** Deploy on a server (AWS/DigitalOcean) — runs 24/7 without your laptop

---

*Built for AS Recruitment — Tier-2 India AI Hiring Engine*
