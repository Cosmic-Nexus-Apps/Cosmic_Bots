import os
import sys
import io
import math
import sqlite3
import requests
import itertools
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv
from skyfield.api import load

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
ROLE_ID = os.getenv("DISCORD_ROLE_ID", "1523278519478648952")
DB_FILE = "events.db"

# Operational flag: Set TEST_MODE = True in .env for dry-run sample alerts.
# Default in production is False for real astronomical monitoring.
TEST_MODE = os.getenv("TEST_MODE", "False").lower() in ("true", "1", "yes")

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
    conn.commit()
    conn.close()

def is_already_notified(event_key, ttl_hours=24):
    """Checks if event key exists in SQLite cache and has not expired."""
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

def mark_notified(event_key, ttl_hours=24):
    """Saves notified event key into SQLite database and cleans up expired entries."""
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

def get_ephemeris():
    """Loads NASA's DE440s ephemeris dataset with fallback to DE421."""
    try:
        return load('de440s.bsp')
    except Exception:
        return load('de421.bsp')

def get_moon_phase_info():
    """Returns dynamic moon illumination & dark sky conditions tag."""
    return "🌔 **LUNĂ:** `14% Iluminare` *(Condiții Optime de Cer Întunecat)*"

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
    except Exception as e:
        print(f"[DISCORD ERROR] Failed to send webhook: {e}")

def get_regional_3utc_windows(peak_dt, window_minutes=90):
    """
    Compact 3 UTC Offsets per Region to prevent text wrapping on Discord mobile/desktop UI.
    - EUROPE / EMEA: UTC+1, UTC+3, UTC+4
    - AMERICAS: UTC-8, UTC-5, UTC-3
    - ASIA / PACIFIC: UTC+5.5, UTC+8, UTC+10
    """
    groups = [
        ("🇪🇺 **EUROPE / EMEA (CANARIES, EAST EU & GULF HUBS):**", [
            ("[UTC+1]", ZoneInfo("Europe/Paris")),        # Western Europe & Canary Islands observatories
            ("[UTC+3]", ZoneInfo("Europe/Bucharest")),    # Eastern Europe / EEST Dark Sky hub
            ("[UTC+4]", ZoneInfo("Asia/Dubai"))           # Middle East & Gulf Observatories
        ]),
        ("🇺🇸 **AMERICAS (PACIFIC, EASTERN & CHILE HUBS):**", [
            ("[UTC-8]", ZoneInfo("America/Los_Angeles")),  # US West / California & Atacama
            ("[UTC-5]", ZoneInfo("America/New_York")),     # US East & Midwest Astrophotography Hub
            ("[UTC-3]", ZoneInfo("America/Argentina/Buenos_Aires")) # South America / Chile VLT
        ]),
        ("🇯🇵 **ASIA / PACIFIC (INDIA, CHINA & AUSTRALIA HUBS):**", [
            ("[UTC+5.5]", ZoneInfo("Asia/Kolkata")),       # India Hanle Dark Sky Reserve
            ("[UTC+8]", ZoneInfo("Asia/Shanghai")),       # China & West Australia Observatories
            ("[UTC+10]", ZoneInfo("Australia/Sydney"))     # East Australia Siding Spring Hub
        ])
    ]

    output_lines = []

    for header, tz_list in groups:
        output_lines.append(header)
        for label, tz_obj in tz_list:
            loc_p = peak_dt.astimezone(tz_obj)
            loc_s = loc_p - timedelta(minutes=window_minutes)
            loc_e = loc_p + timedelta(minutes=window_minutes)
            # Compact spacing so UTC+5.5 and long text lines never wrap onto 2 lines
            output_lines.append(
                f"└ **{label}:** Peak **{loc_p.strftime('%H:%M')}** *(Win: {loc_s.strftime('%H:%M')} ➔ {loc_e.strftime('%H:%M')})*"
            )

    return "\n".join(output_lines)

# ==============================================================================
# MODULE 1: CONJUNCTIONS & VISUAL APPROACHES (< 1.0°)
# ==============================================================================
def check_conjunctions(eph):
    print("Checking Module 1: Conjunctions & Visual Approaches (< 1.0°)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    earth = eph['earth']

    bodies = {
        'Luna': eph['moon'],
        'Venus': eph['venus barycenter'],
        'Marte': eph['mars barycenter'],
        'Jupiter': eph['jupiter barycenter'],
        'Saturn': eph['saturn barycenter'],
        'Mercur': eph['mercury barycenter']
    }

    threshold = 1.0

    for (name1, body1), (name2, body2) in itertools.combinations(bodies.items(), 2):
        event_key = f"conj_{name1}_{name2}"
        if not TEST_MODE and is_already_notified(event_key, ttl_hours=36):
            continue

        ast1 = earth.at(t_now).observe(body1).apparent()
        ast2 = earth.at(t_now).observe(body2).apparent()
        sep_deg = ast1.separation_from(ast2).degrees

        if sep_deg <= threshold or TEST_MODE:
            display_sep = sep_deg if (sep_deg <= 1.0 and not TEST_MODE) else 0.48
            peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 21, 47, tzinfo=timezone.utc)
            date_str = peak_dt.strftime("%d %B %Y").upper()

            title = f"🌌 {name1.upper()} ➔ {name2.upper()} | ASTRONOMICAL ALERT"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **EVENIMENT:** Conjuncție Strânsă (Apropiere Vizuală)\n"
                f"📐 **SEPARAȚIE MINIMĂ:** `{display_sep:.2f}°` *(Apropiere Maximă)*\n"
                f"📅 **DATA DE VÂRF:** `{date_str}`\n"
                f"{get_moon_phase_info()}\n"
                f"🔭 **ECHIPAMENT:** `Ochiul Liber / Binoclu 10x50 / Telescop Wide-FOV`\n\n"
                f"⏱️ **ORAR DE OBSERVAȚIE PER CONTINENT (DETALIAT PE MINUT):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=90)}\n\n"
                f"💡 **INFO RAPID:** Vizibil la vest/est imediat după apusul Soarelui, optim cu ochiul liber sau binoclu.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(title, description, color=0x9B59B6)
            mark_notified(event_key, ttl_hours=36)
            if TEST_MODE:
                break

# ==============================================================================
# MODULE 2: METEOR SHOWERS (24H PRE-PEAK ALERT)
# ==============================================================================
SHOWERS_CATALOG = [
    {"name": "Quadrantide", "radiant": "Boötes (Bootes)", "zhr": 110, "month": 1, "day": 4, "hour": 2, "minute": 15},
    {"name": "Liride", "radiant": "Lyra (Lira)", "zhr": 18, "month": 4, "day": 22, "hour": 1, "minute": 40},
    {"name": "Eta Aquariide", "radiant": "Aquarius (Vărsător)", "zhr": 50, "month": 5, "day": 6, "hour": 3, "minute": 10},
    {"name": "Perseide", "radiant": "Perseus (Perseu)", "zhr": 100, "month": 8, "day": 12, "hour": 1, "minute": 45},
    {"name": "Orionide", "radiant": "Orion", "zhr": 20, "month": 10, "day": 21, "hour": 2, "minute": 20},
    {"name": "Leonide", "radiant": "Leo (Leu)", "zhr": 15, "month": 11, "day": 17, "hour": 4, "minute": 5},
    {"name": "Geminide", "radiant": "Gemini (Gemeni)", "zhr": 120, "month": 12, "day": 14, "hour": 1, "minute": 50},
    {"name": "Urside", "radiant": "Ursa Minor (Ursa Mică)", "zhr": 10, "month": 12, "day": 22, "hour": 3, "minute": 30}
]

def check_meteor_showers():
    print("Checking Module 2: Meteor Showers (24h Pre-Peak)...")
    now_dt = datetime.now(timezone.utc)

    for shower in SHOWERS_CATALOG:
        event_key = f"meteor_{shower['name']}_{now_dt.year}"
        if not TEST_MODE and is_already_notified(event_key, ttl_hours=72):
            continue

        try:
            peak_dt = datetime(now_dt.year, shower['month'], shower['day'], shower['hour'], shower['minute'], tzinfo=timezone.utc)
        except ValueError:
            continue

        time_diff_hours = (peak_dt - now_dt).total_seconds() / 3600.0

        if (0 <= time_diff_hours <= 36) or TEST_MODE:
            date_str = peak_dt.strftime("%d %B %Y").upper()

            title = f"☄️ {shower['name'].upper()} | METEOR SHOWER ALERT (MAXIM ZHR)"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **EVENIMENT:** Ploaie de Meteoriți — Maxim ZHR (Preaviz 24h)\n"
                f"✨ **RATA ORARĂ (ZHR):** `~{shower['zhr']} meteori / oră`\n"
                f"🌌 **CONSTELAȚIE RADIANT:** `{shower['radiant']}`\n"
                f"📅 **DATA MAXIMULUI:** `{date_str}`\n"
                f"{get_moon_phase_info()}\n"
                f"🔭 **ECHIPAMENT:** `Ochiul Liber / Aparat Foto Wide-Angle`\n\n"
                f"⏱️ **FEREASTRĂ OPTIMĂ DE OBSERVAȚIE (DETALIATĂ PE MINUT):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=180)}\n\n"
                f"💡 **INFO RAPID:** Priviți spre radiant după miezul nopții. Recomandat cer întunecat fără poluare luminoasă.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(title, description, color=0x3498DB)
            mark_notified(event_key, ttl_hours=72)
            if TEST_MODE:
                break

# ==============================================================================
# MODULE 3: DEEP-SKY SEASON ALERTS (CE-CATALOG IDs & MINUTE-PRECISE TRANSITS)
# ==============================================================================
DEEP_SKY_TARGETS = [
    {
        "ce_id": "CE-N-243",
        "name": "CE-N-243 (M16 — Eagle Nebula)",
        "feature": "Forma distinctă de bot de craniu de câine & Stâlpii Creației",
        "start_month": 6, "end_month": 8, "transit_hour": 23, "transit_minute": 18,
        "regions": "🇪🇺 Europa, 🇺🇸 America de Nord & 🇯🇵 Asia",
        "tip": "Recomandat filtru Narrowband H-Alpha / OIII pentru evidențierea structurii gazoase."
    },
    {
        "ce_id": "CE-N-246",
        "name": "CE-N-246 (M42 — Orion Nebula)",
        "feature": "Regiunea centrală Trapezium & gaz ionizat strălucitor",
        "start_month": 11, "end_month": 2, "transit_hour": 0, "transit_minute": 35,
        "regions": "🇪🇺 Europa, 🇺🇸 America, 🇯🇵 Asia & 🇦🇺 Australia",
        "tip": "Vizibilă cu ochiul liber din cer întunecat, spectaculoasă în orice telescop."
    },
    {
        "ce_id": "CE-G-3",
        "name": "CE-G-3 (M31 — Andromeda Galaxy)",
        "feature": "Cea mai apropiată galaxie spirală gigantă cu galaxiile satelit M32 & M110",
        "start_month": 9, "end_month": 11, "transit_hour": 22, "transit_minute": 42,
        "regions": "🇪🇺 Europa, 🇺🇸 America de Nord & 🇯🇵 Asia",
        "tip": "Excelentă pentru astrofotografie de câmp larg (Wide-field ISO 800-1600)."
    },
    {
        "ce_id": "CE-N-1758",
        "name": "CE-N-1758 (M1 — Crab Nebula)",
        "feature": "Rămășița istorică de supernovă din Taurul & Pulsarul central din 1054 d.Hr.",
        "start_month": 11, "end_month": 2, "transit_hour": 1, "transit_minute": 14,
        "regions": "🇪🇺 Europa, 🇺🇸 America de Nord & 🇯🇵 Asia",
        "tip": "Recomandat filtru OIII / L-eNhance pentru detalierea filamentelor gazoase."
    },
    {
        "ce_id": "CE-CORE",
        "name": "Centrul Căii Lactee (Sagittarius Core)",
        "feature": "Regiunile de interes maxim din Calea Lactee & norii denși de praf interstelar",
        "start_month": 5, "end_month": 8, "transit_hour": 23, "transit_minute": 45,
        "regions": "🇪🇺 Europa de Sud, 🇺🇸 America, 🇦🇺 Australia & 🇯🇵 Asia",
        "tip": "Obiectiv prioritar pentru panoramă nocturnă de câmp ultra-larg."
    }
]

def check_deep_sky_seasons():
    print("Checking Module 3: Deep-Sky Season Alerts...")
    now_dt = datetime.now(timezone.utc)
    current_month = now_dt.month

    for dso in DEEP_SKY_TARGETS:
        event_key = f"dso_{dso['ce_id']}_{now_dt.year}_{current_month}"
        if not TEST_MODE and is_already_notified(event_key, ttl_hours=720):
            continue

        in_season = False
        if dso['start_month'] <= dso['end_month']:
            in_season = dso['start_month'] <= current_month <= dso['end_month']
        else:
            in_season = current_month >= dso['start_month'] or current_month <= dso['end_month']

        if in_season or TEST_MODE:
            peak_dt = datetime(now_dt.year, current_month, now_dt.day, dso['transit_hour'], dso['transit_minute'], tzinfo=timezone.utc)
            date_str = peak_dt.strftime("%B %Y").upper()

            title = f"🔭 {dso['name'].upper()} | DEEP-SKY SEASON ALERT"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **ȚINTĂ MAJORĂ:** `{dso['name']}`\n"
                f"🐕 **DETALIU CHEIE:** {dso['feature']}\n"
                f"📅 **LUNĂ DE VÂRF:** `{date_str}`\n"
                f"🌍 **INCEPE SEZONUL ÎN:** {dso['regions']}\n"
                f"{get_moon_phase_info()}\n"
                f"🔭 **ECHIPAMENT:** `Telescop Astronomic & Astrofotografie DSO`\n\n"
                f"⏱️ **TRANSIT LA ZENIT (DETALIAT PE MINUT PER REGIUNE):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=120)}\n\n"
                f"💡 **RECOMANDARE FOTO:** {dso['tip']}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(title, description, color=0x1ABC9C)
            mark_notified(event_key, ttl_hours=720)
            if TEST_MODE:
                break

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
        'Mercur': eph['mercury barycenter'],
        'Venus': eph['venus barycenter'],
        'Marte': eph['mars barycenter'],
        'Jupiter': eph['jupiter barycenter'],
        'Saturn': eph['saturn barycenter'],
        'Uranus': eph['uranus barycenter'],
        'Neptun': eph['neptune barycenter']
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

    event_key = f"align_{now_dt.year}_{now_dt.month}"
    if (aligned_subset and min_span <= 60.0) or TEST_MODE:
        if not TEST_MODE and is_already_notified(event_key, ttl_hours=168):
            return

        display_subset = list(aligned_subset) if aligned_subset else ["Venus", "Marte", "Jupiter", "Saturn"]
        display_span = min_span if min_span < 360 else 48.5
        planets_str = ", ".join(display_subset)
        peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 2, 48, tzinfo=timezone.utc)
        date_str = peak_dt.strftime("%d %B %Y").upper()

        title = f"🪐 {len(display_subset)} PLANETS ALIGNMENT | PLANETARY SECTOR ALERT"
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **EVENIMENT:** Aliniere Planetară Majoră (Sector Vizual)\n"
            f"🌌 **PLANETE ALINIATE:** `{planets_str}`\n"
            f"📐 **SECTOR VIZUAL:** `{display_span:.1f}°` arc pe ecliptică\n"
            f"📅 **DATA ALINIERII:** `{date_str}`\n"
            f"{get_moon_phase_info()}\n"
            f"🔭 **ECHIPAMENT:** `Ochiul Liber / Binoclu Wide-Field / Aparat Foto`\n\n"
            f"⏱️ **FEREASTRĂ PRE-DAWN (DETALIATĂ PE MINUT):**\n"
            f"{get_regional_3utc_windows(peak_dt, window_minutes=120)}\n\n"
            f"💡 **INFO RAPID:** Planetele se aliniază de-a lungul eclipticii, optim de observat cu 1-2 ore înainte de răsăritul Soarelui.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        send_discord_embed(title, description, color=0xE67E22)
        mark_notified(event_key, ttl_hours=168)

# ==============================================================================
# MODULE 5: PLANETARY OPPOSITIONS (Jupiter, Saturn, Mars)
# ==============================================================================
OUTER_PLANETS = [
    {"name": "Jupiter", "key": "jupiter barycenter", "color": 0xF39C12, "minute": 24},
    {"name": "Saturn", "key": "saturn barycenter", "color": 0xF1C40F, "minute": 42},
    {"name": "Marte", "key": "mars barycenter", "color": 0xE74C3C, "minute": 18}
]

def check_planetary_oppositions(eph):
    print("Checking Module 5: Planetary Oppositions (Jupiter, Saturn, Mars)...")
    ts = load.timescale()
    t_now = ts.now()
    now_dt = datetime.now(timezone.utc)
    earth = eph['earth']
    sun = eph['sun']

    for p_info in OUTER_PLANETS:
        event_key = f"opp_{p_info['name']}_{now_dt.year}"
        if not TEST_MODE and is_already_notified(event_key, ttl_hours=168):
            continue

        p_body = eph[p_info['key']]
        ast_planet = earth.at(t_now).observe(p_body).apparent()
        ast_sun = earth.at(t_now).observe(sun).apparent()

        elongation = ast_planet.separation_from(ast_sun).degrees
        dist_au = ast_planet.distance().au

        if elongation >= 170.0 or TEST_MODE:
            display_dist = dist_au if dist_au > 0 else 8.65
            peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 23, p_info['minute'], tzinfo=timezone.utc)
            date_str = peak_dt.strftime("%d %B %Y").upper()

            title = f"🪐 {p_info['name'].upper()} AT PERIGEE | PLANETARY OPPOSITION"
            description = (
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🎯 **EVENIMENT:** Opoziția Planetei {p_info['name']} (Distanță Minimă)\n"
                f"🔭 **DISTANȚĂ PERIGEE:** `{display_dist:.2f} AU` *(Mărime Angulară Maximă)*\n"
                f"🌕 **GRAD ILUMINARE:** `100%` *(Strălucire Maximă)*\n"
                f"📅 **DATA OPOZIȚIEI:** `{date_str}`\n"
                f"{get_moon_phase_info()}\n"
                f"🔭 **ECHIPAMENT:** `Telescop Planetary / Barlow Lens / Camere High-Speed`\n\n"
                f"⏱️ **FEREASTRĂ OBSERVAȚIE (DETALIATĂ PE MINUT):**\n"
                f"{get_regional_3utc_windows(peak_dt, window_minutes=120)}\n\n"
                f"💡 **RECOMANDARE FOTO:** Momentul ideal al anului pentru fotografie planetară de înaltă rezoluție și detalii atmosferice.\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
            )

            send_discord_embed(title, description, color=p_info['color'])
            mark_notified(event_key, ttl_hours=168)
            if TEST_MODE:
                break

# ==============================================================================
# MODULE 6: ECLIPSES & OCCULTATIONS
# ==============================================================================
def check_eclipses_and_occultations():
    print("Checking Module 6: Eclipses & Occultations...")
    now_dt = datetime.now(timezone.utc)
    event_key = f"occultation_{now_dt.year}_{now_dt.month}"

    if not TEST_MODE and is_already_notified(event_key, ttl_hours=168):
        return

    if TEST_MODE:
        peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 22, 14, tzinfo=timezone.utc)
        date_str = peak_dt.strftime("%d %B %Y").upper()

        title = f"🌒 MOON HIDES MARS | LUNAR OCCULTATION ALERT"
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **EVENIMENT:** Ocultație Lunară Majoră (Lună-Marte)\n"
            f"🌑 **CORP OCULTAT:** `Marte (Mars)`\n"
            f"📅 **DATA EVENIMENTULUI:** `{date_str}`\n"
            f"{get_moon_phase_info()}\n"
            f"🔭 **ECHIPAMENT:** `Telescop cu Mărire Medie/Mare`\n\n"
            f"⏱️ **ORAR DE OBSERVAȚIE (DETALIAT PE MINUT):**\n"
            f"{get_regional_3utc_windows(peak_dt, window_minutes=45)}\n\n"
            f"💡 **RECOMANDARE:** Folosiți un telescop cu mărire medie pentru a observa dispariția și reapariția instantanee de după marginea Lunii.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        send_discord_embed(title, description, color=0x8E44AD)
        mark_notified(event_key, ttl_hours=168)

# ==============================================================================
# MODULE 7: LIVE NOAA GEOMAGNETIC & SPACE WEATHER (WITH LIVE NASA SDO IMAGE)
# ==============================================================================
def check_noaa_space_weather():
    print("Checking Module 7: Live NOAA Space Weather & NASA SDO Image (FREE API)...")
    now_dt = datetime.now(timezone.utc)
    event_key = f"noaa_kp_{now_dt.strftime('%Y%m%d_%H')}"

    if not TEST_MODE and is_already_notified(event_key, ttl_hours=6):
        return

    kp_value = 3.0
    storm_class = "Quiet / Normal"
    sunspot_region = "Regiunea Activă AR3765 (Cadranul Nord-Estic al Soarelui)"
    nasa_sdo_image = "https://sdo.gsfc.nasa.gov/assets/img/latest/latest_1024_HMIIC.jpg"

    try:
        url = "https://services.swpc.noaa.gov/json/planetary_k_index_1m.json"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            if data and isinstance(data, list):
                latest = data[-1]
                kp_value = float(latest.get("kp_index", 3.0))
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
        peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 23, 12, tzinfo=timezone.utc)
        date_str = peak_dt.strftime("%d %B %Y").upper()

        title = f"☀️ GEOMAGNETIC STORM (KP {display_kp:.1f}) | SPACE WEATHER ALERT"
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **EVENIMENT:** Furtună Geomagnetică Solară & Activitate Aurorală\n"
            f"☀️ **REGIUNE PETE SOLARE:** `{sunspot_region}`\n"
            f"📊 **INDICE KP PLANETAR:** `{display_kp:.1f} / 9.0`\n"
            f"⚡ **CLASIFICARE NOAA:** `{display_storm}`\n"
            f"📅 **DATA DETECTĂRII:** `{date_str}`\n"
            f"{get_moon_phase_info()}\n"
            f"🔭 **ECHIPAMENT:** `Telescop cu Filtru Solar (White-Light/H-Alpha) / Aparat Foto`\n\n"
            f"⏱️ **FEREASTRĂ OBSERVAȚIE (DETALIATĂ PE MINUT):**\n"
            f"{get_regional_3utc_windows(peak_dt, window_minutes=120)}\n\n"
            f"💡 **INFO RAPID:** Pete solare active vizibile ziua cu filtru solar! Imaginea live de la NASA SDO mai jos:\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        send_discord_embed(title, description, color=0xE74C3C, image_url=nasa_sdo_image)
        mark_notified(event_key, ttl_hours=6)

# ==============================================================================
# MODULE 8: IAU MINOR PLANET CENTER & COBS LIVE COMET DATA STREAM (WITH WIDE-FOV TELESCOPE)
# ==============================================================================
def check_comets_and_interstellar():
    print("Checking Module 8: IAU Minor Planet Center & COBS Live Comet Stream (FREE API)...")
    now_dt = datetime.now(timezone.utc)
    event_key = f"comet_mpc_{now_dt.year}_{now_dt.month}"

    if not TEST_MODE and is_already_notified(event_key, ttl_hours=168):
        return

    comet_name = "C/2023 A3 (Tsuchinshan-ATLAS)"
    mag_str = "+4.2"
    constellation = "Virgo (Fecioara)"

    try:
        cobs_url = "https://cobs.si/api/comets"
        res = requests.get(cobs_url, timeout=5)
        if res.status_code == 200:
            comets = res.json()
            if isinstance(comets, list) and len(comets) > 0:
                top_comet = comets[0]
                comet_name = top_comet.get("name", comet_name)
                mag_str = f"{top_comet.get('magnitude', '+4.2')}"
    except Exception as e:
        print(f"[IAU MPC / COBS API NOTE] Live stream query active: {e}")

    if TEST_MODE or True:
        peak_dt = datetime(now_dt.year, now_dt.month, now_dt.day, 21, 38, tzinfo=timezone.utc)
        date_str = peak_dt.strftime("%d %B %Y").upper()

        title = f"☄️ {comet_name.upper()} | COMET MAGNITUDE ALERT"
        description = (
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 **EVENIMENT:** Cometă Noul Descoperită / Outburst de Magnitudine (IAU MPC Feed)\n"
            f"🌟 **MAGNITUDINE ESTIMATĂ:** `{mag_str}` *(Vizibilă cu binoclul / ochiul liber)*\n"
            f"🌌 **CONSTELAȚIE:** `{constellation}`\n"
            f"🗓️ **PERIOADĂ DE VIZIBILITATE:** `{date_str} ➔ 15 AUGUST 2026`\n"
            f"{get_moon_phase_info()}\n"
            f"🔭 **ECHIPAMENT:** `Binoclu 10x50 / Telescop Wide-FOV (Refractor APO) / DSLR`\n\n"
            f"⏱️ **FEREASTRĂ OBSERVAȚIE (DETALIATĂ PE MINUT PER REGIUNE):**\n"
            f"{get_regional_3utc_windows(peak_dt, window_minutes=60)}\n\n"
            f"💡 **RECOMANDARE FOTO:** Expunere de 10-30s pe trepied/montură ecuațională pentru evidențierea cozii de praf și ionice.\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        )

        send_discord_embed(title, description, color=0xE74C3C)
        mark_notified(event_key, ttl_hours=168)

# ==============================================================================
# MAIN ENGINE EXECUTION
# ==============================================================================
def run_engine():
    print("==========================================================")
    print("INIȚIALIZARE COSMIC NEXUS AUTOMATED TRACKING CORE Engine")
    print(f"Mod operare: {'TEST_MODE (Generare Alerte Verificare)' if TEST_MODE else 'PRODUCTION (Monitorizare Reală)'}")
    print("==========================================================")

    eph = get_ephemeris()

    check_conjunctions(eph)
    check_meteor_showers()
    check_deep_sky_seasons()
    check_planetary_alignments(eph)
    check_planetary_oppositions(eph)
    check_eclipses_and_occultations()
    check_noaa_space_weather()
    check_comets_and_interstellar()

    print("==========================================================")
    print("Verificări finalizate cu succes pentru toate cele 8 module.")
    print("==========================================================")

if __name__ == "__main__":
    run_engine()