import os
import sys
import io
import time
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

# Shared SQLite scheduler database file
SCHEDULER_DB = "scheduler.db"
SQLITE_LOCK_TIMEOUT = 15.0  # Prevents 'database is locked' errors under high concurrency
HTTP_TIMEOUT = 10.0         # Strict timeout for external API requests

def init_scheduler_db():
    """Initializes SQLite database table for task execution timestamp tracking."""
    with sqlite3.connect(SCHEDULER_DB, timeout=SQLITE_LOCK_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_execution_schedule (
                task_name TEXT PRIMARY KEY,
                last_run_timestamp REAL
            )
        """)
        conn.commit()

def should_run_task(task_name: str, interval_hours: float = None, target_utc_hour: int = None) -> bool:
    """
    Determines whether a time-gated task should run during the current 5-minute cron cycle.
    
    :param task_name: Unique identifier for the module function.
    :param interval_hours: Minimum hours required between execution runs.
    :param target_utc_hour: Target UTC hour (0-23) for daily tasks.
    :return: Boolean indicating whether the task is due for execution.
    """
    init_scheduler_db()
    now_dt = datetime.now(timezone.utc)
    now_ts = now_dt.timestamp()

    with sqlite3.connect(SCHEDULER_DB, timeout=SQLITE_LOCK_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT last_run_timestamp FROM task_execution_schedule WHERE task_name = ?", (task_name,))
        row = cursor.fetchone()

        if not row:
            if target_utc_hour is not None:
                return target_utc_hour <= now_dt.hour < (target_utc_hour + 3)
            return True

        last_run_ts = row[0]
        elapsed_seconds = now_ts - last_run_ts

        # Fixed Interval Check (e.g. Medium-Frequency: Every 3 to 6 hours)
        if interval_hours is not None:
            return elapsed_seconds >= (interval_hours * 3600)

        # Once-Per-Day Target Hour Check
        if target_utc_hour is not None:
            last_run_dt = datetime.fromtimestamp(last_run_ts, tz=timezone.utc)
            if last_run_dt.date() < now_dt.date() and now_dt.hour >= target_utc_hour:
                return True
            return False

        return True

def record_task_execution(task_name: str):
    """Updates the last execution timestamp for a completed task in SQLite."""
    now_ts = datetime.now(timezone.utc).timestamp()
    with sqlite3.connect(SCHEDULER_DB, timeout=SQLITE_LOCK_TIMEOUT) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO task_execution_schedule (task_name, last_run_timestamp)
            VALUES (?, ?)
        """, (task_name, now_ts))
        conn.commit()

def run_safe(task_name: str, task_func, *args, **kwargs):
    """Wraps task execution in robust error handling to prevent script failures from halting the pipeline."""
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}] Executing Module: '{task_name}'...")
    start_time = time.time()
    try:
        task_func(*args, **kwargs)
        record_task_execution(task_name)
        duration = time.time() - start_time
        print(f"[SUCCESS] Module '{task_name}' completed in {duration:.2f}s.")
    except requests.exceptions.Timeout:
        print(f"[API TIMEOUT] Module '{task_name}' timed out after {HTTP_TIMEOUT}s. Continuing pipeline.")
    except Exception as e:
        print(f"[MODULE ERROR] Module '{task_name}' failed with error: {e}. Continuing pipeline.")

def main():
    print("==================================================================")
    print(" COSMIC NEXUS HIGH-FREQUENCY (5-MIN) CRON ORCHESTRATOR")
    print(f" Timestamp: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("==================================================================")

    # Add subdirectories to Python Path to dynamically import bot modules
    base_dir = os.path.dirname(os.path.abspath(__file__))
    for sub in ['astro-events-bot', 'deep-space-bot', 'space-quiz-bot', 'space-history-bot']:
        p = os.path.join(base_dir, sub)
        if p not in sys.path:
            sys.path.insert(0, p)

    # Lazy-load module dependencies
    try:
        from skyfield.api import load
        try:
            eph = load('astro-events-bot/de440s.bsp')
        except Exception:
            try:
                eph = load('de440s.bsp')
            except Exception:
                eph = load('de421.bsp')
    except Exception as e:
        print(f"[WARN] Skyfield ephemeris loading notice: {e}")
        eph = None

    # Helper function to dynamically import bot modules from file paths
    import importlib.util
    def load_module(mod_name, rel_path):
        file_path = os.path.join(base_dir, rel_path)
        if not os.path.exists(file_path):
            return None
        try:
            spec = importlib.util.spec_from_file_location(mod_name, file_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception as e:
            print(f"[WARN] Could not load module '{mod_name}' from {rel_path}: {e}")
            return None

    events_bot = load_module("astro_events_bot", "astro-events-bot/bot.py")
    ds_bot = load_module("deep_space_bot", "deep-space-bot/bot.py")
    quiz_bot = load_module("space_quiz_bot", "space-quiz-bot/bot.py")
    history_bot = load_module("space_history_bot", "space-history-bot/bot.py")

    # ==============================================================================
    # 1. REAL-TIME EMERGENCY MODULES (5-MINUTE POLLING)
    # ==============================================================================
    print("\n--- [REAL-TIME TELEMETRY & EMERGENCY ALERTS] ---")
    
    # Real-Time Task 1: Rocket Launch Tracking (Launch Library 2 T-0 Countdowns)
    if ds_bot and hasattr(ds_bot, 'check_upcoming_launches'):
        run_safe("Realtime_Launch_Tracking", ds_bot.check_upcoming_launches)

    # Real-Time Task 2: Live NOAA Space Weather & Geomagnetic Storm (Kp >= 5.0)
    if events_bot and hasattr(events_bot, 'check_noaa_space_weather'):
        run_safe("Realtime_Geomagnetic_Storm_Check", events_bot.check_noaa_space_weather, eph)

    # Real-Time Task 3: Emergency Solar Flare Monitoring (X-Class / M-Class)
    if events_bot and hasattr(events_bot, 'check_solar_flares'):
        run_safe("Realtime_Solar_Flare_Check", events_bot.check_solar_flares, eph)

    # ==============================================================================
    # 2. MASTER 24-HOUR SPACED SCHEDULED TASKS
    # ==============================================================================
    print("\n--- [MASTER 24-HOUR SCHEDULED BROADCAST TIMETABLE] ---")
    
    # Slot 1 (07:00 UTC / 10:00 EEST): Morning Space News (Gemini Top Story < 24h)
    if should_run_task("Slot_07UTC_Morning_News", target_utc_hour=7) and events_bot:
        if hasattr(events_bot, 'check_rss_breaking_news'):
            run_safe("Slot_07UTC_Morning_News", events_bot.check_rss_breaking_news)

    # Slot 2 (09:00 UTC / 12:00 EEST): Astronomy Events, Comets & Interstellar Objects
    if should_run_task("Slot_09UTC_Astronomy_Events", target_utc_hour=9) and events_bot:
        if hasattr(events_bot, 'check_conjunctions'):
            run_safe("Slot_09UTC_Conjunctions", events_bot.check_conjunctions, eph)
        if hasattr(events_bot, 'check_planetary_alignments'):
            run_safe("Slot_09UTC_Planetary_Alignments", events_bot.check_planetary_alignments, eph)
        if hasattr(events_bot, 'check_comets_and_interstellar'):
            run_safe("Slot_09UTC_Comets_Interstellar", events_bot.check_comets_and_interstellar, eph)
        if hasattr(events_bot, 'check_meteor_showers'):
            run_safe("Slot_09UTC_Meteor_Showers", events_bot.check_meteor_showers, eph)
        if hasattr(events_bot, 'check_supernovae_transients'):
            run_safe("Slot_09UTC_Supernovae_Transients", events_bot.check_supernovae_transients, eph)

    # Slot 3 (12:00 UTC / 15:00 EEST): Daily Space Quiz (Strictly 1/day)
    if should_run_task("Slot_12UTC_Daily_Space_Quiz", target_utc_hour=12) and quiz_bot:
        if hasattr(quiz_bot, 'run_engine'):
            run_safe("Slot_12UTC_Daily_Space_Quiz", quiz_bot.run_engine)

    # Slot 4 (14:00 UTC / 17:00 EEST): Afternoon Space News (Gemini Top Story — Excludes 07:00 Story)
    if should_run_task("Slot_14UTC_Afternoon_News", target_utc_hour=14) and events_bot:
        if hasattr(events_bot, 'check_rss_breaking_news'):
            run_safe("Slot_14UTC_Afternoon_News", events_bot.check_rss_breaking_news)

    # Slot 5 (16:00 UTC / 19:00 EEST): Today in Space History (Strictly 1/day with Era Rotation)
    if should_run_task("Slot_16UTC_Space_History", target_utc_hour=16) and history_bot:
        if hasattr(history_bot, 'run_engine'):
            run_safe("Slot_16UTC_Space_History", history_bot.run_engine)

    # Slot 6 (18:00 UTC / 21:00 EEST): Deep Space Imagery & ISS Humans in Space Manifest
    if should_run_task("Slot_18UTC_Deep_Space_Imagery", target_utc_hour=18) and ds_bot:
        if hasattr(ds_bot, 'check_deep_space_imagery'):
            run_safe("Slot_18UTC_Deep_Space_Imagery", ds_bot.check_deep_space_imagery)
        if hasattr(ds_bot, 'check_humans_in_space'):
            run_safe("Slot_18UTC_Humans_In_Space", ds_bot.check_humans_in_space)
        if hasattr(ds_bot, 'check_exoplanet_discoveries'):
            run_safe("Slot_18UTC_Exoplanets", ds_bot.check_exoplanet_discoveries)

    # Slot 7 (20:00 UTC / 23:00 EEST): Evening Space News (Gemini Top Story — Excludes Earlier Stories)
    if should_run_task("Slot_20UTC_Evening_News", target_utc_hour=20) and events_bot:
        if hasattr(events_bot, 'check_rss_breaking_news'):
            run_safe("Slot_20UTC_Evening_News", events_bot.check_rss_breaking_news)

    print("\n==================================================================")
    print(" ORCHESTRATION CYCLE COMPLETED SUCCESSFULLY.")
    print("==================================================================")

if __name__ == "__main__":
    main()
