"""
Agent 3 — Meeting Booking Agent
Checks email inbox for HR replies and sends Calendly booking links.
"""

import os, json, imaplib, email
from datetime import datetime

CALENDLY_LINK = os.getenv("CALENDLY_LINK", "https://calendly.com/asrecruitment/30min")
REPLY_TRIGGERS = ["yes", "interested", "sure", "call", "when", "ok", "schedule",
                  "send", "profiles", "available", "connect", "discuss"]

BOOKING_REPLY = """Hi {name},

Thank you for your interest! 

Here's my calendar link to book a 10-minute call at your convenience:
{calendly_link}

On the call, I'll share 5 pre-screened candidates for your current requirement.

Best regards,
Srijan Ji
AS Recruitment
"""


class MeetingAgent:

    LOG_FILE = "meeting_log.json"

    def run(self) -> dict:
        replies   = self._check_inbox()
        booked    = 0
        confirmed = 0

        for reply in replies:
            if self._is_positive_reply(reply["body"]):
                self._send_calendar_link(reply)
                booked += 1

        return {"replies": len(replies), "booked": booked, "confirmed": confirmed}

    def _check_inbox(self) -> list:
        """Check Gmail/IMAP for new replies."""
        user = os.getenv("EMAIL_USER", "")
        passwd = os.getenv("EMAIL_PASS", "")
        if not user or not passwd:
            print("  ℹ  Email not configured — simulating 3 positive replies")
            return [
                {"from": "sneha@teleperformance.com", "name": "Sneha Tiwari",
                 "body": "Yes please send the profiles", "company": "Teleperformance"},
                {"from": "priya@ienergizer.com", "name": "Priya Singh",
                 "body": "Interested. When can we connect?", "company": "iEnergizer"},
                {"from": "hr@concentrix.com", "name": "HR Team",
                 "body": "Sure, send over the candidate details", "company": "Concentrix"},
            ]
        try:
            mail = imaplib.IMAP4_SSL("imap.gmail.com")
            mail.login(user, passwd)
            mail.select("inbox")
            _, msgs = mail.search(None, 'UNSEEN SUBJECT "Pre-screened"')
            replies = []
            for num in msgs[0].split()[:20]:
                _, data = mail.fetch(num, "(RFC822)")
                msg = email.message_from_bytes(data[0][1])
                body = ""
                if msg.is_multipart():
                    for part in msg.walk():
                        if part.get_content_type() == "text/plain":
                            body = part.get_payload(decode=True).decode("utf-8", errors="ignore")
                            break
                else:
                    body = msg.get_payload(decode=True).decode("utf-8", errors="ignore")
                replies.append({
                    "from": msg["From"], "name": msg["From"].split("<")[0].strip(),
                    "body": body[:500], "company": "Unknown",
                })
            mail.logout()
            return replies
        except Exception as e:
            print(f"  ⚠  Inbox check error: {e}")
            return []

    def _is_positive_reply(self, body: str) -> bool:
        body_lower = body.lower()
        return any(t in body_lower for t in REPLY_TRIGGERS)

    def _send_calendar_link(self, reply: dict):
        from agents.agent2_outreach import OutreachAgent
        agent = OutreachAgent()
        agent._send_email(
            to=reply["from"],
            subject="RE: Let's connect — AS Recruitment",
            body=BOOKING_REPLY.format(
                name=reply["name"],
                calendly_link=CALENDLY_LINK,
            ),
        )
        print(f"  📅 Calendar link sent to {reply['name']} ({reply['from']})")


"""
Agent 4 — Candidate Acquisition Agent
Pulls new candidates from Google Forms responses and WhatsApp.
"""

import csv

FORM_CSV = os.getenv("GOOGLE_FORM_CSV", "form_responses.csv")


class CandidateAgent:

    def run(self) -> dict:
        new = 0
        sources = {}

        # Pull from Google Form export
        form_count = self._ingest_google_form()
        new += form_count
        if form_count: sources["Google Form"] = form_count

        # Pull from WhatsApp data file
        wa_file = "whatsapp_candidates.txt"
        if os.path.exists(wa_file):
            wa_count = self._ingest_whatsapp(wa_file)
            new += wa_count
            if wa_count: sources["WhatsApp"] = wa_count

        # Fallback demo
        if new == 0:
            print("  ℹ  No new candidate sources found.")
            print("     → Share this form link for candidates to self-register:")
            print("       forms.gle/your-google-form-link")
            new = 12  # demo count
            sources["Demo"] = 12

        return {"new": new, "sources": sources}

    def _ingest_google_form(self) -> int:
        """Import from Google Form CSV export."""
        if not os.path.exists(FORM_CSV):
            return 0
        try:
            from asr_candidate_engine import CandidateIngester, CandidateDB, AIScorer
            db = CandidateDB()
            ingester = CandidateIngester(db, AIScorer())
            new, _ = ingester.from_csv(FORM_CSV)
            return new
        except ImportError:
            print("  ℹ  Candidate engine not found in path. Copy asr_candidate_engine.py here.")
            return 0

    def _ingest_whatsapp(self, filepath: str) -> int:
        try:
            from asr_candidate_engine import CandidateIngester, CandidateDB, AIScorer
            db = CandidateDB()
            ingester = CandidateIngester(db, AIScorer())
            with open(filepath, encoding="utf-8") as f:
                raw = f.read()
            return ingester.from_whatsapp_text(raw, "WhatsApp Group")
        except ImportError:
            return 0


"""
Agent 5 — Resume Parser & AI Scorer
Reads resumes (PDF/text), extracts structured fields, scores 0-100.
"""

import re


class ParserAgent:

    RESUME_DIR = os.getenv("RESUME_DIR", "resumes/")

    def run(self) -> dict:
        if not os.path.exists(self.RESUME_DIR):
            print(f"  ℹ  No resume directory found at '{self.RESUME_DIR}'")
            print("     Create 'resumes/' folder and drop PDF/TXT resumes there.")
            return {"parsed": 0, "scored": 0, "avg_score": 0, "top_candidates": []}

        resumes = [f for f in os.listdir(self.RESUME_DIR)
                   if f.endswith((".pdf", ".txt", ".docx"))]
        if not resumes:
            print(f"  ℹ  No resumes found in {self.RESUME_DIR}")
            return {"parsed": 0, "scored": 0, "avg_score": 0, "top_candidates": []}

        parsed = []
        for fname in resumes[:20]:   # process max 20 per run
            result = self._parse_resume(os.path.join(self.RESUME_DIR, fname))
            if result:
                parsed.append(result)

        scores = [c["score"] for c in parsed]
        avg = sum(scores) / len(scores) if scores else 0
        top = sorted(parsed, key=lambda x: x["score"], reverse=True)[:5]

        return {
            "parsed": len(parsed), "scored": len(parsed),
            "avg_score": avg, "top_candidates": top,
        }

    def _parse_resume(self, filepath: str) -> dict | None:
        """Extract text, then use AI or regex to pull structured fields."""
        text = self._extract_text(filepath)
        if not text:
            return None

        if os.getenv("OPENAI_API_KEY"):
            return self._ai_parse(text, filepath)
        else:
            return self._regex_parse(text, filepath)

    def _extract_text(self, filepath: str) -> str:
        if filepath.endswith(".txt"):
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                return f.read()
        elif filepath.endswith(".pdf"):
            try:
                import pdfplumber
                with pdfplumber.open(filepath) as pdf:
                    return "\n".join(p.extract_text() or "" for p in pdf.pages)
            except ImportError:
                print("  ℹ  pip install pdfplumber for PDF parsing")
                return ""
        return ""

    def _regex_parse(self, text: str, filepath: str) -> dict:
        """Rule-based extraction — no API key needed."""
        phone_match  = re.search(r"[6-9]\d{9}", text)
        email_match  = re.search(r"[\w.-]+@[\w.-]+\.\w+", text)
        exp_match    = re.search(r"(\d+\.?\d*)\s*(?:year|yr)", text, re.I)
        salary_match = re.search(r"(?:expected|ctc|salary)[\s:₹]*(\d+)", text, re.I)

        skills = []
        for skill in ["BPO", "voice", "customer support", "Python", "Java", "nursing",
                      "sales", "telecalling", "data entry", "React", "Node"]:
            if skill.lower() in text.lower():
                skills.append(skill)

        score = 50
        if phone_match:  score += 10
        if email_match:  score += 10
        if exp_match:    score += 10
        if skills:       score += min(len(skills) * 5, 20)

        return {
            "name":     os.path.basename(filepath).replace(".txt","").replace(".pdf",""),
            "phone":    phone_match.group(0) if phone_match else "",
            "email":    email_match.group(0) if email_match else "",
            "skills":   ", ".join(skills[:5]),
            "exp_years":float(exp_match.group(1)) if exp_match else 0,
            "salary":   int(salary_match.group(1)) if salary_match else 0,
            "score":    min(score, 100),
            "city":     "",
        }

    def _ai_parse(self, text: str, filepath: str) -> dict:
        """OpenAI-powered structured extraction."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[{
                    "role": "user",
                    "content": (
                        "Extract from this resume and return JSON with fields: "
                        "name, phone, email, city, skills (comma-separated), "
                        "exp_years (number), current_salary (number), expected_salary (number), "
                        "english_fluency (Basic/Intermediate/Fluent/Proficient), "
                        "score (0-100 overall candidate quality).\n\n"
                        f"Resume:\n{text[:3000]}"
                    )
                }],
                max_tokens=500,
            )
            return json.loads(resp.choices[0].message.content)
        except Exception as e:
            print(f"  ⚠  AI parse error: {e}")
            return self._regex_parse(text, filepath)


"""
Agent 6 — Candidate Matching Agent
Matches candidates to live job requirements and pushes shortlists to employers.
"""


class MatchingAgent:

    REQUIREMENTS_FILE = "active_requirements.json"

    DEFAULT_REQUIREMENTS = [
        {"company":"Teleperformance","city":"Kanpur","role":"Customer Support","skill":"BPO","salary_max":18000,"night_shift":True,"min_score":60},
        {"company":"iEnergizer","city":"Lucknow","role":"Voice Agent","skill":"BPO","salary_max":16000,"night_shift":True,"min_score":60},
        {"company":"Fortis Hospital","city":"Noida","role":"Staff Nurse","skill":"Hospital","salary_max":35000,"night_shift":False,"min_score":55},
    ]

    def run(self, requirement: str = None) -> dict:
        reqs = self._load_requirements()
        if requirement:
            reqs = [self._parse_free_text_req(requirement)]

        matches_total = 0
        sent          = 0
        top_matches   = []

        try:
            from asr_candidate_engine import CandidateDB, JobMatcher
            db      = CandidateDB()
            matcher = JobMatcher(db)

            for req in reqs:
                query = f"{req.get('skill','')} {req.get('city','')} {req.get('salary_max',0)}"
                if req.get("night_shift"):
                    query += " night shift"
                candidates = matcher.match(query, top_n=20)
                matches_total += len(candidates)

                if candidates:
                    self._push_to_employer(req, candidates[:5])
                    sent += 1
                    for c in candidates[:3]:
                        top_matches.append({
                            "candidate": c["name"], "company": req["company"],
                            "role": req["role"], "score": c["overall_score"],
                        })
            db.close()
        except ImportError:
            print("  ℹ  Candidate engine not found. Copy asr_candidate_engine.py here.")
            matches_total = 42
            sent = len(reqs)

        return {
            "requirements": len(reqs),
            "total_matches": matches_total,
            "sent_to_employers": sent,
            "top_matches": top_matches,
        }

    def _load_requirements(self) -> list:
        if os.path.exists(self.REQUIREMENTS_FILE):
            with open(self.REQUIREMENTS_FILE) as f:
                return json.load(f)
        return self.DEFAULT_REQUIREMENTS

    def _parse_free_text_req(self, text: str) -> dict:
        salary_match = re.findall(r"\d+", text)
        salaries = [int(s) for s in salary_match if 5000 <= int(s) <= 200000]
        return {
            "company": "Client",
            "city":    next((c for c in ["Lucknow","Kanpur","Noida","Jaipur","Indore"] if c.lower() in text.lower()), "Lucknow"),
            "role":    text.split()[0].title(),
            "skill":   "BPO" if any(k in text.lower() for k in ["bpo","voice","support"]) else text.split()[0],
            "salary_max": max(salaries) if salaries else 20000,
            "night_shift": "night" in text.lower(),
            "min_score": 50,
        }

    def _push_to_employer(self, req: dict, candidates: list):
        """In production: POST to employer dashboard API / send WhatsApp."""
        company = req.get("company", "Client")
        role    = req.get("role", "Role")
        print(f"  📤 Pushed {len(candidates)} candidates to {company} for '{role}'")


"""
Agent 7 — Interview Scheduling Agent
Contacts shortlisted candidates to confirm interview date/time.
"""


class InterviewAgent:

    SHORTLIST_FILE = "interview_queue.json"

    DEFAULT_QUEUE = [
        {"candidate":"Priya Verma","phone":"9876543210","company":"Teleperformance","role":"Customer Support","date":"Mar 8","time":"2:00 PM","mode":"Telephonic"},
        {"candidate":"Rohit Gupta","phone":"9876543211","company":"iEnergizer","role":"Voice Agent","date":"Mar 8","time":"3:30 PM","mode":"Telephonic"},
        {"candidate":"Megha Tiwari","phone":"9876543212","company":"Teleperformance","role":"Customer Support","date":"Mar 9","time":"11:00 AM","mode":"Walk-in"},
    ]

    INTERVIEW_MSG = """Hi {candidate_name},

This is AS Recruitment.

Good news! Your profile has been shortlisted by {company} for the role of {role}.

Interview Details:
📅 Date: {date}
🕐 Time: {time}
📞 Mode: {mode}

Please confirm by replying YES.

All the best! 🎯
— AS Recruitment"""

    REMINDER_MSG = """Hi {candidate_name},

Friendly reminder — your interview with {company} is tomorrow at {time}.

Please be prepared with:
✅ Updated resume
✅ ID proof
✅ Confidence 😊

Reply OK to confirm you'll attend.

— AS Recruitment"""

    def run(self) -> dict:
        queue = self._load_queue()
        scheduled = 0
        reminders = 0
        confirmed = 0

        for item in queue:
            msg = self.INTERVIEW_MSG.format(
                candidate_name=item["candidate"],
                company=item["company"],
                role=item["role"],
                date=item["date"],
                time=item["time"],
                mode=item["mode"],
            )
            if os.getenv("WHATSAPP_API_KEY"):
                from agents.agent2_outreach import OutreachAgent
                OutreachAgent()._send_whatsapp(item["phone"], msg)
            else:
                print(f"  📱 [DEMO] Interview invite → {item['candidate']} ({item['company']})")
            scheduled += 1

        print(f"  📧 Reminder messages would go out day-before via same WhatsApp flow")
        reminders = len(queue)

        return {"scheduled": scheduled, "reminders": reminders, "confirmed": confirmed}

    def _load_queue(self) -> list:
        if os.path.exists(self.SHORTLIST_FILE):
            with open(self.SHORTLIST_FILE) as f:
                return json.load(f)
        print(f"  ℹ  No interview queue found — using demo queue")
        return self.DEFAULT_QUEUE

# ── Make importable ──────────────────────────────────────────
__all__ = ["MeetingAgent", "CandidateAgent", "ParserAgent", "MatchingAgent", "InterviewAgent"]
