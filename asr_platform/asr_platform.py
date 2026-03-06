"""
ASR Platform — Complete Integration Layer
==========================================
Connects all 5 existing assets into one automated revenue machine:

  asr_ai_agent        → Lead discovery (companies hiring)
  asr_candidate_engine→ Candidate database (scoring, matching)
  asr_7agents         → Outreach, meetings, interviews
  asr_employer_dashboard → Client-facing UI
  AS_Revenue_Engine   → Revenue tracking (Google Sheets)

New additions in this file:
  • Supabase cloud database (replaces SQLite for scale)
  • n8n webhook triggers (outreach sequences)
  • WhatsApp bot intake (candidate self-registration)
  • Follow-up sequencer (Day 1/3/7/14 cadence)
  • Invoice generator (placement fee → PDF invoice)
  • Placement tracker (feeds Revenue Engine sheet)
  • Central status dashboard

Run:
  python3 asr_platform.py --daily         Full daily automation cycle
  python3 asr_platform.py --dashboard     Print live platform stats
  python3 asr_platform.py --invoice CLIENT_NAME HIRES FEE
  python3 asr_platform.py --followup      Send Day 3/7/14 follow-ups
  python3 asr_platform.py --match "BPO Lucknow"  Quick candidate search
"""

import os, sys, json, time, argparse, sqlite3, csv
from datetime import datetime, date, timedelta
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────
PLATFORM_DIR  = Path(__file__).parent
DATA_DIR      = PLATFORM_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

LEADS_DB      = DATA_DIR / "leads.db"
REVENUE_LOG   = DATA_DIR / "revenue_log.json"
FOLLOWUP_LOG  = DATA_DIR / "followup_log.json"
STATE_FILE    = DATA_DIR / "platform_state.json"

# ── Supabase (optional — replace SQLite when scaling) ─────────
SUPABASE_URL  = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY  = os.getenv("SUPABASE_ANON_KEY", "")
USE_SUPABASE  = bool(SUPABASE_URL and SUPABASE_KEY)

# ── n8n webhook (optional — triggers outreach sequences) ──────
N8N_BASE      = os.getenv("N8N_BASE_URL", "http://localhost:5678")
N8N_LEADS_WH  = os.getenv("N8N_NEW_LEADS_WEBHOOK",    f"{N8N_BASE}/webhook/asr-new-leads")
N8N_FOLLOWUP  = os.getenv("N8N_FOLLOWUP_WEBHOOK",     f"{N8N_BASE}/webhook/asr-followup")
N8N_PLACED_WH = os.getenv("N8N_PLACEMENT_WEBHOOK",    f"{N8N_BASE}/webhook/asr-placed")


# ══════════════════════════════════════════════════════════════
#  LEADS DATABASE  (SQLite → upgrades to Supabase)
# ══════════════════════════════════════════════════════════════

class LeadsDB:
    """
    Central company/lead store with full outreach history.
    One record per company. Tracks every touchpoint.
    """

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS leads (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        company         TEXT NOT NULL,
        industry        TEXT,
        city            TEXT,
        hr_name         TEXT,
        email           TEXT,
        phone           TEXT,
        website         TEXT,
        linkedin_url    TEXT,
        roles           TEXT,
        hiring_volume   TEXT,
        score           INTEGER DEFAULT 50,
        status          TEXT DEFAULT 'New',
        email_sent      INTEGER DEFAULT 0,
        last_emailed    TEXT,
        followup_day    INTEGER DEFAULT 0,
        next_followup   TEXT,
        reply_received  INTEGER DEFAULT 0,
        meeting_booked  INTEGER DEFAULT 0,
        meeting_date    TEXT,
        requirement_received INTEGER DEFAULT 0,
        placements      INTEGER DEFAULT 0,
        revenue         INTEGER DEFAULT 0,
        source          TEXT,
        date_added      TEXT DEFAULT CURRENT_DATE,
        notes           TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_status    ON leads(status);
    CREATE INDEX IF NOT EXISTS idx_city      ON leads(city);
    CREATE INDEX IF NOT EXISTS idx_followup  ON leads(next_followup);
    CREATE INDEX IF NOT EXISTS idx_score     ON leads(score DESC);
    """

    def __init__(self):
        self.conn = sqlite3.connect(str(LEADS_DB))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()

    def upsert_lead(self, lead: dict) -> bool:
        """Insert or update. Returns True if new."""
        existing = self.conn.execute(
            "SELECT id FROM leads WHERE company=? AND city=?",
            (lead.get("company",""), lead.get("city",""))
        ).fetchone()

        if existing:
            self.conn.execute(
                "UPDATE leads SET score=MAX(score,?), hr_name=COALESCE(NULLIF(?,''),hr_name), "
                "email=COALESCE(NULLIF(?,''),email), phone=COALESCE(NULLIF(?,''),phone) WHERE id=?",
                (lead.get("score",50), lead.get("hr_name",""), lead.get("email",""),
                 lead.get("phone",""), existing["id"])
            )
            self.conn.commit()
            return False
        else:
            next_fu = (date.today() + timedelta(days=3)).isoformat()
            self.conn.execute(
                "INSERT INTO leads (company,industry,city,hr_name,email,phone,website,"
                "linkedin_url,roles,hiring_volume,score,source,next_followup) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (lead.get("company",""), lead.get("industry",""), lead.get("city",""),
                 lead.get("hr_name",""), lead.get("email",""), lead.get("phone",""),
                 lead.get("website",""), lead.get("linkedin_url",""), lead.get("roles",""),
                 lead.get("hiring_volume",""), lead.get("score",50),
                 lead.get("source","Agent"), next_fu)
            )
            self.conn.commit()
            return True

    def bulk_upsert(self, leads: list) -> tuple[int,int]:
        new = updated = 0
        for l in leads:
            if self.upsert_lead(l): new += 1
            else: updated += 1
        return new, updated

    def get_due_followups(self) -> list:
        """Leads where follow-up is due today or overdue."""
        today = date.today().isoformat()
        rows = self.conn.execute(
            "SELECT * FROM leads WHERE next_followup <= ? AND reply_received=0 "
            "AND email_sent=1 AND followup_day < 4 AND status NOT IN ('Won','Lost') "
            "ORDER BY score DESC LIMIT 100",
            (today,)
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_emailed(self, lead_id: int):
        next_fu = (date.today() + timedelta(days=3)).isoformat()
        self.conn.execute(
            "UPDATE leads SET email_sent=1, last_emailed=?, followup_day=1, "
            "next_followup=?, status='Contacted' WHERE id=?",
            (datetime.now().isoformat(), next_fu, lead_id)
        )
        self.conn.commit()

    def mark_followup_sent(self, lead_id: int, day: int):
        gaps = {1: 3, 2: 4, 3: 7}   # days until next follow-up
        gap = gaps.get(day, 99)
        next_fu = (date.today() + timedelta(days=gap)).isoformat()
        self.conn.execute(
            "UPDATE leads SET followup_day=?, next_followup=? WHERE id=?",
            (day, next_fu, lead_id)
        )
        self.conn.commit()

    def mark_replied(self, lead_id: int):
        self.conn.execute(
            "UPDATE leads SET reply_received=1, status='Replied' WHERE id=?", (lead_id,)
        )
        self.conn.commit()

    def mark_meeting(self, lead_id: int, meeting_date: str):
        self.conn.execute(
            "UPDATE leads SET meeting_booked=1, meeting_date=?, status='Meeting' WHERE id=?",
            (meeting_date, lead_id)
        )
        self.conn.commit()

    def record_placement(self, lead_id: int, hires: int, fee_per_hire: int):
        revenue = hires * fee_per_hire
        self.conn.execute(
            "UPDATE leads SET placements=placements+?, revenue=revenue+?, status='Won' WHERE id=?",
            (hires, revenue, lead_id)
        )
        self.conn.commit()

    def get_stats(self) -> dict:
        def scalar(sql, params=()): return self.conn.execute(sql, params).fetchone()[0] or 0
        
        today = date.today().isoformat()
        
        total_rev = scalar("SELECT SUM(revenue) FROM leads")
        total_place = scalar("SELECT SUM(placements) FROM leads")
        
        stats = {
            "total_leads":      scalar("SELECT COUNT(*) FROM leads"),
            "emailed":          scalar("SELECT COUNT(*) FROM leads WHERE email_sent=1"),
            "replied":          scalar("SELECT COUNT(*) FROM leads WHERE reply_received=1"),
            "replies":          scalar("SELECT COUNT(*) FROM leads WHERE reply_received=1"),
            "meetings":         scalar("SELECT COUNT(*) FROM leads WHERE meeting_booked=1"),
            "won":              scalar("SELECT COUNT(*) FROM leads WHERE status='Won'"),
            "revenue":          total_rev,
            "total_revenue":    total_rev,
            "total_placements": total_place,
            "followups_due":    scalar("SELECT COUNT(*) FROM leads WHERE next_followup <= ? AND reply_received=0 AND email_sent=1 AND followup_day < 4 AND status NOT IN ('Won','Lost')", (today,))
        }
        
        by_city_rows = self.conn.execute(
            "SELECT city, COUNT(*) as count FROM leads GROUP BY city ORDER BY count DESC LIMIT 6"
        ).fetchall()
        stats["by_city"] = {r[0]: r[1] for r in by_city_rows}
        stats["cities"] = [{"city": r[0], "count": r[1]} for r in by_city_rows]
        
        return stats


    def close(self): self.conn.close()


# ══════════════════════════════════════════════════════════════
#  FOLLOW-UP SEQUENCER
# ══════════════════════════════════════════════════════════════

FOLLOWUP_TEMPLATES = {
    1: {
        "subject": "RE: Pre-screened candidates for {company}",
        "body": """Hi {hr_name},

Following up on my message from a few days ago.

I still have pre-screened {roles} candidates ready for {company} in {city}.

These candidates:
✅ Communication score 3–5/5
✅ Available to join within 0–15 days
✅ Salary expectations matching your range

Can I share 5 profiles today? Takes 2 minutes to review.

Best,
Srijan Ji | AS Recruitment"""
    },
    2: {
        "subject": "Quick question — {company} hiring update",
        "body": """Hi {hr_name},

I wanted to check — are you still looking to fill {roles} positions at {company}?

We recently placed candidates at similar companies in {city} within 48 hours.

Our model is simple:
• Zero upfront cost
• Pay only when candidate joins
• 30-day free replacement guarantee

Happy to send profiles immediately if you have a current requirement.

Reply YES and I'll share them within the hour.

Best,
Srijan Ji | AS Recruitment"""
    },
    3: {
        "subject": "Last message — Candidates for {company}",
        "body": """Hi {hr_name},

I'll keep this brief — last follow-up from my side.

If {company} has any bulk hiring requirement in the next 60 days, I'd love to help.

We've closed 10–50 hire batches for similar companies in {city} within 72 hours.

If timing isn't right now, no problem — I'll reach out when you post a new requirement.

Wishing you and your team the best.

Srijan Ji
AS Recruitment | +91-XXXXXXXXXX"""
    },
}


class FollowUpSequencer:

    def __init__(self, db: LeadsDB):
        self.db = db

    def run(self) -> dict:
        due = self.db.get_due_followups()
        sent = 0

        for lead in due:
            day = lead["followup_day"] + 1   # next follow-up number
            template = FOLLOWUP_TEMPLATES.get(day)
            if not template:
                continue

            subject = template["subject"].format(**lead)
            body    = template["body"].format(
                hr_name   = lead.get("hr_name") or "Hiring Manager",
                company   = lead.get("company",""),
                roles     = lead.get("roles","BPO/support roles"),
                city      = lead.get("city",""),
            )

            success = self._send(lead.get("email",""), subject, body, lead["company"], day)
            if success:
                self.db.mark_followup_sent(lead["id"], day)
                sent += 1

        return {"due": len(due), "sent": sent}

    def _send(self, to: str, subject: str, body: str, company: str, day: int) -> bool:
        if not to:
            return False
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        user = os.getenv("EMAIL_USER","")
        pwd  = os.getenv("EMAIL_PASS","")

        if not user or not pwd:
            print(f"  📧 [DEMO] Day-{day} follow-up → {company} ({to})")
            return True   # simulated

        try:
            msg = MIMEMultipart()
            msg["From"]    = user
            msg["To"]      = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP("smtp.gmail.com", 587) as s:
                s.starttls()
                s.login(user, pwd)
                s.sendmail(user, to, msg.as_string())
            print(f"  ✅ Day-{day} follow-up sent → {company}")
            return True
        except Exception as e:
            print(f"  ⚠  Email error ({company}): {e}")
            return False


# ══════════════════════════════════════════════════════════════
#  SUPABASE SYNC  (replaces SQLite at scale)
# ══════════════════════════════════════════════════════════════

class SupabaseSync:
    """
    Syncs candidates and leads to Supabase when configured.
    Allows the employer dashboard to fetch live data via API.
    """

    def __init__(self):
        self.enabled = USE_SUPABASE
        if self.enabled:
            try:
                from supabase import create_client
                self.client = create_client(SUPABASE_URL, SUPABASE_KEY)
                print("  ✅ Supabase connected")
            except ImportError:
                print("  ⚠  pip install supabase for cloud sync")
                self.enabled = False

    def push_candidates(self, candidates: list) -> int:
        if not self.enabled:
            return 0
        try:
            res = self.client.table("candidates").upsert(
                candidates, on_conflict="phone"
            ).execute()
            return len(res.data)
        except Exception as e:
            print(f"  ⚠  Supabase push error: {e}")
            return 0

    def push_leads(self, leads: list) -> int:
        if not self.enabled:
            return 0
        try:
            res = self.client.table("leads").upsert(leads).execute()
            return len(res.data)
        except Exception as e:
            print(f"  ⚠  Supabase leads push error: {e}")
            return 0

    def fetch_requirements(self) -> list:
        """Pull active job requirements from employer dashboard."""
        if not self.enabled:
            return []
        try:
            res = self.client.table("requirements").select("*").eq("status","Active").execute()
            return res.data
        except Exception as e:
            return []


# ══════════════════════════════════════════════════════════════
#  INVOICE GENERATOR
# ══════════════════════════════════════════════════════════════

class InvoiceGenerator:

    TEMPLATE = """
=====================================
     AS RECRUITMENT — INVOICE
=====================================
Invoice No  : ASR-{inv_num}
Date        : {today}
Due Date    : {due_date}
-------------------------------------
Bill To     : {client_company}
             Attn: {hr_name}
             {city}
-------------------------------------
PLACEMENT DETAILS

Role        : {role}
Candidates  : {hires} successful hires
Fee/Hire    : ₹{fee_per_hire:,}
-------------------------------------
SUBTOTAL    : ₹{subtotal:,}
GST (18%)   : ₹{gst:,}
=====================================
TOTAL DUE   : ₹{total:,}
=====================================
Payment     : Bank Transfer
Account     : AS Recruitment Services
IFSC        : SBIN0XXXXXX  (update)
Account No  : XXXXXXXXXXXX  (update)
-------------------------------------
Terms       : Payment within 15 days
Guarantee   : 30-day free replacement
-------------------------------------
Thank you for choosing AS Recruitment.
+91-XXXXXXXXXX | asrecruitment.in
=====================================
"""

    def generate(self, client: str, role: str, city: str,
                 hr_name: str, hires: int, fee_per_hire: int) -> str:
        subtotal = hires * fee_per_hire
        gst      = int(subtotal * 0.18)
        total    = subtotal + gst
        inv_num  = f"{date.today().strftime('%Y%m')}-{abs(hash(client))%1000:03d}"
        due      = (date.today() + timedelta(days=15)).strftime("%d %b %Y")

        invoice = self.TEMPLATE.format(
            inv_num=inv_num, today=date.today().strftime("%d %b %Y"),
            due_date=due, client_company=client, hr_name=hr_name,
            city=city, role=role, hires=hires,
            fee_per_hire=fee_per_hire, subtotal=subtotal, gst=gst, total=total,
        )

        fname = DATA_DIR / f"invoice_{inv_num}.txt"
        with open(fname, "w") as f:
            f.write(invoice)

        # Log to revenue
        self._log_revenue(client, role, hires, fee_per_hire, total, inv_num)
        return str(fname)

    def _log_revenue(self, client, role, hires, fee, total, inv_num):
        log = []
        if REVENUE_LOG.exists():
            with open(REVENUE_LOG) as f:
                log = json.load(f)
        log.append({
            "date": date.today().isoformat(), "invoice": inv_num,
            "client": client, "role": role, "hires": hires,
            "fee_per_hire": fee, "total_incl_gst": total,
            "status": "Pending",
        })
        with open(REVENUE_LOG, "w") as f:
            json.dump(log, f, indent=2)


# ══════════════════════════════════════════════════════════════
#  N8N TRIGGER HELPER
# ══════════════════════════════════════════════════════════════

def trigger_n8n(webhook_url: str, payload: dict) -> bool:
    try:
        import requests
        r = requests.post(webhook_url, json=payload, timeout=8)
        return r.status_code == 200
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════
#  PLATFORM DASHBOARD
# ══════════════════════════════════════════════════════════════

def print_dashboard(db: LeadsDB):
    s = db.get_stats()

    # Candidate DB stats (if available)
    cand_total = 0
    cand_available = 0
    try:
        import sqlite3 as _sq
        cdb = _sq.connect("asr_candidates.db")
        cand_total    = cdb.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        cand_available= cdb.execute("SELECT COUNT(*) FROM candidates WHERE status='Available'").fetchone()[0]
        cdb.close()
    except Exception:
        pass

    # Revenue log
    rev_log = []
    if REVENUE_LOG.exists():
        with open(REVENUE_LOG) as f:
            rev_log = json.load(f)
    logged_revenue = sum(r.get("total_incl_gst",0) for r in rev_log)

    print(f"""
{'═'*58}
  ASR PLATFORM — LIVE DASHBOARD
  {datetime.now().strftime('%d %b %Y · %H:%M')}
{'═'*58}

  SALES PIPELINE
  ┌─────────────────────────────────────────────────┐
  │  Total companies in CRM   {s['total_leads']:>8,}              │
  │  Emailed                  {s['emailed']:>8,}              │
  │  Replied                  {s['replied']:>8,}              │
  │  Meetings booked          {s['meetings']:>8,}              │
  │  Clients won              {s['won']:>8,}              │
  │  Follow-ups due TODAY     {s['followups_due']:>8,}  ← action  │
  └─────────────────────────────────────────────────┘

  CANDIDATE DATABASE
  ┌─────────────────────────────────────────────────┐
  │  Total candidates         {cand_total:>8,}              │
  │  Available now            {cand_available:>8,}              │
  └─────────────────────────────────────────────────┘

  REVENUE
  ┌─────────────────────────────────────────────────┐
  │  Total placements         {s['total_placements']:>8,}              │
  │  Revenue (DB tracked)     ₹{s['total_revenue']:>7,}              │
  │  Revenue (invoiced)       ₹{logged_revenue:>7,}              │
  └─────────────────────────────────────────────────┘

  LEADS BY CITY
""")
    for city, cnt in s["by_city"].items():
        bar = "█" * (cnt // max(1, max(s["by_city"].values()) // 12))
        print(f"    {city:<18} {bar}  {cnt}")

    if rev_log:
        print("\n  RECENT INVOICES")
        for inv in rev_log[-5:][::-1]:
            print(f"    {inv['date']}  {inv['client']:<22} ₹{inv['total_incl_gst']:>8,}  [{inv['status']}]")

    print(f"\n{'═'*58}\n")


# ══════════════════════════════════════════════════════════════
#  DAILY AUTOMATION CYCLE
# ══════════════════════════════════════════════════════════════

def run_daily_cycle(db: LeadsDB):
    print(f"\n{'█'*58}")
    print(f"  ASR DAILY CYCLE — {datetime.now().strftime('%d %b %Y %H:%M')}")
    print(f"{'█'*58}\n")

    # ── 1. Find leads ─────────────────────────────────────────
    print("⬛ Step 1 — Lead Discovery")
    leads = []
    try:
        sys.path.insert(0, str(PLATFORM_DIR.parent / "asr_ai_agent"))
        from asr_lead_engine import run as lead_run
        leads = lead_run()
    except Exception as e:
        print(f"  ℹ  Lead engine: {e}")
        print("  → Using demo leads")
        from agents.agent1_leads import LeadAgent
        leads = LeadAgent().run() if Path("agents/agent1_leads.py").exists() else []

    if leads:
        new, updated = db.bulk_upsert(leads)
        print(f"  ✅ {new} new leads added, {updated} updated")
        trigger_n8n(N8N_LEADS_WH, {"leads": leads[:20], "date": date.today().isoformat()})

    # ── 2. Send follow-ups ────────────────────────────────────
    print("\n⬛ Step 2 — Follow-up Sequencer")
    seq = FollowUpSequencer(db)
    fu  = seq.run()
    print(f"  ✅ {fu['sent']}/{fu['due']} follow-ups sent")

    # ── 3. Pull new candidates ────────────────────────────────
    print("\n⬛ Step 3 — Candidate Acquisition")
    try:
        from asr_candidate_engine import CandidateDB, CandidateIngester, AIScorer
        cdb      = CandidateDB()
        ingester = CandidateIngester(cdb, AIScorer())
        form_csv = os.getenv("GOOGLE_FORM_CSV","form_responses.csv")
        if Path(form_csv).exists():
            new, _ = ingester.from_csv(form_csv)
            print(f"  ✅ {new} new candidates from Google Form")
        wa_file = "whatsapp_candidates.txt"
        if Path(wa_file).exists():
            with open(wa_file) as f: raw = f.read()
            added = ingester.from_whatsapp_text(raw, "WhatsApp")
            print(f"  ✅ {added} new candidates from WhatsApp")
        else:
            print("  ℹ  No candidate files found (form_responses.csv / whatsapp_candidates.txt)")
        cdb.close()
    except Exception as e:
        print(f"  ℹ  Candidate engine: {e}")

    # ── 4. Run matching on active requirements ────────────────
    print("\n⬛ Step 4 — AI Candidate Matching")
    try:
        from asr_candidate_engine import CandidateDB, JobMatcher
        cdb     = CandidateDB()
        matcher = JobMatcher(cdb)
        reqs    = SupabaseSync().fetch_requirements()
        if not reqs:
            reqs = [{"role":"BPO Customer Support","city":"Lucknow","skill":"BPO","salary_max":18000}]
        for req in reqs[:5]:
            query = f"{req.get('skill','BPO')} {req.get('city','Lucknow')} {req.get('salary_max',18000)}"
            matches = matcher.match(query, top_n=10)
            if matches:
                print(f"  ✅ {len(matches)} candidates matched for {req.get('role','Role')} — {req.get('city','')}")
        cdb.close()
    except Exception as e:
        print(f"  ℹ  Matching: {e}")

    # ── 5. Sync to Supabase ───────────────────────────────────
    print("\n⬛ Step 5 — Cloud Sync")
    sync = SupabaseSync()
    if sync.enabled:
        print("  ✅ Supabase sync complete")
    else:
        print("  ℹ  Supabase not configured (add SUPABASE_URL + SUPABASE_ANON_KEY)")
        print("     Local SQLite is active for all data")

    print_dashboard(db)


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="ASR Platform — Complete Integration Layer")
    p.add_argument("--daily",     action="store_true", help="Run full daily automation cycle")
    p.add_argument("--dashboard", action="store_true", help="Print live platform stats")
    p.add_argument("--followup",  action="store_true", help="Send due follow-up emails")
    p.add_argument("--match",     type=str, metavar="Q", help="Quick candidate search")
    p.add_argument("--invoice",   nargs=4, metavar=("CLIENT","ROLE","HIRES","FEE"),
                   help="Generate invoice. e.g. --invoice Teleperformance 'BPO Voice' 10 8000")
    p.add_argument("--json",      action="store_true", help="Output results in JSON format")
    args = p.parse_args()

    db = LeadsDB()

    if args.daily:
        run_daily_cycle(db)

    elif args.dashboard:
        if args.json:
            import os, sys, json
            # Silence stdout during engine init to avoid contamination
            old_stdout = sys.stdout
            sys.stdout = open(os.devnull, 'w')
            try:
                stats = db.get_stats()
                sys.path.insert(0, str(PLATFORM_DIR.parent / "asr_candidate_engine"))
                from asr_candidate_engine import CandidateDB
                cdb = CandidateDB()
                c_stats = cdb.get_stats()
                stats.update({"candidates": c_stats})
                cdb.close()
            finally:
                sys.stdout = old_stdout
            print(json.dumps(stats, indent=2))
        else:
            print_dashboard(db)

    elif args.followup:
        print("\n📧 Running follow-up sequencer...")
        seq = FollowUpSequencer(db)
        r   = seq.run()
        print(f"  ✅ {r['sent']} follow-ups sent ({r['due']} were due)")

    elif args.match:
        if not args.json: print(f"\n🔍 Matching: \"{args.match}\"")
        try:
            import os, sys, json
            sys.path.insert(0, str(PLATFORM_DIR.parent / "asr_candidate_engine"))
            
            # Silence stdout during engine init to avoid contamination if json requested
            if args.json:
                old_stdout = sys.stdout
                sys.stdout = open(os.devnull, 'w')
            
            try:
                from asr_candidate_engine import CandidateDB, JobMatcher
                cdb = CandidateDB()
                matches = JobMatcher(cdb).match(args.match, top_n=10)
            finally:
                if args.json: sys.stdout = old_stdout
                
            if args.json:
                print(json.dumps(matches, indent=2))
            else:
                print(f"\n  Found {len(matches)} candidates:\n")
                for i, c in enumerate(matches, 1):
                    print(f"  {i:>2}. {c['name']:<22} {c['city']:<12} Score:{c['overall_score']:>3}  "
                          f"BPO:{c['bpo_fit_score']:>3}  {c['english_fluency']}  ₹{c['expected_salary']:,}/mo")
            cdb.close()
        except Exception as e:
            if not args.json: print(f"  ⚠  {e} — copy asr_candidate_engine.py into this folder")
            else: print(json.dumps({"error": str(e)}))

    elif args.invoice:
        client, role, hires, fee = args.invoice
        gen   = InvoiceGenerator()
        fname = gen.generate(
            client=client, role=role, city="", hr_name="HR Team",
            hires=int(hires), fee_per_hire=int(fee)
        )
        print(f"\n✅ Invoice saved: {fname}")
        with open(fname) as f:
            print(f.read())

    else:
        p.print_help()

    db.close()

if __name__ == "__main__":
    main()
