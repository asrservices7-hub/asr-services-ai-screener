"""
ASR 7-Agent Automation System
================================
7 AI workers running ASR Services 24/7.

  Agent 1 — Lead Generation      : Finds hiring companies from LinkedIn/Maps/Naukri
  Agent 2 — Outreach              : Sends personalised emails + WhatsApp to HR
  Agent 3 — Meeting Booking       : Converts replies into Calendly-booked calls
  Agent 4 — Candidate Acquisition : Pulls candidates from WhatsApp/forms/job portals
  Agent 5 — Resume Parser + Scorer: AI reads resumes, extracts fields, scores 0–100
  Agent 6 — Matching              : Matches candidates to live job requirements
  Agent 7 — Interview Scheduler   : Sends interview invites + reminders via WhatsApp

Run the full loop:
  python3 asr_system.py --run-all

Run individual agents:
  python3 asr_system.py --leads
  python3 asr_system.py --outreach
  python3 asr_system.py --candidates
  python3 asr_system.py --match "BPO Lucknow night shift 15000"
  python3 asr_system.py --score
  python3 asr_system.py --schedule
  python3 asr_system.py --status
"""

import os, sys, json, time, argparse
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Shared state file ────────────────────────────────────────
STATE_FILE = "asr_system_state.json"

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "leads_today": 0, "outreach_today": 0, "replies_today": 0,
        "meetings_today": 0, "candidates_today": 0, "matches_today": 0,
        "interviews_today": 0, "last_run": "", "total_leads": 0,
        "total_candidates": 0, "total_placements": 0, "total_revenue": 0,
    }

def save_state(state: dict):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

def header(title: str):
    w = 60
    print("\n" + "═"*w)
    print(f"  {title}")
    print("═"*w)

def step(msg: str): print(f"  ✦ {msg}")
def done(msg: str): print(f"  ✅ {msg}")
def warn(msg: str): print(f"  ⚠  {msg}")


# ══════════════════════════════════════════════════════════════
#  AGENT 1 — LEAD GENERATION
# ══════════════════════════════════════════════════════════════
def run_lead_agent(state: dict):
    header("AGENT 1 — LEAD GENERATION")
    step("Importing lead engine...")

    try:
        from agents.agent1_leads import LeadAgent
        agent = LeadAgent()
        leads = agent.run()
        state["leads_today"] = len(leads)
        state["total_leads"] += len(leads)
        done(f"{len(leads)} new leads discovered and saved → leads_output.json")
        return leads
    except ImportError as e:
        warn(f"Lead engine not configured: {e}")
        warn("→ Add OPENAI_API_KEY and optionally SERPAPI_API_KEY to .env")
        return []


# ══════════════════════════════════════════════════════════════
#  AGENT 2 — OUTREACH
# ══════════════════════════════════════════════════════════════
def run_outreach_agent(state: dict, leads: list = None):
    header("AGENT 2 — OUTREACH AGENT")

    try:
        from agents.agent2_outreach import OutreachAgent
        agent = OutreachAgent()

        if not leads:
            leads = agent.load_pending_leads()

        if not leads:
            warn("No pending leads to contact. Run --leads first.")
            return

        results = agent.run(leads)
        state["outreach_today"] = results["sent"]
        done(f"Outreach sent: {results['sent']} emails, {results['whatsapp']} WhatsApp")
        done(f"Open rate estimate: {results.get('open_rate_pct', 0):.0f}%")
    except ImportError as e:
        warn(f"Outreach agent not configured: {e}")
        warn("→ Add EMAIL_HOST, EMAIL_USER, EMAIL_PASS to .env")


# ══════════════════════════════════════════════════════════════
#  AGENT 3 — MEETING BOOKING
# ══════════════════════════════════════════════════════════════
def run_meeting_agent(state: dict):
    header("AGENT 3 — MEETING BOOKING AGENT")

    try:
        from agents.agent3_meetings import MeetingAgent
        agent = MeetingAgent()
        results = agent.run()
        state["replies_today"]  = results["replies"]
        state["meetings_today"] = results["booked"]
        done(f"Replies processed: {results['replies']}")
        done(f"Meetings booked: {results['booked']}")
    except ImportError as e:
        warn(f"Meeting agent not configured: {e}")
        warn("→ Add CALENDLY_API_KEY and EMAIL credentials to .env")


# ══════════════════════════════════════════════════════════════
#  AGENT 4 — CANDIDATE ACQUISITION
# ══════════════════════════════════════════════════════════════
def run_candidate_agent(state: dict):
    header("AGENT 4 — CANDIDATE ACQUISITION AGENT")

    try:
        from agents.agent4_candidates import CandidateAgent
        agent = CandidateAgent()
        results = agent.run()
        state["candidates_today"] = results["new"]
        state["total_candidates"] += results["new"]
        done(f"New candidates added: {results['new']}")
        done(f"Total database: {state['total_candidates']:,} candidates")
        if results.get("sources"):
            for src, cnt in results["sources"].items():
                step(f"  {src}: {cnt}")
    except ImportError as e:
        warn(f"Candidate agent not configured: {e}")
        warn("→ Add GOOGLE_SHEET_ID and WHATSAPP_API_KEY to .env")


# ══════════════════════════════════════════════════════════════
#  AGENT 5 — RESUME PARSER + SCORER
# ══════════════════════════════════════════════════════════════
def run_parser_agent(state: dict):
    header("AGENT 5 — RESUME PARSER & SCORER")

    try:
        from agents.agent5_parser import ParserAgent
        agent = ParserAgent()
        results = agent.run()
        done(f"Resumes parsed: {results['parsed']}")
        done(f"AI scores assigned: {results['scored']}")
        done(f"Avg score: {results.get('avg_score', 0):.1f}/100")
        if results.get("top_candidates"):
            step("Top new candidates:")
            for c in results["top_candidates"][:5]:
                step(f"  {c['name']} ({c['city']}) — Score: {c['score']}/100")
    except ImportError as e:
        warn(f"Parser agent not configured: {e}")
        warn("→ Add OPENAI_API_KEY to .env (required for AI scoring)")


# ══════════════════════════════════════════════════════════════
#  AGENT 6 — MATCHING
# ══════════════════════════════════════════════════════════════
def run_matching_agent(state: dict, requirement: str = None):
    header("AGENT 6 — CANDIDATE MATCHING AGENT")

    try:
        from agents.agent6_matching import MatchingAgent
        agent = MatchingAgent()
        results = agent.run(requirement=requirement)
        state["matches_today"] = results["total_matches"]
        done(f"Requirements processed: {results['requirements']}")
        done(f"Candidate-job matches made: {results['total_matches']}")
        done(f"Shortlists sent to employers: {results['sent_to_employers']}")
        if results.get("top_matches"):
            step("\nTop matches this run:")
            for m in results["top_matches"][:5]:
                step(f"  {m['candidate']} → {m['company']} ({m['role']}) — Match: {m['score']}%")
    except ImportError as e:
        warn(f"Matching agent not configured: {e}")
        warn("→ Requires candidate database (run --candidates first)")


# ══════════════════════════════════════════════════════════════
#  AGENT 7 — INTERVIEW SCHEDULER
# ══════════════════════════════════════════════════════════════
def run_scheduler_agent(state: dict):
    header("AGENT 7 — INTERVIEW SCHEDULING AGENT")

    try:
        from agents.agent7_interviews import InterviewAgent
        agent = InterviewAgent()
        results = agent.run()
        state["interviews_today"] = results["scheduled"]
        done(f"Interviews scheduled: {results['scheduled']}")
        done(f"Reminders sent: {results['reminders']}")
        done(f"Confirmations received: {results['confirmed']}")
    except ImportError as e:
        warn(f"Interview agent not configured: {e}")
        warn("→ Add WHATSAPP_API_KEY and GOOGLE_CALENDAR_KEY to .env")


# ══════════════════════════════════════════════════════════════
#  STATUS DASHBOARD
# ══════════════════════════════════════════════════════════════
def print_status(state: dict):
    header("ASR SYSTEM STATUS — TODAY'S NUMBERS")
    print(f"""
  ┌─────────────────────────────────────────────┐
  │  DAILY PIPELINE                             │
  │  Leads discovered      {state['leads_today']:>6}                │
  │  Outreach sent         {state['outreach_today']:>6}                │
  │  Replies received      {state['replies_today']:>6}                │
  │  Meetings booked       {state['meetings_today']:>6}                │
  ├─────────────────────────────────────────────┤
  │  CANDIDATE SUPPLY                           │
  │  New candidates added  {state['candidates_today']:>6}                │
  │  Total database        {state['total_candidates']:>6,}                │
  │  Matches made          {state['matches_today']:>6}                │
  │  Interviews scheduled  {state['interviews_today']:>6}                │
  ├─────────────────────────────────────────────┤
  │  REVENUE                                    │
  │  Total placements      {state['total_placements']:>6}                │
  │  Revenue earned (₹)    {state['total_revenue']:>6,}                │
  └─────────────────────────────────────────────┘
    """)
    print(f"  Last full run: {state.get('last_run', 'Never')}\n")


# ══════════════════════════════════════════════════════════════
#  FULL LOOP
# ══════════════════════════════════════════════════════════════
def run_all(state: dict):
    print(f"""
{'█'*60}
  ASR 7-AGENT SYSTEM — FULL DAILY RUN
  {datetime.now().strftime('%d %b %Y · %H:%M')}
{'█'*60}
""")
    leads = run_lead_agent(state)
    time.sleep(1)
    run_outreach_agent(state, leads)
    time.sleep(1)
    run_meeting_agent(state)
    time.sleep(1)
    run_candidate_agent(state)
    time.sleep(1)
    run_parser_agent(state)
    time.sleep(1)
    run_matching_agent(state)
    time.sleep(1)
    run_scheduler_agent(state)

    state["last_run"] = datetime.now().strftime("%d %b %Y %H:%M")
    save_state(state)
    print_status(state)


# ══════════════════════════════════════════════════════════════
#  CLI
# ══════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="ASR 7-Agent Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  python3 asr_system.py --run-all           Full daily loop (all 7 agents)
  python3 asr_system.py --leads             Agent 1: Find hiring companies
  python3 asr_system.py --outreach          Agent 2: Send HR outreach
  python3 asr_system.py --meetings          Agent 3: Book meetings from replies
  python3 asr_system.py --candidates        Agent 4: Pull new candidates
  python3 asr_system.py --parse             Agent 5: Score resumes
  python3 asr_system.py --match "BPO Lucknow" Agent 6: Match to requirement
  python3 asr_system.py --schedule          Agent 7: Schedule interviews
  python3 asr_system.py --status            Show today's numbers
        """
    )
    parser.add_argument("--run-all",    action="store_true")
    parser.add_argument("--leads",      action="store_true")
    parser.add_argument("--outreach",   action="store_true")
    parser.add_argument("--meetings",   action="store_true")
    parser.add_argument("--candidates", action="store_true")
    parser.add_argument("--parse",      action="store_true")
    parser.add_argument("--match",      type=str, metavar="QUERY")
    parser.add_argument("--schedule",   action="store_true")
    parser.add_argument("--status",     action="store_true")
    args = parser.parse_args()

    state = load_state()

    if args.run_all:   run_all(state)
    elif args.leads:   run_lead_agent(state); save_state(state)
    elif args.outreach:run_outreach_agent(state); save_state(state)
    elif args.meetings:run_meeting_agent(state); save_state(state)
    elif args.candidates: run_candidate_agent(state); save_state(state)
    elif args.parse:   run_parser_agent(state); save_state(state)
    elif args.match:   run_matching_agent(state, args.match); save_state(state)
    elif args.schedule:run_scheduler_agent(state); save_state(state)
    elif args.status:  print_status(state)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
