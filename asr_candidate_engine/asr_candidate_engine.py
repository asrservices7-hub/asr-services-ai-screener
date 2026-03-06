"""
ASR Candidate Database Engine
================================
Builds and manages your candidate inventory — the asset that
turns you from a recruiter into a hiring platform.

What this does:
  1. Ingests candidates from 6 sources (CSV, Naukri, WhatsApp data, walk-ins, referrals, forms)
  2. Deduplicates by phone number (the unique identifier in India)
  3. AI-scores every candidate on 5 dimensions (0–100 overall)
  4. Stores in SQLite (portable, no server needed — runs on your laptop)
  5. Matches candidates to job requirements in seconds
  6. Syncs top candidates to your Google Sheet CANDIDATE_POOL tab
  7. Exports shortlists as CSV / WhatsApp-ready message batches

Usage:
  python3 asr_candidate_engine.py --ingest-csv my_candidates.csv
  python3 asr_candidate_engine.py --match "BPO voice Lucknow night shift 13000-18000"
  python3 asr_candidate_engine.py --stats
  python3 asr_candidate_engine.py --sync-sheets
  python3 asr_candidate_engine.py --export-whatsapp 20
"""

import os
import re
import csv
import json
import time
import sqlite3
import hashlib
import argparse
from datetime import datetime, date
from typing import Optional
from dataclasses import dataclass, asdict, field

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Optional AI scoring ──────────────────────────────────────
try:
    from langchain_openai import ChatOpenAI
    from langchain.prompts import PromptTemplate
    from langchain.chains import LLMChain
    AI_AVAILABLE = bool(os.getenv("OPENAI_API_KEY"))
except ImportError:
    AI_AVAILABLE = False

# ── Optional Google Sheets sync ──────────────────────────────
try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════

CONFIG = {
    "db_path":           "asr_candidates.db",
    "google_sheet_id":   os.getenv("GOOGLE_SHEET_ID", ""),
    "google_creds_json": os.getenv("GOOGLE_CREDS_JSON", "credentials.json"),
    "sheet_tab":         "CANDIDATE_POOL",
    "ai_model":          "gpt-4o-mini",

    # Scoring weights (must sum to 100)
    "score_weights": {
        "communication":     30,   # most important for BPO
        "experience_match":  25,
        "location_match":    20,
        "availability":      15,
        "salary_fit":        10,
    },

    # Target markets (for location scoring)
    "target_cities": ["Lucknow", "Kanpur", "Noida", "Jaipur", "Indore"],

    # BPO-specific thresholds
    "bpo_salary_range": (10000, 25000),

    # Minimum score to be marked "Active"
    "active_threshold": 50,
}


# ═══════════════════════════════════════════════════════════════
#  CANDIDATE DATA MODEL
# ═══════════════════════════════════════════════════════════════

@dataclass
class Candidate:
    # ── Identity (dedup key = phone) ─────────────────────────
    candidate_id:          str  = ""
    name:                  str  = ""
    phone:                 str  = ""
    email:                 str  = ""

    # ── Location ─────────────────────────────────────────────
    city:                  str  = ""
    state:                 str  = ""
    willing_to_relocate:   str  = "No"

    # ── Professional profile ──────────────────────────────────
    primary_skill:         str  = ""          # BPO/Voice, IT/Tech, Hospital, Sales, Retail, SME
    secondary_skill:       str  = ""
    preferred_role:        str  = ""
    total_experience_yrs:  float = 0.0
    last_company:          str  = ""
    current_salary:        int  = 0
    expected_salary:       int  = 0
    notice_period_days:    int  = 0

    # ── Job readiness ─────────────────────────────────────────
    available_to_join:     str  = "Yes"
    night_shift_ok:        str  = "No"
    english_fluency:       str  = "Basic"     # Basic / Intermediate / Fluent / Proficient
    interview_ready:       str  = "Yes"

    # ── AI scores ─────────────────────────────────────────────
    communication_score:   int  = 0           # 0–30
    experience_score:      int  = 0           # 0–25
    location_score:        int  = 0           # 0–20
    availability_score:    int  = 0           # 0–15
    salary_score:          int  = 0           # 0–10
    overall_score:         int  = 0           # 0–100
    bpo_fit_score:         int  = 0           # 0–100 specialised BPO score

    # ── Source tracking ───────────────────────────────────────
    source:                str  = ""          # WhatsApp / Naukri / LinkedIn / Walk-in / Referral / Form / CSV
    source_detail:         str  = ""          # e.g. "WhatsApp Group: Lucknow Jobs"
    referred_by:           str  = ""

    # ── Status ───────────────────────────────────────────────
    status:                str  = "Available" # Available / Submitted / Interviewing / Placed / Cold / Inactive
    submitted_to:          str  = ""
    placed_at:             str  = ""
    placement_date:        str  = ""
    placement_fee:         int  = 0

    # ── Data quality ─────────────────────────────────────────
    resume_link:           str  = ""
    linkedin_url:          str  = ""
    profile_verified:      str  = "No"
    last_contacted:        str  = ""
    notes:                 str  = ""

    # ── Timestamps ───────────────────────────────────────────
    date_added:            str  = field(default_factory=lambda: date.today().isoformat())
    last_updated:          str  = field(default_factory=lambda: datetime.now().isoformat())


# ═══════════════════════════════════════════════════════════════
#  DATABASE LAYER
# ═══════════════════════════════════════════════════════════════

class CandidateDB:
    """SQLite-based candidate store. Portable, no server needed."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS candidates (
        candidate_id          TEXT PRIMARY KEY,
        name                  TEXT,
        phone                 TEXT UNIQUE,
        email                 TEXT,
        city                  TEXT,
        state                 TEXT,
        willing_to_relocate   TEXT,
        primary_skill         TEXT,
        secondary_skill       TEXT,
        preferred_role        TEXT,
        total_experience_yrs  REAL,
        last_company          TEXT,
        current_salary        INTEGER,
        expected_salary       INTEGER,
        notice_period_days    INTEGER,
        available_to_join     TEXT,
        night_shift_ok        TEXT,
        english_fluency       TEXT,
        interview_ready       TEXT,
        communication_score   INTEGER,
        experience_score      INTEGER,
        location_score        INTEGER,
        availability_score    INTEGER,
        salary_score          INTEGER,
        overall_score         INTEGER,
        bpo_fit_score         INTEGER,
        source                TEXT,
        source_detail         TEXT,
        referred_by           TEXT,
        status                TEXT,
        submitted_to          TEXT,
        placed_at             TEXT,
        placement_date        TEXT,
        placement_fee         INTEGER,
        resume_link           TEXT,
        linkedin_url          TEXT,
        profile_verified      TEXT,
        last_contacted        TEXT,
        notes                 TEXT,
        date_added            TEXT,
        last_updated          TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_city          ON candidates(city);
    CREATE INDEX IF NOT EXISTS idx_skill         ON candidates(primary_skill);
    CREATE INDEX IF NOT EXISTS idx_score         ON candidates(overall_score DESC);
    CREATE INDEX IF NOT EXISTS idx_status        ON candidates(status);
    CREATE INDEX IF NOT EXISTS idx_bpo_fit       ON candidates(bpo_fit_score DESC);
    CREATE INDEX IF NOT EXISTS idx_night_shift   ON candidates(night_shift_ok);
    CREATE INDEX IF NOT EXISTS idx_exp_salary    ON candidates(expected_salary);
    """

    def __init__(self, db_path: str = CONFIG["db_path"]):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(self.SCHEMA)
        self.conn.commit()
        print(f"✅ Database: {db_path}  ({self.count()} candidates)")

    def _generate_id(self, phone: str) -> str:
        """Stable ID based on phone number."""
        return "CND-" + hashlib.md5(phone.encode()).hexdigest()[:8].upper()

    def _clean_phone(self, phone: str) -> str:
        """Normalise to 10-digit Indian mobile."""
        digits = re.sub(r"\D", "", str(phone))
        if digits.startswith("91") and len(digits) == 12:
            digits = digits[2:]
        return digits[-10:] if len(digits) >= 10 else digits

    def upsert(self, candidate: Candidate) -> tuple[bool, str]:
        """Insert or update. Returns (is_new, candidate_id)."""
        phone = self._clean_phone(candidate.phone)
        if not phone or len(phone) < 10:
            return False, ""

        candidate.phone        = phone
        candidate.candidate_id = self._generate_id(phone)
        candidate.last_updated = datetime.now().isoformat()

        fields = [f for f in Candidate.__dataclass_fields__]
        values = [getattr(candidate, f) for f in fields]
        placeholders = ", ".join(["?"] * len(fields))
        col_names    = ", ".join(fields)
        updates      = ", ".join([f"{f}=excluded.{f}" for f in fields if f != "candidate_id"])

        sql = f"""
            INSERT INTO candidates ({col_names})
            VALUES ({placeholders})
            ON CONFLICT(phone) DO UPDATE SET {updates}
        """
        cur = self.conn.execute(sql, values)
        self.conn.commit()
        is_new = cur.rowcount == 1
        return is_new, candidate.candidate_id

    def search(self,
               city: Optional[str]       = None,
               skill: Optional[str]      = None,
               max_salary: Optional[int] = None,
               min_salary: Optional[int] = None,
               night_shift: Optional[bool] = None,
               available_only: bool      = True,
               min_score: int            = 0,
               min_english: Optional[str] = None,
               limit: int                = 50) -> list[dict]:
        """Flexible candidate search — returns list of dicts sorted by score."""

        conditions = ["overall_score >= ?"]
        params: list = [min_score]

        if city:
            conditions.append("(city LIKE ? OR willing_to_relocate = 'Yes')")
            params.append(f"%{city}%")
        if skill:
            conditions.append("(primary_skill LIKE ? OR secondary_skill LIKE ? OR preferred_role LIKE ?)")
            params += [f"%{skill}%", f"%{skill}%", f"%{skill}%"]
        if max_salary:
            conditions.append("expected_salary <= ?")
            params.append(max_salary)
        if min_salary:
            conditions.append("expected_salary >= ?")
            params.append(min_salary)
        if night_shift is not None:
            conditions.append("night_shift_ok = ?")
            params.append("Yes" if night_shift else "No")
        if available_only:
            conditions.append("status IN ('Available', 'Submitted')")
        if min_english:
            english_rank = {"Basic": 1, "Intermediate": 2, "Fluent": 3, "Proficient": 4}
            min_rank = english_rank.get(min_english, 1)
            placeholders = ",".join(["?" for _ in english_rank if english_rank[_] >= min_rank])
            eligible = [k for k, v in english_rank.items() if v >= min_rank]
            conditions.append(f"english_fluency IN ({','.join(['?']*len(eligible))})")
            params += eligible

        where = " AND ".join(conditions)
        sql = f"""
            SELECT * FROM candidates
            WHERE {where}
            ORDER BY overall_score DESC, bpo_fit_score DESC
            LIMIT ?
        """
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Database statistics for FOUNDER_CONTROL_ROOM."""
        stats = {}
        stats["total"]   = self._scalar("SELECT COUNT(*) FROM candidates")
        stats["active"]  = self._scalar("SELECT COUNT(*) FROM candidates WHERE status IN ('Available','Submitted','Interviewing')")
        stats["placed"]  = self._scalar("SELECT COUNT(*) FROM candidates WHERE status = 'Placed'")
        stats["avg_score"] = self._scalar("SELECT AVG(overall_score) FROM candidates") or 0

        # By city
        rows = self.conn.execute(
            "SELECT city, COUNT(*) as cnt FROM candidates GROUP BY city ORDER BY cnt DESC LIMIT 8"
        ).fetchall()
        stats["by_city"] = {r["city"]: r["cnt"] for r in rows}

        # By skill
        rows = self.conn.execute(
            "SELECT primary_skill, COUNT(*) as cnt FROM candidates GROUP BY primary_skill ORDER BY cnt DESC"
        ).fetchall()
        stats["by_skill"] = {r["primary_skill"]: r["cnt"] for r in rows}

        # By source
        rows = self.conn.execute(
            "SELECT source, COUNT(*) as cnt FROM candidates GROUP BY source ORDER BY cnt DESC"
        ).fetchall()
        stats["by_source"] = {r["source"]: r["cnt"] for r in rows}

        # Revenue potential
        placed_fees = self._scalar("SELECT SUM(placement_fee) FROM candidates WHERE placement_fee > 0") or 0
        stats["revenue_earned"] = placed_fees
        stats["pipeline_value"] = stats["active"] * 8000 * 0.12   # 12% placement rate × ₹8K

        # BPO-ready (score ≥ 70 + night shift)
        stats["bpo_ready"] = self._scalar(
            "SELECT COUNT(*) FROM candidates WHERE bpo_fit_score >= 70 AND available_to_join = 'Yes'"
        )
        return stats

    def mark_submitted(self, candidate_id: str, company: str):
        self.conn.execute(
            "UPDATE candidates SET status='Submitted', submitted_to=?, last_updated=? WHERE candidate_id=?",
            (company, datetime.now().isoformat(), candidate_id)
        )
        self.conn.commit()

    def mark_placed(self, candidate_id: str, company: str, fee: int):
        self.conn.execute(
            "UPDATE candidates SET status='Placed', placed_at=?, placement_fee=?, placement_date=?, last_updated=? WHERE candidate_id=?",
            (company, fee, date.today().isoformat(), datetime.now().isoformat(), candidate_id)
        )
        self.conn.commit()

    def count(self) -> int:
        return self._scalar("SELECT COUNT(*) FROM candidates") or 0

    def _scalar(self, sql: str, params: list = []):
        row = self.conn.execute(sql, params).fetchone()
        return row[0] if row else None

    def close(self):
        self.conn.close()


# ═══════════════════════════════════════════════════════════════
#  AI SCORING ENGINE
# ═══════════════════════════════════════════════════════════════

class AIScorer:
    """Scores candidates using rule-based logic (always) + optional LLM refinement."""

    def score(self, c: Candidate) -> Candidate:
        """Calculate all scores and attach to candidate object."""
        c.communication_score = self._score_communication(c)
        c.experience_score    = self._score_experience(c)
        c.location_score      = self._score_location(c)
        c.availability_score  = self._score_availability(c)
        c.salary_score        = self._score_salary(c)
        c.overall_score       = (
            c.communication_score +
            c.experience_score    +
            c.location_score      +
            c.availability_score  +
            c.salary_score
        )
        c.bpo_fit_score = self._score_bpo_fit(c)
        return c

    def _score_communication(self, c: Candidate) -> int:
        """0–30 points."""
        base = {"Basic": 10, "Intermediate": 18, "Fluent": 25, "Proficient": 30}
        score = base.get(c.english_fluency, 10)
        # Bonus for BPO/voice role preference
        if "bpo" in c.primary_skill.lower() or "voice" in c.primary_skill.lower():
            score = min(score + 3, 30)
        return score

    def _score_experience(self, c: Candidate) -> int:
        """0–25 points."""
        exp = c.total_experience_yrs
        if exp == 0:     return 12   # fresher — acceptable for BPO
        if exp <= 1:     return 18
        if exp <= 3:     return 22
        if exp <= 6:     return 25
        if exp <= 10:    return 23   # over-experienced for entry BPO
        return 18

    def _score_location(self, c: Candidate) -> int:
        """0–20 points."""
        if any(city.lower() == c.city.lower() for city in CONFIG["target_cities"]):
            return 20
        if c.willing_to_relocate == "Yes":
            return 12
        return 5

    def _score_availability(self, c: Candidate) -> int:
        """0–15 points."""
        score = 0
        if c.available_to_join == "Yes":  score += 8
        if c.notice_period_days == 0:     score += 5
        elif c.notice_period_days <= 15:  score += 3
        elif c.notice_period_days <= 30:  score += 1
        if c.interview_ready == "Yes":    score += 2
        return min(score, 15)

    def _score_salary(self, c: Candidate) -> int:
        """0–10 points based on market fit."""
        lo, hi = CONFIG["bpo_salary_range"]
        exp = c.expected_salary
        if exp == 0:          return 5    # unknown — neutral
        if lo <= exp <= hi:   return 10   # perfect fit
        if exp <= hi * 1.2:   return 7    # slightly above — negotiate
        if exp >= lo * 0.8:   return 8    # slightly below — easy to close
        return 3                          # too high/low

    def _score_bpo_fit(self, c: Candidate) -> int:
        """
        Specialised BPO fit score (0–100).
        Used specifically for BPO client shortlists.
        """
        score = 0
        # Communication (35%)
        comm_map = {"Basic": 15, "Intermediate": 25, "Fluent": 32, "Proficient": 35}
        score += comm_map.get(c.english_fluency, 15)
        # Night shift (25%)
        if c.night_shift_ok == "Yes":  score += 25
        elif c.night_shift_ok == "Flexible": score += 15
        # Salary fit for BPO range (20%)
        lo, hi = CONFIG["bpo_salary_range"]
        if c.expected_salary == 0:          score += 10
        elif lo <= c.expected_salary <= hi: score += 20
        elif c.expected_salary <= hi * 1.1: score += 13
        # Availability (20%)
        if c.available_to_join == "Yes":
            score += 10
            if c.notice_period_days == 0:    score += 10
            elif c.notice_period_days <= 15: score += 6
            elif c.notice_period_days <= 30: score += 3
        return min(score, 100)


# ═══════════════════════════════════════════════════════════════
#  JOB REQUIREMENT MATCHER
# ═══════════════════════════════════════════════════════════════

class JobMatcher:
    """
    Parse a natural-language job requirement string and return
    the best matching candidates from the database.
    """

    def __init__(self, db: CandidateDB):
        self.db = db

    def match(self, requirement: str, top_n: int = 10) -> list[dict]:
        """
        Parse requirement and search DB.
        Example: "BPO voice Lucknow night shift 13000-18000 fluent english"
        """
        req = self._parse_requirement(requirement)
        candidates = self.db.search(
            city          = req.get("city"),
            skill         = req.get("skill"),
            max_salary    = req.get("max_salary"),
            min_salary    = req.get("min_salary"),
            night_shift   = req.get("night_shift"),
            available_only= True,
            min_score     = 40,
            min_english   = req.get("min_english"),
            limit         = top_n * 3,   # fetch more, then re-rank
        )

        # Re-rank by BPO fit if BPO requirement
        if req.get("is_bpo"):
            candidates.sort(key=lambda x: x.get("bpo_fit_score", 0), reverse=True)
        
        return candidates[:top_n]

    def _parse_requirement(self, text: str) -> dict:
        text_lower = text.lower()
        req = {}

        # City detection
        for city in CONFIG["target_cities"]:
            if city.lower() in text_lower:
                req["city"] = city
                break

        # Skill / vertical detection
        skill_map = {
            "bpo": "BPO", "voice": "BPO", "call center": "BPO", "telecall": "BPO",
            "hospital": "Hospital", "nurse": "Hospital", "healthcare": "Hospital",
            "it": "IT", "developer": "IT", "python": "IT", "software": "IT",
            "sales": "Sales", "retail": "Retail", "teaching": "Coaching",
            "faculty": "Coaching",
        }
        for keyword, skill in skill_map.items():
            if keyword in text_lower:
                req["skill"] = skill
                req["is_bpo"] = (skill == "BPO")
                break

        # Salary range
        salary_match = re.findall(r"(\d+)[\s-]*(\d+)?(?:k|000)?", text)
        salaries = []
        for m in salary_match:
            for v in m:
                if v:
                    n = int(v)
                    if n < 200:    n *= 1000   # e.g. "15k" → 15000
                    if 5000 <= n <= 200000:
                        salaries.append(n)
        if len(salaries) >= 2:
            req["min_salary"] = min(salaries[:2])
            req["max_salary"] = max(salaries[:2])
        elif len(salaries) == 1:
            req["max_salary"] = salaries[0]

        # Night shift
        if "night" in text_lower:
            req["night_shift"] = True

        # English level
        if "fluent" in text_lower or "excellent" in text_lower:
            req["min_english"] = "Fluent"
        elif "intermediate" in text_lower:
            req["min_english"] = "Intermediate"

        return req


# ═══════════════════════════════════════════════════════════════
#  INGESTION SOURCES
# ═══════════════════════════════════════════════════════════════

class CandidateIngester:
    """Handles bulk import from multiple sources into the DB."""

    def __init__(self, db: CandidateDB, scorer: AIScorer):
        self.db     = db
        self.scorer = scorer

    def from_csv(self, filepath: str) -> tuple[int, int]:
        """
        Import from CSV. Flexible column mapping — handles both
        ASR sheet exports and raw Naukri/Indeed CSV downloads.

        Returns (new_count, updated_count).
        """
        new = updated = 0
        COLUMN_MAP = {
            # ASR sheet names → Candidate fields
            "candidate name": "name", "name": "name",
            "phone": "phone", "mobile": "phone", "contact": "phone",
            "email": "email",
            "city": "city", "location": "city",
            "skill": "primary_skill", "primary skill": "primary_skill",
            "skill vertical": "primary_skill", "vertical": "primary_skill",
            "experience": "total_experience_yrs", "exp (yrs)": "total_experience_yrs",
            "experience (years)": "total_experience_yrs", "experience_yrs": "total_experience_yrs",
            "current salary": "current_salary", "current salary (₹)": "current_salary",
            "expected salary": "expected_salary", "expected salary (₹)": "expected_salary",
            "english fluency": "english_fluency", "english": "english_fluency",
            "ready to join": "available_to_join", "available": "available_to_join",
            "night shift": "night_shift_ok",
            "notice period": "notice_period_days", "notice period (days)": "notice_period_days",
            "source": "source", "referred by": "referred_by",
            "linkedin": "linkedin_url", "linkedin url": "linkedin_url",
            "resume link": "resume_link",
            "notes": "notes", "status": "status",
        }
        with open(filepath, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                c = Candidate(source="CSV", source_detail=filepath)
                for csv_col, value in row.items():
                    field_name = COLUMN_MAP.get(csv_col.strip().lower())
                    if field_name and value and value.strip():
                        v = value.strip()
                        # Type coercions
                        if field_name in ("total_experience_yrs",):
                            try: v = float(re.sub(r"[^0-9.]", "", v))
                            except: v = 0.0
                        elif field_name in ("current_salary", "expected_salary", "notice_period_days", "placement_fee"):
                            try: v = int(re.sub(r"[^0-9]", "", v))
                            except: v = 0
                        setattr(c, field_name, v)
                if not c.name or not c.phone:
                    continue
                c = self.scorer.score(c)
                is_new, _ = self.db.upsert(c)
                if is_new: new += 1
                else: updated += 1
        print(f"  CSV import: {new} new, {updated} updated from {filepath}")
        return new, updated

    def from_whatsapp_text(self, raw_text: str, group_name: str = "WhatsApp Group") -> int:
        """
        Parse unstructured WhatsApp candidate messages.
        Format expected per candidate block:
          Name: Priya Verma
          Phone: 9876543210
          City: Lucknow
          Skill: BPO
          Salary: 15000
          English: Fluent
          Night shift: Yes
        Blocks separated by blank lines or '---'
        """
        added = 0
        blocks = re.split(r"\n(?:---+|\n)", raw_text.strip())
        for block in blocks:
            if not block.strip():
                continue
            c = Candidate(source="WhatsApp", source_detail=group_name)
            lines = block.strip().splitlines()
            for line in lines:
                if ":" not in line: continue
                key, _, val = line.partition(":")
                key = key.strip().lower(); val = val.strip()
                if not val: continue
                if key in ("name",):              c.name = val
                elif key in ("phone", "mobile"): c.phone = val
                elif key in ("city",):            c.city = val
                elif key in ("skill", "role"):    c.primary_skill = val
                elif key in ("salary", "expected salary"):
                    try: c.expected_salary = int(re.sub(r"[^0-9]", "", val))
                    except: pass
                elif key in ("english",):         c.english_fluency = val
                elif key in ("night shift", "night"):
                    c.night_shift_ok = "Yes" if val.lower() in ("yes","y","ok") else "No"
                elif key in ("experience", "exp"):
                    try: c.total_experience_yrs = float(re.sub(r"[^0-9.]","",val))
                    except: pass
            if c.name and c.phone:
                c = self.scorer.score(c)
                is_new, _ = self.db.upsert(c)
                if is_new: added += 1
        print(f"  WhatsApp import: {added} candidates added from '{group_name}'")
        return added

    def add_single(self, **kwargs) -> str:
        """Add a single candidate from walk-in or form registration."""
        c = Candidate(**{k: v for k, v in kwargs.items() if k in Candidate.__dataclass_fields__})
        c = self.scorer.score(c)
        is_new, cid = self.db.upsert(c)
        action = "Added" if is_new else "Updated"
        print(f"  {action}: {c.name} ({c.phone}) — Score: {c.overall_score}/100")
        return cid

    def generate_sample_database(self, count: int = 100) -> int:
        """
        Generates a realistic sample candidate database for testing.
        Removes the need for real data to start using the system.
        """
        import random
        NAMES = [
            "Priya Verma","Rohit Gupta","Megha Tiwari","Shailendra Verma","Riya Srivastava",
            "Satish Yadav","Ankita Dubey","Neha Gupta","Pallavi Singh","Deepak Kumar",
            "Gaurav Singh","Monika Verma","Pradeep Joshi","Ritika Bajpai","Rajeev Kumar",
            "Sunita Sharma","Manish Tiwari","Kavita Yadav","Amit Verma","Pooja Singh",
            "Sandeep Kumar","Divya Srivastava","Vikram Gupta","Nisha Pandey","Ajay Kumar",
            "Preeti Jain","Sanjay Yadav","Rekha Sharma","Mohit Singh","Swati Verma",
            "Rakesh Gupta","Meena Joshi","Vijay Kumar","Asha Tiwari","Suresh Verma",
            "Poonam Yadav","Naresh Singh","Geeta Srivastava","Hemant Kumar","Ritu Gupta",
        ]
        CITIES = CONFIG["target_cities"]
        SKILLS = ["BPO/Voice", "BPO/Voice", "BPO/Voice", "Sales", "Hospital/Health",
                  "IT/Tech", "Retail/Ops", "Coaching/Edu", "SME/Admin"]
        SOURCES = ["WhatsApp", "WhatsApp", "Naukri", "LinkedIn", "Walk-in",
                   "Referral", "Database", "Meta Ads", "Form Registration"]
        ENGLISH = ["Basic", "Intermediate", "Intermediate", "Fluent", "Proficient"]
        ROLES = {
            "BPO/Voice": ["Customer Support Executive", "Telecaller", "Voice Process Agent", "Night Shift Agent"],
            "Sales": ["Sales Executive", "Business Development Executive", "Field Sales"],
            "Hospital/Health": ["Staff Nurse", "GNM Nurse", "Lab Technician", "Billing Executive"],
            "IT/Tech": ["Python Developer", "React Developer", "System Admin", "Tech Support"],
            "Retail/Ops": ["Store Manager", "Floor Supervisor", "Visual Merchandiser"],
            "Coaching/Edu": ["Math Faculty", "Physics Teacher", "English Trainer"],
            "SME/Admin": ["Accountant", "Data Entry Operator", "Office Admin"],
        }

        added = 0
        used_phones = set()
        for i in range(count):
            phone = f"9{''.join([str(random.randint(0,9)) for _ in range(9)])}"
            while phone in used_phones:
                phone = f"9{''.join([str(random.randint(0,9)) for _ in range(9)])}"
            used_phones.add(phone)

            skill = random.choice(SKILLS)
            exp   = round(random.uniform(0, 8), 1)
            base_sal = {"BPO/Voice": 14000, "Sales": 16000, "Hospital/Health": 25000,
                        "IT/Tech": 50000, "Retail/Ops": 14000, "Coaching/Edu": 20000, "SME/Admin": 18000}
            curr = random.randint(int(base_sal.get(skill,14000)*0.8), int(base_sal.get(skill,14000)*1.1)) if exp > 0 else 0
            expected = random.randint(int(curr*1.05), int(curr*1.25)) if curr > 0 else random.randint(10000, 20000)

            c = Candidate(
                name               = random.choice(NAMES),
                phone              = phone,
                city               = random.choice(CITIES),
                primary_skill      = skill,
                preferred_role     = random.choice(ROLES.get(skill, ["Executive"])),
                total_experience_yrs= exp,
                current_salary     = curr,
                expected_salary    = expected,
                english_fluency    = random.choice(ENGLISH),
                night_shift_ok     = random.choice(["Yes","No","No"]),
                notice_period_days = random.choice([0,0,15,30,30,45,60]),
                available_to_join  = random.choice(["Yes","Yes","Yes","No"]),
                willing_to_relocate= random.choice(["Yes","No","No"]),
                source             = random.choice(SOURCES),
                status             = random.choice(["Available","Available","Available","Submitted","Placed"]),
                interview_ready    = random.choice(["Yes","Yes","No"]),
            )
            c = self.scorer.score(c)
            is_new, _ = self.db.upsert(c)
            if is_new: added += 1
        print(f"  ✅ Sample database: {added} candidates generated")
        return added


# ═══════════════════════════════════════════════════════════════
#  GOOGLE SHEETS SYNC
# ═══════════════════════════════════════════════════════════════

class SheetsSyncer:
    """Syncs top candidates to CANDIDATE_POOL tab in your ASR sheet."""

    COLUMNS = [
        "candidate_id","name","primary_skill","city","total_experience_yrs",
        "current_salary","expected_salary","english_fluency","night_shift_ok",
        "available_to_join","notice_period_days","source","status",
        "overall_score","bpo_fit_score","submitted_to","phone","linkedin_url","notes",
    ]

    def __init__(self):
        self.sheet = None
        if not SHEETS_AVAILABLE or not CONFIG["google_sheet_id"]:
            return
        try:
            creds  = Credentials.from_service_account_file(
                CONFIG["google_creds_json"],
                scopes=["https://spreadsheets.google.com/feeds","https://www.googleapis.com/auth/drive"]
            )
            gc     = gspread.authorize(creds)
            wb     = gc.open_by_key(CONFIG["google_sheet_id"])
            try:
                self.sheet = wb.worksheet(CONFIG["sheet_tab"])
            except gspread.WorksheetNotFound:
                self.sheet = wb.add_worksheet(CONFIG["sheet_tab"], rows=2000, cols=20)
                self.sheet.append_row(self.COLUMNS)
            print(f"✅ Connected to Google Sheet: {CONFIG['sheet_tab']}")
        except Exception as e:
            print(f"⚠  Google Sheets: {e}")

    def sync(self, candidates: list[dict]) -> int:
        if not self.sheet:
            print("ℹ  Sheets not configured — skipping sync")
            return 0
        rows = [[str(c.get(col, "")) for col in self.COLUMNS] for c in candidates]
        # Clear existing data and rewrite (simple approach)
        self.sheet.clear()
        self.sheet.append_row(self.COLUMNS)
        for row in rows:
            self.sheet.append_row(row)
            time.sleep(0.3)
        print(f"✅ Synced {len(rows)} candidates to {CONFIG['sheet_tab']}")
        return len(rows)


# ═══════════════════════════════════════════════════════════════
#  REPORTING & EXPORTS
# ═══════════════════════════════════════════════════════════════

def print_stats(db: CandidateDB):
    stats = db.get_stats()
    print("\n" + "═"*55)
    print("  ASR CANDIDATE DATABASE — LIVE STATS")
    print("═"*55)
    print(f"  Total Candidates      : {stats['total']:,}")
    print(f"  Active / Available    : {stats['active']:,}")
    print(f"  Placed (Revenue Done) : {stats['placed']:,}")
    print(f"  Avg Quality Score     : {stats['avg_score']:.1f}/100")
    print(f"  BPO-Ready Now         : {stats['bpo_ready']:,}  (score≥70, available)")
    print(f"  Revenue Earned (₹)    : ₹{stats['revenue_earned']:,.0f}")
    print(f"  Pipeline Value (₹)    : ₹{stats['pipeline_value']:,.0f}")
    print("─"*55)
    print("  By City:")
    for city, cnt in stats["by_city"].items():
        bar = "█" * (cnt // max(1, max(stats["by_city"].values()) // 15))
        print(f"    {city:<18} {bar}  {cnt}")
    print("─"*55)
    print("  By Skill:")
    for skill, cnt in stats["by_skill"].items():
        print(f"    {skill:<22} {cnt}")
    print("─"*55)
    print("  By Source:")
    for source, cnt in stats["by_source"].items():
        print(f"    {source:<22} {cnt}")
    print("═"*55 + "\n")


def export_shortlist_csv(candidates: list[dict], filename: str = "shortlist.csv"):
    if not candidates:
        print("  No candidates to export.")
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=candidates[0].keys(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(candidates)
    print(f"  ✅ Exported {len(candidates)} candidates → {filename}")


def export_whatsapp_messages(candidates: list[dict], count: int = 10) -> str:
    """Generate copy-paste WhatsApp messages for candidates."""
    messages = []
    for i, c in enumerate(candidates[:count], 1):
        msg = (
            f"*Candidate {i} — {c.get('primary_skill','BPO')} Role*\n"
            f"• Name: {c.get('name','')}\n"
            f"• City: {c.get('city','')}\n"
            f"• Exp: {c.get('total_experience_yrs',0)} yrs\n"
            f"• English: {c.get('english_fluency','')}\n"
            f"• Night Shift: {c.get('night_shift_ok','')}\n"
            f"• Expected: ₹{c.get('expected_salary',0):,}/month\n"
            f"• Available: {c.get('available_to_join','')}  "
            f"(Notice: {c.get('notice_period_days',0)} days)\n"
            f"• Score: {c.get('overall_score',0)}/100\n"
        )
        messages.append(msg)

    full_msg = (
        f"*Pre-Screened Candidates — AS Recruitment*\n"
        f"{'─'*35}\n\n" +
        "\n".join(messages) +
        "\n\n_For interviews, reply YES or call directly._\n_AS Recruitment | 48-Hr Guarantee_"
    )
    print(full_msg)
    # Save to file too
    with open("whatsapp_candidates.txt", "w", encoding="utf-8") as f:
        f.write(full_msg)
    print(f"\n  ✅ WhatsApp message saved to whatsapp_candidates.txt")
    return full_msg


def print_match_results(candidates: list[dict], requirement: str):
    print(f"\n{'═'*55}")
    print(f"  MATCH RESULTS: \"{requirement}\"")
    print(f"  Found {len(candidates)} candidates")
    print("═"*55)
    for i, c in enumerate(candidates, 1):
        print(f"\n  {i}. {c['name']}  |  {c['city']}  |  Score: {c['overall_score']}/100  BPO: {c['bpo_fit_score']}/100")
        print(f"     Skill: {c['primary_skill']}  |  Exp: {c['total_experience_yrs']}yr  |  English: {c['english_fluency']}")
        print(f"     Night Shift: {c['night_shift_ok']}  |  Salary: ₹{c['expected_salary']:,}/mo  |  Notice: {c['notice_period_days']}d")
        print(f"     Status: {c['status']}  |  Source: {c['source']}")
    print("═"*55 + "\n")


# ═══════════════════════════════════════════════════════════════
#  CLI ENTRY POINT
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="ASR Candidate Database Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 asr_candidate_engine.py --seed 100
  python3 asr_candidate_engine.py --ingest-csv my_candidates.csv
  python3 asr_candidate_engine.py --match "BPO voice Lucknow night shift 13000-18000"
  python3 asr_candidate_engine.py --stats
  python3 asr_candidate_engine.py --shortlist "BPO Lucknow" --export-csv
  python3 asr_candidate_engine.py --export-whatsapp 10
  python3 asr_candidate_engine.py --sync-sheets
        """
    )
    parser.add_argument("--seed",           type=int,  metavar="N",  help="Generate N sample candidates (testing)")
    parser.add_argument("--ingest-csv",     type=str,  metavar="FILE", help="Import candidates from CSV file")
    parser.add_argument("--ingest-whatsapp",type=str,  metavar="FILE", help="Import from WhatsApp text dump file")
    parser.add_argument("--match",          type=str,  metavar="QUERY",help="Match candidates to a job requirement")
    parser.add_argument("--shortlist",      type=str,  metavar="QUERY",help="Generate shortlist (same as --match)")
    parser.add_argument("--top",            type=int,  default=10,    help="Number of candidates to return (default: 10)")
    parser.add_argument("--export-csv",     action="store_true",      help="Export match results to CSV")
    parser.add_argument("--export-whatsapp",type=int,  metavar="N",   help="Export N candidates as WhatsApp message")
    parser.add_argument("--sync-sheets",    action="store_true",      help="Sync top candidates to Google Sheet")
    parser.add_argument("--stats",          action="store_true",      help="Show database statistics")
    parser.add_argument("--db",             type=str,  default=CONFIG["db_path"], help="Database file path")
    args = parser.parse_args()

    # Initialise
    db       = CandidateDB(args.db)
    scorer   = AIScorer()
    ingester = CandidateIngester(db, scorer)
    matcher  = JobMatcher(db)

    # ── Actions ───────────────────────────────────────────
    if args.seed:
        print(f"\n🌱 Generating {args.seed} sample candidates...")
        ingester.generate_sample_database(args.seed)

    if args.ingest_csv:
        print(f"\n📥 Importing from CSV: {args.ingest_csv}")
        ingester.from_csv(args.ingest_csv)

    if args.ingest_whatsapp:
        print(f"\n📱 Importing WhatsApp data: {args.ingest_whatsapp}")
        with open(args.ingest_whatsapp, encoding="utf-8") as f:
            raw = f.read()
        ingester.from_whatsapp_text(raw, group_name=args.ingest_whatsapp)

    query = args.match or args.shortlist
    if query:
        print(f"\n🔍 Matching: \"{query}\"")
        results = matcher.match(query, top_n=args.top)
        print_match_results(results, query)
        if args.export_csv:
            export_shortlist_csv(results, f"shortlist_{query[:20].replace(' ','_')}.csv")

    if args.export_whatsapp:
        query = query or "BPO Lucknow"
        results = matcher.match(query, top_n=args.export_whatsapp)
        export_whatsapp_messages(results, args.export_whatsapp)

    if args.sync_sheets:
        print("\n☁  Syncing to Google Sheets...")
        top_candidates = db.search(min_score=50, limit=500)
        syncer = SheetsSyncer()
        syncer.sync(top_candidates)

    if args.stats or not any([args.seed, args.ingest_csv, args.ingest_whatsapp, query, args.export_whatsapp, args.sync_sheets]):
        print_stats(db)

    db.close()


if __name__ == "__main__":
    main()
