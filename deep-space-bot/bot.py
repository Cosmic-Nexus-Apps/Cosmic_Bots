import os
import sys
import io
import sqlite3
import requests
import random
import time
import hashlib
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

WEBHOOK_URL = os.getenv("DEEP_SPACE_BOT_DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
ROLE_ID = os.getenv("DEEP_SPACE_BOT_DISCORD_ROLE_ID") or os.getenv("DISCORD_ROLE_ID")
NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")
DB_FILE = "deep_space.db"

# Operational flag: TEST_MODE = True generates sample launch & telescope embeds.
TEST_MODE = os.getenv("TEST_MODE", "FALSE").upper() == "TRUE"

def init_db():
    """Initializes SQLite database for deep space tracking and crew state storage."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS launch_cache (
            item_id TEXT PRIMARY KEY,
            expire_timestamp REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS crew_state (
            key_name TEXT PRIMARY KEY,
            manifest_text TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS module_hydration (
            module_name TEXT PRIMARY KEY,
            hydrated_at REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS exoplanet_cache (
            planet_name TEXT PRIMARY KEY,
            expire_timestamp REAL
        )
    """)
    conn.commit()
    conn.close()

def is_module_hydrated(module_name):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT hydrated_at FROM module_hydration WHERE module_name = ?", (module_name,))
    row = cursor.fetchone()
    conn.close()
    return row is not None

def set_module_hydrated(module_name):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()
    cursor.execute("INSERT OR REPLACE INTO module_hydration (module_name, hydrated_at) VALUES (?, ?)", (module_name, now_ts))
    conn.commit()
    conn.close()

def get_stored_crew_manifest():
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT manifest_text FROM crew_state WHERE key_name = 'astros_manifest'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else None

def save_stored_crew_manifest(manifest_str):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO crew_state (key_name, manifest_text) VALUES ('astros_manifest', ?)", (manifest_str,))
    conn.commit()
    conn.close()

try:
    import persistent_history
except Exception:
    persistent_history = None

def is_already_notified(item_id, ttl_hours=None):
    if persistent_history and persistent_history.is_published(item_id):
        return True

    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()

    cursor.execute("SELECT expire_timestamp FROM launch_cache WHERE item_id = ?", (item_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row[0] > now_ts:
        return True
    return False

def mark_notified(item_id, ttl_hours=168):
    if persistent_history:
        persistent_history.record_published(item_id, ttl_hours=ttl_hours)

    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()
    expire_ts = now_ts + (ttl_hours * 3600)

    cursor.execute("""
        INSERT OR REPLACE INTO launch_cache (item_id, expire_timestamp)
        VALUES (?, ?)
    """, (item_id, expire_ts))

    cursor.execute("DELETE FROM launch_cache WHERE expire_timestamp <= ?", (now_ts,))
    conn.commit()
    conn.close()

def is_item_or_title_notified(item_id, title_str="", ttl_hours=720):
    """Checks both raw item_id AND normalized title hash to prevent duplicate news posts."""
    if persistent_history and persistent_history.is_published(item_id, title_str=title_str):
        return True
    if is_already_notified(item_id):
        return True
    if title_str:
        import re
        clean_t = re.sub(r'\W+', '', title_str.lower())
        if clean_t:
            t_hash = hashlib.md5(clean_t.encode('utf-8')).hexdigest()
            if is_already_notified(f"title_{t_hash}"):
                return True
    return False

def mark_item_and_title_notified(item_id, title_str="", ttl_hours=720):
    """Saves both raw item_id AND normalized title hash into persistent SQLite & JSON cache."""
    if persistent_history:
        persistent_history.record_published(item_id, title_str=title_str, ttl_hours=ttl_hours)
    mark_notified(item_id, ttl_hours=ttl_hours)
    if title_str:
        import re
        clean_t = re.sub(r'\W+', '', title_str.lower())
        if clean_t:
            t_hash = hashlib.md5(clean_t.encode('utf-8')).hexdigest()
            mark_notified(f"title_{t_hash}", ttl_hours=ttl_hours)

def send_discord_embed(title, description, color=0x1F618D, role_id=ROLE_ID, image_url=None, fields=None, author=None, thumbnail_url=None):
    if not WEBHOOK_URL:
        print(f"[DISCORD EMBED - NO WEBHOOK CONFIGURED]\nTitle: {title}\n{description}\n")
        return

    embed_obj = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": "Cosmic Nexus | Deep Space & Rocket Launch Telemetry Core"
        }
    }

    if author:
        embed_obj["author"] = author

    if thumbnail_url:
        embed_obj["thumbnail"] = {"url": thumbnail_url}

    if fields:
        embed_obj["fields"] = fields

    if image_url:
        embed_obj["image"] = {"url": image_url}

    payload = {
        "embeds": [embed_obj]
    }

    if role_id:
        payload["content"] = f"<@&{role_id}>"

    try:
        res = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        print(f"[DISCORD POST] Status: {res.status_code} for '{title}'")
        time.sleep(1)
    except Exception as e:
        print(f"[DISCORD ERROR] Failed to send webhook: {e}")

def get_regional_3utc_windows(peak_dt, window_minutes=60):
    """
    Calculates exact minute-precise local launch times across 3 UTC offsets per continent region:
    - EUROPE / EMEA: UTC+1, UTC+3, UTC+4
    - AMERICAS: UTC-8, UTC-5, UTC-3
    - ASIA / PACIFIC: UTC+5.5, UTC+8, UTC+10
    """
    groups = [
        ("🇪🇺 **EUROPE / EMEA (CANARIES, EAST EU & GULF HUBS):**", [
            ("[UTC+1]", ZoneInfo("Europe/Paris")),
            ("[UTC+3]", ZoneInfo("Europe/Bucharest")),
            ("[UTC+4]", ZoneInfo("Asia/Dubai"))
        ]),
        ("🇺🇸 **AMERICAS (PACIFIC, EASTERN & CHILE HUBS):**", [
            ("[UTC-8]", ZoneInfo("America/Los_Angeles")),
            ("[UTC-5]", ZoneInfo("America/New_York")),
            ("[UTC-3]", ZoneInfo("America/Argentina/Buenos_Aires"))
        ]),
        ("🇯🇵 **ASIA / PACIFIC (INDIA, CHINA & AUSTRALIA HUBS):**", [
            ("[UTC+5.5]", ZoneInfo("Asia/Kolkata")),
            ("[UTC+8]", ZoneInfo("Asia/Shanghai")),
            ("[UTC+10]", ZoneInfo("Australia/Sydney"))
        ])
    ]

    epoch_ts = int(peak_dt.timestamp())
    output_lines = [f"⏳ **LIVE COUNTDOWN:** <t:{epoch_ts}:R> *(T-0: <t:{epoch_ts}:F>)*"]

    for header, tz_list in groups:
        output_lines.append(header)
        for label, tz_obj in tz_list:
            loc_p = peak_dt.astimezone(tz_obj)
            output_lines.append(
                f"└ **{label}:** Launch Time: **{loc_p.strftime('%H:%M')}** *({loc_p.strftime('%d %B')})*"
            )

    return "\n".join(output_lines)

# ==============================================================================
# MODULE 1: MAJOR ROCKET LAUNCHES & MISSION OUTCOME TELEMETRY CORE
# ==============================================================================
PRIORITY_LAUNCH_KEYWORDS = [
    "starship", "artemis", "falcon heavy", "jwst", "james webb",
    "euclid", "europa clipper", "roman", "crew", "moon", "lunar", "mars",
    "sls", "ariane 6", "curiosity", "perseverance", "chandrayaan", "gaganyaan", "kinetica"
]

def is_priority_launch(name, provider_name=""):
    """Returns True if this is a high-profile mission deserving full cascade alerts (T-24h, T-6h, T-2h, T-0)."""
    combined = (name + " " + provider_name).lower()
    return any(kw in combined for kw in PRIORITY_LAUNCH_KEYWORDS)

def get_provider_color(name, provider_name=""):
    combined = (name + " " + provider_name).lower()
    if "spacex" in combined or "starship" in combined:
        return 0x000000
    elif "nasa" in combined or "sls" in combined or "artemis" in combined:
        return 0x003366
    elif "esa" in combined or "ariane" in combined or "euclid" in combined:
        return 0x0099CC
    elif "isro" in combined or "gaganyaan" in combined:
        return 0xFF9900
    elif "cas" in combined or "china" in combined or "kinetica" in combined or "casc" in combined:
        return 0xDE2910
    return 0x2980B9

def get_webcast_url(launch_data, mission_name, provider_name=""):
    vid_urls = launch_data.get("vidURLs", []) if isinstance(launch_data, dict) else []
    if vid_urls and isinstance(vid_urls, list) and len(vid_urls) > 0:
        first_vid = vid_urls[0].get("url")
        if first_vid and len(first_vid) > 5:
            return first_vid

    combined = (mission_name + " " + provider_name).lower()
    if "spacex" in combined:
        return "https://www.youtube.com/@SpaceX"
    elif "nasa" in combined:
        return "https://www.youtube.com/@NASAGovVideo"
    elif "esa" in combined:
        return "https://www.youtube.com/@EuropeanSpaceAgency"
    elif "isro" in combined:
        return "https://www.youtube.com/@isroofficial"

    search_query = requests.utils.quote(f"{mission_name} {provider_name} Launch Stream")
    return f"https://www.youtube.com/results?search_query={search_query}"

def format_clean_mission_brief(launch_obj, max_len=400):
    """Extracts authentic mission description from Launch Library 2 API without inventing text."""
    mission_dict = launch_obj.get("mission", {}) if isinstance(launch_obj, dict) else {}
    desc = ""
    if isinstance(mission_dict, dict):
        desc = mission_dict.get("description", "").strip()
    if not desc:
        status_dict = launch_obj.get("status", {}) if isinstance(launch_obj, dict) else {}
        desc = status_dict.get("description", "").strip() if isinstance(status_dict, dict) else ""
    if not desc:
        desc = "Spacecraft orbital insertion and payload deployment mission."
    
    if len(desc) > max_len:
        last_space = desc[:max_len].rfind(' ')
        desc = desc[:last_space] + "..." if last_space > 100 else desc[:max_len] + "..."
    return desc

def check_upcoming_launches():
    print("Checking Module 1: High-Impact Rocket Launches & Telemetry Core...")
    now_dt = datetime.now(timezone.utc)

    # 1. Fetch upcoming launches from Launch Library 2 API
    url = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=10"
    launches = []
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            launches = data.get("results", [])
    except Exception as e:
        print(f"[LAUNCH API NOTE] Could not fetch live launch API: {e}")

    # 2. Process Upcoming & Live Launches (Strict T-2 Hours Pre-Launch & T-0 Liftoff Alerts)
    for launch in launches:
        launch_id = launch.get("id", "sample_launch")
        name = launch.get("name", "SpaceX Rocket Launch")
        net_raw = launch.get("net", "")
        
        launch_dt = now_dt
        if net_raw:
            try:
                launch_dt = datetime.fromisoformat(net_raw.replace('Z', '+00:00'))
            except Exception:
                launch_dt = now_dt

        time_until_launch_sec = (launch_dt - now_dt).total_seconds()
        rocket_img = launch.get("image", "https://images-assets.nasa.gov/image/KSC-20200530-PH-KSC01_0001/KSC-20200530-PH-KSC01_0001~medium.jpg")
        provider_name = launch.get("launch_service_provider", {}).get("name", "SpaceX")
        pad_name = launch.get("pad", {}).get("name", "Space Launch Complex")
        location = launch.get("pad", {}).get("location", {}).get("name", "USA")
        raw_status = launch.get("status", {}).get("name", "Go for Launch")
        orbit_type = launch.get("orbit", {}).get("name", "Low Earth Orbit") if launch.get("orbit") else "Low Earth Orbit"

        webcast_url = get_webcast_url(launch, name, provider_name)
        embed_color = get_provider_color(name, provider_name)
        short_mission = name.split("|")[0].strip() if "|" in name else name
        mission_brief = format_clean_mission_brief(launch)
        utc_date_str = launch_dt.strftime("%d %B %Y at %H:%M UTC").upper()
        priority = is_priority_launch(name, provider_name)

        # ==== PRIORITY LAUNCHES: Full cascade T-24h → T-6h → T-2h → T-0 ====
        # ==== NON-PRIORITY: Only T-2h (or T-0 if missed) + landing report ====

        # Alert: T-24h Pre-Launch (Priority only, window: 22h–26h before launch)
        if priority and (22 * 3600) <= time_until_launch_sec <= (26 * 3600):
            item_key = f"launch_t24h_{launch_id}"
            if TEST_MODE or not is_already_notified(item_key, ttl_hours=72):
                title = f"📅 LAUNCH IN 24 HOURS | {short_mission.upper()}"
                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🚨 **PRIORITY MISSION ALERT:** Launch is exactly **24 hours away!**\n\n"
                    f"🎯 **MISSION:** `{name}`\n"
                    f"🏢 **LAUNCH PROVIDER:** `{provider_name}`\n"
                    f"🛰️ **TARGET ORBIT / DESTINATION:** `{orbit_type}`\n"
                    f"📍 **LAUNCH PAD:** `{pad_name} ({location})`\n"
                    f"⚡ **LAUNCH STATUS:** `🟢 {raw_status}`\n"
                    f"📅 **EXACT T-0 DATE & TIME:** `{utc_date_str}`\n\n"
                    f"📖 **MISSION DETAILS:**\n{mission_brief}\n\n"
                    f"⏱️ **GLOBAL LAUNCH TIMES:**\n"
                    f"{get_regional_3utc_windows(launch_dt)}\n\n"
                    f"📺 **LIVE STREAM:** [Watch Official Broadcast]({webcast_url})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                send_discord_embed(title, description, color=embed_color, image_url=rocket_img)
                mark_notified(item_key, ttl_hours=72)

        # Alert: T-6h Pre-Launch (Priority only, window: 5h–8h before launch)
        elif priority and (5 * 3600) <= time_until_launch_sec <= (8 * 3600):
            item_key = f"launch_t6h_{launch_id}"
            if TEST_MODE or not is_already_notified(item_key, ttl_hours=24):
                title = f"⏳ LAUNCH IN 6 HOURS | {short_mission.upper()}"
                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔥 **T-MINUS 6 HOURS:** `{name}` launches in **6 hours!**\n\n"
                    f"🎯 **MISSION:** `{name}`\n"
                    f"🏢 **LAUNCH PROVIDER:** `{provider_name}`\n"
                    f"📍 **LAUNCH PAD:** `{pad_name} ({location})`\n"
                    f"⚡ **STATUS:** `🟢 {raw_status}`\n"
                    f"📅 **T-0:** `{utc_date_str}`\n\n"
                    f"⏱️ **COUNTDOWN PER REGION:**\n"
                    f"{get_regional_3utc_windows(launch_dt)}\n\n"
                    f"📺 **LIVE STREAM:** [Watch Official Broadcast]({webcast_url})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                send_discord_embed(title, description, color=embed_color, image_url=rocket_img)
                mark_notified(item_key, ttl_hours=24)

        # Alert: T-2h Pre-Launch Reminder (ALL launches, window: 0–2.5h before launch)
        elif 0 <= time_until_launch_sec <= (2.5 * 3600):
            item_key = f"launch_t2h_{launch_id}"
            if TEST_MODE or not is_already_notified(item_key, ttl_hours=72):
                title = f"🚀 ROCKET LAUNCH REMINDER (T-MINUS 2 HOURS) | {short_mission.upper()}"
                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"⏰ **T-MINUS 2 HOURS LAUNCH ALERT:** Launch is scheduled in **2 hours**!\n\n"
                    f"🎯 **MISSION:** `{name}`\n"
                    f"🏢 **LAUNCH PROVIDER:** `{provider_name}`\n"
                    f"🛰️ **TARGET ORBIT / DESTINATION:** `{orbit_type}`\n"
                    f"📍 **LAUNCH PAD:** `{pad_name} ({location})`\n"
                    f"⚡ **LAUNCH STATUS:** `🟢 {raw_status}`\n"
                    f"📅 **EXACT T-0 LAUNCH DATE & TIME:** `{utc_date_str}`\n\n"
                    f"📖 **AUTHENTIC MISSION DETAILS (API):**\n{mission_brief}\n\n"
                    f"⏱️ **TARGET LAUNCH TIME PER REGION (MINUTE-PRECISE):**\n"
                    f"{get_regional_3utc_windows(launch_dt)}\n\n"
                    f"📺 **LIVE STREAM:** [Watch Official Broadcast]({webcast_url})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                send_discord_embed(title, description, color=embed_color, image_url=rocket_img)
                mark_notified(item_key, ttl_hours=72)

        # Alert 2: T-0 Liftoff Alert (Sent right at launch time)
        elif -900 <= time_until_launch_sec <= 1800:
            item_key = f"launch_t0_{launch_id}"
            if TEST_MODE or not is_already_notified(item_key, ttl_hours=72):
                title = f"🚀 ROCKET LIFTOFF (T-0 LAUNCH) | {short_mission.upper()}"
                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔥 **LIFTOFF!** `{name}` has launched from `{pad_name}`!\n\n"
                    f"🎯 **MISSION:** `{name}`\n"
                    f"🏢 **LAUNCH PROVIDER:** `{provider_name}`\n"
                    f"📅 **LAUNCH DATE & TIME:** `{utc_date_str}`\n"
                    f"🛰️ **TARGET ORBIT:** `{orbit_type}`\n\n"
                    f"📖 **MISSION DETAILS:**\n{mission_brief}\n\n"
                    f"📺 **LIVE STREAM:** [Watch Official Broadcast]({webcast_url})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                send_discord_embed(title, description, color=0xE74C3C, image_url=rocket_img)
                mark_notified(item_key, ttl_hours=72)

    # 3. Process Completed & Past Launches (for Landing Reports & Final Outcome)
    check_completed_launches()

def check_completed_launches():
    """Queries recent completed launches to send authentic Mission Landing & Final Outcome reports.
    Filters out launches that completed > 24 hours ago to prevent old notification spam.
    Shows both Launch Date & Time (Decolare) and Completion Date & Time (Finalizare)."""
    now_dt = datetime.now(timezone.utc)
    url = "https://ll.thespacedevs.com/2.2.0/launch/previous/?limit=10"
    launches = []
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            launches = data.get("results", [])
    except Exception as e:
        print(f"[PREVIOUS LAUNCH API NOTE] {e}")

    for launch in launches:
        launch_id = launch.get("id", "past_launch")
        name = launch.get("name", "SpaceX Launch")
        raw_status = launch.get("status", {}).get("name", "Success")
        status_desc = launch.get("status", {}).get("description", "")
        provider_name = launch.get("launch_service_provider", {}).get("name", "SpaceX")
        rocket_img = launch.get("image", "https://images-assets.nasa.gov/image/KSC-20200530-PH-KSC01_0001/KSC-20200530-PH-KSC01_0001~medium.jpg")
        orbit_type = launch.get("orbit", {}).get("name", "Low Earth Orbit") if launch.get("orbit") else "Low Earth Orbit"
        short_mission = name.split("|")[0].strip() if "|" in name else name

        net_raw = launch.get("net", "")
        window_end_raw = launch.get("window_end", "")
        last_updated_raw = launch.get("last_updated", "")

        l_dt = None
        launch_date_str = "UNKNOWN DATE"
        if net_raw:
            try:
                l_dt = datetime.fromisoformat(net_raw.replace('Z', '+00:00'))
                launch_date_str = l_dt.strftime("%d %B %Y at %H:%M UTC").upper()
            except Exception:
                launch_date_str = net_raw

        comp_dt = None
        completion_date_str = launch_date_str
        if window_end_raw:
            try:
                comp_dt = datetime.fromisoformat(window_end_raw.replace('Z', '+00:00'))
                completion_date_str = comp_dt.strftime("%d %B %Y at %H:%M UTC").upper()
            except Exception:
                pass

        if not comp_dt and last_updated_raw:
            try:
                comp_dt = datetime.fromisoformat(last_updated_raw.replace('Z', '+00:00'))
                completion_date_str = comp_dt.strftime("%d %B %Y at %H:%M UTC").upper()
            except Exception:
                pass

        # Strict cutoff: If launch/completion was > 24 hours ago, skip sending Discord notification
        ref_dt = comp_dt or l_dt
        item_key = f"launch_landing_{launch_id}"
        if ref_dt:
            age_hours = (now_dt - ref_dt).total_seconds() / 3600.0
            if age_hours > 24.0:
                mark_notified(item_key, ttl_hours=168)
                continue

        mission_brief = format_clean_mission_brief(launch)

        if TEST_MODE or not is_already_notified(item_key, ttl_hours=168):
            status_lower = raw_status.lower()
            status_badge = "✅ Mission Successful (Orbit Achieved)" if "success" in status_lower else f"⚠️ {raw_status}"

            title = f"🛬 MISSION COMPLETED & OUTCOME REPORT | {short_mission.upper()}"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **MISSION:** `{name}`\n"
                f"🏢 **LAUNCH PROVIDER:** `{provider_name}`\n"
                f"🛰️ **ORBIT / DESTINATION:** `{orbit_type}`\n"
                f"📅 **LAUNCH DATE & TIME (DECOLARE):** `{launch_date_str}`\n"
                f"🏁 **COMPLETION DATE & TIME (FINALIZARE):** `{completion_date_str}`\n"
                f"📊 **FINAL MISSION STATUS:** `{status_badge}`\n\n"
                f"📖 **MISSION SUMMARY & OUTCOME (AUTHENTIC API DATA):**\n"
                f"{mission_brief}\n"
                f"{f'*Note: {status_desc}*' if status_desc else ''}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            send_discord_embed(title, description, color=0x27AE60 if "success" in status_lower else 0xE74C3C, image_url=rocket_img)
            mark_notified(item_key, ttl_hours=168)


# ==============================================================================
# MODULE 2: LIVE MULTI-TELESCOPE STREAM (NASA APOD + NASA IMAGE API FOR JWST, HST, EUCLID, CHANDRA)
# ==============================================================================
TELESCOPE_SEARCH_QUERIES = [
    {"query": "James Webb Space Telescope discovery", "name": "JAMES WEBB SPACE TELESCOPE (JWST)", "color": 0x8E44AD},
    {"query": "Hubble Space Telescope discovery", "name": "HUBBLE SPACE TELESCOPE (HST)", "color": 0x16A085},
    {"query": "Euclid Space Telescope discovery", "name": "EUCLID SPACE TELESCOPE (ESA)", "color": 0x2980B9},
    {"query": "Chandra X-Ray Observatory discovery", "name": "CHANDRA X-RAY OBSERVATORY", "color": 0xE74C3C},
    {"query": "Vera C. Rubin Observatory", "name": "VERA C. RUBIN OBSERVATORY (LSST)", "color": 0x9B59B6},
    {"query": "Exoplanet discovery", "name": "EXOPLANET & ALIEN WORLD DISCOVERY", "color": 0xF39C12},
    {"query": "Very Large Telescope discovery", "name": "VERY LARGE TELESCOPE (ESO VLT)", "color": 0x1ABC9C}
]

def format_clean_summary(text, max_len=3000):
    if not text:
        return ""
    text = text.strip()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    last_period = truncated.rfind('.')
    if last_period > int(max_len * 0.4):
        return truncated[:last_period + 1]
    last_space = truncated.rfind(' ')
    if last_space > int(max_len * 0.4):
        return truncated[:last_space] + "."
    return truncated

def detect_actual_observatory(title_str, raw_desc, default_scope_name):
    """
    Dynamically identifies the true observatory from title & description text
    to prevent cross-query misattribution (e.g. Roman Space Telescope photos matching Hubble search queries).
    """
    combined = (title_str + " " + raw_desc).lower()
    
    # Title-level explicit checks take top priority
    t_lower = title_str.lower()
    if "roman" in t_lower:
        return "NANCY GRACE ROMAN SPACE TELESCOPE (NGRST)"
    elif "james webb" in t_lower or "jwst" in t_lower:
        return "JAMES WEBB SPACE TELESCOPE (JWST)"
    elif "hubble" in t_lower or "hst" in t_lower:
        return "HUBBLE SPACE TELESCOPE (HST)"
    elif "euclid" in t_lower:
        return "EUCLID SPACE TELESCOPE (ESA)"
    elif "chandra" in t_lower:
        return "CHANDRA X-RAY OBSERVATORY"
    elif "rubin" in t_lower or "lsst" in t_lower:
        return "VERA C. RUBIN OBSERVATORY (LSST)"
    elif "very large telescope" in t_lower or "vlt" in t_lower:
        return "VERY LARGE TELESCOPE (ESO VLT)"
    elif "spitzer" in t_lower:
        return "SPITZER SPACE TELESCOPE"

    # Description checks if title is ambiguous
    if "roman space telescope" in combined:
        return "NANCY GRACE ROMAN SPACE TELESCOPE (NGRST)"
    elif "james webb space telescope" in combined:
        return "JAMES WEBB SPACE TELESCOPE (JWST)"
    elif "hubble space telescope" in combined and default_scope_name == "HUBBLE SPACE TELESCOPE (HST)":
        return "HUBBLE SPACE TELESCOPE (HST)"
        
    return default_scope_name

def check_deep_space_imagery():
    print("Checking Module 2: Live Multi-Telescope Telemetry Stream (NASA APOD & NASA Image Library)...")
    now_dt = datetime.now(timezone.utc)
    current_year = now_dt.year
    hydrated = is_module_hydrated("deep_space_imagery")

    # 1. Query Live NASA APOD (Astronomy Picture of the Day) API for TODAY'S picture
    try:
        apod_url = f"https://api.nasa.gov/planetary/apod?api_key={NASA_API_KEY}"
        res = requests.get(apod_url, timeout=6)
        if res.status_code == 200:
            apod_data = res.json()
            apod_date = apod_data.get("date", now_dt.strftime("%Y-%m-%d"))
            item_key = f"apod_{apod_date}"

            if TEST_MODE or not is_item_or_title_notified(item_key, apod_data.get("title", ""), ttl_hours=24):
                title_str = apod_data.get("title", "Astronomy Picture of the Day")
                media_type = apod_data.get("media_type", "image")
                img_url = apod_data.get("url") if media_type == "image" else apod_data.get("thumbnail_url")
                hd_url = apod_data.get("hdurl", img_url)
                copyright_credit = apod_data.get("copyright", "NASA / APOD Science Core").replace('\n', ' ')
                explanation = format_clean_summary(apod_data.get("explanation", "Daily astronomical observation release."), max_len=3000)

                embed_title = f"🔭 NASA APOD | {title_str.upper()}"

                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🌌 **PHOTOGRAPHED TARGET:** `{title_str}`\n"
                    f"🎯 **OBSERVATORY / SOURCE:** `NASA Astronomy Picture of the Day`\n"
                    f"📷 **IMAGE CREDIT:** `{copyright_credit}`\n"
                    f"📅 **RELEASE DATE:** `{apod_date.upper()}`\n\n"
                    f"📖 **SCIENTIFIC SUMMARY:**\n{explanation}\n\n"
                    f"💾 **FULL-RESOLUTION IMAGE:** [Open High-Res Image File]({hd_url})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )

                if img_url:
                    if not TEST_MODE and not hydrated:
                        mark_item_and_title_notified(item_key, title_str, ttl_hours=24)
                        print(f"[HYDRATION] Initialized APOD {item_key} silently.")
                    else:
                        send_discord_embed(embed_title, description, color=0x8E44AD, image_url=img_url)
                        mark_item_and_title_notified(item_key, title_str, ttl_hours=24)
                        set_module_hydrated("deep_space_imagery")
                        return
    except Exception as e:
        print(f"[APOD API NOTE] Query active stream fallback: {e}")

    # 2. Query Live NASA Image Search API for JWST, Hubble, Euclid, Chandra, Rubin, VLT, Exoplanets
    ignored_keywords = ["cinema", "screening", "auditorium", "cleanroom", "mirror", "installation", "building", "facility", "speech"]

    for scope in TELESCOPE_SEARCH_QUERIES:
        try:
            search_url = f"https://images-api.nasa.gov/search?q={requests.utils.quote(scope['query'])}&media_type=image&year_start={current_year}"
            res = requests.get(search_url, timeout=6)
            items = []
            if res.status_code == 200:
                items = res.json().get("collection", {}).get("items", [])
            
            if not items:
                search_url = f"https://images-api.nasa.gov/search?q={requests.utils.quote(scope['query'])}&media_type=image&year_start={current_year - 1}"
                res = requests.get(search_url, timeout=6)
                if res.status_code == 200:
                    items = res.json().get("collection", {}).get("items", [])

            def get_item_date(it):
                d_list = it.get("data", [])
                return d_list[0].get("date_created", "1970-01-01") if d_list else "1970-01-01"

            items.sort(key=get_item_date, reverse=True)

            for item in items[:10]:
                data_list = item.get("data", [])
                links_list = item.get("links", [])
                if not data_list or not links_list:
                    continue

                item_data = data_list[0]
                nasa_id = item_data.get("nasa_id", "")
                title_str = item_data.get("title", scope["query"])
                raw_desc = item_data.get("description", "Scientific space telescope discovery.")
                description_str = format_clean_summary(raw_desc, max_len=3000)
                date_created = item_data.get("date_created", "")[:10]

                if any(kw in title_str.lower() for kw in ignored_keywords):
                    continue

                actual_observatory = detect_actual_observatory(title_str, raw_desc, scope["name"])
                img_url = links_list[0].get("href", "")
                item_key = f"nasa_img_{nasa_id}"

                if TEST_MODE or not is_item_or_title_notified(item_key, title_str, ttl_hours=720):
                    embed_title = f"🔭 {actual_observatory} | {title_str.upper()}"

                    description = (
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"🌌 **PHOTOGRAPHED TARGET:** `{title_str}`\n"
                        f"🎯 **OBSERVATORY:** `{actual_observatory}`\n"
                        f"📷 **IMAGE CREDIT:** `NASA / STScI / ESA Space Science`\n"
                        f"📅 **RELEASE DATE:** `{date_created.upper()}`\n\n"
                        f"📖 **SCIENTIFIC SUMMARY:**\n{description_str}\n\n"
                        f"💾 **FULL-RESOLUTION IMAGE:** [Open High-Res Image File]({img_url})\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                    )

                    if not TEST_MODE and not hydrated:
                        mark_item_and_title_notified(item_key, title_str, ttl_hours=720)
                        print(f"[HYDRATION] Initialized telescope discovery '{title_str}' silently.")
                    else:
                        send_discord_embed(embed_title, description, color=scope["color"], image_url=img_url)
                        mark_item_and_title_notified(item_key, title_str, ttl_hours=720)
                        set_module_hydrated("deep_space_imagery")
                        return
        except Exception as e:
            print(f"[NASA TELESCOPE SEARCH API NOTE] {scope['name']}: {e}")

    if not hydrated:
        set_module_hydrated("deep_space_imagery")
        print("[HYDRATION] Completed initial silent hydration for Deep Space Imagery module.")

# ==============================================================================
# MODULE 3: HUMANS IN SPACE LIVE TRACKER (OPEN-NOTIFY ASTROS API)
# ==============================================================================
ASTRONAUT_METADATA_DB = {
    # NASA / USA (Male 👨‍🚀 🇺🇸)
    "butch wilmore": ("👨‍🚀", "🇺🇸"),
    "barry wilmore": ("👨‍🚀", "🇺🇸"),
    "nick hague": ("👨‍🚀", "🇺🇸"),
    "matthew dominick": ("👨‍🚀", "🇺🇸"),
    "michael barratt": ("👨‍🚀", "🇺🇸"),
    "don pettit": ("👨‍🚀", "🇺🇸"),
    "jonny kim": ("👨‍🚀", "🇺🇸"),
    "victor glover": ("👨‍🚀", "🇺🇸"),
    "reid wiseman": ("👨‍🚀", "🇺🇸"),

    # NASA / USA (Female 👩‍🚀 🇺🇸)
    "sunita williams": ("👩‍🚀", "🇺🇸"),
    "tracy caldwell dyson": ("👩‍🚀", "🇺🇸"),
    "tracy dyson": ("👩‍🚀", "🇺🇸"),
    "jeanette epps": ("👩‍🚀", "🇺🇸"),
    "loral o'hara": ("👩‍🚀", "🇺🇸"),
    "christina koch": ("👩‍🚀", "🇺🇸"),
    "jessica meir": ("👩‍🚀", "🇺🇸"),
    "kate rubins": ("👩‍🚀", "🇺🇸"),
    "anne mcclain": ("👩‍🚀", "🇺🇸"),
    "nicole mann": ("👩‍🚀", "🇺🇸"),
    "jasmin moghbeli": ("👩‍🚀", "🇺🇸"),

    # ROSCOSMOS / RUSSIA & BELARUS (Male 👨‍🚀 / Female 👩‍🚀 🇷🇺 🇧🇾)
    "oleg kononenko": ("👨‍🚀", "🇷🇺"),
    "nikolai chub": ("👨‍🚀", "🇷🇺"),
    "alexander grebenkin": ("👨‍🚀", "🇷🇺"),
    "alexey ovchinin": ("👨‍🚀", "🇷🇺"),
    "ivan vagner": ("👨‍🚀", "🇷🇺"),
    "sergey prokopyev": ("👨‍🚀", "🇷🇺"),
    "dmitry petelin": ("👨‍🚀", "🇷🇺"),
    "konstantin borisov": ("👨‍🚀", "🇷🇺"),
    "alexander gorbunov": ("👨‍🚀", "🇷🇺"),
    "marina vasilevskaya": ("👩‍🚀", "🇧🇾"),
    "anna kikina": ("👩‍🚀", "🇷🇺"),

    # CNSA / CHINA (Male 👨‍🚀 / Female 👩‍🚀 🇨🇳)
    "ye guangfu": ("👨‍🚀", "🇨🇳"),
    "li cong": ("👨‍🚀", "🇨🇳"),
    "li guangsu": ("👨‍🚀", "🇨🇳"),
    "tang hongbo": ("👨‍🚀", "🇨🇳"),
    "tang shengjie": ("👨‍🚀", "🇨🇳"),
    "jiang xinlin": ("👨‍🚀", "🇨🇳"),
    "jing haipeng": ("👨‍🚀", "🇨🇳"),
    "zhu yangzhu": ("👨‍🚀", "🇨🇳"),
    "gui haichao": ("👨‍🚀", "🇨🇳"),
    "cai xuzhe": ("👨‍🚀", "🇨🇳"),
    "song lingdong": ("👨‍🚀", "🇨🇳"),
    "wang yaping": ("👩‍🚀", "🇨🇳"),
    "liu yang": ("👩‍🚀", "🇨🇳"),
    "wang haoze": ("👩‍🚀", "🇨🇳"),

    # ESA / EUROPE
    "samantha cristoforetti": ("👩‍🚀", "🇮🇹"),
    "alexander gerst": ("👨‍🚀", "🇩🇪"),
    "thomas pesquet": ("👨‍🚀", "🇫🇷"),
    "andreas mogensen": ("👨‍🚀", "🇩🇰"),
    "tim peake": ("👨‍🚀", "🇬🇧"),
    "marcus wandt": ("👨‍🚀", "🇸🇪"),
    "pablo alvarez": ("👨‍🚀", "🇪🇸"),
    "sophie adenot": ("👩‍🚀", "🇫🇷"),

    # JAXA / JAPAN
    "satoshi furukawa": ("👨‍🚀", "🇯🇵"),
    "akihiko hoshide": ("👨‍🚀", "🇯🇵"),
    "soichi noguchi": ("👨‍🚀", "🇯🇵"),
    "koichi wakata": ("👨‍🚀", "🇯🇵"),

    # CSA / CANADA & ISRO / INDIA & UAE
    "jeremy hansen": ("👨‍🚀", "🇨🇦"),
    "jenni sidey-gibbons": ("👩‍🚀", "🇨🇦"),
    "shubhanshu shukla": ("👨‍🚀", "🇮🇳"),
    "sultan al neyadi": ("👨‍🚀", "🇦🇪"),
    "rayyanah barnawi": ("👩‍🚀", "🇸🇦"),
}

def resolve_astronaut_metadata(name, craft="ISS"):
    name_lower = name.lower().strip()
    for key, val in ASTRONAUT_METADATA_DB.items():
        if key in name_lower or name_lower in key:
            return val

    is_female = any(fn in name_lower for fn in ["sunita", "tracy", "jeanette", "loral", "christina", "jessica", "kate", "anne", "nicole", "jasmin", "samantha", "marina", "anna", "wang", "liu", "sophie", "rayyanah"])
    gender_emoji = "👩‍🚀" if is_female else "👨‍🚀"

    if "tiangong" in craft.lower() or any(cn_surname in name_lower for cn_surname in ["ye ", "li ", "tang ", "jiang ", "jing ", "zhu ", "gui ", "cai ", "song ", "wang ", "liu "]):
        flag = "🇨🇳"
    elif any(ru_name in name_lower for ru_name in ["oleg", "nikolai", "alexander", "alexey", "ivan", "sergey", "dmitry", "konstantin", "ovchinin", "vagner", "prokopyev", "gorbunov"]):
        flag = "🇷🇺"
    else:
        flag = "🇺🇸"

    return gender_emoji, flag

def check_humans_in_space():
    print("Checking Module 3: Humans in Space Live Tracking Telemetry...")
    now_dt = datetime.now(timezone.utc)

    total_count = 10
    craft_groups = {}

    try:
        url = "https://api.open-notify.org/astros.json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            total_count = data.get("number", 10)
            people = data.get("people", [])
            for p in people:
                craft = p.get("craft", "ISS")
                name = p.get("name", "Astronaut")
                if craft not in craft_groups:
                    craft_groups[craft] = []
                craft_groups[craft].append(name)
    except Exception as e:
        print(f"[ASTROS API NOTE] Using default orbital manifest fallback: {e}")

    if not craft_groups:
        craft_groups = {
            "ISS (International Space Station)": ["Sunita Williams", "Butch Wilmore", "Nick Hague", "Alexander Gorbunov", "Oleg Kononenko", "Nikolai Chub", "Tracy Caldwell Dyson", "Matthew Dominick", "Michael Barratt", "Jeanette Epps", "Alexander Grebenkin"],
            "Tiangong Space Station": ["Ye Guangfu", "Li Cong", "Li Guangsu"]
        }
        total_count = sum(len(v) for v in craft_groups.values())

    all_crew = []
    manifest_lines = []
    for craft, names in craft_groups.items():
        manifest_lines.append(f"🛸 **{craft.upper()}:** ({len(names)} Crew)")
        for n in names:
            all_crew.append(f"{craft}:{n}")
            emoji, flag = resolve_astronaut_metadata(n, craft)
            manifest_lines.append(f"  └ {emoji} `{n}` {flag}")

    current_crew_set = set(all_crew)
    current_crew_str = "|".join(sorted(all_crew))

    stored_crew_str = get_stored_crew_manifest()

    if stored_crew_str is None:
        # First time running: record initial crew state silently to prevent sending random notifications on startup
        save_stored_crew_manifest(current_crew_str)
        print(f"[ASTROS NOTE] Initialized crew manifest state with {len(current_crew_set)} astronauts. No change alert sent.")
        return

    if not TEST_MODE and stored_crew_str == current_crew_str:
        print(f"[ASTROS NOTE] Orbital crew manifest unchanged ({len(current_crew_set)} astronauts). Skipping message.")
        return

    # Crew change detected! Calculate specific arrivals and departures
    stored_crew_set = set(stored_crew_str.split("|")) if stored_crew_str else set()
    joined = current_crew_set - stored_crew_set
    left = stored_crew_set - current_crew_set

    updates_text = ""
    if joined:
        joined_names = [j.split(":")[-1] for j in joined]
        updates_text += f"\n✨ **NEW CREW ARRIVALS IN ORBIT:** {', '.join(joined_names)}"
    if left:
        left_names = [l.split(":")[-1] for l in left]
        updates_text += f"\n🪂 **CREW RETURNED TO EARTH:** {', '.join(left_names)}"

    manifest_text = "\n".join(manifest_lines)
    date_str = now_dt.strftime("%d %B %Y").upper()

    title = f"👨‍🚀 HUMANS IN SPACE LIVE | CREW CHANGE UPDATE ({total_count} IN ORBIT)"
    description = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🚨 **CREW MANIFEST UPDATE DETECTED ({date_str}):**"
        f"{updates_text}\n\n"
        f"🎯 **UPDATED ORBITAL MANIFEST:**\n"
        f"🌍 **TOTAL HUMANS IN LOW EARTH ORBIT:** `{total_count} Crew Members`\n\n"
        f"{manifest_text}\n\n"
        f"💡 **FACT:** These astronauts orbit Earth every 90 minutes at ~28,000 km/h (~17,500 mph).\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    send_discord_embed(title, description, color=0x34495E, image_url="https://images-assets.nasa.gov/image/jsc2011e021164/jsc2011e021164~medium.jpg")
    save_stored_crew_manifest(current_crew_str)

# ==============================================================================
# MODULE 4: EXOPLANET DISCOVERY TRACKER (NASA EXOPLANET ARCHIVE)
# ==============================================================================

def is_exoplanet_notified(planet_name):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()
    cursor.execute("SELECT expire_timestamp FROM exoplanet_cache WHERE planet_name = ?", (planet_name,))
    row = cursor.fetchone()
    conn.close()
    return bool(row and row[0] > now_ts)

def mark_exoplanet_notified(planet_name, ttl_hours=8760):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()
    expire_ts = now_ts + (ttl_hours * 3600)
    cursor.execute(
        "INSERT OR REPLACE INTO exoplanet_cache (planet_name, expire_timestamp) VALUES (?, ?)",
        (planet_name, expire_ts)
    )
    cursor.execute("DELETE FROM exoplanet_cache WHERE expire_timestamp <= ?", (now_ts,))
    conn.commit()
    conn.close()
    if persistent_history:
        persistent_history.record_published(f"exoplanet_{planet_name}", ttl_hours=ttl_hours)

def get_habitability_badge(pl_rade, pl_orbper):
    """Returns a simple habitability indicator based on planet radius and orbital period."""
    try:
        radius = float(pl_rade) if pl_rade else 0
        period = float(pl_orbper) if pl_orbper else 0
        if 0.5 <= radius <= 2.0 and 10 <= period <= 500:
            return "🌊 Potentially Rocky & Habitable Zone"
        elif radius < 0.5:
            return "🪨 Sub-Earth / Rocky"
        elif radius <= 4.0:
            return "🌍 Super-Earth / Mini-Neptune"
        elif radius <= 10.0:
            return "🌊 Neptune-class Gas World"
        else:
            return "🪐 Gas Giant (Jupiter-class)"
    except Exception:
        return "🔭 Unknown Class"

def check_exoplanet_discoveries():
    """Checks NASA Exoplanet Archive for newly confirmed exoplanets and posts discoveries."""
    print("Checking Module 4: Exoplanet Discovery Tracker (NASA Exoplanet Archive)...")
    now_dt = datetime.now(timezone.utc)
    current_year = now_dt.year

    # Query NASA Exoplanet Archive TAP service for recent confirmations this year
    try:
        query = (
            f"select pl_name,disc_year,disc_facility,disc_method,pl_rade,pl_bmasse,"
            f"pl_orbper,pl_eqt,st_dist,sy_snum,sy_pnum "
            f"from ps "
            f"where disc_year={current_year} "
            f"order by rowupdate desc"
        )
        url = f"https://exoplanetarchive.ipac.caltech.edu/TAP/sync?query={requests.utils.quote(query)}&format=json"
        res = requests.get(url, timeout=10)
        if res.status_code != 200:
            print(f"[EXOPLANET API NOTE] Status {res.status_code}")
            return
        planets = res.json()
        if not planets:
            print("[EXOPLANET] No new discoveries found for this year yet.")
            return
    except Exception as e:
        print(f"[EXOPLANET API ERROR] {e}")
        return

    hydrated = is_module_hydrated("exoplanet_tracker")
    posted_count = 0

    for planet in planets:
        pl_name     = planet.get("pl_name", "").strip()
        disc_year   = planet.get("disc_year", current_year)
        disc_fac    = planet.get("disc_facility", "Unknown Observatory")
        disc_method = planet.get("disc_method", "Transit Photometry")
        pl_rade     = planet.get("pl_rade")   # Earth radii
        pl_bmasse   = planet.get("pl_bmasse") # Earth masses
        pl_orbper   = planet.get("pl_orbper") # Orbital period (days)
        pl_eqt      = planet.get("pl_eqt")   # Equilibrium temperature (K)
        st_dist     = planet.get("st_dist")   # Distance to star (parsecs)
        sy_snum     = planet.get("sy_snum", 1) # Stars in system
        sy_pnum     = planet.get("sy_pnum", 1) # Planets in system

        if not pl_name or is_exoplanet_notified(pl_name):
            continue

        habitability = get_habitability_badge(pl_rade, pl_orbper)

        # Format optional fields
        radius_str = f"{float(pl_rade):.2f}× Earth" if pl_rade else "Unknown"
        mass_str   = f"{float(pl_bmasse):.1f}× Earth" if pl_bmasse else "Unknown"
        period_str = f"{float(pl_orbper):.1f} days" if pl_orbper else "Unknown"
        temp_str   = f"{int(float(pl_eqt))} K ({int(float(pl_eqt)) - 273}°C)" if pl_eqt else "Unknown"
        dist_str   = f"{float(st_dist):.1f} parsecs ({float(st_dist)*3.26:.0f} light-years)" if st_dist else "Unknown"

        # Fetch NASA image for the discovery facility / method
        try:
            from google_ai_helper import fetch_best_nasa_image
            img_keywords = [pl_name.split()[0], disc_fac, "exoplanet discovery"]
            img_url = fetch_best_nasa_image(img_keywords)
        except Exception:
            img_url = "https://images-assets.nasa.gov/image/PIA19830/PIA19830~medium.jpg"

        embed_title = f"🌍 EXOPLANET DISCOVERED | {pl_name.upper()}"
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🌟 **NEWLY CONFIRMED EXOPLANET:** `{pl_name}`\n"
            f"📅 **DISCOVERY YEAR:** `{disc_year}`\n"
            f"🔭 **DISCOVERED BY:** `{disc_fac}`\n"
            f"🧪 **DETECTION METHOD:** `{disc_method}`\n\n"
            f"📐 **PLANET PROFILE:**\n"
            f"└ 📏 **Radius:** `{radius_str}`\n"
            f"└ ⚖️ **Mass:** `{mass_str}`\n"
            f"└ 🔄 **Orbital Period:** `{period_str}`\n"
            f"└ 🌡️ **Equilibrium Temp:** `{temp_str}`\n"
            f"└ 📡 **Distance from Earth:** `{dist_str}`\n"
            f"└ ⭐ **Stars in System:** `{sy_snum}` | 🪐 **Known Planets:** `{sy_pnum}`\n\n"
            f"🏷️ **CLASSIFICATION:** {habitability}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        if not TEST_MODE and not hydrated:
            mark_exoplanet_notified(pl_name, ttl_hours=8760)
            print(f"[HYDRATION] Initialized exoplanet '{pl_name}' silently.")
        else:
            send_discord_embed(embed_title, description, color=0x1ABC9C, image_url=img_url)
            mark_exoplanet_notified(pl_name, ttl_hours=8760)
            set_module_hydrated("exoplanet_tracker")
            posted_count += 1
            if posted_count >= 1:  # Post max 1 new exoplanet per cycle
                break

    if not hydrated and posted_count == 0:
        set_module_hydrated("exoplanet_tracker")
        print("[HYDRATION] Completed silent hydration for Exoplanet Tracker module.")

# ==============================================================================
# MAIN BOT EXECUTION
# ==============================================================================
def run_engine():
    print("==========================================================")
    print("INITIALIZING COSMIC NEXUS DEEP SPACE & LAUNCH ENGINE")
    print(f"Operating Mode: {'TEST_MODE (Dry-Run Alerts)' if TEST_MODE else 'PRODUCTION (Real Live Monitoring)'}")
    print("==========================================================")

    check_upcoming_launches()
    check_deep_space_imagery()
    check_humans_in_space()
    check_exoplanet_discoveries()

    print("==========================================================")
    print("Deep Space & Launch Check Completed Successfully.")
    print("==========================================================")

if __name__ == "__main__":
    run_engine()
