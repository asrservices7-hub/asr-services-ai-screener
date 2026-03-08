"""
ASR n8n Companion Script
=========================
This script runs the lead engine on a schedule and optionally
triggers n8n webhooks for:
  - WhatsApp outreach to new leads
  - Email sequence trigger
  - Slack/Telegram daily summary

Works alongside asr_lead_engine.py.
Run via cron: 0 8 * * 1-5 python3 asr_scheduler.py
(Runs Mon–Fri at 8 AM)
"""

import os
import json
import time
import requests
import schedule
from datetime import datetime

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── n8n webhook URLs (set these after importing the n8n workflows) ──
N8N_WEBHOOKS = {
    # Trigger this after new leads are found — n8n sends WhatsApp/email
    "new_leads_found":    os.getenv("N8N_NEW_LEADS_WEBHOOK", ""),
    # Trigger this to send daily summary to Telegram/Slack
    "daily_summary":      os.getenv("N8N_DAILY_SUMMARY_WEBHOOK", ""),
    # Trigger follow-up sequences for leads older than 3 days with no reply
    "followup_trigger":   os.getenv("N8N_FOLLOWUP_WEBHOOK", ""),
}

# ── Telegram bot (optional — for daily summary ─────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID", "")


def trigger_n8n_webhook(webhook_name: str, payload: dict) -> bool:
    """POST payload to n8n webhook. Returns True on success."""
    url = N8N_WEBHOOKS.get(webhook_name, "")
    if not url:
        print(f"  ℹ  n8n webhook '{webhook_name}' not configured. Skipping.")
        return False
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"  ✅ n8n webhook '{webhook_name}' triggered.")
            return True
        else:
            print(f"  ⚠  n8n webhook '{webhook_name}' returned {r.status_code}")
            return False
    except Exception as e:
        print(f"  ⚠  n8n webhook error: {e}")
        return False


def send_telegram_summary(message: str):
    """Send daily summary to Telegram channel."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       message,
            "parse_mode": "Markdown",
        }, timeout=10)
        print("  ✅ Telegram summary sent.")
    except Exception as e:
        print(f"  ⚠  Telegram error: {e}")


def run_daily_lead_generation():
    """
    Daily job: run lead engine, push to n8n, send Telegram summary.
    """
    print(f"\n{'='*50}")
    print(f"ASR Daily Lead Run — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}\n")

    # Run the main lead engine
    try:
        from asr_lead_engine import run
        leads = run()
    except Exception as e:
        print(f"❌ Lead engine error: {e}")
        return

    if not leads:
        print("⚠  No leads generated today.")
        return

    # Push to n8n for outreach automation
    trigger_n8n_webhook("new_leads_found", {
        "leads":          leads,
        "count":          len(leads),
        "date":           datetime.today().strftime("%Y-%m-%d"),
        "hot_leads":      [l for l in leads if l.get("confidence_score", 0) >= 80],
    })

    # Build Telegram summary
    hot   = len([l for l in leads if l.get("confidence_score", 0) >= 80])
    warm  = len([l for l in leads if 60 <= l.get("confidence_score", 0) < 80])
    top3  = sorted(leads, key=lambda x: x.get("confidence_score", 0), reverse=True)[:3]
    top3_text = "\n".join([
        f"  • {l['company']} ({l['city']}) — Score: {l['confidence_score']}"
        for l in top3
    ])

    message = (
        f"*🤖 ASR Daily Lead Report — {datetime.now().strftime('%d %b %Y')}*\n\n"
        f"Total leads found: *{len(leads)}*\n"
        f"🔥 Hot leads: *{hot}*\n"
        f"🟡 Warm leads: *{warm}*\n\n"
        f"*Top 3 to call today:*\n{top3_text}\n\n"
        f"Check your AI\\_OUTREACH\\_TRACKER sheet for the full list."
    )
    send_telegram_summary(message)

    # Trigger follow-up for stale leads
    trigger_n8n_webhook("followup_trigger", {
        "check_leads_older_than_days": 3,
        "date": datetime.today().strftime("%Y-%m-%d"),
    })

    print(f"\n✅ Daily run complete. {len(leads)} leads added.")


def run_weekly_report():
    """
    Weekly summary: revenue pipeline, outreach stats, top clients.
    Runs every Monday morning.
    """
    print("\n📊 Generating weekly report...")
    message = (
        f"*📊 ASR Weekly Report — Week of {datetime.now().strftime('%d %b %Y')}*\n\n"
        "Check your REVENUE\\_FORECAST and HIRING\\_VELOCITY sheets for this week's numbers.\n\n"
        "*Reminder targets this week:*\n"
        "• 500 employer calls\n"
        "• 100 HR conversations\n"
        "• 20 hiring discussions\n"
        "• 5 mandates\n"
        "• 1 retainer pitch to best client"
    )
    send_telegram_summary(message)
    trigger_n8n_webhook("daily_summary", {"type": "weekly", "date": datetime.today().strftime("%Y-%m-%d")})


# ── Schedule ──────────────────────────────────────────────────
# Mon–Fri 8:00 AM: run lead generation
schedule.every().monday.at("08:00").do(run_daily_lead_generation)
schedule.every().tuesday.at("08:00").do(run_daily_lead_generation)
schedule.every().wednesday.at("08:00").do(run_daily_lead_generation)
schedule.every().thursday.at("08:00").do(run_daily_lead_generation)
schedule.every().friday.at("08:00").do(run_daily_lead_generation)

# Every Monday 9:00 AM: weekly summary
schedule.every().monday.at("09:00").do(run_weekly_report)


if __name__ == "__main__":
    print("🕐 ASR Scheduler started. Waiting for scheduled jobs...")
    print("   Lead generation: Mon–Fri at 08:00")
    print("   Weekly report:   Monday at 09:00")
    print("   Press Ctrl+C to stop.\n")

    # Run immediately on start (optional)
    import sys
    if "--now" in sys.argv:
        print("--now flag detected. Running immediately...\n")
        run_daily_lead_generation()
    
    while True:
        schedule.run_pending()
        time.sleep(60)
