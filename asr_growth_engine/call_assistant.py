"""
ASR Call Script Generator + Live Objection Handler
====================================================
Use this during your calls. Keep it open in one window,
call with your phone, ask AI for help when HR objects.

python3 call_assistant.py --script "BPO Lucknow 20 agents"
python3 call_assistant.py --objection "we already have a vendor"
python3 call_assistant.py --followup-msg "Teleperformance HR replied interested"
python3 call_assistant.py --batch-scripts 10    Generate scripts for 10 companies
"""

import os, sys, argparse

try:
    from dotenv import load_dotenv; load_dotenv()
except ImportError:
    pass

OPENAI_KEY = os.getenv("OPENAI_API_KEY","")

# ── Hard-coded scripts (no API key needed) ────────────────────

OPENING = """
╔══════════════════════════════════════════════════════╗
  ASR CALL SCRIPT — {company} | {city} | {industry}
╚══════════════════════════════════════════════════════╝

BEFORE DIALLING:
  • Check company on LinkedIn first
  • Note: {roles} roles, {city} location
  • Target: HR Manager / Talent Acquisition

─────────────────────────────────────────────────────
  OPENING (first 20 seconds — speak clearly, smile)
─────────────────────────────────────────────────────

"Hello, am I speaking with the HR Manager?"
  [Wait for yes]

"Good [morning/afternoon], I'm Srijan from AS Recruitment.
 We specialize in placing pre-screened {industry} candidates
 in {city} within 48 hours.
 Is {company} currently hiring for any {roles} roles?"

─────────────────────────────────────────────────────
  IF THEY SAY YES — Requirement capture
─────────────────────────────────────────────────────

"Excellent! How many positions are you looking to fill?"
  [Note: ______]

"What is the expected joining timeline?"
  [Note: ______]

"What salary range are you offering?"
  [Note: ______]

"Would night shift candidates work for you?"
  [Note: ______]

"Perfect. I can send you 5 pre-screened profiles by tomorrow morning.
 Our fee is ₹8,000 per candidate who successfully joins.
 No payment unless they join — zero risk for you.
 Can I get your email to send the profiles?"
  [Note email: ______]

─────────────────────────────────────────────────────
  CLOSING
─────────────────────────────────────────────────────

"Excellent. I'll send the profiles within 24 hours.
 You can review, shortlist, and interview — I'll coordinate everything.
 Thank you, [Name]. Looking forward to working with {company}."

─────────────────────────────────────────────────────
  AFTER CALL — immediately update your sheet:
  Company | HR Name | Phone | Email | Requirement | Date
─────────────────────────────────────────────────────
"""

OBJECTIONS = {
    "no vacancy": """
OBJECTION: "We are not hiring right now."

RESPONSE:
"Understood, and I appreciate you telling me.
 Many of our clients told us the same — and then suddenly needed
 20 agents within a week due to a new project.
 
 Can I keep your contact for when hiring opens?
 I'll send a quick email with our candidate pool so you have
 it ready when the need arises. Would that be alright?"

[If yes → get email. Follow up in 30 days.]
""",

    "vendor": """
OBJECTION: "We already have a recruitment partner."

RESPONSE:
"That's great — strong companies always have good partners.
 Most of our clients work with 2–3 agencies to ensure
 they never face a shortage during peak hiring.
 
 We're particularly strong in pre-screened BPO candidates
 in Tier-2 cities, which some agencies struggle with.
 
 Would you be open to a quick trial — send us one requirement
 and compare our delivery speed? No commitment needed."

[Goal: get one trial requirement]
""",

    "too expensive": """
OBJECTION: "Your fees are too high." / "We pay less."

RESPONSE:
"I completely understand — and we're open to discussing.
 
 A few things that might change the math:
 • You pay ONLY when the candidate joins — zero risk
 • 30-day free replacement if they leave early
 • Pre-screened means fewer interviews, faster closure
 
 For bulk hiring of 20+ candidates, we also offer
 a reduced rate of ₹6,000–₹7,000 per joining.
 
 What rate would make this work for you?"

[Negotiate down to ₹6,000 minimum for bulk]
""",

    "send details": """
RESPONSE FOR: "Send me details on email."

ACTION:
1. Confirm their email on the call
2. Send within 30 minutes (while you're still fresh in their mind)
3. Subject: "AS Recruitment — Pre-screened {role} candidates | {company}"
4. Include: 2–3 anonymised candidate profiles, your fee, your guarantee
5. Follow up by call in 2 days if no reply

EMAIL TO SEND:
─────────────────────────────────────────────────────
Subject: Pre-screened customer support candidates — AS Recruitment

Hi [Name],

As discussed, here are 3 sample candidate profiles:

Candidate 1: 2yr BPO exp, Lucknow, Fluent English, ₹16K expected
Candidate 2: Fresher, Night shift ready, ₹13K, available immediately  
Candidate 3: 1yr voice process, Kanpur, ₹15K expected

Our terms:
• ₹8,000 per candidate who joins (pay after joining only)
• 30-day free replacement guarantee
• Shortlist to interview arranged within 48 hours

Shall I send 5 more matching profiles for your current requirement?

Best,
Srijan Ji | AS Recruitment | +91-XXXXXXXXXX
─────────────────────────────────────────────────────
""",

    "think about it": """
OBJECTION: "Let me think about it." / "I'll check with my manager."

RESPONSE:
"Of course, take your time.
 
 Just so I understand — is there any specific concern
 I can address right now? Sometimes I can solve it on the spot.
 
 [Listen carefully]
 
 Alright. I'll call you back on [day after tomorrow] — would
 [10 AM or 4 PM] work better for you?"

[Book a specific follow-up time before hanging up]
""",

    "not interested": """
OBJECTION: "We're not interested."

RESPONSE:
"No problem at all, I respect that.
 
 Just one last question — do you know any other HR manager
 in your network who might be hiring right now?
 Even a referral would help us a lot.
 
 [If yes → get the name/number]
 
 Thank you for your time. Have a great day."

[Always end positively — they might come back later]
""",
}


def get_script(context: str) -> str:
    """Generate a call script from context string."""
    # Extract info from context
    city = next((c for c in ["Lucknow","Kanpur","Noida","Jaipur","Indore","Delhi","Gurgaon"]
                 if c.lower() in context.lower()), "your city")
    ind  = next((i for i in ["BPO","Hospital","IT","Sales","Retail","Logistics"]
                 if i.lower() in context.lower()), "BPO")
    role = "customer support" if "bpo" in context.lower() else \
           "nursing staff" if "hospital" in context.lower() else \
           "sales executive" if "sales" in context.lower() else "support"

    script = OPENING.format(
        company=context.split()[0].title() if context else "the company",
        city=city, industry=ind, roles=role,
    )

    if OPENAI_KEY:
        script += _ai_extra_tips(context, city, ind, role)

    return script


def get_objection(objection: str) -> str:
    """Find best matching objection handler."""
    obj_lower = objection.lower()
    if "vendor" in obj_lower or "partner" in obj_lower or "agency" in obj_lower:
        return OBJECTIONS["vendor"]
    elif "expens" in obj_lower or "fee" in obj_lower or "cost" in obj_lower or "high" in obj_lower:
        return OBJECTIONS["too expensive"]
    elif "send" in obj_lower or "email" in obj_lower or "details" in obj_lower:
        return OBJECTIONS["send details"]
    elif "think" in obj_lower or "manager" in obj_lower or "later" in obj_lower:
        return OBJECTIONS["think about it"]
    elif "not interest" in obj_lower:
        return OBJECTIONS["not interested"]
    elif "no" in obj_lower and ("vacanc" in obj_lower or "hiring" in obj_lower or "opening" in obj_lower):
        return OBJECTIONS["no vacancy"]
    elif OPENAI_KEY:
        return _ai_objection(objection)
    else:
        return OBJECTIONS.get("no vacancy", "Stay calm, acknowledge their concern, pivot to one small ask.")


def _ai_objection(objection: str) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role":"system",
                "content":"You are a sales coach for AS Recruitment, a BPO staffing company in India. Give a brief, practical objection handling response (3–5 sentences max). Be confident but not pushy."
            },{
                "role":"user",
                "content":f"The HR manager said: '{objection}'. How should I respond?"
            }],
            max_tokens=200,
        )
        return f"\nAI RESPONSE SUGGESTION:\n{'─'*40}\n{resp.choices[0].message.content}\n{'─'*40}\n"
    except Exception as e:
        return f"\n⚠  AI not available: {e}\n"


def _ai_extra_tips(context, city, ind, role) -> str:
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_KEY)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{
                "role":"user",
                "content":f"Give 2 quick tips for cold calling {ind} companies in {city} India for recruiting {role} staff. Keep it very brief, practical, India-specific."
            }],
            max_tokens=120,
        )
        return f"\nAI TIPS FOR THIS CALL:\n{'─'*40}\n{resp.choices[0].message.content}\n{'─'*40}\n"
    except Exception:
        return ""


def batch_scripts(db_path: str, count: int = 10):
    """Generate call scripts for top N companies from growth DB."""
    import sqlite3
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM companies WHERE phone!='' ORDER BY score DESC LIMIT ?", (count,)
        ).fetchall()
        conn.close()
    except Exception:
        print("  ⚠  Run growth_engine.py --discover first to build company database")
        return

    print(f"\n{'═'*55}")
    print(f"  CALL BATCH — TOP {len(rows)} COMPANIES TO CALL TODAY")
    print(f"{'═'*55}\n")
    for i, r in enumerate(rows, 1):
        r = dict(r)
        print(f"{i:>2}. {r['company']:<30} {r['city']:<12} {r['phone']}")
        print(f"    Role: {r.get('roles','BPO/support')}  Score: {r['score']}/100")
        print()

    print("To get full script for any company:")
    print("  python3 call_assistant.py --script \"Teleperformance BPO Lucknow 20 agents\"")
    print("\nTo handle an objection during a call:")
    print("  python3 call_assistant.py --objection \"we already have a vendor\"")


def main():
    p = argparse.ArgumentParser(description="ASR Call Script Generator + Live Objection Handler")
    p.add_argument("--script",    type=str, metavar="CONTEXT", help="Generate call script. e.g. 'BPO Lucknow 20 agents'")
    p.add_argument("--objection", type=str, metavar="OBJECTION", help="Get objection handling response")
    p.add_argument("--batch-scripts", type=int, metavar="N", help="Print top N companies to call today")
    p.add_argument("--list-objections", action="store_true", help="Show all objection handlers")
    args = p.parse_args()

    if args.script:
        print(get_script(args.script))
    elif args.objection:
        print(get_objection(args.objection))
    elif args.batch_scripts:
        batch_scripts("growth_data/growth_leads.db", args.batch_scripts)
    elif args.list_objections:
        for key, val in OBJECTIONS.items():
            print(f"\n{'━'*55}")
            print(f"  OBJECTION: {key.upper()}")
            print(val)
    else:
        p.print_help()
        print("\n  Quick examples:")
        print("  python3 call_assistant.py --script 'BPO Kanpur night shift'")
        print("  python3 call_assistant.py --objection 'we already have an agency'")
        print("  python3 call_assistant.py --batch-scripts 10")


if __name__ == "__main__":
    main()
