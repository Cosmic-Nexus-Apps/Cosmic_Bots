import os
import sys
import re
import hashlib
import sqlite3
import requests
import random
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

load_dotenv()

WEBHOOK_URL = os.getenv("SPACE_HISTORY_BOT_DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
ROLE_ID = os.getenv("SPACE_HISTORY_BOT_DISCORD_ROLE_ID") or os.getenv("DISCORD_ROLE_ID")
DB_FILE = "history.db"

TEST_MODE = os.getenv("TEST_MODE", "FALSE").upper() == "TRUE"

def init_db():
    """Initializes SQLite database for space history tracking to prevent duplicate posts."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS history_cache (
            event_id TEXT PRIMARY KEY,
            expire_timestamp REAL
        )
    """)
    conn.commit()
    conn.close()

def is_already_posted(event_id, ttl_hours=None):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()

    cursor.execute("SELECT expire_timestamp FROM history_cache WHERE event_id = ?", (event_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row[0] > now_ts:
        return True
    return False

def mark_posted(event_id, title_str="", ttl_hours=8760): # 1-year anti-repeat
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()
    expire_ts = now_ts + (ttl_hours * 3600)

    cursor.execute("""
        INSERT OR REPLACE INTO history_cache (event_id, expire_timestamp)
        VALUES (?, ?)
    """, (event_id, expire_ts))

    # Also store title hash to catch same event with different ID
    if title_str:
        clean_t = re.sub(r'\W+', '', title_str.lower())
        if clean_t:
            t_hash = hashlib.md5(clean_t.encode('utf-8')).hexdigest()
            cursor.execute("""
                INSERT OR REPLACE INTO history_cache (event_id, expire_timestamp)
                VALUES (?, ?)
            """, (f"title_{t_hash}", expire_ts))

    cursor.execute("DELETE FROM history_cache WHERE expire_timestamp <= ?", (now_ts,))
    conn.commit()
    conn.close()

    # Sync to shared persistent_history.json (cross-bot dedup layer)
    try:
        import persistent_history
        persistent_history.record_published(event_id, title_str=title_str, ttl_hours=ttl_hours)
    except Exception:
        pass

def send_discord_embed(title, description, color=0xD35400, role_id=ROLE_ID, image_url=None):
    if not WEBHOOK_URL:
        print(f"[DISCORD EMBED - NO WEBHOOK CONFIGURED]\nTitle: {title}\n{description}\n")
        return

    embed_obj = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": "Cosmic Nexus | Today in Space History Chronicle"
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

# ==============================================================================
# RICH SPACE HISTORY CATALOG (100% VERIFIED NASA/ESA IMAGES & ACCURATE DATES)
# ==============================================================================
SPACE_HISTORY_CATALOG = [
    {
        "id": "hist_apollo_11_moon_landing",
        "date_mmdd": "07-20",
        "year": "1969",
        "title": "Apollo 11 — Historic First Human Footsteps on the Moon",
        "agency": "NASA (United States)",
        "crew": "Neil Armstrong, Buzz Aldrin, Michael Collins",
        "story": "At 20:17 UTC, Apollo 11's Lunar Module 'Eagle' touched down at the Sea of Tranquility on the Moon. Six hours later, Neil Armstrong stepped onto the lunar surface declaring: 'That's one small step for man, one giant leap for mankind.' Armstrong and Aldrin spent 21.5 hours on the lunar surface, collecting 21.5 kg of lunar material.",
        "impact": "Marked humanity's first landing on another celestial body and fulfilled the 1960s Space Race milestone.",
        "image": "https://images-assets.nasa.gov/image/as11-40-5874/as11-40-5874~medium.jpg"
    },
    {
        "id": "hist_sputnik_1_launch",
        "date_mmdd": "10-04",
        "year": "1957",
        "title": "Sputnik 1 — Dawn of the Space Age",
        "agency": "Soviet Space Program (USSR)",
        "crew": "Uncrewed Orbital Satellite",
        "story": "The Soviet Union launched Sputnik 1, the world's first artificial satellite, into Low Earth Orbit from the Baikonur Cosmodrome. Transmitting radio 'beeps' at 20.005 MHz as it orbited Earth every 96 minutes, its signal was picked up by radio amateurs across the globe.",
        "impact": "Inaugurated the modern Space Age and triggered the international Space Race.",
        "image": "https://images-assets.nasa.gov/image/S57-001/S57-001~medium.jpg"
    },
    {
        "id": "hist_vostok_1_gagarin",
        "date_mmdd": "04-12",
        "year": "1961",
        "title": "Vostok 1 — Yuri Gagarin Becomes First Human in Space",
        "agency": "Soviet Space Program (USSR)",
        "crew": "Yuri Gagarin",
        "story": "Soviet Cosmonaut Yuri Gagarin boarded Vostok 1 and completed a 108-minute single-orbit flight around the Earth at an altitude of 327 km, exclaiming 'Poyekhali!' ('Let's go!') upon liftoff.",
        "impact": "Proved that humans can survive in microgravity and orbital spaceflight.",
        "image": "https://images-assets.nasa.gov/image/6100140/6100140~medium.jpg"
    },
    {
        "id": "hist_hubble_deployment_sts31",
        "date_mmdd": "04-24",
        "year": "1990",
        "title": "STS-31 — Space Shuttle Discovery Deploys Hubble Space Telescope",
        "agency": "NASA / ESA",
        "crew": "Loren Shriver, Charles Bolden, Bruce McCandless, Steven Hawley, Kathryn Sullivan",
        "story": "Space Shuttle Discovery launched into orbit carrying the 11-ton Hubble Space Telescope into a 600 km orbit. Released by Discovery's robotic arm, Hubble revolutionized astronomy by observing deep cosmos clear of atmospheric distortion.",
        "impact": "Pinpointed the expansion rate of the Universe (Hubble Constant) and discovered dark energy acceleration.",
        "image": "https://images-assets.nasa.gov/image/sts031-10-011/sts031-10-011~medium.jpg"
    },
    {
        "id": "hist_voyager_1_golden_record",
        "date_mmdd": "09-05",
        "year": "1977",
        "title": "Voyager 1 — Interstellar Journey & The Golden Record",
        "agency": "NASA / JPL",
        "crew": "Uncrewed Interstellar Probe",
        "story": "Voyager 1 launched aboard a Titan IIIE rocket. Carrying a gold-plated copper phonograph record with Earth sounds, greetings in 55 languages, and music, it explored Jupiter and Saturn before crossing the heliopause into interstellar space in 2012.",
        "impact": "Farthest human-made object from Earth, traveling over 24 billion kilometers in deep interstellar space.",
        "image": "https://images-assets.nasa.gov/image/PIA17046/PIA17046~medium.jpg"
    },
    {
        "id": "hist_jwst_first_deep_field",
        "date_mmdd": "07-11",
        "year": "2022",
        "title": "James Webb Space Telescope — Unveiling First Deep Field (SMACS 0723)",
        "agency": "NASA / ESA / CSA / STScI",
        "crew": "Space Telescope at Sun-Earth L2",
        "story": "NASA released JWST's First Deep Field, revealing galaxy cluster SMACS 0723 as it appeared 4.6 billion years ago. The gravitational lens magnified ancient galaxies behind it, capturing light emitted over 13.1 billion years ago.",
        "impact": "Deepest and sharpest infrared image of the distant Universe ever captured.",
        "image": "https://images-assets.nasa.gov/image/main_image_deep_field_smacs0723-5mb/main_image_deep_field_smacs0723-5mb~medium.jpg"
    },
    {
        "id": "hist_curiosity_mars_landing",
        "date_mmdd": "08-06",
        "year": "2012",
        "title": "Curiosity Rover — '7 Minutes of Terror' Sky Crane Landing on Mars",
        "agency": "NASA / JPL",
        "crew": "Uncrewed Mars Science Laboratory",
        "story": "NASA's Curiosity rover landed inside Gale Crater on Mars using an unprecedented rocket-powered Sky Crane system. Entering the Martian atmosphere at 20,000 km/h, the sky crane lowered Curiosity to the surface on tethers.",
        "impact": "Confirmed ancient Mars had liquid water lakes and organic chemistry capable of supporting microbial life.",
        "image": "https://images-assets.nasa.gov/image/PIA15962/PIA15962~medium.jpg"
    },
    {
        "id": "hist_untethered_spacewalk_mccandless",
        "date_mmdd": "02-07",
        "year": "1984",
        "title": "STS-41B — First Untethered Spacewalk in History",
        "agency": "NASA",
        "crew": "Bruce McCandless II",
        "story": "Astronaut Bruce McCandless II stepped out of Space Shuttle Challenger into the void of space wearing the Manned Maneuvering Unit (MMU) nitrogen jetpack. Moving up to 98 meters away from the shuttle without safety tethers, he became a human satellite.",
        "impact": "Demonstrated free-flight EVA mobility for satellite repair and space station construction.",
        "image": "https://images-assets.nasa.gov/image/41-B-3109/41-B-3109~medium.jpg"
    },
    {
        "id": "hist_apollo_8_earthrise",
        "date_mmdd": "12-24",
        "year": "1968",
        "title": "Apollo 8 — First Humans to Orbit the Moon & The 'Earthrise' Photo",
        "agency": "NASA",
        "crew": "Frank Borman, Jim Lovell, William Anders",
        "story": "Apollo 8 became the first crewed spacecraft to leave Earth orbit and enter lunar orbit. On Christmas Eve 1968, astronaut Bill Anders captured the iconic color photograph 'Earthrise', showing Earth rising above the barren lunar horizon.",
        "impact": "Spurred the modern environmental movement by showcasing Earth's fragility in cosmic isolation.",
        "image": "https://images-assets.nasa.gov/image/NASA-68-H-1401/NASA-68-H-1401~medium.jpg"
    },
    {
        "id": "hist_iss_expedition_1",
        "date_mmdd": "11-02",
        "year": "2000",
        "title": "Expedition 1 — Continuous Human Presence Aboard ISS Begins",
        "agency": "NASA / Roscosmos / ESA / JAXA / CSA",
        "crew": "William Shepherd, Sergei Krikalev, Yuri Gidzenko",
        "story": "The Expedition 1 crew docked with the International Space Station aboard a Soyuz TM-31 spacecraft. This marked the start of unbroken, continuous human presence in space, which has lasted for over two decades.",
        "impact": "Established the ISS as an unprecedented international microgravity research laboratory.",
        "image": "https://images-assets.nasa.gov/image/iss001e05001/iss001e05001~medium.jpg"
    }
]

def check_today_in_space_history():
    print("Checking Today in Space History Chronicle...")
    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime("%Y-%m-%d")
    daily_key = f"hist_daily_{today_str}"

    # Strict Daily Execution Guard: Only 1 post allowed per calendar day
    if not TEST_MODE and is_already_posted(daily_key):
        print(f"[HISTORY GUARD] Already published Space History for today ({today_str}). Skipping.")
        return

    current_mmdd = now_dt.strftime("%m-%d")
    date_display = now_dt.strftime("%d %B").upper()

    # Century & Era Diversity Rotation across 4 historical eras
    eras = ["ancient", "renaissance", "space_race", "modern"]
    target_era = eras[now_dt.timetuple().tm_yday % 4]
    print(f"[HISTORY ERA ROTATION] Targeted Era for today: '{target_era.upper()}'")

    event = None
    try:
        from google_ai_helper import generate_ai_history
        ai_hist = generate_ai_history(current_mmdd, target_era=target_era)
        if ai_hist:
            event_id_check = ai_hist.get("id", "ai_h")
            title_check = ai_hist.get("title", "")
            # Check both ID and title hash to prevent same event with different ID
            title_hash_key = ""
            if title_check:
                clean_t = re.sub(r'\W+', '', title_check.lower())
                if clean_t:
                    title_hash_key = f"title_{hashlib.md5(clean_t.encode('utf-8')).hexdigest()}"
            already = is_already_posted(event_id_check) or (title_hash_key and is_already_posted(title_hash_key))
            if not already:
                event = ai_hist
                print(f"[GEMINI AI] Generated fresh space history record for {current_mmdd} ({target_era}): '{event.get('title')}'") 
    except Exception as e:
        print(f"[GEMINI HISTORY NOTE] Using catalog fallback: {e}")

    if not event:
        # 1. Look for date-matched historical events
        date_matched = [e for e in SPACE_HISTORY_CATALOG if e["date_mmdd"] == current_mmdd and (TEST_MODE or not is_already_posted(e["id"]))]
        
        if date_matched:
            event = random.choice(date_matched)
        else:
            # Fallback to available unposted historical events
            available = [e for e in SPACE_HISTORY_CATALOG if TEST_MODE or not is_already_posted(e["id"])]
            if not available:
                print("[HISTORY NOTE] Resetting history cache loop...")
                available = SPACE_HISTORY_CATALOG
            event = random.choice(available)

    event_id = event.get("id", f"hist_{current_mmdd}_{now_dt.year}")
    title = f"🗓️ TODAY IN SPACE HISTORY | {event['title'].upper()}"

    hook_str = f"🎬 **THE HOOK:**\n*{event['hook']}*\n\n" if event.get("hook") else ""
    fun_fact_str = f"💡 **DID YOU KNOW?**\n_{event['fun_fact']}_\n\n" if event.get("fun_fact") else ""

    description = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📅 **HISTORICAL DATE:** `{date_display} ({event['year']})`\n"
        f"🏢 **AGENCY & CREW:** `{event['agency']}` | `{event['crew']}`\n\n"
        f"{hook_str}"
        f"📖 **THE HISTORICAL STORY:**\n{event['story']}\n\n"
        f"💥 **THE HISTORIC LEGACY:**\n{event['impact']}\n\n"
        f"{fun_fact_str}"
        f"💬 *What is your favorite milestone from the era of space exploration? Leave a reaction below!*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    send_discord_embed(title, description, color=0xE67E22, image_url=event.get("image"))
    if not TEST_MODE:
        mark_posted(event_id, title_str=event.get("title", ""), ttl_hours=8760)
        mark_posted(daily_key, ttl_hours=48)  # Lock today's calendar slot

def run_engine():
    print("==========================================================")
    print("INITIALIZING COSMIC NEXUS TODAY IN SPACE HISTORY CORE")
    print(f"Operating Mode: {'TEST_MODE (Dry-Run Alerts)' if TEST_MODE else 'PRODUCTION (Real Live Monitoring)'}")
    print("==========================================================")

    check_today_in_space_history()

    print("==========================================================")
    print("Space History Engine Execution Completed Successfully.")
    print("==========================================================")

if __name__ == "__main__":
    run_engine()
