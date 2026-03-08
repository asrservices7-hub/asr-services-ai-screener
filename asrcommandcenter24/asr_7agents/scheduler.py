"""
ASR Daily Scheduler
Runs all 7 agents on a daily schedule.

Start: python3 scheduler.py
Or cron: 0 8 * * 1-5 cd /path/to/asr_7agents && python3 scheduler.py --now
"""

import schedule, time, sys, subprocess
from datetime import datetime

def run_system(mode="full"):
    print(f"\n🚀 ASR System starting — {datetime.now().strftime('%d %b %Y %H:%M')}")
    subprocess.run([sys.executable, "asr_system.py", "--run-all"])

def run_reminders():
    print(f"\n⏰ Interview reminders — {datetime.now().strftime('%d %b %Y %H:%M')}")
    subprocess.run([sys.executable, "asr_system.py", "--schedule"])

# ── Daily schedules ──────────────────────────────────────────
for day in ["monday","tuesday","wednesday","thursday","friday"]:
    getattr(schedule.every(), day).at("08:00").do(run_system)   # morning: full run
    getattr(schedule.every(), day).at("18:00").do(run_reminders) # evening: interview reminders

if __name__ == "__main__":
    if "--now" in sys.argv:
        run_system()
    else:
        print("📅 ASR Scheduler running. Mon–Fri 8AM full run, 6PM reminders.")
        print("   Press Ctrl+C to stop.\n")
        while True:
            schedule.run_pending()
            time.sleep(60)
