#!/usr/bin/env python3
"""Tick le scheduler Hermes toutes les 60 secondes."""
import sys, time, os
sys.path.insert(0, "/home/hermeswebui/.hermes/hermes-agent")
os.environ["HERMES_HOME"] = "/home/hermeswebui/.hermes"

from cron.scheduler import tick

print("✅ Scheduler Hermes actif (tick toutes les 60s)")
while True:
    try:
        tick()
    except Exception as e:
        print(f"⚠️ Tick error: {e}")
    time.sleep(60)
