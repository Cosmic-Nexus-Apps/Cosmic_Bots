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
            return True

        last_run_ts = row[0]
        elapsed_seconds = now_ts - last_run_ts

        # Fixed Interval Check (e.g. Medium-Frequency: Every 3 to 6 hours)
        if interval_hours is not None:
            return elapsed_seconds >= (interval_hours * 3600)

        # Once-Per-Day Target Hour Check (e.g. Low-Frequency: Daily at 12:00 UTC)
        if target_utc_hour is not None:
            last_run_dt = datetime.fromtimestamp(last_run_ts, tz=timezone.utc)
            # Run if it has not run today yet AND current hour is at or past target_utc_hour
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
    for sub in ['events-bot', 'deep-space-bot', 'space-quiz-bot']:
        p = os.path.join(base_dir, sub)
        if p not in sys.path:
            sys.path.insert(0, p)

    # Lazy-load module dependencies
    try:
        from skyfield.api import load
        try:
            eph = load('events-bot/de440s.bsp')
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

    events_bot = load_module("events_bot", "events-bot/bot.py")
    ds_bot = load_module("deep_space_bot", "deep-space-bot/bot.py")
    quiz_bot = load_module("space_quiz_bot", "space-quiz-bot/bot.py")

    # ==============================================================================
    # 1. HIGH-FREQUENCY MODULES (RUNS ON EVERY 5-MINUTE EXECUTION)
    # ==============================================================================
    print("\n--- [HIGH-FREQUENCY TIER: 5-MINUTE POLLING] ---")
    
    # High-Frequency Task 1: Rocket Launch Tracking (Launch Library 2 T-0 Telemetry)
    if ds_bot and hasattr(ds_bot, 'check_upcoming_launches'):
        run_safe("High_Freq_Launch_Tracking", ds_bot.check_upcoming_launches)

    # High-Frequency Task 2: Live NOAA Space Weather & Geomagnetic Storm (Kp >= 5.0)
    if events_bot and hasattr(events_bot, 'check_noaa_space_weather'):
        run_safe("High_Freq_Geomagnetic_Storm_Check", events_bot.check_noaa_space_weather, eph)

    # High-Frequency Task 3: Emergency Solar Flare Monitoring (X-Class / M-Class)
    if events_bot and hasattr(events_bot, 'check_solar_flares'):
        run_safe("High_Freq_Solar_Flare_Check", events_bot.check_solar_flares, eph)

    # ==============================================================================
    # 2. MEDIUM-FREQUENCY MODULES (RUNS ONCE EVERY 3 TO 6 HOURS)
    # ==============================================================================
    print("\n--- [MEDIUM-FREQUENCY TIER: 3-6 HOUR POLLING] ---")
    
    # Medium-Frequency Task 1: Deep Space Telescope Imagery & Humans in Space Manifest
    if should_run_task("Med_Freq_Deep_Space_Imagery", interval_hours=4) and ds_bot:
        if hasattr(ds_bot, 'check_deep_space_imagery'):
            run_safe("Med_Freq_Deep_Space_Imagery", ds_bot.check_deep_space_imagery)
        if hasattr(ds_bot, 'check_humans_in_space'):
            run_safe("Med_Freq_Humans_In_Space", ds_bot.check_humans_in_space)

    # Medium-Frequency Task 2: Planetary Conjunctions
    if should_run_task("Med_Freq_Conjunctions", interval_hours=3) and events_bot and hasattr(events_bot, 'check_conjunctions'):
        run_safe("Med_Freq_Conjunctions", events_bot.check_conjunctions, eph)

    # Medium-Frequency Task 3: Planetary Alignments & Oppositions
    if should_run_task("Med_Freq_Planetary_Alignments", interval_hours=6) and events_bot:
        if hasattr(events_bot, 'check_planetary_alignments'):
            run_safe("Med_Freq_Planetary_Alignments", events_bot.check_planetary_alignments, eph)
        if hasattr(events_bot, 'check_planetary_oppositions'):
            run_safe("Med_Freq_Planetary_Oppositions", events_bot.check_planetary_oppositions, eph)

    # Medium-Frequency Task 4: Meteor Showers & Comet Streams
    if should_run_task("Med_Freq_Meteor_Showers_Comets", interval_hours=6) and events_bot:
        if hasattr(events_bot, 'check_meteor_showers'):
            run_safe("Med_Freq_Meteor_Showers", events_bot.check_meteor_showers, eph)
        if hasattr(events_bot, 'check_comets_and_interstellar'):
            run_safe("Med_Freq_Comet_Stream", events_bot.check_comets_and_interstellar, eph)

    # ==============================================================================
    # 3. LOW-FREQUENCY MODULES (RUNS ONCE PER DAY AT ~12:00 UTC)
    # ==============================================================================
    print("\n--- [LOW-FREQUENCY TIER: ONCE DAILY AT ~12:00 UTC] ---")
    
    # Low-Frequency Task 1: Daily Space Quiz
    if should_run_task("Low_Freq_Daily_Space_Quiz", target_utc_hour=12) and quiz_bot:
        if hasattr(quiz_bot, 'run_engine'):
            run_safe("Low_Freq_Daily_Space_Quiz", quiz_bot.run_engine)

    # Low-Frequency Task 2: Deep-Sky Seasons Alert
    if should_run_task("Low_Freq_Deep_Sky_Seasons", target_utc_hour=12) and events_bot and hasattr(events_bot, 'check_deep_sky_seasons'):
        run_safe("Low_Freq_Deep_Sky_Seasons", events_bot.check_deep_sky_seasons, eph)

    print("\n==================================================================")
    print(" ORCHESTRATION CYCLE COMPLETED SUCCESSFULLY.")
    print("==================================================================")

if __name__ == "__main__":
    main()
