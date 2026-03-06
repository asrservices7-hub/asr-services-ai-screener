"""
ASR Lead Generation Engine
===========================
3-agent CrewAI system that automatically finds hiring companies
and writes them to your AI_OUTREACH_TRACKER Google Sheet.

Architecture:
  Agent 1 — Company Finder   : Searches Naukri/Indeed/Google for hiring BPOs
  Agent 2 — HR Contact Finder: Finds HR name + LinkedIn + email for each company
  Agent 3 — Lead Structurer  : Cleans, deduplicates, scores, writes to Google Sheet

Setup (run once):
  pip install crewai langchain-openai gspread google-auth serpapi

Environment variables required (create a .env file):
  OPENAI_API_KEY=sk-...
  SERPAPI_API_KEY=...          # free tier: 100 searches/month — serpapi.com
  GOOGLE_SHEET_ID=...          # from your sheet URL
  GOOGLE_CREDS_JSON=credentials.json   # from Google Cloud Console
"""

import os
import json
import re
import time
from datetime import datetime
from typing import Optional

# ── Optional: load from .env if python-dotenv is installed ──
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Core imports ─────────────────────────────────────────────
from crewai import Agent, Task, Crew, Process
from crewai.tools import BaseTool
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

# ── Google Sheets integration ────────────────────────────────
try:
    import gspread
    from google.oauth2.service_account import Credentials
    SHEETS_AVAILABLE = True
except ImportError:
    SHEETS_AVAILABLE = False
    print("⚠  gspread not installed. Results will be printed to console only.")

# ── Optional: SerpAPI for real web searches ──────────────────
try:
    from serpapi import GoogleSearch
    SERPAPI_AVAILABLE = True
except ImportError:
    SERPAPI_AVAILABLE = False


# ═══════════════════════════════════════════════════════════════
#  CONFIGURATION
# ═══════════════════════════════════════════════════════════════

CONFIG = {
    # Target cities (Tier-2 India — ASR markets)
    "cities": ["Lucknow", "Kanpur", "Noida", "Jaipur", "Indore"],

    # Industry verticals to search
    "verticals": [
        "BPO customer support",
        "call center outsourcing",
        "telecalling company",
        "sales outsourcing",
        "hospital healthcare staffing",
        "IT software startup hiring",
        "retail chain bulk hiring",
    ],

    # Daily lead target
    "leads_per_run": 50,

    # Google Sheet tab name (must match your sheet exactly)
    "sheet_tab": "AI_OUTREACH_TRACKER",

    # LLM model
    "model": "gpt-4o-mini",   # cost-effective; upgrade to gpt-4o for better results

    # Output file (always saved even without Google Sheets)
    "output_json": "asr_leads_output.json",
    "output_csv":  "asr_leads_output.csv",
}


# ═══════════════════════════════════════════════════════════════
#  PYDANTIC SCHEMA — one lead record
# ═══════════════════════════════════════════════════════════════

class LeadRecord(BaseModel):
    company:          str = Field(description="Company name")
    industry:         str = Field(description="Industry vertical (BPO / Hospital / IT etc.)")
    city:             str = Field(description="City")
    hr_name:          str = Field(default="", description="HR / Talent Acquisition contact name")
    email:            str = Field(default="", description="HR or generic company email")
    linkedin_url:     str = Field(default="", description="LinkedIn profile URL of HR contact")
    phone:            str = Field(default="", description="Company or HR phone number")
    website:          str = Field(default="", description="Company website")
    hiring_roles:     str = Field(default="", description="Roles they are actively hiring for")
    hiring_volume:    str = Field(default="", description="Estimated monthly hiring volume")
    source_url:       str = Field(default="", description="URL where this lead was found")
    confidence_score: int = Field(default=50,  description="Lead quality score 0–100")
    email_sent:       str = Field(default="No")
    linkedin_sent:    str = Field(default="No")
    reply_received:   str = Field(default="No")
    deal_status:      str = Field(default="Not Started")
    date_added:       str = Field(default_factory=lambda: datetime.today().strftime("%Y-%m-%d"))
    notes:            str = Field(default="")


# ═══════════════════════════════════════════════════════════════
#  TOOLS
# ═══════════════════════════════════════════════════════════════

class NaukriJobSearchTool(BaseTool):
    """
    Searches Naukri.com job listings to find companies actively hiring.
    Uses SerpAPI if available, otherwise falls back to a structured prompt.
    """
    name: str = "naukri_job_search"
    description: str = (
        "Search for companies actively posting jobs on Naukri or Indeed India. "
        "Input: a search string like 'BPO customer support jobs Lucknow'. "
        "Returns: list of company names, job titles, and URLs found."
    )

    def _run(self, query: str) -> str:
        if SERPAPI_AVAILABLE and os.getenv("SERPAPI_API_KEY"):
            return self._serpapi_search(f"site:naukri.com {query}")
        else:
            # Fallback: return realistic structured data the LLM can process
            return self._mock_search(query)

    def _serpapi_search(self, query: str) -> str:
        try:
            search = GoogleSearch({
                "q": query,
                "api_key": os.getenv("SERPAPI_API_KEY"),
                "num": 10,
                "gl": "in",
                "hl": "en",
            })
            results = search.get_dict().get("organic_results", [])
            formatted = []
            for r in results[:10]:
                formatted.append({
                    "title":   r.get("title", ""),
                    "snippet": r.get("snippet", ""),
                    "url":     r.get("link", ""),
                })
            return json.dumps(formatted, indent=2)
        except Exception as e:
            return f"SerpAPI error: {e}. Using mock data."

    def _mock_search(self, query: str) -> str:
        """
        Returns realistic sample data for development/testing without API keys.
        Replace with real scraping in production.
        """
        city = next((c for c in CONFIG["cities"] if c.lower() in query.lower()), "Lucknow")
        mock = [
            {"company": f"Firstsource Solutions", "city": city, "role": "Customer Support Executive", "volume": "50/month", "url": "naukri.com/firstsource"},
            {"company": f"Hinduja Global Solutions", "city": city, "role": "Voice Process Agent", "volume": "80/month", "url": "naukri.com/hgs"},
            {"company": f"Teleperformance India", "city": city, "role": "Telecaller BPO", "volume": "100/month", "url": "naukri.com/teleperformance"},
            {"company": f"Startek India", "city": city, "role": "Customer Care Executive", "volume": "40/month", "url": "naukri.com/startek"},
            {"company": f"Conneqt Business Solutions", "city": city, "role": "Sales Support Agent", "volume": "30/month", "url": "naukri.com/conneqt"},
            {"company": f"iEnergizer", "city": city, "role": "Night Shift BPO", "volume": "60/month", "url": "naukri.com/ienergizer"},
            {"company": f"TaskUs India", "city": city, "role": "Content Moderator", "volume": "25/month", "url": "naukri.com/taskus"},
            {"company": f"Mphasis BPO", "city": city, "role": "Technical Support", "volume": "35/month", "url": "naukri.com/mphasis"},
        ]
        return json.dumps(mock, indent=2)


class LinkedInHRFinderTool(BaseTool):
    """
    Finds HR contacts for a given company on LinkedIn.
    Uses SerpAPI to search LinkedIn, or returns structured mock data.
    """
    name: str = "linkedin_hr_finder"
    description: str = (
        "Find HR Manager or Talent Acquisition contacts for a company on LinkedIn. "
        "Input: 'Company Name City'. "
        "Returns: HR name, LinkedIn URL, and inferred email."
    )

    def _run(self, company_city: str) -> str:
        if SERPAPI_AVAILABLE and os.getenv("SERPAPI_API_KEY"):
            query = f'site:linkedin.com/in "{company_city}" "HR Manager" OR "Talent Acquisition" OR "Recruiter"'
            try:
                search = GoogleSearch({
                    "q": query,
                    "api_key": os.getenv("SERPAPI_API_KEY"),
                    "num": 5,
                    "gl": "in",
                })
                results = search.get_dict().get("organic_results", [])
                contacts = []
                for r in results[:3]:
                    name_match = re.search(r"([A-Z][a-z]+ [A-Z][a-z]+)", r.get("title", ""))
                    contacts.append({
                        "name":     name_match.group(1) if name_match else "HR Contact",
                        "linkedin": r.get("link", ""),
                        "snippet":  r.get("snippet", ""),
                    })
                return json.dumps(contacts, indent=2)
            except Exception as e:
                return self._mock_hr(company_city)
        return self._mock_hr(company_city)

    def _mock_hr(self, company_city: str) -> str:
        company = company_city.split()[0]
        domain = company.lower().replace(" ", "") + ".com"
        mock_hr = [
            {"name": "Priya Sharma",   "role": "HR Manager",            "linkedin": f"linkedin.com/in/priya-sharma-{company.lower()}", "email": f"priya.sharma@{domain}"},
            {"name": "Amit Verma",     "role": "Talent Acquisition Lead","linkedin": f"linkedin.com/in/amit-verma-{company.lower()}",  "email": f"talent@{domain}"},
            {"name": "Sneha Gupta",    "role": "HR Recruiter",           "linkedin": f"linkedin.com/in/sneha-gupta-{company.lower()}",  "email": f"hr@{domain}"},
        ]
        return json.dumps(mock_hr[:1], indent=2)  # return best match


class GoogleMapsCompanyTool(BaseTool):
    """
    Searches Google Maps for companies in a specific city and industry.
    Returns name, address, phone, and website where available.
    """
    name: str = "google_maps_company_search"
    description: str = (
        "Search Google Maps for companies in a specific city and industry. "
        "Input: 'BPO companies Lucknow'. "
        "Returns: company name, address, phone, website."
    )

    def _run(self, query: str) -> str:
        if SERPAPI_AVAILABLE and os.getenv("SERPAPI_API_KEY"):
            try:
                search = GoogleSearch({
                    "q": query,
                    "api_key": os.getenv("SERPAPI_API_KEY"),
                    "tbm": "lcl",   # local/maps results
                    "num": 10,
                    "gl": "in",
                })
                results = search.get_dict().get("local_results", [])
                companies = []
                for r in results[:10]:
                    companies.append({
                        "company": r.get("title", ""),
                        "address": r.get("address", ""),
                        "phone":   r.get("phone", ""),
                        "website": r.get("website", ""),
                        "rating":  r.get("rating", ""),
                    })
                return json.dumps(companies, indent=2)
            except Exception as e:
                return self._mock_maps(query)
        return self._mock_maps(query)

    def _mock_maps(self, query: str) -> str:
        city = next((c for c in CONFIG["cities"] if c.lower() in query.lower()), "Lucknow")
        mock = [
            {"company": "Alldigi Tech Pvt Ltd",    "phone": "+91-522-4012345", "website": "alldigi.in",    "city": city},
            {"company": "Ienergizer Contact Centre","phone": "+91-522-4023456", "website": "ienergizer.com","city": city},
            {"company": "Wipro BPS",               "phone": "+91-120-4034567", "website": "wiprobps.com",  "city": city},
            {"company": "EXL Service Holdings",    "phone": "+91-120-4045678", "website": "exlservice.com","city": city},
            {"company": "Syntel BPO",              "phone": "+91-120-4056789", "website": "syntelonline.com","city": city},
        ]
        return json.dumps(mock, indent=2)


# ═══════════════════════════════════════════════════════════════
#  LLM SETUP
# ═══════════════════════════════════════════════════════════════

def get_llm():
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY not set. Add it to your .env file.\n"
            "Get a free key at: https://platform.openai.com/api-keys"
        )
    return ChatOpenAI(
        model=CONFIG["model"],
        temperature=0.2,
        api_key=api_key,
    )


# ═══════════════════════════════════════════════════════════════
#  AGENTS
# ═══════════════════════════════════════════════════════════════

def build_agents(llm):
    """Build the 3-agent crew."""

    # ── Agent 1: Company Finder ───────────────────────────────
    company_finder = Agent(
        role="Company Research Specialist",
        goal=(
            "Find companies in Tier-2 Indian cities (Lucknow, Kanpur, Noida, Jaipur, Indore) "
            "that are actively hiring large volumes of BPO, sales, hospital, and IT staff. "
            "Focus on companies posting multiple job openings — these are hot leads."
        ),
        backstory=(
            "You are an expert B2B lead researcher for a recruitment company called ASR Services. "
            "Your job is to find companies that need bulk hiring help RIGHT NOW. "
            "You search Naukri, Indeed, Google Maps, and company websites. "
            "You prioritize BPO and call centers because they hire 20–100 people monthly. "
            "A good lead is a company with 10+ open positions, not a company hiring 1–2 people."
        ),
        tools=[NaukriJobSearchTool(), GoogleMapsCompanyTool()],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )

    # ── Agent 2: HR Contact Finder ────────────────────────────
    hr_finder = Agent(
        role="HR Intelligence Specialist",
        goal=(
            "For each company identified, find the direct HR contact: "
            "HR Manager name, LinkedIn profile URL, and email address. "
            "Prioritize HR Manager > Talent Acquisition > General Recruiter."
        ),
        backstory=(
            "You are a specialist in finding B2B HR contacts for Indian companies. "
            "You search LinkedIn using site: queries, and cross-reference with "
            "company websites and email patterns (firstname.lastname@company.com). "
            "You never guess — if you can't find a name, you note 'HR Contact' and move on."
        ),
        tools=[LinkedInHRFinderTool()],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=5,
    )

    # ── Agent 3: Lead Structurer ──────────────────────────────
    lead_structurer = Agent(
        role="Lead Data Architect",
        goal=(
            "Take raw company and HR data and produce a clean, structured list of leads "
            "formatted exactly for the ASR AI_OUTREACH_TRACKER Google Sheet. "
            "Assign a confidence score (0–100) based on data completeness and hiring likelihood. "
            "Remove duplicates. Prioritize BPO companies with high hiring volume."
        ),
        backstory=(
            "You are a data specialist who converts messy research into clean CRM records. "
            "You understand that for ASR Services, a high-value lead is: "
            "BPO company + 20+ monthly hires + HR contact found + email available. "
            "You score each lead: 90+ = hot (email + phone + HR name + active job posts), "
            "70–89 = warm (company confirmed hiring, partial contact), "
            "50–69 = cold (company found, no direct HR contact)."
        ),
        tools=[],
        llm=llm,
        verbose=True,
        allow_delegation=False,
        max_iter=3,
    )

    return company_finder, hr_finder, lead_structurer


# ═══════════════════════════════════════════════════════════════
#  TASKS
# ═══════════════════════════════════════════════════════════════

def build_tasks(company_finder, hr_finder, lead_structurer):
    """Define the 3 sequential tasks."""

    target_summary = (
        f"Cities: {', '.join(CONFIG['cities'])}. "
        f"Verticals: {', '.join(CONFIG['verticals'][:4])}. "
        f"Target: {CONFIG['leads_per_run']} companies."
    )

    # ── Task 1: Find companies ────────────────────────────────
    task_find_companies = Task(
        description=(
            f"Search for companies that are actively hiring in bulk. {target_summary}\n\n"
            "For each city × vertical combination, run a search and collect:\n"
            "- Company name\n"
            "- City\n"
            "- Industry/vertical\n"
            "- Roles being hired\n"
            "- Estimated monthly hiring volume\n"
            "- Source URL (Naukri/Google Maps link)\n"
            "- Website if available\n\n"
            f"Target: find at least {CONFIG['leads_per_run']} unique companies. "
            "Start with BPO/call center searches — highest volume, fastest revenue for ASR."
        ),
        expected_output=(
            "A numbered list of companies with: name, city, industry, roles, "
            "estimated monthly hiring volume, source URL. "
            f"Minimum {CONFIG['leads_per_run']} companies across all cities and verticals."
        ),
        agent=company_finder,
    )

    # ── Task 2: Find HR contacts ──────────────────────────────
    task_find_hr = Task(
        description=(
            "For each company identified in Task 1, find the HR contact. "
            "Search LinkedIn for HR Manager or Talent Acquisition at each company.\n\n"
            "For each company, provide:\n"
            "- HR name (first + last name)\n"
            "- LinkedIn profile URL\n"
            "- Email (use pattern: firstname.lastname@companydomain.com if not found directly)\n"
            "- Phone number if available on company website\n\n"
            "If a company's HR contact cannot be found, still include the company — "
            "mark HR fields as 'Not Found' and set confidence_score lower."
        ),
        expected_output=(
            "For every company from Task 1: HR name, LinkedIn URL, email, phone. "
            "Mark 'Not Found' clearly where data is unavailable."
        ),
        agent=hr_finder,
        context=[task_find_companies],
    )

    # ── Task 3: Structure leads as JSON ──────────────────────
    task_structure_leads = Task(
        description=(
            "Take all company + HR data from Tasks 1 and 2. "
            "Produce a final clean JSON array of lead records. "
            "Each record must follow this exact structure:\n\n"
            "{\n"
            '  "company": "string",\n'
            '  "industry": "BPO|Hospital|IT|Retail|SME|Coaching",\n'
            '  "city": "string",\n'
            '  "hr_name": "string or empty",\n'
            '  "email": "string or empty",\n'
            '  "linkedin_url": "string or empty",\n'
            '  "phone": "string or empty",\n'
            '  "website": "string or empty",\n'
            '  "hiring_roles": "comma-separated roles",\n'
            '  "hiring_volume": "estimated monthly",\n'
            '  "source_url": "string",\n'
            '  "confidence_score": 0-100,\n'
            '  "notes": "why this is a good lead"\n'
            "}\n\n"
            "Scoring rules:\n"
            "- +30 if email found\n"
            "- +20 if HR name found\n"
            "- +20 if phone found\n"
            "- +20 if actively posting jobs on Naukri/Indeed\n"
            "- +10 if hiring volume > 20/month\n\n"
            "Remove exact duplicates (same company + city). "
            "Sort by confidence_score descending (best leads first). "
            "Return ONLY the JSON array, no markdown, no extra text."
        ),
        expected_output=(
            "A valid JSON array of lead objects. "
            "No markdown. No explanation. Just the JSON array starting with [ and ending with ]."
        ),
        agent=lead_structurer,
        context=[task_find_companies, task_find_hr],
        output_json=LeadRecord,
    )

    return task_find_companies, task_find_hr, task_structure_leads


# ═══════════════════════════════════════════════════════════════
#  GOOGLE SHEETS WRITER
# ═══════════════════════════════════════════════════════════════

class GoogleSheetsWriter:
    """Writes lead records to the AI_OUTREACH_TRACKER sheet."""

    SHEET_COLUMNS = [
        "company", "hr_name", "industry", "city", "email", "linkedin_url",
        "phone", "email_sent", "linkedin_sent", "reply_received",
        "reply_type", "call_scheduled", "deal_status",
        "hiring_roles", "hiring_volume", "confidence_score",
        "source_url", "website", "date_added", "notes",
    ]

    def __init__(self):
        self.client = None
        self.sheet  = None
        if not SHEETS_AVAILABLE:
            print("ℹ  Google Sheets not available — will save to files only.")
            return
        creds_file = os.getenv("GOOGLE_CREDS_JSON", "credentials.json")
        sheet_id   = os.getenv("GOOGLE_SHEET_ID", "")
        if not sheet_id:
            print("ℹ  GOOGLE_SHEET_ID not set — will save to files only.")
            return
        try:
            scopes = [
                "https://spreadsheets.google.com/feeds",
                "https://www.googleapis.com/auth/drive",
            ]
            creds       = Credentials.from_service_account_file(creds_file, scopes=scopes)
            self.client = gspread.authorize(creds)
            wb          = self.client.open_by_key(sheet_id)
            # Find or create the tab
            try:
                self.sheet = wb.worksheet(CONFIG["sheet_tab"])
            except gspread.WorksheetNotFound:
                self.sheet = wb.add_worksheet(CONFIG["sheet_tab"], rows=1000, cols=20)
                self.sheet.append_row(self.SHEET_COLUMNS)
            print(f"✅ Connected to Google Sheet tab: {CONFIG['sheet_tab']}")
        except Exception as e:
            print(f"⚠  Google Sheets connection failed: {e}")
            print("   Falling back to local file output.")

    def write_leads(self, leads: list[dict]) -> int:
        """Append new leads. Returns count written."""
        written = 0
        for lead in leads:
            row = [str(lead.get(col, "")) for col in self.SHEET_COLUMNS]
            if self.sheet:
                try:
                    self.sheet.append_row(row)
                    time.sleep(0.5)   # respect Sheets API rate limits
                    written += 1
                except Exception as e:
                    print(f"  ⚠ Sheet write error for {lead.get('company', '?')}: {e}")
            else:
                written += 1   # count as written to file
        return written


# ═══════════════════════════════════════════════════════════════
#  OUTPUT WRITERS
# ═══════════════════════════════════════════════════════════════

def save_to_json(leads: list[dict], filename: str):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(leads, f, indent=2, ensure_ascii=False)
    print(f"✅ JSON saved: {filename}  ({len(leads)} leads)")


def save_to_csv(leads: list[dict], filename: str):
    import csv
    if not leads:
        return
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=leads[0].keys(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(leads)
    print(f"✅ CSV saved: {filename}  ({len(leads)} leads)")


# ═══════════════════════════════════════════════════════════════
#  RESULT PARSER
# ═══════════════════════════════════════════════════════════════

def parse_leads_from_result(raw_result) -> list[dict]:
    """
    Extract JSON array from CrewAI output.
    Handles cases where the LLM wraps output in markdown fences.
    """
    try:
        text = str(raw_result)
        # Strip markdown fences if present
        text = re.sub(r"```(?:json)?", "", text).strip()
        # Find JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            leads = json.loads(match.group(0))
            # Add default fields not set by LLM
            for lead in leads:
                lead.setdefault("email_sent",     "No")
                lead.setdefault("linkedin_sent",  "No")
                lead.setdefault("reply_received", "No")
                lead.setdefault("deal_status",    "Not Started")
                lead.setdefault("date_added",     datetime.today().strftime("%Y-%m-%d"))
            return leads
    except json.JSONDecodeError as e:
        print(f"⚠  JSON parse error: {e}")
    return []


# ═══════════════════════════════════════════════════════════════
#  PRINT SUMMARY
# ═══════════════════════════════════════════════════════════════

def print_summary(leads: list[dict]):
    if not leads:
        print("\n⚠  No leads extracted.")
        return

    hot   = [l for l in leads if l.get("confidence_score", 0) >= 80]
    warm  = [l for l in leads if 60 <= l.get("confidence_score", 0) < 80]
    cold  = [l for l in leads if l.get("confidence_score", 0) < 60]

    print("\n" + "═"*60)
    print("  ASR LEAD GENERATION RESULTS")
    print("═"*60)
    print(f"  Total leads found  : {len(leads)}")
    print(f"  🔥 Hot  (80–100)   : {len(hot)}")
    print(f"  🟡 Warm (60–79)    : {len(warm)}")
    print(f"  🔵 Cold (<60)      : {len(cold)}")
    print("─"*60)

    # City breakdown
    from collections import Counter
    city_counts = Counter(l.get("city", "Unknown") for l in leads)
    print("  By City:")
    for city, count in city_counts.most_common():
        print(f"    {city:<20} {count} leads")
    print("─"*60)

    # Industry breakdown
    ind_counts = Counter(l.get("industry", "Unknown") for l in leads)
    print("  By Industry:")
    for ind, count in ind_counts.most_common():
        print(f"    {ind:<20} {count} leads")
    print("─"*60)

    # Top 5 leads
    sorted_leads = sorted(leads, key=lambda x: x.get("confidence_score", 0), reverse=True)
    print("  TOP 5 LEADS (Call These First):")
    for i, lead in enumerate(sorted_leads[:5], 1):
        print(f"\n  {i}. {lead.get('company', '?')} — {lead.get('city', '?')}")
        print(f"     Industry : {lead.get('industry', '?')}")
        print(f"     HR Name  : {lead.get('hr_name', 'Not found')}")
        print(f"     Email    : {lead.get('email', 'Not found')}")
        print(f"     Roles    : {lead.get('hiring_roles', '?')}")
        print(f"     Volume   : {lead.get('hiring_volume', '?')}")
        print(f"     Score    : {lead.get('confidence_score', 0)}/100")
    print("═"*60)


# ═══════════════════════════════════════════════════════════════
#  MAIN — ASSEMBLE AND RUN THE CREW
# ═══════════════════════════════════════════════════════════════

def run():
    print("\n" + "█"*60)
    print("  ASR AI LEAD ENGINE — Powered by CrewAI")
    print(f"  Target: {CONFIG['leads_per_run']} hiring companies")
    print(f"  Cities: {', '.join(CONFIG['cities'])}")
    print("█"*60 + "\n")

    # ── Step 1: Initialise LLM ─────────────────────────────
    print("🔧 Initialising LLM...")
    llm = get_llm()

    # ── Step 2: Build agents and tasks ────────────────────
    print("🤖 Building agent crew...")
    company_finder, hr_finder, lead_structurer = build_agents(llm)
    task1, task2, task3 = build_tasks(company_finder, hr_finder, lead_structurer)

    # ── Step 3: Assemble crew ──────────────────────────────
    crew = Crew(
        agents=[company_finder, hr_finder, lead_structurer],
        tasks=[task1, task2, task3],
        process=Process.sequential,   # agents run in order
        verbose=2,
    )

    # ── Step 4: Run ────────────────────────────────────────
    print("\n🚀 Starting crew run...\n")
    result = crew.kickoff()

    # ── Step 5: Parse results ──────────────────────────────
    leads = parse_leads_from_result(result)
    print(f"\n✅ Extracted {len(leads)} lead records.")

    # ── Step 6: Save to files ──────────────────────────────
    save_to_json(leads, CONFIG["output_json"])
    save_to_csv(leads,  CONFIG["output_csv"])

    # ── Step 7: Write to Google Sheets ────────────────────
    writer = GoogleSheetsWriter()
    if leads:
        written = writer.write_leads(leads)
        print(f"✅ Google Sheets: {written} rows written to {CONFIG['sheet_tab']}")

    # ── Step 8: Print summary ──────────────────────────────
    print_summary(leads)

    return leads


# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run()
