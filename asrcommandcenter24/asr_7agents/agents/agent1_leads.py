"""
Agent 1 — Lead Generation
Finds companies actively hiring using CrewAI + SerpAPI.
Falls back to realistic mock data when APIs not configured.
"""

import os, json
from datetime import datetime

CITIES     = ["Lucknow", "Kanpur", "Noida", "Jaipur", "Indore"]
VERTICALS  = ["BPO customer support", "call center", "hospital healthcare staffing",
               "IT startup hiring", "retail bulk hiring", "sales outsourcing"]

# ── Optional: real search via SerpAPI ────────────────────────
try:
    from serpapi import GoogleSearch
    SERPAPI_KEY = os.getenv("SERPAPI_API_KEY", "")
    SERPAPI_OK  = bool(SERPAPI_KEY)
except ImportError:
    SERPAPI_OK = False

# ── Optional: CrewAI enrichment ──────────────────────────────
try:
    from crewai import Agent, Task, Crew, Process
    from langchain_openai import ChatOpenAI
    CREWAI_OK = bool(os.getenv("OPENAI_API_KEY"))
except ImportError:
    CREWAI_OK = False


class LeadAgent:

    OUTPUT_FILE = "leads_output.json"

    MOCK_COMPANIES = [
        {"company":"Teleperformance","city":"Kanpur","industry":"BPO","roles":"Customer Support","volume":"80/month","score":92,"email":"hr@teleperformance.com","phone":"+91-512-4001234","website":"teleperformance.com"},
        {"company":"iEnergizer","city":"Lucknow","industry":"BPO","roles":"Voice Process","volume":"60/month","score":88,"email":"talent@ienergizer.com","phone":"+91-522-4002345","website":"ienergizer.com"},
        {"company":"Concentrix","city":"Lucknow","industry":"BPO","roles":"Customer Care","volume":"70/month","score":90,"email":"hr@concentrix.com","phone":"+91-522-4003456","website":"concentrix.com"},
        {"company":"Genpact","city":"Noida","industry":"BPO","roles":"Finance BPO","volume":"50/month","score":85,"email":"careers@genpact.com","phone":"+91-120-4004567","website":"genpact.com"},
        {"company":"Sutherland Global","city":"Jaipur","industry":"BPO","roles":"Voice Support","volume":"45/month","score":83,"email":"hr@sutherlandglobal.com","phone":"+91-141-4005678","website":"sutherlandglobal.com"},
        {"company":"Fortis Hospital","city":"Noida","industry":"Hospital","roles":"Staff Nurses, Lab Tech","volume":"20/month","score":79,"email":"hr@fortishealthcare.com","phone":"+91-120-4006789","website":"fortishealthcare.com"},
        {"company":"Narayana Hospital","city":"Jaipur","industry":"Hospital","roles":"Nurses, Admin","volume":"18/month","score":75,"email":"hr@narayanahealth.org","phone":"+91-141-4007890","website":"narayanahealth.org"},
        {"company":"Shiprocket","city":"Noida","industry":"IT/Startup","roles":"Tech Support, Dev","volume":"15/month","score":78,"email":"hr@shiprocket.com","phone":"+91-120-4008901","website":"shiprocket.com"},
        {"company":"V-Mart Retail","city":"Lucknow","industry":"Retail","roles":"Floor Supervisors","volume":"25/month","score":74,"email":"hr@vmart.co.in","phone":"+91-522-4009012","website":"vmart.co.in"},
        {"company":"Taskus India","city":"Noida","industry":"BPO","roles":"Content Moderation","volume":"30/month","score":81,"email":"recruiting@taskus.com","phone":"+91-120-4010123","website":"taskus.com"},
        {"company":"Mphasis BPO","city":"Kanpur","industry":"BPO","roles":"Technical Support","volume":"35/month","score":80,"email":"hr@mphasis.com","phone":"+91-512-4011234","website":"mphasis.com"},
        {"company":"EXL Service","city":"Noida","industry":"BPO","roles":"Analytics, Voice","volume":"40/month","score":82,"email":"careers@exlservice.com","phone":"+91-120-4012345","website":"exlservice.com"},
        {"company":"WNS Global","city":"Indore","industry":"BPO","roles":"F&A, Customer Support","volume":"55/month","score":86,"email":"hr@wns.com","phone":"+91-731-4013456","website":"wns.com"},
        {"company":"Firstsource Solutions","city":"Jaipur","industry":"BPO","roles":"Collections, Support","volume":"45/month","score":84,"email":"careers@firstsource.com","phone":"+91-141-4014567","website":"firstsource.com"},
        {"company":"IndiaMart","city":"Noida","industry":"SME","roles":"Sales Executives","volume":"20/month","score":71,"email":"hr@indiamart.com","phone":"+91-120-4015678","website":"indiamart.com"},
    ]

    def run(self) -> list:
        if CREWAI_OK:
            return self._run_crewai()
        elif SERPAPI_OK:
            return self._run_serpapi()
        else:
            return self._run_mock()

    def _run_mock(self) -> list:
        print("  ℹ  Running in demo mode (no API keys). Returning 15 sample leads.")
        print("     Add OPENAI_API_KEY + SERPAPI_API_KEY for real web searches.")
        leads = [dict(l, date_added=datetime.today().strftime("%Y-%m-%d"),
                      email_sent="No", deal_status="Not Started") for l in self.MOCK_COMPANIES]
        self._save(leads)
        return leads

    def _run_serpapi(self) -> list:
        """Real searches via SerpAPI when OpenAI not available."""
        leads = []
        for city in CITIES[:3]:           # limit to 3 cities per run
            for vertical in VERTICALS[:3]:
                query = f"{vertical} companies hiring {city} India"
                try:
                    search = GoogleSearch({"q": query, "api_key": SERPAPI_KEY, "num": 5, "gl": "in"})
                    results = search.get_dict().get("organic_results", [])
                    for r in results:
                        leads.append({
                            "company": r.get("title", "").split(" - ")[0][:50],
                            "city": city, "industry": vertical.split()[0].title(),
                            "roles": vertical, "volume": "Unknown",
                            "score": 60,
                            "email": "", "phone": "", "website": r.get("link", ""),
                            "date_added": datetime.today().strftime("%Y-%m-%d"),
                            "email_sent": "No", "deal_status": "Not Started",
                        })
                except Exception as e:
                    print(f"  ⚠  SerpAPI error: {e}")
        self._save(leads)
        return leads

    def _run_crewai(self) -> list:
        """Full CrewAI run — requires OPENAI_API_KEY."""
        from crewai import Agent, Task, Crew, Process
        from langchain_openai import ChatOpenAI
        import re

        llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.2,
                         api_key=os.getenv("OPENAI_API_KEY"))

        finder = Agent(
            role="B2B Lead Researcher",
            goal="Find BPO and bulk-hiring companies in Tier-2 Indian cities",
            backstory="Expert in finding companies hiring 20+ people monthly in India. Focus on BPO first.",
            llm=llm, verbose=False, max_iter=3,
        )
        task = Task(
            description=(
                f"Find 20 companies hiring in bulk in these cities: {', '.join(CITIES)}. "
                "Prioritise BPO/call center companies. Return JSON array with fields: "
                "company, city, industry, roles, volume (monthly), score (0-100), email, phone, website."
                "Return ONLY the JSON array."
            ),
            expected_output="JSON array of lead objects",
            agent=finder,
        )
        crew = Crew(agents=[finder], tasks=[task], process=Process.sequential, verbose=False)
        raw = str(crew.kickoff())
        try:
            m = __import__("re").search(r"\[.*\]", raw, __import__("re").DOTALL)
            leads = json.loads(m.group(0)) if m else self.MOCK_COMPANIES
        except Exception:
            leads = self.MOCK_COMPANIES

        for l in leads:
            l.setdefault("date_added", datetime.today().strftime("%Y-%m-%d"))
            l.setdefault("email_sent", "No")
            l.setdefault("deal_status", "Not Started")
        self._save(leads)
        return leads

    def _save(self, leads: list):
        with open(self.OUTPUT_FILE, "w") as f:
            json.dump(leads, f, indent=2)
        print(f"  💾 Saved to {self.OUTPUT_FILE}")
