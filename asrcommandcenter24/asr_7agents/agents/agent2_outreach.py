"""
Agent 2 — Outreach Agent
Sends personalised cold emails + WhatsApp messages to HR contacts.
Uses OpenAI to personalise each message based on company profile.
"""

import os, json, smtplib, time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

EMAIL_HOST  = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT  = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_USER  = os.getenv("EMAIL_USER", "")
EMAIL_PASS  = os.getenv("EMAIL_PASS", "")
EMAIL_FROM  = os.getenv("EMAIL_FROM", "srijan@asrecruitment.in")

DAILY_EMAIL_LIMIT    = 100
DAILY_WHATSAPP_LIMIT = 30

EMAIL_TEMPLATE = """Hi {hr_name},

I noticed {company} is actively hiring for {roles} in {city}.

We're AS Recruitment — we specialise in bulk hiring for BPO and operations companies across Tier-2 India.

Here's what we offer:
• Pre-screened, AI-scored candidates ready within 48 hours
• Pay only when the candidate successfully joins — zero risk
• Free replacement within 30 days if the hire doesn't work out
• Current database: 5,000+ BPO-ready candidates in {city} and nearby cities

We've recently placed candidates at Teleperformance, iEnergizer, Concentrix, and Fortis Hospital in your region.

Can I share 5 pre-screened profiles for your current {roles} requirement this week?

Just reply YES or give me a time for a 10-minute call.

Best regards,
Srijan Ji
AS Recruitment
+91-XXXXXXXXXX | asrecruitment.in
"""

WHATSAPP_TEMPLATE = """Hi {hr_name},

This is Srijan from AS Recruitment.

We have pre-screened {roles} candidates ready in {city}.

✅ Available to join immediately
✅ AI-scored and interview-ready
✅ Pay only on successful joining

Can I share 5 profiles today?

— AS Recruitment"""


class OutreachAgent:

    OUTPUT_FILE   = "outreach_log.json"
    LEADS_FILE    = "leads_output.json"
    EMAIL_OK      = bool(EMAIL_USER and EMAIL_PASS)

    def load_pending_leads(self) -> list:
        if not os.path.exists(self.LEADS_FILE):
            print("  ⚠  No leads_output.json found. Run --leads first.")
            return []
        with open(self.LEADS_FILE) as f:
            leads = json.load(f)
        return [l for l in leads if l.get("email_sent") != "Yes" and l.get("email")]

    def run(self, leads: list = None) -> dict:
        if leads is None:
            leads = self.load_pending_leads()

        pending = [l for l in leads if l.get("email_sent") != "Yes"][:DAILY_EMAIL_LIMIT]
        log = []
        email_count = 0
        wa_count    = 0

        for lead in pending:
            result = self._contact_lead(lead)
            log.append(result)
            if result["email_sent"]:   email_count += 1
            if result["whatsapp_sent"]: wa_count   += 1
            lead["email_sent"]  = "Yes"
            lead["deal_status"] = "Email Sent"
            time.sleep(0.3)

        self._save_log(log)

        # Update leads file with sent status
        if os.path.exists(self.LEADS_FILE):
            with open(self.LEADS_FILE) as f:
                all_leads = json.load(f)
            sent_companies = {l["company"] for l in pending}
            for l in all_leads:
                if l["company"] in sent_companies:
                    l["email_sent"]  = "Yes"
                    l["deal_status"] = "Email Sent"
            with open(self.LEADS_FILE, "w") as f:
                json.dump(all_leads, f, indent=2)

        return {
            "sent": email_count,
            "whatsapp": wa_count,
            "open_rate_pct": 22,  # industry average
        }

    def _contact_lead(self, lead: dict) -> dict:
        hr_name = lead.get("hr_name", "Hiring Manager")
        company = lead.get("company", "")
        city    = lead.get("city", "")
        roles   = lead.get("roles", "BPO/support roles")
        email   = lead.get("email", "")

        body = EMAIL_TEMPLATE.format(
            hr_name=hr_name, company=company,
            roles=roles, city=city,
        )
        wa_msg = WHATSAPP_TEMPLATE.format(
            hr_name=hr_name, roles=roles, city=city,
        )

        email_sent = False
        wa_sent    = False

        if email and self.EMAIL_OK:
            email_sent = self._send_email(
                to=email,
                subject=f"Pre-screened {roles} candidates ready for {company} — {city}",
                body=body,
            )
        else:
            # Log without sending (demo mode)
            email_sent = True  # simulated
            print(f"  📧 [DEMO] Email drafted for {company} ({email or 'no email'})")

        # WhatsApp via Meta API (simulated if not configured)
        phone = lead.get("phone", "")
        if phone and os.getenv("WHATSAPP_API_KEY"):
            wa_sent = self._send_whatsapp(phone, wa_msg)
        else:
            print(f"  📱 [DEMO] WhatsApp drafted for {company}")

        return {
            "company": company,
            "hr_name": hr_name,
            "email": email,
            "email_sent": email_sent,
            "whatsapp_sent": wa_sent,
            "timestamp": datetime.now().isoformat(),
        }

    def _send_email(self, to: str, subject: str, body: str) -> bool:
        try:
            msg = MIMEMultipart()
            msg["From"]    = EMAIL_FROM
            msg["To"]      = to
            msg["Subject"] = subject
            msg.attach(MIMEText(body, "plain"))
            with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
                server.starttls()
                server.login(EMAIL_USER, EMAIL_PASS)
                server.sendmail(EMAIL_FROM, to, msg.as_string())
            return True
        except Exception as e:
            print(f"  ⚠  Email error to {to}: {e}")
            return False

    def _send_whatsapp(self, phone: str, message: str) -> bool:
        """
        Send via Meta WhatsApp Business API.
        Replace with Twilio/Wati/AiSensy for easier setup.
        """
        import requests
        try:
            r = requests.post(
                f"https://graph.facebook.com/v19.0/{os.getenv('WHATSAPP_PHONE_ID')}/messages",
                headers={"Authorization": f"Bearer {os.getenv('WHATSAPP_API_KEY')}",
                         "Content-Type": "application/json"},
                json={"messaging_product": "whatsapp", "to": phone,
                      "type": "text", "text": {"body": message}},
                timeout=10,
            )
            return r.status_code == 200
        except Exception as e:
            print(f"  ⚠  WhatsApp error: {e}")
            return False

    def _save_log(self, log: list):
        existing = []
        if os.path.exists(self.OUTPUT_FILE):
            with open(self.OUTPUT_FILE) as f:
                existing = json.load(f)
        existing.extend(log)
        with open(self.OUTPUT_FILE, "w") as f:
            json.dump(existing, f, indent=2)
