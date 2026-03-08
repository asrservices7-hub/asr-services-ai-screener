"""
ASR WhatsApp Candidate Bot
===========================
Handles candidate self-registration via WhatsApp Business API.
When a candidate messages your WhatsApp number, this bot:
  1. Asks for their details step by step
  2. Stores their profile in the candidate database
  3. Sends a confirmation with their score

Integration options (cheapest to most powerful):
  A) AiSensy  — ₹999/month, no code, just webhook URL
  B) Wati     — ₹2,499/month, better automation
  C) Twilio   — pay-per-message, most flexible

Run as Flask webhook:
  pip install flask
  python3 whatsapp_bot.py

Point your WhatsApp API webhook to:
  https://your-domain.com/webhook/whatsapp
  or use ngrok for local testing:
  ngrok http 5000
"""

import os, json, re
from datetime import datetime

try:
    from flask import Flask, request, jsonify
    FLASK_OK = True
except ImportError:
    FLASK_OK = False

try:
    from asr_candidate_engine import CandidateDB, CandidateIngester, AIScorer, Candidate
    CANDIDATE_ENGINE_OK = True
except ImportError:
    CANDIDATE_ENGINE_OK = False

app = Flask(__name__) if FLASK_OK else None

# ── Conversation state (in-memory — upgrade to Redis for scale) ──
sessions = {}   # phone → {step, data}

FLOW = [
    ("name",            "👋 Welcome to AS Recruitment!\n\nPlease share your *full name*:"),
    ("city",            "📍 Which *city* are you based in?\n(Lucknow / Kanpur / Noida / Jaipur / Indore / Other)"),
    ("skill",           "💼 What is your *primary skill/field*?\n\n1️⃣ BPO / Customer Support\n2️⃣ Sales / Marketing\n3️⃣ Hospital / Healthcare\n4️⃣ IT / Tech\n5️⃣ Retail / Operations\n6️⃣ Other\n\nReply with the number or skill name:"),
    ("experience",      "📅 How many *years of experience* do you have?\n(Reply 0 if fresher)"),
    ("expected_salary", "💰 What is your *expected monthly salary* (₹)?\n(Example: 15000)"),
    ("english_fluency", "🗣 Rate your *English communication*:\n\n1️⃣ Basic\n2️⃣ Intermediate\n3️⃣ Fluent\n4️⃣ Proficient"),
    ("night_shift",     "🌙 Are you open to *night shifts*?\n\n1️⃣ Yes\n2️⃣ No\n3️⃣ Flexible"),
    ("notice_period",   "⏰ What is your *notice period* (days)?\n(Reply 0 if immediately available)"),
]

SKILL_MAP = {"1":"BPO/Voice","2":"Sales","3":"Hospital/Health","4":"IT/Tech","5":"Retail/Ops","6":"Other"}
ENGLISH_MAP = {"1":"Basic","2":"Intermediate","3":"Fluent","4":"Proficient"}
NIGHT_MAP = {"1":"Yes","2":"No","3":"Flexible"}

TRIGGERS = ["hi","hello","job","apply","register","work","hiring","career","नमस्ते","नौकरी"]


def get_next_question(step: int) -> str:
    if step < len(FLOW):
        return FLOW[step][1]
    return None

def process_answer(phone: str, text: str) -> str:
    text = text.strip()
    session = sessions.get(phone, {"step": -1, "data": {}})

    # ── Trigger: start registration ──────────────────────────
    if session["step"] == -1:
        if any(t in text.lower() for t in TRIGGERS):
            sessions[phone] = {"step": 0, "data": {"phone": phone, "source": "WhatsApp Bot"}}
            return FLOW[0][1]
        return (
            "👋 Welcome to *AS Recruitment*!\n\n"
            "We help job seekers in Lucknow, Kanpur, Noida, Jaipur & Indore "
            "get placed in top BPO, hospital, sales & IT companies.\n\n"
            "Type *APPLY* or *JOB* to register your profile. It takes 2 minutes!"
        )

    step = session["step"]
    data = session["data"]

    # ── Store answer ─────────────────────────────────────────
    field = FLOW[step][0]

    if field == "skill":
        data[field] = SKILL_MAP.get(text, text)
    elif field == "english_fluency":
        data[field] = ENGLISH_MAP.get(text, text)
    elif field == "night_shift":
        data["night_shift_ok"] = NIGHT_MAP.get(text, text)
    elif field in ("experience",):
        try: data["total_experience_yrs"] = float(re.sub(r"[^0-9.]","",text))
        except: data["total_experience_yrs"] = 0
    elif field == "expected_salary":
        try:
            n = int(re.sub(r"[^0-9]","",text))
            data["expected_salary"] = n * 1000 if n < 500 else n
        except: data["expected_salary"] = 0
    elif field == "notice_period":
        try: data["notice_period_days"] = int(re.sub(r"[^0-9]","",text))
        except: data["notice_period_days"] = 0
    else:
        data[field] = text

    step += 1
    session["step"] = step
    sessions[phone] = session

    # ── More questions? ──────────────────────────────────────
    if step < len(FLOW):
        return FLOW[step][1]

    # ── Registration complete — save to DB ───────────────────
    return _complete_registration(phone, data)


def _complete_registration(phone: str, data: dict) -> str:
    if CANDIDATE_ENGINE_OK:
        try:
            c = Candidate(
                name                 = data.get("name",""),
                phone                = phone,
                city                 = data.get("city",""),
                primary_skill        = data.get("skill",""),
                total_experience_yrs = data.get("total_experience_yrs",0),
                expected_salary      = data.get("expected_salary",0),
                english_fluency      = data.get("english_fluency","Basic"),
                night_shift_ok       = data.get("night_shift_ok","No"),
                notice_period_days   = data.get("notice_period_days",0),
                available_to_join    = "Yes",
                source               = "WhatsApp Bot",
                status               = "Available",
            )
            db      = CandidateDB()
            scorer  = AIScorer()
            c       = scorer.score(c)
            ingester = CandidateIngester(db, scorer)
            _, cid  = db.upsert(c)
            db.close()
            score   = c.overall_score
            bpo     = c.bpo_fit_score

            # Clear session
            sessions.pop(phone, None)

            return (
                f"✅ *Registration Complete!*\n\n"
                f"Hi {data.get('name','')}, your profile has been saved.\n\n"
                f"*Your Profile Score: {score}/100*\n"
                f"BPO Fit Score: {bpo}/100\n\n"
                f"Our team will contact you when a matching job opens in {data.get('city','')}.\n\n"
                f"📞 Questions? Call: +91-XXXXXXXXXX\n"
                f"🏢 AS Recruitment | Fast Hiring, Tier-2 India"
            )
        except Exception as e:
            return f"✅ Profile saved! We'll contact you soon.\n\n(Error: {e})"
    else:
        sessions.pop(phone, None)
        return (
            f"✅ *Registration Complete!*\n\n"
            f"Hi {data.get('name','')}, profile saved.\n"
            f"We'll contact you when a matching job opens.\n\n"
            f"📞 AS Recruitment | +91-XXXXXXXXXX"
        )


# ══════════════════════════════════════════════════════════════
#  FLASK WEBHOOK
# ══════════════════════════════════════════════════════════════

if FLASK_OK and app:

    @app.route("/webhook/whatsapp", methods=["GET","POST"])
    def whatsapp_webhook():
        # ── Meta webhook verification ──────────────────────
        if request.method == "GET":
            challenge = request.args.get("hub.challenge","")
            verify    = request.args.get("hub.verify_token","")
            if verify == os.getenv("WHATSAPP_VERIFY_TOKEN","asr2024"):
                return challenge
            return "Verification failed", 403

        # ── Incoming message ───────────────────────────────
        data = request.json or {}
        try:
            entry   = data["entry"][0]["changes"][0]["value"]
            msg     = entry["messages"][0]
            phone   = msg["from"]
            text    = msg.get("text",{}).get("body","")
            reply   = process_answer(phone, text)
            _send_reply(phone, reply)
        except (KeyError, IndexError):
            pass
        return jsonify({"status":"ok"})

    @app.route("/webhook/form", methods=["POST"])
    def google_form_webhook():
        """Webhook for Google Forms via n8n → on new form submission."""
        payload = request.json or {}
        if CANDIDATE_ENGINE_OK:
            try:
                from asr_candidate_engine import CandidateDB, CandidateIngester, AIScorer, Candidate
                c = Candidate(
                    name            = payload.get("name",""),
                    phone           = payload.get("phone",""),
                    city            = payload.get("city",""),
                    primary_skill   = payload.get("skill",""),
                    expected_salary = int(payload.get("salary",0)),
                    english_fluency = payload.get("english","Basic"),
                    source          = "Google Form",
                )
                db = CandidateDB()
                CandidateIngester(db, AIScorer()).add_single(**{k:v for k,v in vars(c).items()})
                db.close()
                return jsonify({"status":"ok","message":"Candidate saved"})
            except Exception as e:
                return jsonify({"status":"error","message":str(e)}), 500
        return jsonify({"status":"ok"})

    @app.route("/health")
    def health():
        return jsonify({"status":"running","time":datetime.now().isoformat()})


def _send_reply(phone: str, message: str):
    """Send WhatsApp reply via Meta Business API."""
    api_key   = os.getenv("WHATSAPP_API_KEY","")
    phone_id  = os.getenv("WHATSAPP_PHONE_ID","")
    if not api_key:
        print(f"  📱 BOT → {phone}: {message[:80]}...")
        return
    import requests
    requests.post(
        f"https://graph.facebook.com/v19.0/{phone_id}/messages",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type":"application/json"},
        json={"messaging_product":"whatsapp","to":phone,"type":"text","text":{"body":message}},
        timeout=10,
    )


if __name__ == "__main__":
    if not FLASK_OK:
        print("Install Flask: pip install flask")
        exit(1)
    print("🤖 ASR WhatsApp Bot starting on port 5000...")
    print("   Webhook URL: http://localhost:5000/webhook/whatsapp")
    print("   Use ngrok to expose: ngrok http 5000")
    app.run(host="0.0.0.0", port=5000, debug=False)
