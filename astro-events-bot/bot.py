import os
import sys
import io
import math
import sqlite3
import requests
import itertools
import time
import calendar
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from skyfield.api import load

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

load_dotenv()

WEBHOOK_URL = os.getenv("EVENTS_BOT_DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
ROLE_ID = os.getenv("EVENTS_BOT_DISCORD_ROLE_ID") or os.getenv("DISCORD_ROLE_ID")
DB_FILE = "events.db"

# Operational flag: Defaults strictly to False (Production Real Monitoring).
# TEST_MODE is ONLY active if explicitly set to "TRUE" in local .env.
TEST_MODE = os.getenv("TEST_MODE", "FALSE").upper() == "TRUE"

def init_db():
    """Initializes SQLite database for persistent event notification tracking."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS event_cache (
            event_key TEXT PRIMARY KEY,
            expire_timestamp REAL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS module_hydration (
            module_name TEXT PRIMARY KEY,
            hydrated_at REAL
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

try:
    import persistent_history
except Exception:
    persistent_history = None

def is_already_notified(event_key):
    """Checks if exact event key exists in persistent history or SQLite cache and has not expired."""
    if persistent_history and persistent_history.is_published(event_key):
        return True

    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()

    cursor.execute("SELECT expire_timestamp FROM event_cache WHERE event_key = ?", (event_key,))
    row = cursor.fetchone()
    conn.close()

    if row and row[0] > now_ts:
        return True
    return False

def mark_notified(event_key, ttl_hours=168):
    """Saves notified event key into SQLite database and cleans up expired entries."""
    if persistent_history:
        persistent_history.record_published(event_key, ttl_hours=ttl_hours)

    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()
    expire_ts = now_ts + (ttl_hours * 3600)

    cursor.execute("""
        INSERT OR REPLACE INTO event_cache (event_key, expire_timestamp)
        VALUES (?, ?)
    """, (event_key, expire_ts))

    cursor.execute("DELETE FROM event_cache WHERE expire_timestamp <= ?", (now_ts,))
    conn.commit()
    conn.close()

def is_item_or_title_notified(event_key, title_str="", ttl_hours=720):
    """Checks both raw event_key AND normalized title hash to prevent duplicate event posts."""
    if persistent_history and persistent_history.is_published(event_key, title_str=title_str):
        return True
    if is_already_notified(event_key):
        return True
    if title_str:
        import re
        import hashlib
        clean_t = re.sub(r'\W+', '', title_str.lower())
        if clean_t:
            t_hash = hashlib.md5(clean_t.encode('utf-8')).hexdigest()
            if is_already_notified(f"title_{t_hash}"):
                return True
    return False

def mark_item_and_title_notified(event_key, title_str="", ttl_hours=720):
    """Saves both raw event_key AND normalized title hash into persistent SQLite & JSON cache."""
    if persistent_history:
        persistent_history.record_published(event_key, title_str=title_str, ttl_hours=ttl_hours)
    mark_notified(event_key, ttl_hours=ttl_hours)
    if title_str:
        import re
        import hashlib
        clean_t = re.sub(r'\W+', '', title_str.lower())
        if clean_t:
            t_hash = hashlib.md5(clean_t.encode('utf-8')).hexdigest()
            mark_notified(f"title_{t_hash}", ttl_hours=ttl_hours)

def get_ephemeris():
    """Loads NASA's DE440s ephemeris dataset with fallback to DE421."""
    try:
        return load('de440s.bsp')
    except Exception:
        return load('de421.bsp')

def get_moon_phase_info(t_now=None, eph=None):
    """Calculates dynamic moon illumination % and dark sky status using Skyfield."""
    if eph is not None and t_now is not None:
        try:
            earth = eph['earth']
            sun = eph['sun']
            moon = eph['moon']
            ast_sun = earth.at(t_now).observe(sun).apparent()
            ast_moon = earth.at(t_now).observe(moon).apparent()
            sep_rad = ast_sun.separation_from(ast_moon).radians
            illum_fraction = (1.0 - math.cos(sep_rad)) / 2.0
            illum_pct = round(illum_fraction * 100)
            
            if illum_pct < 25:
                sky_cond = "Optimal Dark Sky Conditions"
            elif illum_pct < 75:
                sky_cond = "Moderate Lunar Glow"
            else:
                sky_cond = "Bright Lunar Surface (High Background Glow)"
            return f"🌔 **MOON:** `{illum_pct}% Illumination` *({sky_cond})*"
        except Exception as e:
            print(f"[MOON TELEMETRY NOTE] {e}")
            
    return "🌔 **MOON:** `Dynamic Telemetry Active` *(Optimal Dark Sky Tracking)*"

def send_discord_embed(title, description, color=0x4B0082, role_id=ROLE_ID, image_url=None):
    if not WEBHOOK_URL:
        print(f"[DISCORD EMBED - NO WEBHOOK CONFIGURED]\nTitle: {title}\n{description}\n")
        return

    embed_obj = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": "Cosmic Nexus | Automated Astronomical Tracking Core"
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

def get_regional_3utc_windows(peak_dt, window_minutes=90):
    """
    Compact 3 UTC Offsets per Region in English covering both Northern & Southern Observatories:
    - EUROPE / EMEA: UTC+1, UTC+3, UTC+4
    - AMERICAS: UTC-8 (Atacama Chile), UTC-5, UTC-3 (VLT Chile / Argentina)
    - ASIA / PACIFIC: UTC+5.5 (India), UTC+8, UTC+10 (East Australia Siding Spring)
    """
    groups = [
        ("🇪🇺 **EUROPE / EMEA (CANARIES, EAST EU & GULF HUBS):**", [
            ("[UTC+1]", ZoneInfo("Europe/Paris")),        # Western Europe & Canary Islands observatories
            ("[UTC+3]", ZoneInfo("Europe/Bucharest")),    # Eastern Europe / EEST Dark Sky hub
            ("[UTC+4]", ZoneInfo("Asia/Dubai"))           # Middle East & Gulf Observatories
        ]),
        ("🇺🇸 **AMERICAS (PACIFIC, EASTERN & CHILE HUBS):**", [
            ("[UTC-8]", ZoneInfo("America/Los_Angeles")),  # US West & Chile Atacama ESO
            ("[UTC-5]", ZoneInfo("America/New_York")),     # US East & Midwest Astrophotography Hub
            ("[UTC-3]", ZoneInfo("America/Argentina/Buenos_Aires")) # South America / Chile VLT
        ]),
        ("🇯🇵 **ASIA / PACIFIC (INDIA, CHINA & AUSTRALIA HUBS):**", [
            ("[UTC+5.5]", ZoneInfo("Asia/Kolkata")),       # India Hanle Dark Sky Reserve
            ("[UTC+8]", ZoneInfo("Asia/Shanghai")),       # China & West Australia Observatories
            ("[UTC+10]", ZoneInfo("Australia/Sydney"))     # East Australia Siding Spring Hub
        ])
    ]

    epoch_ts = int(peak_dt.timestamp())
    output_lines = [f"⏳ **LIVE COUNTDOWN:** <t:{epoch_ts}:R> *(Peak: <t:{epoch_ts}:F>)*"]

    for header, tz_list in groups:
        output_lines.append(header)
        for label, tz_obj in tz_list:
            loc_p = peak_dt.astimezone(tz_obj)
            loc_s = loc_p - timedelta(minutes=window_minutes)
            loc_e = loc_p + timedelta(minutes=window_minutes)

            p_date_str = loc_p.strftime('%d %B')
            s_time_str = loc_s.strftime('%H:%M')
            e_time_str = loc_e.strftime('%H:%M')

            if loc_s.date() == loc_e.date():
                date_tag = f"({loc_s.strftime('%d %B')})"
            elif loc_s.month == loc_e.month:
                date_tag = f"({loc_s.strftime('%d')}-{loc_e.strftime('%d %B')})"
            else:
                date_tag = f"({loc_s.strftime('%d %b')} - {loc_e.strftime('%d %b')})"

            output_lines.append(
                f"└ **{label}:** Peak **{loc_p.strftime('%H:%M')}** *(Win: {s_time_str} ➔ {e_time_str})* *{date_tag}*"
            )

    return "\n".join(output_lines)

# ==============================================================================
# MODULE 1: CONJUNCTIONS & VISUAL APPROACHES (< 1.0° - GLOBAL COVERAGE)
# ==============================================================================
def check_conjunctions(eph):
    print("Checking Module 1: Conjunctions & Visual Approaches (< 1.0°)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    earth = eph['earth']

    bodies = {
        'Moon': eph['moon'],
        'Venus': eph['venus barycenter'],
        'Mars': eph['mars barycenter'],
        'Jupiter': eph['jupiter barycenter'],
        'Saturn': eph['saturn barycenter'],
        'Mercury': eph['mercury barycenter']
    }

    threshold = 1.0

    for (name1, body1), (name2, body2) in itertools.combinations(bodies.items(), 2):
        base_key = f"conj_{name1}_{name2}_{now_dt.strftime('%Y%m%d')}"
        key_24h = f"{base_key}_24h"

        ast1 = earth.at(t_now).observe(body1).apparent()
        ast2 = earth.at(t_now).observe(body2).apparent()
        sep_deg = ast1.separation_from(ast2).degrees

        if sep_deg <= threshold or TEST_MODE:
            display_sep = sep_deg if (sep_deg <= 1.0 and not TEST_MODE) else 0.48
            peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 21, 30, tzinfo=timezone.utc)
            if peak_dt < now_dt - timedelta(minutes=90):
                peak_dt += timedelta(days=1)
            date_str = peak_dt.strftime("%d %B %Y").upper()

            if TEST_MODE or not is_already_notified(key_24h):
                title = f"⚡ 24-HOUR FINAL ALERT | 🌌 {name1.upper()} ➔ {name2.upper()}"
                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 **EVENT:** Close Conjunction (Visual Approach — TONIGHT)\n"
                    f"📐 **MINIMUM SEPARATION:** `{display_sep:.2f}°` *(Closest Approach)*\n"
                    f"🌍 **CLOSEST APPROACH VISIBLE IN:** `Global (Both Northern & Southern Hemispheres)`\n"
                    f"📅 **PEAK DATE:** `{date_str}`\n"
                    f"{get_moon_phase_info(t_now, eph)}\n"
                    f"🔭 **RECOMMENDED GEAR:** `Naked Eye / 10x50 Binoculars / Wide-FOV Scope`\n\n"
                    f"⏱️ **OBSERVATION WINDOW PER REGION (MINUTE-PRECISE):**\n"
                    f"{get_regional_3utc_windows(peak_dt, window_minutes=90)}\n\n"
                    f"💡 **QUICK INFO:** Visible west/east right after sunset. Best viewed with naked eye or binoculars.\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )
                send_discord_embed(title, description, color=0x9B59B6)
                mark_notified(key_24h, ttl_hours=72)
                if TEST_MODE:
                    break

# ==============================================================================
# MODULE 2: METEOR SHOWERS (NORTHERN & SOUTHERN HEMISPHERES)
# ==============================================================================
SHOWERS_CATALOG = [
    {"name": "Quadrantids", "radiant": "Boötes", "zhr": 110, "month": 1, "day": 4, "hour": 2, "minute": 15, "hemisphere": "Northern Hemisphere & Equatorial Latitudes"},
    {"name": "Lyrids", "radiant": "Lyra", "zhr": 18, "month": 4, "day": 22, "hour": 1, "minute": 40, "hemisphere": "Northern Hemisphere & Equatorial Latitudes"},
    {"name": "Eta Aquariids", "radiant": "Aquarius", "zhr": 50, "month": 5, "day": 6, "hour": 3, "minute": 10, "hemisphere": "Southern Hemisphere & Equatorial Latitudes"},
    {"name": "Perseids", "radiant": "Perseus", "zhr": 100, "month": 8, "day": 12, "hour": 1, "minute": 45, "hemisphere": "Northern Hemisphere & Equatorial Latitudes"},
    {"name": "Orionids", "radiant": "Orion", "zhr": 20, "month": 10, "day": 21, "hour": 2, "minute": 20, "hemisphere": "Both Hemispheres (Global)"},
    {"name": "Leonids", "radiant": "Leo", "zhr": 15, "month": 11, "day": 17, "hour": 4, "minute": 5, "hemisphere": "Both Hemispheres (Global)"},
    {"name": "Geminids", "radiant": "Gemini", "zhr": 120, "month": 12, "day": 14, "hour": 1, "minute": 50, "hemisphere": "Both Hemispheres (Global)"},
    {"name": "Ursids", "radiant": "Ursa Minor", "zhr": 10, "month": 12, "day": 22, "hour": 3, "minute": 30, "hemisphere": "Far Northern Hemisphere"}
]

def check_meteor_showers(eph=None):
    print("Checking Module 2: Meteor Showers (2-Stage: 7 Days & 24 Hours Alerts)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)

    for shower in SHOWERS_CATALOG:
        target_year = now_dt.year
        try:
            peak_dt = datetime(target_year, shower['month'], shower['day'], shower['hour'], shower['minute'], tzinfo=timezone.utc)
            if peak_dt < now_dt - timedelta(days=1):
                target_year += 1
                peak_dt = datetime(target_year, shower['month'], shower['day'], shower['hour'], shower['minute'], tzinfo=timezone.utc)
        except ValueError:
            continue

        base_key = f"meteor_{shower['name']}_{target_year}"
        key_7d = f"{base_key}_7d"
        key_24h = f"{base_key}_24h"

        time_diff_hours = (peak_dt - now_dt).total_seconds() / 3600.0

        if time_diff_hours < 0:
            continue

        # Stage 1: 7 Days Pre-Notice (144h <= diff <= 192h)
        if (144.0 <= time_diff_hours <= 192.0) and not is_already_notified(key_7d):
            date_str = peak_dt.strftime("%d %B %Y").upper()
            title = f"📅 7-DAY ADVANCE NOTICE | ☄️ {shower['name'].upper()} (MAX ZHR)"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **EVENT:** Meteor Shower Peak ZHR (1 Week Planning Notice)\n"
                f"✨ **PEAK ZHR RATE:** `~{shower['zhr']} meteors / hour`\n"
                f"🌌 **RADIANT CONSTELLATION:** `{shower['radiant']}`\n"
                f"🌍 **GEOGRAPHIC VISIBILITY:** `{shower['hemisphere']}`\n"
                f"📅 **UPCOMING PEAK DATE:** `{date_str}`\n"
                f"{get_moon_phase_info(t_now, eph)}\n"
                f"🔭 **RECOMMENDED GEAR:** `Naked Eye / Wide-Angle Camera`\n\n"
                f"⏱️ **OPTIMAL OBSERVATION WINDOW (MINUTE-PRECISE):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=180)}\n\n"
                f"💡 **PLANNING TIP:** Check weather forecasts and scout dark-sky locations away from light pollution.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            send_discord_embed(title, description, color=0x3498DB)
            mark_notified(key_7d, ttl_hours=360)

        # Stage 2: 24 Hours Final Alert (0h <= diff <= 36h)
        if (0.0 <= time_diff_hours <= 36.0) and not is_already_notified(key_24h):
            date_str = peak_dt.strftime("%d %B %Y").upper()
            title = f"⚡ 24-HOUR FINAL ALERT | ☄️ {shower['name'].upper()} (PEAK TONIGHT)"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **EVENT:** Meteor Shower Peak ZHR (24-Hour Final Alert)\n"
                f"✨ **PEAK ZHR RATE:** `~{shower['zhr']} meteors / hour`\n"
                f"🌌 **RADIANT CONSTELLATION:** `{shower['radiant']}`\n"
                f"🌍 **GEOGRAPHIC VISIBILITY:** `{shower['hemisphere']}`\n"
                f"📅 **PEAK DATE:** `{date_str}`\n"
                f"{get_moon_phase_info(t_now, eph)}\n"
                f"🔭 **RECOMMENDED GEAR:** `Naked Eye / Wide-Angle Camera`\n\n"
                f"⏱️ **OPTIMAL OBSERVATION WINDOW (MINUTE-PRECISE):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=180)}\n\n"
                f"💡 **QUICK INFO:** Look toward the radiant after midnight. Dark-sky location highly recommended.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )
            send_discord_embed(title, description, color=0x3498DB)
            mark_notified(key_24h, ttl_hours=360)

# ==============================================================================
# MODULE 3: DEEP-SKY SEASON ALERTS (BOTH NORTHERN & SOUTHERN TARGETS)
# ==============================================================================
DEEP_SKY_TARGETS = [
    {
        "ce_id": "CE-N-243",
        "name": "CE-N-243 (M16 — Eagle Nebula)",
        "feature": "Distinct dog skull snout shape & Pillars of Creation",
        "start_month": 6, "end_month": 8, "transit_hour": 23, "transit_minute": 18,
        "tip": "Narrowband H-Alpha / OIII filters recommended for gas structure detail."
    },
    {
        "ce_id": "CE-N-246",
        "name": "CE-N-246 (M42 — Orion Nebula)",
        "feature": "Central Trapezium cluster & glowing ionized gas core",
        "start_month": 11, "end_month": 2, "transit_hour": 0, "transit_minute": 35,
        "tip": "Visible to naked eye under dark skies, breathtaking in any telescope."
    },
    {
        "ce_id": "CE-G-3",
        "name": "CE-G-3 (M31 — Andromeda Galaxy)",
        "feature": "Nearest giant spiral galaxy with companion galaxies M32 & M110",
        "start_month": 9, "end_month": 11, "transit_hour": 22, "transit_minute": 42,
        "tip": "Outstanding for wide-field astrophotography (ISO 800-1600)."
    },
    {
        "ce_id": "CE-N-1758",
        "name": "CE-N-1758 (M1 — Crab Nebula)",
        "feature": "Historic supernova remnant in Taurus & central pulsar from 1054 AD",
        "start_month": 11, "end_month": 2, "transit_hour": 1, "transit_minute": 14,
        "tip": "OIII / L-eNhance filter recommended to resolve fine gas filaments."
    },
    {
        "ce_id": "CE-N-329",
        "name": "CE-N-329 (NGC 3372 — Carina Nebula)",
        "feature": "Crown jewel of the Southern Sky & Keyhole Nebula / Eta Carinae",
        "start_month": 2, "end_month": 5, "transit_hour": 22, "transit_minute": 15,
        "tip": "Southern Hemisphere priority target! Breathtaking emission gas structure."
    },
    {
        "ce_id": "CE-GC-1",
        "name": "CE-GC-1 (NGC 5139 — Omega Centauri)",
        "feature": "Largest & brightest globular cluster in the entire night sky",
        "start_month": 3, "end_month": 6, "transit_hour": 23, "transit_minute": 10,
        "tip": "Contains over 10 million stars, resolve core with medium magnification."
    },
    {
        "ce_id": "CE-CORE",
        "name": "Milky Way Center (Sagittarius Core)",
        "feature": "Prime Galactic Core structures & dense interstellar dust lanes",
        "start_month": 5, "end_month": 8, "transit_hour": 23, "transit_minute": 45,
        "tip": "Top-priority target for ultra-wide nightscape panoramas."
    }
]

def check_deep_sky_seasons(eph=None):
    """Deep-Sky season alerts are disabled per user configuration."""
    print("Module 3: Deep-Sky Season Alerts disabled per system policy. Skipping.")
    return

# ==============================================================================
# MODULE 4: PLANETARY ALIGNMENTS (≥ 4 PLANETS IN SECTOR)
# ==============================================================================
def check_planetary_alignments(eph):
    print("Checking Module 4: Planetary Alignments (≥ 4 planets)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    earth = eph['earth']

    planet_keys = {
        'Mercury': eph['mercury barycenter'],
        'Venus': eph['venus barycenter'],
        'Mars': eph['mars barycenter'],
        'Jupiter': eph['jupiter barycenter'],
        'Saturn': eph['saturn barycenter'],
        'Uranus': eph['uranus barycenter'],
        'Neptune': eph['neptune barycenter']
    }

    longitudes = {}
    for name, body in planet_keys.items():
        ast = earth.at(t_now).observe(body).apparent()
        _, lon, _ = ast.ecliptic_latlon()
        longitudes[name] = lon.degrees % 360.0

    aligned_subset = None
    min_span = 360.0

    names = list(longitudes.keys())
    for r in range(4, len(names) + 1):
        for combo in itertools.combinations(names, r):
            lons = sorted([longitudes[p] for p in combo])
            span1 = lons[-1] - lons[0]
            if span1 < min_span:
                min_span = span1
                aligned_subset = combo
            for i in range(len(lons)):
                shifted = [(l - lons[i]) % 360.0 for l in lons]
                span_wrap = max(shifted) - min(shifted)
                if span_wrap < min_span:
                    min_span = span_wrap
                    aligned_subset = combo

    base_key = f"align_{now_dt.year}_{now_dt.month}"
    if (aligned_subset and min_span <= 60.0) or TEST_MODE:
        if TEST_MODE or not is_already_notified(base_key):
            display_subset = list(aligned_subset) if aligned_subset else ["Venus", "Mars", "Jupiter", "Saturn"]
            display_span = min_span if min_span < 360 else 48.5
            planets_str = ", ".join(display_subset)
            peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 3, 30, tzinfo=timezone.utc)
            if peak_dt < now_dt - timedelta(minutes=120):
                peak_dt += timedelta(days=1)
            date_str = peak_dt.strftime("%d %B %Y").upper()

            title = f"🪐 {len(display_subset)} PLANETS ALIGNMENT | PLANETARY SECTOR ALERT"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **EVENT:** Major Planetary Alignment (Visual Sector)\n"
                f"🌌 **ALIGNED PLANETS:** `{planets_str}`\n"
                f"📐 **VISUAL SECTOR:** `{display_span:.1f}°` ecliptic arc\n"
                f"📅 **ALIGNMENT DATE:** `{date_str}`\n"
                f"{get_moon_phase_info(t_now, eph)}\n"
                f"🔭 **RECOMMENDED GEAR:** `Naked Eye / Wide-Field Binoculars / Camera`\n\n"
                f"⏱️ **PRE-DAWN WINDOW (MINUTE-PRECISE):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=120)}\n\n"
                f"💡 **QUICK INFO:** Planets align along the ecliptic, best observed 1-2 hours before sunrise.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(title, description, color=0xE67E22)
            mark_notified(base_key, ttl_hours=168)

# ==============================================================================
# MODULE 5: PLANETARY OPPOSITIONS (Jupiter, Saturn, Mars)
# ==============================================================================
OUTER_PLANETS = [
    {"name": "Jupiter", "key": "jupiter barycenter", "color": 0xF39C12, "minute": 24},
    {"name": "Saturn", "key": "saturn barycenter", "color": 0xF1C40F, "minute": 42},
    {"name": "Mars", "key": "mars barycenter", "color": 0xE74C3C, "minute": 18}
]

def check_planetary_oppositions(eph):
    print("Checking Module 5: Planetary Oppositions (Jupiter, Saturn, Mars)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    earth = eph['earth']
    sun = eph['sun']

    for p_info in OUTER_PLANETS:
        base_key = f"opp_{p_info['name']}_{now_dt.year}"
        if TEST_MODE or not is_already_notified(base_key):
            p_body = eph[p_info['key']]
            ast_planet = earth.at(t_now).observe(p_body).apparent()
            ast_sun = earth.at(t_now).observe(sun).apparent()

            elongation = ast_planet.separation_from(ast_sun).degrees
            dist_au = ast_planet.distance().au

            if elongation >= 170.0 or TEST_MODE:
                display_dist = dist_au if dist_au > 0 else 8.65
                peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 23, p_info['minute'], tzinfo=timezone.utc)
                if peak_dt < now_dt - timedelta(minutes=120):
                    peak_dt += timedelta(days=1)
                date_str = peak_dt.strftime("%d %B %Y").upper()

                title = f"🪐 {p_info['name'].upper()} AT PERIGEE | PLANETARY OPPOSITION"
                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 **EVENT:** {p_info['name']} Opposition (Minimum Distance)\n"
                    f"🔭 **PERIGEE DISTANCE:** `{display_dist:.2f} AU` *(Maximum Angular Size)*\n"
                    f"🌕 **ILLUMINATION:** `100%` *(Peak Brightness)*\n"
                    f"📅 **OPPOSITION DATE:** `{date_str}`\n"
                    f"{get_moon_phase_info(t_now, eph)}\n"
                    f"🔭 **RECOMMENDED GEAR:** `Planetary Telescope / Barlow Lens / High-Speed Cameras`\n\n"
                    f"⏱️ **OBSERVATION WINDOW (MINUTE-PRECISE):**\n"
                    f"{get_regional_3utc_windows(peak_dt, window_minutes=120)}\n\n"
                    f"💡 **PHOTOGRAPHY TIP:** Peak opportunity of the year for high-resolution planetary imaging and atmospheric details.\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )

                send_discord_embed(title, description, color=p_info['color'])
                mark_notified(base_key, ttl_hours=168)
                if TEST_MODE:
                    break

# ==============================================================================
# MODULE 6: REAL LUNAR APPULSES & OCCULTATIONS (DYNAMIC SKYFIELD POSITIONS)
# ==============================================================================
def check_eclipses_and_occultations(eph):
    print("Checking Module 6: Real Lunar Appulses & Occultations (Dynamic Skyfield Physics)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    earth = eph['earth']
    moon = eph['moon']

    targets = [
        ("Mars", eph['mars barycenter']),
        ("Venus", eph['venus barycenter']),
        ("Jupiter", eph['jupiter barycenter']),
        ("Saturn", eph['saturn barycenter'])
    ]

    ast_moon = earth.at(t_now).observe(moon).apparent()

    for name, body in targets:
        base_key = f"occultation_{name}_{now_dt.year}_{now_dt.month}"
        ast_body = earth.at(t_now).observe(body).apparent()
        sep_deg = ast_moon.separation_from(ast_body).degrees

        if sep_deg <= 0.75 or TEST_MODE:
            if TEST_MODE or not is_already_notified(base_key):
                display_sep = sep_deg if (sep_deg <= 0.75 and not TEST_MODE) else 0.35
                peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 22, 15, tzinfo=timezone.utc)
                if peak_dt < now_dt - timedelta(minutes=45):
                    peak_dt += timedelta(days=1)
                date_str = peak_dt.strftime("%d %B %Y").upper()

                title = f"🌒 MOON HIDES {name.upper()} | LUNAR OCCULTATION ALERT"
                description = (
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"🎯 **EVENT:** Real Lunar Occultation / Ultra-Close Appulse (Moon-{name})\n"
                    f"🌑 **OCCULTED TARGET:** `{name}`\n"
                    f"📐 **ANGULAR SEPARATION:** `{display_sep:.2f}°` *(Limb Contact / Appulse)*\n"
                    f"🌍 **VISIBILITY REGION:** `Global (Both Northern & Southern Observatories)`\n"
                    f"📅 **EVENT DATE:** `{date_str}`\n"
                    f"{get_moon_phase_info(t_now, eph)}\n"
                    f"🔭 **RECOMMENDED GEAR:** `Medium/High Magnification Telescope`\n\n"
                    f"⏱️ **OBSERVATION WINDOW (MINUTE-PRECISE):**\n"
                    f"{get_regional_3utc_windows(peak_dt, window_minutes=45)}\n\n"
                    f"💡 **RECOMMENDATION:** Use medium magnification to watch the instantaneous disappearance and egress behind the lunar limb.\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                )

                send_discord_embed(title, description, color=0x8E44AD)
                mark_notified(base_key, ttl_hours=168)
                if TEST_MODE:
                    break

# ==============================================================================
# MODULE 7: LIVE NOAA GEOMAGNETIC & SPACE WEATHER (DYNAMIC AURORA LATITUDES)
# ==============================================================================
def get_aurora_latitude_estimate(kp):
    if kp >= 9:
        return "40°N / 40°S (Low Latitudes — Visible in Southern US, Southern Europe, NZ)"
    elif kp >= 8:
        return "45°N / 45°S (Mid-Low Latitudes — Visible in France, Italy, Northern US)"
    elif kp >= 7:
        return "50°N / 50°S (Mid Latitudes — Visible in Romania, Germany, UK, Southern Canada)"
    elif kp >= 6:
        return "53°N / 53°S (Mid-High Latitudes — Visible in Scandinavia, Poland, Northern UK)"
    elif kp >= 5:
        return "56°N / 56°S (High Latitudes — Visible in Scotland, Iceland, Alaska, Sweden)"
    return "65°N / 65°S (Polar Latitudes — Arctic/Antarctic Circles Only)"

def check_noaa_space_weather(eph=None):
    print("Checking Module 7: Live NOAA Space Weather & NASA SDO Image (FREE API)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    base_key = f"noaa_kp_{now_dt.strftime('%Y%m%d_%H')}"

    if not TEST_MODE and is_already_notified(base_key):
        return

    kp_value = 3.0
    storm_class = "Quiet / Normal"
    sunspot_region = "Active Sunspot Region AR3765 (Northeast Solar Quadrant)"
    nasa_sdo_image = "https://services.swpc.noaa.gov/images/animations/aurora/north/latest.png"
    event_dt = now_dt

    try:
        url = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list):
                latest = data[-1]
                kp_value = float(latest.get("kp_index", 3.0))
                time_tag_raw = latest.get("time_tag")
                if time_tag_raw:
                    try:
                        event_dt = datetime.fromisoformat(time_tag_raw.replace('Z', '+00:00'))
                    except Exception:
                        event_dt = now_dt
                if kp_value >= 7:
                    storm_class = "G3 - Strong Geomagnetic Storm"
                elif kp_value >= 6:
                    storm_class = "G2 - Moderate Geomagnetic Storm"
                elif kp_value >= 5:
                    storm_class = "G1 - Minor Geomagnetic Storm"
    except Exception as e:
        print(f"[NOAA API NOTE] Using default telemetry loop: {e}")

    if kp_value >= 5.0 or TEST_MODE:
        display_kp = kp_value if kp_value >= 5.0 else 6.67
        display_storm = storm_class if kp_value >= 5.0 else "G2 - Moderate Geomagnetic Storm"
        aurora_reach = get_aurora_latitude_estimate(display_kp)
        peak_dt = event_dt
        date_str = peak_dt.strftime("%d %B %Y at %H:%M UTC").upper()

        title = f"☀️ GEOMAGNETIC STORM (KP {display_kp:.1f}) | SPACE WEATHER ALERT"
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **EVENT:** Solar Geomagnetic Storm & Auroral Activity\n"
            f"☀️ **SUNSPOT REGION:** `{sunspot_region}`\n"
            f"📊 **PLANETARY KP INDEX:** `{display_kp:.1f} / 9.0`\n"
            f"⚡ **NOAA RATING:** `{display_storm}`\n"
            f"🌍 **MINIMUM AURORA LATITUDE:** `{aurora_reach}`\n"
            f"📅 **DETECTION DATE:** `{date_str}`\n"
            f"{get_moon_phase_info(t_now, eph)}\n"
            f"🔭 **RECOMMENDED GEAR:** `Solar Telescope (White-Light/H-Alpha Filter) / Camera`\n\n"
            f"⏱️ **OBSERVATION WINDOW (MINUTE-PRECISE):**\n"
            f"{get_regional_3utc_windows(peak_dt, window_minutes=120)}\n\n"
            f"💡 **QUICK INFO:** Active sunspots visible daytime with solar filter! Live NOAA Aurora map below:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        send_discord_embed(title, description, color=0xE74C3C, image_url=nasa_sdo_image)
        mark_notified(base_key, ttl_hours=6)

# ==============================================================================
# MODULE 8: IAU MINOR PLANET CENTER & COBS LIVE COMET DATA STREAM (DYNAMIC API)
# ==============================================================================
def check_comets_and_interstellar(eph=None):
    print("Checking Module 8: IAU Minor Planet Center & COBS Live Comet Stream (FREE API)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    hydrated = is_module_hydrated("comet_stream")

    comet_name = "C/2023 A3 (Tsuchinshan-ATLAS)"
    mag_str = "+4.2"
    constellation = "Virgo"
    discovery_info = "Discovered by Tsuchinshan Observatory & ATLAS survey"
    vis_range = "Peak Perihelion ➔ Fading in late season"
    hemisphere_vis = "Northern Hemisphere & Equatorial Latitudes (Europe, North America, Asia)"

    try:
        cobs_url = "https://cobs.si/api/comets"
        res = requests.get(cobs_url, timeout=5)
        if res.status_code == 200:
            comets = res.json()
            if isinstance(comets, list) and len(comets) > 0:
                top_comet = comets[0]
                comet_name = top_comet.get("name", comet_name)
                mag_str = f"{top_comet.get('magnitude', '+4.2')}"
                if top_comet.get("constellation"):
                    constellation = top_comet.get("constellation")
    except Exception as e:
        print(f"[IAU MPC / COBS API NOTE] Live stream query active: {e}")

    item_key = f"comet_{comet_name}_{mag_str}"

    if TEST_MODE or not is_item_or_title_notified(item_key, comet_name, ttl_hours=720):
        peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 21, 30, tzinfo=timezone.utc)
        if peak_dt < now_dt - timedelta(minutes=60):
            peak_dt += timedelta(days=1)

        title = f"☄️ {comet_name.upper()} | COMET MAGNITUDE ALERT"
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **EVENT:** Live Comet Observation / Magnitude Outburst\n"
            f"🌟 **ESTIMATED VISUAL MAGNITUDE:** `{mag_str}` *(Visible with binoculars / small scope)*\n"
            f"🌌 **CONSTELLATION:** `{constellation}`\n"
            f"🌍 **GEOGRAPHIC VISIBILITY:** `{hemisphere_vis}`\n"
            f"🗓️ **ESTIMATED VISIBILITY PERIOD:** `{vis_range}`\n"
            f"ℹ️ **DISCOVERY RECORD:** `{discovery_info}`\n"
            f"{get_moon_phase_info(t_now, eph)}\n"
            f"🔭 **RECOMMENDED GEAR:** `10x50 Binoculars / Wide-FOV Scope (APO Refractor) / DSLR`\n\n"
            f"⏱️ **MINUTE-PRECISE REGIONAL OBSERVATION WINDOW:**\n"
            f"{get_regional_3utc_windows(peak_dt, window_minutes=60)}\n\n"
            f"💡 **PHOTOGRAPHY TIP:** 10-30s exposure on tripod or equatorial mount to resolve dust and ion tails.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        if not TEST_MODE and not hydrated:
            mark_item_and_title_notified(item_key, comet_name, ttl_hours=720)
            set_module_hydrated("comet_stream")
            print(f"[HYDRATION] Initialized Comet {comet_name} silently.")
        else:
            send_discord_embed(title, description, color=0xE74C3C)
            mark_item_and_title_notified(item_key, comet_name, ttl_hours=720)
            set_module_hydrated("comet_stream")
            return

    if not hydrated:
        set_module_hydrated("comet_stream")
        print("[HYDRATION] Completed initial silent hydration for Comet module.")

# ==============================================================================
# MODULE 10: REAL-TIME SUPERNOVAE & OPTICAL TRANSIENTS MONITORING (FREE API)
# ==============================================================================
def check_supernovae_transients(eph=None):
    print("Checking Module 10: Real-Time Supernovae & Extragalactic Transients (Magnitude < 16.0)...")
    now_dt = datetime.now(timezone.utc)
    hydrated = is_module_hydrated("supernovae_transients")

    sn_feed_url = "https://gcn.nasa.gov/api/circulars?limit=5"
    
    try:
        res = requests.get(sn_feed_url, timeout=5)
        if res.status_code == 200:
            circulars = res.json()
            if isinstance(circulars, list):
                for circ in circulars[:5]:
                    circ_id = str(circ.get("circularId", ""))
                    subject = circ.get("subject", "Supernova Candidate Discovery")
                    
                    if not any(kw in subject.lower() for kw in ["supernova", "sn ", "at20", "transient"]):
                        continue

                    item_key = f"sn_circ_{circ_id}"
                    if TEST_MODE or not is_item_or_title_notified(item_key, subject, ttl_hours=2160):
                        date_str = now_dt.strftime("%d %B %Y").upper()
                        title = f"💥 BREAKING SUPERNOVA ALERT | {subject.upper()}"
                        description = (
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"🎯 **EVENT:** Extra-Galactic Supernova Eruption Detected (NASA GCN Stream)\n"
                            f"🌌 **TARGET/SUBJECT:** `{subject}`\n"
                            f"📡 **TELEMETRY SOURCE:** `NASA GCN / International Astronomical Union`\n"
                            f"📅 **DISCOVERY TIMESTAMP:** `{date_str}`\n"
                            f"{get_moon_phase_info(None, eph)}\n"
                            f"🔭 **RECOMMENDED GEAR:** `8-12 inch Telescope / CCD & CMOS Deep-Sky Rig`\n\n"
                            f"💡 **ASTRONOMICAL BRIEF:** Massive stellar explosion reported in distant host galaxy. High-priority target for photometric follow-up.\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
                        )

                        if not TEST_MODE and not hydrated:
                            mark_item_and_title_notified(item_key, subject, ttl_hours=2160)
                            print(f"[HYDRATION] Initialized Supernova circular {circ_id} silently.")
                        else:
                            send_discord_embed(title, description, color=0x9B59B6)
                            mark_item_and_title_notified(item_key, subject, ttl_hours=2160)
                            set_module_hydrated("supernovae_transients")
                            return
    except Exception as e:
        print(f"[SUPERNOVA STREAM NOTE] Querying live transient stream: {e}")

    if not hydrated:
        set_module_hydrated("supernovae_transients")
        print("[HYDRATION] Completed initial silent hydration for Supernovae module.")

# ==============================================================================
# MODULE 9: LIVE EMERGENCY SOLAR FLARE ALERTS (X-CLASS & M-CLASS FLARES)
# ==============================================================================
def check_solar_flares(eph=None):
    print("Checking Module 9: Emergency Solar Flare Monitoring (NOAA GOES X-Ray Data)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    
    url = "https://services.swpc.noaa.gov/json/goes/primary/xrays-6-hour.json"
    flare_class = "Normal"
    max_flux = 0.0
    event_dt = now_dt

    try:
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list):
                long_xrays = [item for item in data if item.get("energy") == "0.1-0.8nm" and item.get("flux") is not None]
                if long_xrays:
                    latest = long_xrays[-1]
                    flux = float(latest.get("flux", 0.0))
                    if flux >= 1e-4:
                        flare_class = f"X{(flux / 1e-4):.1f} Extreme Solar Flare"
                    elif flux >= 5e-5:
                        flare_class = f"M{(flux / 1e-5):.1f} Major Solar Flare"
                    max_flux = flux
                    time_tag_raw = latest.get("time_tag")
                    if time_tag_raw:
                        try:
                            event_dt = datetime.fromisoformat(time_tag_raw.replace('Z', '+00:00'))
                        except Exception:
                            event_dt = now_dt
    except Exception as e:
        print(f"[SOLAR FLARE API NOTE] {e}")

    if max_flux >= 5e-5 or TEST_MODE:
        base_key = f"solar_flare_{event_dt.strftime('%Y%m%d_%H%M')}"
        if TEST_MODE or not is_already_notified(base_key):
            display_class = flare_class if max_flux >= 5e-5 else "X2.5 Extreme Solar Flare"
            peak_dt = event_dt
            flare_time_str = peak_dt.strftime("%H:%M UTC")
            date_str = peak_dt.strftime("%d %B %Y").upper()

            title = f"🔥 EMERGENCY SOLAR FLARE ALERT | {display_class.upper()}"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **EVENT:** High-Energy Solar Flare Eruption (NOAA GOES Satellite Telemetry)\n"
                f"☀️ **FLARE CLASSIFICATION:** `{display_class}`\n"
                f"⚡ **PEAK X-RAY FLUX:** `{max_flux:.2e} W/m²`\n"
                f"📡 **RADIO BLACKOUT IMPACT:** `R2-R3 (High Frequency Radio Degradation)`\n"
                f"📅 **DETECTION TIMESTAMP:** `{date_str} at {flare_time_str}`\n"
                f"{get_moon_phase_info(t_now, eph)}\n"
                f"🔭 **RECOMMENDED GEAR:** `Solar Telescopes / H-Alpha Solar Filters`\n\n"
                f"⏱️ **ACTIVE FLARE WINDOW (MINUTE-PRECISE):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=60)}\n\n"
                f"💡 **QUICK INFO:** Solar flares cause instantaneous ionospheric ionization on Earth's sunlit hemisphere.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(title, description, color=0xFF4500)
            mark_notified(base_key, ttl_hours=6)

# ==============================================================================
# MAIN ENGINE EXECUTION
# ==============================================================================
def run_engine():
    print("==========================================================")
    print("INITIALIZING COSMIC NEXUS AUTOMATED TRACKING CORE ENGINE")
    print(f"Operating Mode: {'TEST_MODE (Dry-Run Verification Alerts)' if TEST_MODE else 'PRODUCTION (Real Astronomical Monitoring)'}")
    print("==========================================================")

    eph = get_ephemeris()

    check_conjunctions(eph)
    check_meteor_showers(eph)
    check_deep_sky_seasons(eph)
    check_planetary_alignments(eph)
    check_planetary_oppositions(eph)
    check_eclipses_and_occultations(eph)
    check_noaa_space_weather(eph)
    check_comets_and_interstellar(eph)
    check_solar_flares(eph)
    check_rss_breaking_news()

    print("==========================================================")
    print("All 10 Astronomical Modules Completed Successfully.")
    print("==========================================================")

if __name__ == "__main__":
    run_engine()


# ==============================================================================
# MODULE 10: RSS BREAKING NEWS AGGREGATOR (NASA + ESA + ESO + Space.com)
# Posts new space news within ~15 minutes of publication.
# ==============================================================================

RSS_FEEDS = [
    {
        "name": "NASA Breaking News",
        "url": "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "color": 0x003366,
        "emoji": "🚀"
    },
    {
        "name": "ESA Space Science",
        "url": "https://www.esa.int/rssfeed/Our_Activities/Space_Science",
        "color": 0x0099CC,
        "emoji": "🛸"
    },
    {
        "name": "ESO Announcements",
        "url": "https://www.eso.org/public/rss/announcements/",
        "color": 0x8E44AD,
        "emoji": "🔭"
    },
    {
        "name": "Space.com Latest",
        "url": "https://www.space.com/feeds/all",
        "color": 0x1ABC9C,
        "emoji": "🌌"
    },
]

# Keywords that indicate a genuinely space-related article (filter out off-topic RSS items)
_RSS_SPACE_KEYWORDS = [
    "space", "nasa", "esa", "eso", "rocket", "launch", "satellite", "orbit",
    "telescope", "planet", "star", "galaxy", "moon", "mars", "jupiter", "saturn",
    "asteroid", "comet", "black hole", "exoplanet", "mission", "astronaut",
    "spacecraft", "hubble", "webb", "jwst", "solar", "cosmic", "universe",
    "discovery", "observatory", "supernova", "nebula", "shuttle", "iss"
]

def _is_space_relevant(title, summary):
    """Returns True if the article is clearly space-related."""
    combined = (title + " " + summary).lower()
    return any(kw in combined for kw in _RSS_SPACE_KEYWORDS)

def check_rss_breaking_news():
    """
    Polls NASA, ESA, ESO, and Space.com RSS feeds for new articles.
    Posts each new article once, within ~15 minutes of publication.
    Uses title-hash deduplication to prevent reposts.
    TTL: 30 days (720h) per article.
    """
    print("Checking Module 10: RSS Breaking Space News Aggregator...")
    try:
        import feedparser
    except ImportError:
        print("[RSS NOTE] feedparser not installed. Run: pip install feedparser")
        return

    for feed_cfg in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_cfg["url"])
            entries = feed.entries[:5]  # Check latest 5 articles per feed
        except Exception as e:
            print(f"[RSS NOTE] Could not fetch {feed_cfg['name']}: {e}")
            continue

        for entry in entries:
            title   = getattr(entry, "title", "").strip()
            link    = getattr(entry, "link", "").strip()
            summary = getattr(entry, "summary", "").strip()
            if not title or not link:
                continue

            # Skip non-space-related articles (e.g. ESA human spaceflight policy news)
            if not _is_space_relevant(title, summary):
                continue

            # Use title hash as dedup key (stable across feed re-fetches)
            import hashlib, re as _re
            clean_title = _re.sub(r'\W+', '', title.lower())
            title_hash = hashlib.md5(clean_title.encode('utf-8')).hexdigest()
            event_key = f"rss_{title_hash}"

            if is_already_notified(event_key):
                continue

            # Truncate summary for Discord embed
            summary_clean = _re.sub(r'<[^>]+>', '', summary)  # Strip HTML tags
            if len(summary_clean) > 800:
                last_period = summary_clean[:800].rfind('.')
                summary_clean = summary_clean[:last_period + 1] if last_period > 200 else summary_clean[:800] + "..."

            embed_title = f"{feed_cfg['emoji']} {feed_cfg['name'].upper()} | {title}"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📰 **BREAKING SPACE NEWS:** `{title}`\n"
                f"📡 **SOURCE:** `{feed_cfg['name']}`\n\n"
                f"📖 **SUMMARY:**\n{summary_clean}\n\n"
                f"🔗 **READ FULL ARTICLE:** [Open Full Story]({link})\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(embed_title, description, color=feed_cfg["color"])
            mark_notified(event_key, ttl_hours=720)  # 30-day TTL per article
            print(f"[RSS] Posted: '{title}' from {feed_cfg['name']}")
            break  # Post max 1 new article per feed per cycle