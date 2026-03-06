# ASR Growth Engine 🚀
### ₹0 outreach system. Finds companies, emails them, follows up, generates call scripts.

---

## Two files. That's it.

| File | What it does |
|---|---|
| `growth_engine.py` | Finds companies → sends emails → sequences follow-ups → LinkedIn + WhatsApp batches |
| `call_assistant.py` | Generates call scripts + live objection handling during calls |

---

## Start in 60 seconds (no API keys needed)

```bash
pip install -r requirements.txt

# See your pipeline (starts with 25 pre-loaded companies)
python3 growth_engine.py --stats

# Send outreach emails (demo mode — prints emails, doesn't send)
python3 growth_engine.py --outreach

# Generate LinkedIn messages for top 30 companies
python3 growth_engine.py --linkedin

# Generate WhatsApp messages for top 50 companies with phones
python3 growth_engine.py --whatsapp

# Get a call script before dialling
python3 call_assistant.py --script "BPO Lucknow night shift 20 agents"

# Handle an objection DURING a call (keep this open on laptop)
python3 call_assistant.py --objection "we already have a recruitment partner"
```

---

## Daily Routine (30 min of your time → system does the rest)

```bash
# Morning: full daily cycle
python3 growth_engine.py --daily

# Check who to call today
python3 call_assistant.py --batch-scripts 10

# Make your calls. For each objection:
python3 call_assistant.py --objection "not hiring right now"

# Evening: follow-ups sent automatically by the daily cycle
```

---

## Make Emails Real (10 min setup)

```bash
# 1. Enable Gmail App Password:
#    Google Account → Security → 2-Step Verification → App Passwords → Create

# 2. Add to .env:
EMAIL_USER=srijan@asrecruitment.in
EMAIL_PASS=your-16-char-app-password

# 3. Run — emails now send for real
python3 growth_engine.py --outreach --count 50
```

Gmail free tier: 500 emails/day. Enough for all of Phase 1.

---

## Import Your Own Company List

If you have a CSV of companies (from Google Maps, Naukri, JustDial, anywhere):

```bash
python3 growth_engine.py --import-csv my_companies.csv
```

Expected columns (flexible, maps automatically):
`company name, city, industry, email, phone, website, roles`

---

## Objection Handlers Built In

| What HR says | Command |
|---|---|
| "We already have a vendor" | `--objection "we already have a vendor"` |
| "Not hiring right now" | `--objection "no vacancy"` |
| "Fees are too high" | `--objection "too expensive"` |
| "Send details on email" | `--objection "send details"` |
| "Let me think about it" | `--objection "think about it"` |
| "Not interested" | `--objection "not interested"` |

Add `OPENAI_API_KEY` to `.env` for AI-generated responses to any objection.

---

## Revenue Math

At 50 emails/day (Gmail free tier):

```
50 emails/day × 8% reply rate = 4 replies
4 replies × 50% meeting rate  = 2 meetings
2 meetings × 50% close rate   = 1 client/week
1 client × 10 hires × ₹8,000 = ₹80,000/week
```

Scale to 200 emails/day with a custom domain → ₹3.2L/week potential.

---

## Connect to the Full ASR Platform

```
growth_engine.py → finds companies and emails them
       ↓
asr_platform.py  → tracks replies, books meetings, runs follow-ups
       ↓
asr_candidate_engine → matches candidates to requirements
       ↓
asr_employer_dashboard → employer views candidates
       ↓
Invoice generated → revenue recorded
```

All files work together. Put them in the same folder.

---

*AS Recruitment — AI-Powered Hiring for Tier-2 India*
