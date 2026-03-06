# ASR Candidate Database Engine 🧑‍💼
### Your candidate inventory — the asset that makes placements instant

---

## What This Does

Turns your candidate collection from a scattered WhatsApp list into a
searchable, scored, AI-ready database that matches candidates to jobs in seconds.

```
INPUT SOURCES                    OUTPUT
─────────────────                ─────────────────────────────────────
WhatsApp group dumps    →        SQLite database (asr_candidates.db)
CSV from your sheet     →        Google Sheet: CANDIDATE_POOL (synced)
Walk-in registrations   →        Shortlist CSV per job requirement
Naukri/Indeed exports   →        WhatsApp-ready candidate message
Manual entry            →        Live stats dashboard
```

**Core capability:** Type a job requirement in plain English →
get top 10 matching candidates in seconds, scored by AI.

```
python3 asr_candidate_engine.py --match "BPO voice Lucknow night shift 13000-18000 fluent"
```

---

## Files

| File | Purpose |
|---|---|
| `asr_candidate_engine.py` | Main engine — database, scoring, matching, export |
| `sample_candidates.csv` | 20 sample candidates — test import immediately |
| `sample_whatsapp_data.txt` | WhatsApp format template + 5 sample entries |
| `requirements.txt` | Python dependencies |

---

## Quick Start (5 Minutes)

```bash
# Install dependencies
pip install -r requirements.txt

# Generate 100 sample candidates to explore the system
python3 asr_candidate_engine.py --seed 100

# See database stats
python3 asr_candidate_engine.py --stats

# Match candidates to a BPO job
python3 asr_candidate_engine.py --match "BPO voice Lucknow night shift 15000"

# Import your own CSV
python3 asr_candidate_engine.py --ingest-csv sample_candidates.csv

# Export 10 candidates as WhatsApp message (copy-paste to HR)
python3 asr_candidate_engine.py --match "BPO Lucknow" --export-whatsapp 10
```

No API keys needed. Works fully offline.

---

## All Commands

```bash
# ── IMPORT ────────────────────────────────────────────────
# Add sample test data
python3 asr_candidate_engine.py --seed 100

# Import from CSV (your CANDIDATE_POOL sheet export, Naukri export, etc.)
python3 asr_candidate_engine.py --ingest-csv my_candidates.csv

# Import from WhatsApp text dump
python3 asr_candidate_engine.py --ingest-whatsapp sample_whatsapp_data.txt

# ── SEARCH & MATCH ────────────────────────────────────────
# Match by job requirement (natural language)
python3 asr_candidate_engine.py --match "BPO voice Lucknow night shift"
python3 asr_candidate_engine.py --match "hospital nurse Jaipur GNM"
python3 asr_candidate_engine.py --match "IT developer Noida Python React 50000-70000"
python3 asr_candidate_engine.py --match "sales Indore 15000-20000"

# Control result count (default: 10)
python3 asr_candidate_engine.py --match "BPO Lucknow" --top 20

# ── EXPORT ────────────────────────────────────────────────
# Export match results to CSV
python3 asr_candidate_engine.py --match "BPO Lucknow" --export-csv

# Export as WhatsApp message (print + save to file)
python3 asr_candidate_engine.py --export-whatsapp 10

# ── SYNC ──────────────────────────────────────────────────
# Sync top 500 candidates to Google Sheet
python3 asr_candidate_engine.py --sync-sheets

# ── STATS ─────────────────────────────────────────────────
python3 asr_candidate_engine.py --stats
```

---

## AI Scoring System

Every candidate gets scored automatically — no manual rating needed.

| Dimension | Max Points | What It Measures |
|---|---|---|
| Communication | 30 | English level + verbal role fit |
| Experience | 25 | Years of exp vs role requirements |
| Location | 20 | City match or relocation willingness |
| Availability | 15 | Joining date + notice period |
| Salary fit | 10 | Expected vs market range |
| **Overall** | **100** | Sum of all dimensions |
| **BPO Fit** | **100** | Specialised score for BPO clients |

**Score thresholds:**
- 80–100: Top candidate — share immediately
- 60–79: Good candidate — include in shortlist
- 40–59: Potential — needs screening call
- Below 40: Cold — re-engage later

---

## Candidate Sources

The system tracks where every candidate came from, so you know which channels work.

| Source | How to Import |
|---|---|
| **WhatsApp groups** | Save chat → export as TXT → `--ingest-whatsapp` |
| **Your existing sheet** | Export CANDIDATE_POOL tab as CSV → `--ingest-csv` |
| **Naukri/Indeed** | Download resume search CSV → `--ingest-csv` |
| **Walk-in drives** | Use `add_single()` in code, or add to CSV and import |
| **Google Forms** | Export responses as CSV → `--ingest-csv` |
| **Manual** | Add directly to CSV and import |

---

## Google Sheets Integration

Sync your top candidates back to the CANDIDATE_POOL tab automatically.

### Setup
1. Follow Google Sheets setup from the lead engine README
2. Add to `.env`:
   ```
   GOOGLE_SHEET_ID=your-sheet-id
   GOOGLE_CREDS_JSON=credentials.json
   ```
3. Run: `python3 asr_candidate_engine.py --sync-sheets`

This overwrites the CANDIDATE_POOL tab with your top 500 scored candidates.

---

## Database Structure

Stored in `asr_candidates.db` (SQLite — single file, no server needed).

**Key fields per candidate:**
- Identity: name, phone (unique key), email
- Location: city, state, willing_to_relocate
- Profile: primary_skill, experience, current/expected salary
- Readiness: available_to_join, notice_period, night_shift_ok, english_fluency
- Scores: communication_score, experience_score, overall_score, bpo_fit_score
- Status: Available → Submitted → Interviewing → Placed
- Source: WhatsApp / Naukri / LinkedIn / Walk-in / Referral / CSV
- Revenue: placed_at, placement_fee, placement_date

**Deduplication:** Phone number is the unique key.
Importing the same person twice just updates their record — no duplicates.

---

## Connect to the Lead Engine

When a lead (company) comes in from `asr_lead_engine.py`:

```python
from asr_candidate_engine import CandidateDB, JobMatcher

db = CandidateDB()
matcher = JobMatcher(db)

# Company sends: "Need 20 BPO agents in Lucknow, night shift, salary 12-16K"
candidates = matcher.match("BPO Lucknow night shift 12000-16000", top_n=10)

# Export as WhatsApp message to send to HR immediately
from asr_candidate_engine import export_whatsapp_messages
export_whatsapp_messages(candidates, count=5)
```

This is the 24-hour close workflow:
- Lead found at 8 AM
- Candidates matched at 8:01 AM
- Profiles sent to HR by 9 AM
- Interview scheduled same day

---

## Revenue Tracking

Every placement is recorded in the database:

```python
db.mark_placed("CND-ABC12345", company="Teleperformance Kanpur", fee=8000)
```

Run `--stats` to see total revenue earned and pipeline value.

---

## Phase 2 Upgrades (When You're Ready)

**Resume Parsing (Month 3)**
```bash
pip install spacy
python -m spacy download en_core_web_sm
```
Point candidates to a Google Form with resume upload.
spaCy extracts skills, experience, and companies automatically.

**PostgreSQL Migration (Month 6)**
When database exceeds 50,000 candidates, migrate from SQLite to PostgreSQL
for multi-user access and faster queries.

**LangChain Matching (Month 4)**
For complex requirements ("senior nurse with ICU experience, speaks Hindi and English,
available within 7 days, salary under ₹35K"), LangChain reads the requirement
and queries the DB with AI-generated filters.

---

## The Long-Term Asset

At 1,000 candidates: you close BPO deals in 24 hours instead of 7 days.
At 10,000 candidates: companies come to you because you respond instantly.
At 1,00,000 candidates: you are the fastest recruiter in Tier-2 India.
At 10,00,000 candidates: you are a hiring platform, not an agency.

Every candidate you add today compounds in value.
The database is your moat.

---

*Built for AS Recruitment — Tier-2 India AI Hiring Engine*
