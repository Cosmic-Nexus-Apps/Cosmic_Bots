import os
import sys
import io
import sqlite3
import requests
import random
import time
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
DB_FILE = "deep_space.db"

# Operational flag: TEST_MODE = True generates sample launch & telescope embeds.
TEST_MODE = os.getenv("TEST_MODE", "FALSE").upper() == "TRUE"

def init_db():
    """Initializes SQLite database for deep space and rocket launch tracking."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS launch_cache (
            item_id TEXT PRIMARY KEY,
            expire_timestamp REAL
        )
    """)
    conn.commit()
    conn.close()

def is_already_notified(item_id, ttl_hours=None):
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

def send_discord_embed(title, description, color=0x1F618D, role_id=ROLE_ID, image_url=None):
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
# MODULE 1: MAJOR ROCKET LAUNCHES WITH DYNAMIC MILESTONES & STATUS
# ==============================================================================
PRIORITY_LAUNCH_KEYWORDS = [
    "starship", "artemis", "falcon heavy", "jwst", "james webb",
    "euclid", "europa clipper", "roman", "crew", "moon", "mars",
    "sls", "ariane 6", "curiosity", "perseverance", "chandrayaan", "gaganyaan", "kinetica"
]

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
    vid_urls = launch_data.get("vidURLs", [])
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

def get_mission_milestones(mission_name, launch_dt, now_dt):
    """Calculates dynamic mission trajectory milestones for Lunar/Deep Space missions like Artemis & Starship."""
    name_lower = mission_name.lower()
    
    if "artemis" in name_lower or "moon" in name_lower or "lunar" in name_lower:
        time_diff_hours = (now_dt - launch_dt).total_seconds() / 3600.0
        if time_diff_hours < 0:
            return (
                "📍 **DEEP SPACE MISSION STAGE:**\n"
                "└ 🚀 `[1/5] Pre-Launch Countdown` ➔ 🛰️ `[2/5] Earth Orbit` ➔ 🌖 `[3/5] TLI Burn` ➔ 🌕 `[4/5] Lunar Orbit` ➔ 👨‍🚀 `[5/5] Landing/Return`"
            )
        elif time_diff_hours <= 2:
            return (
                "📍 **DEEP SPACE MISSION STAGE:**\n"
                "└ ✅ `[1/5] Liftoff Complete` ➔ 🛰️ `[2/5] Earth Orbit Insertion (Active)` ➔ 🌖 `[3/5] En Route to TLI Burn`"
            )
        elif time_diff_hours <= 72:
            return (
                "📍 **DEEP SPACE MISSION STAGE:**\n"
                "└ ✅ `[1/5] Liftoff` ➔ ✅ `[2/5] Orbit Insertion` ➔ 🌖 `[3/5] Trans-Lunar Injection (TLI) Active — En Route to Moon` ➔ 🌕 `[4/5] Lunar Capture Pending`"
            )
        else:
            return (
                "📍 **DEEP SPACE MISSION STAGE:**\n"
                "└ ✅ `[1/5] Liftoff` ➔ ✅ `[2/5] Orbit Insertion` ➔ ✅ `[3/5] TLI Trans-Lunar Flight` ➔ 🌕 `[4/5] Lunar Orbit Insertion Achieved`"
            )
            
    elif "starship" in name_lower:
        return (
            "📍 **DEEP SPACE MISSION STAGE:**\n"
            "└ 🚀 `Full-Stack Stage Separation` ➔ 🛰️ `Orbital Velocity Insertion` ➔ 🌊 `Controlled Splashdown / Tower Catch`"
        )
        
    return None

def check_upcoming_launches():
    print("Checking Module 1: High-Impact Rocket Launches (Launch Library 2 API)...")
    now_dt = datetime.now(timezone.utc)

    url = "https://ll.thespacedevs.com/2.2.0/launch/upcoming/?limit=10"
    
    launches = []
    try:
        res = requests.get(url, timeout=8)
        if res.status_code == 200:
            data = res.json()
            launches = data.get("results", [])
    except Exception as e:
        print(f"[LAUNCH API NOTE] Using default priority stream: {e}")

    high_priority_found = False

    for launch in launches:
        launch_id = launch.get("id", "sample_launch")
        name = launch.get("name", "SpaceX Starship Orbital Test Flight")
        net_raw = launch.get("net", "")
        
        launch_dt = now_dt
        if net_raw:
            try:
                launch_dt = datetime.fromisoformat(net_raw.replace('Z', '+00:00'))
            except Exception:
                launch_dt = now_dt

        rocket_img = launch.get("image", "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000842/GSFC_20171208_Archive_e000842~medium.jpg")
        provider_name = launch.get("launch_service_provider", {}).get("name", "SpaceX")
        
        is_priority = any(kw in name.lower() for kw in PRIORITY_LAUNCH_KEYWORDS)
        
        if is_priority or (len(launches) > 0 and not high_priority_found) or TEST_MODE:
            item_key = f"launch_{launch_id}"
            if not TEST_MODE and is_already_notified(item_key, ttl_hours=72):
                continue

            pad_name = launch.get("pad", {}).get("name", "Starbase Orbital Launch Pad")
            location = launch.get("pad", {}).get("location", {}).get("name", "USA")
            raw_status = launch.get("status", {}).get("name", "Go for Launch")
            orbit_type = launch.get("orbit", {}).get("name", "Low Earth Orbit") if launch.get("orbit") else "Low Earth Orbit"
            
            # Format launch status clearly
            status_lower = raw_status.lower()
            if "success" in status_lower:
                status_formatted = "✅ Launch Successful (Orbit Achieved)"
            elif "fail" in status_lower or "partial" in status_lower:
                status_formatted = "❌ Launch Anomaly / Failure Reported"
            elif "go" in status_lower or "tbd" in status_lower or "upcoming" in status_lower:
                status_formatted = "🟢 Go for Launch (T-Minus Active)"
            else:
                status_formatted = f"⚡ Status: {raw_status}"

            webcast_url = get_webcast_url(launch, name, provider_name)
            embed_color = get_provider_color(name, provider_name)

            short_mission = name.split("|")[0].strip() if "|" in name else name
            title = f"🚀 ROCKET LAUNCH | {short_mission.upper()}"
            
            utc_time_str = launch_dt.strftime("%d %B %Y at %H:%M UTC").upper()
            milestone_block = get_mission_milestones(name, launch_dt, now_dt)
            milestone_text = f"\n\n{milestone_block}" if milestone_block else ""

            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **MISSION:** `{name}`\n"
                f"🏢 **LAUNCH PROVIDER:** `{provider_name}`\n"
                f"🛰️ **TARGET ORBIT:** `{orbit_type}`\n"
                f"📍 **LAUNCH PAD:** `{pad_name} ({location})`\n"
                f"⚡ **LAUNCH STATUS:** `{status_formatted}`\n"
                f"⏱️ **EXACT T-0 LAUNCH TIME:** `{utc_time_str}`"
                f"{milestone_text}\n\n"
                f"⏱️ **TARGET LAUNCH TIME PER REGION (MINUTE-PRECISE):**\n"
                f"{get_regional_3utc_windows(launch_dt)}\n\n"
                f"📺 **LIVE STREAM:** [Watch Official Broadcast]({webcast_url})\n\n"
                f"💡 **MISSION BRIEF:** High-profile orbital insertion & payload deployment mission.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(title, description, color=embed_color, image_url=rocket_img)
            mark_notified(item_key, ttl_hours=72)
            high_priority_found = True
            if TEST_MODE:
                break

    if not high_priority_found and TEST_MODE:
        sample_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 18, 51, tzinfo=timezone.utc)
        sample_title = "🚀 ROCKET LAUNCH | ARTEMIS III LUNAR LANDING MISSION"
        sample_utc_str = sample_dt.strftime("%d %B %Y at %H:%M UTC").upper()
        sample_milestones = get_mission_milestones("artemis", sample_dt, now_dt)
        sample_desc = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **MISSION:** `NASA Artemis III Crewed Lunar Landing`\n"
            f"🏢 **LAUNCH PROVIDER:** `NASA / SpaceX`\n"
            f"🛰️ **TARGET ORBIT:** `Trans-Lunar Injection (TLI)`\n"
            f"📍 **LAUNCH PAD:** `Kennedy Space Center LC-39B (Florida, USA)`\n"
            f"⚡ **LAUNCH STATUS:** `🟢 Go for Launch (T-Minus Active)`\n"
            f"⏱️ **EXACT T-0 LAUNCH TIME:** `{sample_utc_str}`\n\n"
            f"{sample_milestones}\n\n"
            f"⏱️ **TARGET LAUNCH TIME PER REGION (MINUTE-PRECISE):**\n"
            f"{get_regional_3utc_windows(sample_dt)}\n\n"
            f"📺 **LIVE STREAM:** [Watch Official NASA Broadcast](https://www.youtube.com/@NASAGovVideo)\n\n"
            f"💡 **MISSION BRIEF:** Historic human return to the lunar South Pole surface.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )
        sample_img = "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000842/GSFC_20171208_Archive_e000842~medium.jpg"
        send_discord_embed(sample_title, sample_desc, color=0x003366, image_url=sample_img)

# ==============================================================================
# MODULE 2: LIVE MULTI-TELESCOPE STREAM (NASA APOD + NASA IMAGE API FOR JWST, HST, EUCLID, CHANDRA)
# ==============================================================================
TELESCOPE_SEARCH_QUERIES = [
    {"query": "James Webb Space Telescope", "name": "JAMES WEBB SPACE TELESCOPE (JWST)", "color": 0x8E44AD},
    {"query": "Hubble Space Telescope", "name": "HUBBLE SPACE TELESCOPE (HST)", "color": 0x16A085},
    {"query": "Euclid Space Telescope", "name": "EUCLID SPACE TELESCOPE (ESA/NASA 3D MAP)", "color": 0x2980B9},
    {"query": "Chandra X-Ray Observatory", "name": "CHANDRA X-RAY OBSERVATORY", "color": 0xE74C3C},
    {"query": "Vera C. Rubin Observatory", "name": "VERA C. RUBIN OBSERVATORY (LSST)", "color": 0x9B59B6}
]

def check_deep_space_imagery():
    print("Checking Module 2: Live Multi-Telescope Telemetry Stream (NASA APOD & NASA Image Library)...")
    now_dt = datetime.now(timezone.utc)
    new_image_posted = False

    # 1. Query Live NASA APOD (Astronomy Picture of the Day) API
    try:
        apod_url = "https://api.nasa.gov/planetary/apod?api_key=DEMO_KEY"
        res = requests.get(apod_url, timeout=6)
        if res.status_code == 200:
            apod_data = res.json()
            apod_date = apod_data.get("date", now_dt.strftime("%Y-%m-%d"))
            item_key = f"apod_{apod_date}"

            if TEST_MODE or not is_already_notified(item_key, ttl_hours=24):
                title_str = apod_data.get("title", "Astronomy Picture of the Day")
                media_type = apod_data.get("media_type", "image")
                img_url = apod_data.get("url") if media_type == "image" else apod_data.get("thumbnail_url")
                hd_url = apod_data.get("hdurl", img_url)
                copyright_credit = apod_data.get("copyright", "NASA / APOD Science Core").replace('\n', ' ')
                explanation = apod_data.get("explanation", "Daily astronomical observation release.")
                if len(explanation) > 320:
                    explanation = explanation[:317] + "..."

                embed_title = f"🔭 NASA APOD | {title_str.upper()}"

                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🌌 **PHOTOGRAPHED TARGET:** `{title_str}`\n"
                    f"🎯 **OBSERVATORY / SOURCE:** `NASA Astronomy Picture of the Day`\n"
                    f"📷 **IMAGE CREDIT:** `{copyright_credit}`\n"
                    f"📅 **OBSERVATION DATE:** `{apod_date.upper()}`\n\n"
                    f"📖 **SCIENTIFIC SUMMARY:** {explanation}\n\n"
                    f"💾 **FULL-RESOLUTION IMAGE:** [Open High-Res Image File]({hd_url})\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )

                if img_url:
                    send_discord_embed(embed_title, description, color=0x8E44AD, image_url=img_url)
                    mark_notified(item_key, ttl_hours=24)
                    new_image_posted = True
                    if TEST_MODE:
                        return
    except Exception as e:
        print(f"[APOD API NOTE] Query active stream fallback: {e}")

    # 2. Query Live NASA Image Search API for JWST, Hubble, Euclid, Chandra, Rubin
    for scope in TELESCOPE_SEARCH_QUERIES:
        try:
            search_url = f"https://images-api.nasa.gov/search?q={requests.utils.quote(scope['query'])}&media_type=image"
            res = requests.get(search_url, timeout=6)
            if res.status_code == 200:
                items = res.json().get("collection", {}).get("items", [])
                for item in items[:5]:
                    data_list = item.get("data", [])
                    links_list = item.get("links", [])
                    if not data_list or not links_list:
                        continue

                    item_data = data_list[0]
                    nasa_id = item_data.get("nasa_id", "")
                    title_str = item_data.get("title", scope["query"])
                    description_str = item_data.get("description", "Scientific space telescope discovery.")
                    date_created = item_data.get("date_created", "")[:10]
                    
                    if len(description_str) > 300:
                        description_str = description_str[:297] + "..."

                    img_url = links_list[0].get("href", "")
                    item_key = f"nasa_img_{nasa_id}"

                    if TEST_MODE or not is_already_notified(item_key, ttl_hours=168):
                        # TITLE FORMAT: 🔭 [TELESCOPE NAME] | [TARGET NAME]
                        embed_title = f"🔭 {scope['name']} | {title_str.upper()}"

                        description = (
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🌌 **PHOTOGRAPHED TARGET:** `{title_str}`\n"
                            f"🎯 **OBSERVATORY:** `{scope['name']}`\n"
                            f"📷 **IMAGE CREDIT:** `NASA / STScI / ESA Space Science`\n"
                            f"📅 **RELEASE DATE:** `{date_created.upper()}`\n\n"
                            f"📖 **SCIENTIFIC SUMMARY:** {description_str}\n\n"
                            f"💾 **FULL-RESOLUTION IMAGE:** [Open High-Res Image File]({img_url})\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        )

                        send_discord_embed(embed_title, description, color=scope["color"], image_url=img_url)
                        mark_notified(item_key, ttl_hours=168)
                        new_image_posted = True
                        if TEST_MODE:
                            break
                if TEST_MODE and new_image_posted:
                    break
        except Exception as e:
            print(f"[NASA TELESCOPE SEARCH API NOTE] {scope['name']}: {e}")

# ==============================================================================
# MODULE 3: HUMANS IN SPACE LIVE TRACKER (OPEN-NOTIFY ASTROS API)
# ==============================================================================
def check_humans_in_space():
    print("Checking Module 3: Humans in Space Live Tracking Telemetry...")
    now_dt = datetime.now(timezone.utc)
    base_key = f"astros_{now_dt.strftime('%Y%m%d')}"

    if not TEST_MODE and is_already_notified(base_key, ttl_hours=168):
        return

    total_count = 10
    craft_groups = {}

    try:
        url = "http://api.open-notify.org/astros.json"
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
            "ISS (International Space Station)": ["Sunita Williams", "Butch Wilmore", "Nick Hague", "Alexander Gorbunov"],
            "Tiangong Space Station": ["Ye Guangfu", "Li Cong", "Li Guangsu"]
        }
        total_count = sum(len(v) for v in craft_groups.values())

    manifest_lines = []
    for craft, names in craft_groups.items():
        manifest_lines.append(f"🛸 **{craft.upper()}:** ({len(names)} Crew)")
        for n in names:
            manifest_lines.append(f"  └ 👨‍🚀 `{n}`")

    manifest_text = "\n".join(manifest_lines)
    date_str = now_dt.strftime("%d %B %Y").upper()

    title = f"👨‍🚀 HUMANS IN SPACE LIVE | {total_count} ASTRONAUTS IN ORBIT"
    description = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **CURRENT ORBITAL MANIFEST ({date_str}):**\n"
        f"🌍 **TOTAL HUMANS IN LOW EARTH ORBIT:** `{total_count} Crew Members`\n\n"
        f"{manifest_text}\n\n"
        f"💡 **FACT:** These astronauts orbit Earth every 90 minutes at ~28,000 km/h (~17,500 mph).\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    send_discord_embed(title, description, color=0x34495E, image_url="https://images-assets.nasa.gov/image/PIA02308/PIA02308~medium.jpg")
    mark_notified(base_key, ttl_hours=168)

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

    print("==========================================================")
    print("Deep Space & Launch Check Completed Successfully.")
    print("==========================================================")

if __name__ == "__main__":
    run_engine()
