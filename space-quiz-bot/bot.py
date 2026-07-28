import os
import sys
import io
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

WEBHOOK_URL = os.getenv("SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
ROLE_ID = os.getenv("SPACE_QUIZ_BOT_DISCORD_ROLE_ID") or os.getenv("DISCORD_ROLE_ID")
DB_FILE = "quiz.db"

TEST_MODE = os.getenv("TEST_MODE", "FALSE").upper() == "TRUE"

def init_db():
    """Initializes SQLite database for quiz question tracking with 1-year anti-repeat retention."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quiz_cache (
            question_id TEXT PRIMARY KEY,
            expire_timestamp REAL
        )
    """)
    conn.commit()
    conn.close()

def is_already_asked(question_id):
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()

    cursor.execute("SELECT expire_timestamp FROM quiz_cache WHERE question_id = ?", (question_id,))
    row = cursor.fetchone()
    conn.close()

    if row and row[0] > now_ts:
        return True
    return False

def mark_asked(question_id, ttl_hours=8760): # 8760 hours = 365 Days / 1 Full Year Anti-Repeat
    init_db()
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now_ts = datetime.now(timezone.utc).timestamp()
    expire_ts = now_ts + (ttl_hours * 3600)

    cursor.execute("""
        INSERT OR REPLACE INTO quiz_cache (question_id, expire_timestamp)
        VALUES (?, ?)
    """, (question_id, expire_ts))

    cursor.execute("DELETE FROM quiz_cache WHERE expire_timestamp <= ?", (now_ts,))
    conn.commit()
    conn.close()

    # Sync to shared persistent_history.json (cross-bot dedup layer)
    try:
        import persistent_history
        persistent_history.record_published(question_id, ttl_hours=ttl_hours)
    except Exception:
        pass

def send_discord_embed(title, description, color=0x9B59B6, role_id=ROLE_ID, image_url=None):
    if not WEBHOOK_URL:
        print(f"[DISCORD EMBED - NO WEBHOOK CONFIGURED]\nTitle: {title}\n{description}\n")
        return

    embed_obj = {
        "title": title,
        "description": description,
        "color": color,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "footer": {
            "text": "Cosmic Nexus | Daily Space Quiz & Astronomy Trivia Core"
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
# WORLD-CLASS ASTRONOMY & SPACE QUIZ CATALOG (100% ENGLISH - 1-YEAR NO-REPEAT)
# ==============================================================================
QUIZ_CATALOG = [
    {
        "id": "q_black_hole_time_dilation",
        "category": "Astrophysics & Black Holes",
        "question": "What happens to time for an observer falling toward the Event Horizon of a supermassive black hole as seen by a distant observer?",
        "options": [
            "🇦 Time accelerates exponentially",
            "🇧 Time appears to slow down continuously, appearing frozen at the horizon",
            "🇨 Time reverses at the speed of light",
            "🇩 Time is unaffected by gravitational curvature"
        ],
        "answer": "🇧 Time appears to slow down continuously, appearing frozen at the horizon",
        "explanation": "Due to gravitational time dilation predicted by Einstein's General Relativity, extreme gravitational fields slow down coordinate time. A distant observer sees the falling object asymptotically freeze at the event horizon while redshifting out of view.",
        "image": "https://images-assets.nasa.gov/image/PIA23122/PIA23122~medium.jpg"
    },
    {
        "id": "q_coldest_place_universe",
        "category": "Deep Space Extremes",
        "question": "What is the coldest known natural place in the observable Universe?",
        "options": [
            "🇦 Pluto's South Pole",
            "🇧 The Boomerang Nebula",
            "🇨 Core of the Andromeda Galaxy",
            "🇩 Surface of Saturn's moon Titan"
        ],
        "answer": "🇧 The Boomerang Nebula (-272°C / 1 Kelvin)",
        "explanation": "The Boomerang Nebula (located 5,000 light-years away in Centaurus) is expanding so rapidly that adiabatic expansion cools its gas to just 1 Kelvin (-272°C), making it colder than the Cosmic Microwave Background radiation of the Universe (2.7 K).",
        "image": "https://images-assets.nasa.gov/image/PIA04215/PIA04215~medium.jpg"
    },
    {
        "id": "q_jwst_lagrange_l2",
        "category": "Space Telescopes & Orbits",
        "question": "At which special orbital point is NASA's James Webb Space Telescope (JWST) stationed?",
        "options": [
            "🇦 Low Earth Orbit (LEO)",
            "🇧 Sun-Earth Lagrange Point 2 (L2)",
            "🇨 Highly elliptical Lunar Orbit",
            "🇩 Sun-Mercurian Lagrange Point 1"
        ],
        "answer": "🇧 Sun-Earth Lagrange Point 2 (L2)",
        "explanation": "The L2 point allows JWST to orbit the Sun in synchronization with Earth while keeping its sunshield permanently positioned between the telescope and the Sun/Earth/Moon system, maintaining cryogenic temperatures around -233°C.",
        "image": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e001446/GSFC_20171208_Archive_e001446~medium.jpg"
    },
    {
        "id": "q_sunlight_travel_time",
        "category": "Solar System Physics",
        "question": "Approximately how long does it take for light emitted from the Sun to reach Earth?",
        "options": [
            "🇦 8 minutes and 20 seconds",
            "🇧 1.3 seconds",
            "🇨 Exactly 1 hour",
            "🇩 24 hours"
        ],
        "answer": "🇦 8 minutes and 20 seconds",
        "explanation": "The average distance between the Sun and Earth is ~149.6 million kilometers (1 Astronomical Unit). Dividing this distance by the speed of light (~300,000 km/s) yields roughly 500 seconds, or 8 minutes and 20 seconds.",
        "image": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000842/GSFC_20171208_Archive_e000842~medium.jpg"
    },
    {
        "id": "q_olympus_mons_height",
        "category": "Planetary Geology",
        "question": "What is the tallest volcano and mountain known in the entire Solar System?",
        "options": [
            "🇦 Mauna Kea on Earth",
            "🇧 Olympus Mons on Mars",
            "🇨 Caloris Montes on Mercury",
            "🇩 Maxwell Montes on Venus"
        ],
        "answer": "🇧 Olympus Mons on Mars (21.9 km elevation)",
        "explanation": "Olympus Mons is a massive Martian shield volcano standing roughly 22 kilometers high—nearly 2.5 times Mount Everest's height above sea level—with a footprint roughly the size of Poland.",
        "image": "https://images-assets.nasa.gov/image/PIA02406/PIA02406~medium.jpg"
    },
    {
        "id": "q_neutron_star_density",
        "category": "Stellar Evolution",
        "question": "How heavy would one teaspoon (approx. 5 mL) of neutron star material be on Earth?",
        "options": [
            "🇦 About 100 kilograms",
            "🇧 Roughly 6 billion tons (equivalent to Mount Everest)",
            "🇨 About 10 tons",
            "🇩 500 grams"
        ],
        "answer": "🇧 Roughly 6 billion tons (equivalent to Mount Everest)",
        "explanation": "Neutron stars compress the mass of a star larger than our Sun into a sphere only ~20 km in diameter. Protons and electrons are squeezed into neutrons, resulting in extreme densities exceeding 10^14 g/cm³.",
        "image": "https://images-assets.nasa.gov/image/PIA12110/PIA12110~medium.jpg"
    },
    {
        "id": "q_fastest_spacecraft_parker",
        "category": "Space Exploration Records",
        "question": "What is the fastest human-made object ever launched, reaching speeds over 600,000 km/h?",
        "options": [
            "🇦 Voyager 1 Spacecraft",
            "🇧 Parker Solar Probe",
            "🇨 New Horizons Pluto Probe",
            "🇩 Apollo 10 Command Module"
        ],
        "answer": "🇧 Parker Solar Probe",
        "explanation": "NASA's Parker Solar Probe uses Venus gravity assists to fall deep into the Sun's gravity well, achieving heliocentric speeds exceeding 635,000 km/h (0.05% the speed of light) near perihelion.",
        "image": "https://images-assets.nasa.gov/image/PIA20061/PIA20061~medium.jpg"
    },
    {
        "id": "q_first_exoplanet_discovered",
        "category": "Exoplanets & Alien Worlds",
        "question": "What was the name of the first exoplanet discovered orbiting a main-sequence star (51 Pegasi b)?",
        "options": [
            "🇦 Proxima Centauri b",
            "🇧 Dimidium (51 Pegasi b)",
            "🇨 TRAPPIST-1e",
            "🇩 Kepler-22b"
        ],
        "answer": "🇧 Dimidium (51 Pegasi b)",
        "explanation": "Discovered in 1995 by Michel Mayor and Didier Queloz (who won the 2019 Nobel Prize in Physics), 51 Pegasi b is a 'Hot Jupiter' gas giant orbiting its host star in just 4.2 days.",
        "image": "https://images-assets.nasa.gov/image/PIA19830/PIA19830~medium.jpg"
    },
    {
        "id": "q_most_volcanic_body",
        "category": "Solar System Extremes",
        "question": "Which moon in the Solar System is the most volcanically active body known?",
        "options": [
            "🇦 Europa (Jupiter)",
            "🇧 Io (Jupiter)",
            "🇨 Enceladus (Saturn)",
            "🇩 Titan (Saturn)"
        ],
        "answer": "🇧 Io (Jupiter)",
        "explanation": "Io has over 400 active volcanoes continuously erupting sulfur and silicate lava up to 500 km high, powered by immense tidal heating from Jupiter's gravitational field.",
        "image": "https://images-assets.nasa.gov/image/PIA02308/PIA02308~medium.jpg"
    },
    {
        "id": "q_supernova_type_1a",
        "category": "Cosmology & Dark Energy",
        "question": "Why are Type Ia Supernovae crucial standard candles in measuring cosmic distance?",
        "options": [
            "🇦 They occur exclusively in dwarf galaxies",
            "🇧 They always reach nearly identical peak intrinsic luminosity near the Chandrasekhar limit",
            "🇨 They emit no radio waves",
            "🇩 They last for thousands of years"
        ],
        "answer": "🇧 They always reach nearly identical peak intrinsic luminosity near the Chandrasekhar limit",
        "explanation": "Type Ia supernovae occur when a white dwarf in a binary system accretes matter until reaching ~1.44 solar masses (Chandrasekhar limit), triggering a runaway thermonuclear explosion with a predictable peak brightness.",
        "image": "https://images-assets.nasa.gov/image/PIA13082/PIA13082~medium.jpg"
    },
    {
        "id": "q_fermi_paradox",
        "category": "Astrobiology & SETI",
        "question": "What is the famous question posed by Enrico Fermi regarding extraterrestrial civilizations?",
        "options": [
            "🇦 'How big is the Milky Way?'",
            "🇧 'Where is everybody?'",
            "🇨 'Is light speed absolute?'",
            "🇩 'Why is space cold?'"
        ],
        "answer": "🇧 'Where is everybody?'",
        "explanation": "The Fermi Paradox highlights the apparent contradiction between the high probability of extraterrestrial civilizations existing in our billions-of-years-old galaxy and the complete lack of evidence or contact.",
        "image": "https://images-assets.nasa.gov/image/PIA03606/PIA03606~medium.jpg"
    },
    {
        "id": "q_hawking_radiation",
        "category": "Quantum Astrophysics",
        "question": "What phenomenon predicted by Stephen Hawking causes black holes to slowly lose mass and evaporate?",
        "options": [
            "🇦 Hawking Radiation",
            "🇧 Gravitational Lensing",
            "🇨 Accretion Friction",
            "🇩 Frame Dragging"
        ],
        "answer": "🇦 Hawking Radiation",
        "explanation": "Quantum field effects near the event horizon generate virtual particle pairs. One particle falls in while the other escapes, causing the black hole to radiate thermal energy and gradually evaporate over cosmic timescales.",
        "image": "https://images-assets.nasa.gov/image/PIA16695/PIA16695~medium.jpg"
    },
    {
        "id": "q_hottest_planet_solar_system",
        "category": "Planetary Atmospheres",
        "question": "Which planet is the hottest in the Solar System, despite not being closest to the Sun?",
        "options": [
            "🇦 Mercury",
            "🇧 Venus",
            "🇨 Mars",
            "🇩 Jupiter"
        ],
        "answer": "🇧 Venus (Surface temperature ~465°C)",
        "explanation": "Venus's dense atmosphere of 96.5% Carbon Dioxide creates a runaway greenhouse effect, trapping heat and maintaining surface temperatures hot enough to melt lead (~465°C / 870°F).",
        "image": "https://images-assets.nasa.gov/image/PIA00104/PIA00104~medium.jpg"
    },
    {
        "id": "q_voyager1_golden_record",
        "category": "Interstellar Probes",
        "question": "What famous artifact carried aboard Voyager 1 and 2 contains sounds and images of Earth for alien life?",
        "options": [
            "🇦 The Golden Record",
            "🇧 The Pioneer Plaque",
            "🇨 The Arecibo Message",
            "🇩 The Kepler Disk"
        ],
        "answer": "🇦 The Golden Record",
        "explanation": "The Voyager Golden Records are 12-inch gold-plated copper phonograph discs containing greetings in 55 languages, music, natural sounds, and scientific diagrams curated by Carl Sagan.",
        "image": "https://images-assets.nasa.gov/image/PIA17046/PIA17046~medium.jpg"
    },
    {
        "id": "q_dark_matter_percentage",
        "category": "Cosmology & Universe Composition",
        "question": "Approximately what percentage of the total energy-mass content of the Universe consists of Dark Energy and Dark Matter combined?",
        "options": [
            "🇦 10%",
            "🇧 50%",
            "🇨 Roughly 95%",
            "🇩 25%"
        ],
        "answer": "🇨 Roughly 95% (~68% Dark Energy, ~27% Dark Matter)",
        "explanation": "Ordinary baryonic matter (stars, planets, atoms) accounts for only ~5% of the Universe. Dark Energy makes up ~68% and Dark Matter ~27%, leaving the vast majority of the Universe invisible.",
        "image": "https://images-assets.nasa.gov/image/PIA16873/PIA16873~medium.jpg"
    },
    {
        "id": "q_pulsar_definition",
        "category": "Stellar Remnants",
        "question": "What is a pulsar?",
        "options": [
            "🇦 A rapidly rotating neutron star emitting beams of electromagnetic radiation from its magnetic poles",
            "🇧 A young protostar before nuclear fusion ignites",
            "🇨 A dying red giant pulsing in size",
            "🇩 A binary system of twin black holes"
        ],
        "answer": "🇦 A rapidly rotating neutron star emitting beams of electromagnetic radiation from its magnetic poles",
        "explanation": "Pulsars rotate at high speeds (up to hundreds of times per second), creating a lighthouse-like beam of radiation that sweeps across space and is detected as precise periodic pulses on Earth.",
        "image": "https://images-assets.nasa.gov/image/PIA21421/PIA21421~medium.jpg"
    },
    {
        "id": "q_great_red_spot_storm",
        "category": "Gas Giants",
        "question": "How long has Jupiter's famous Great Red Spot storm been continuously observed?",
        "options": [
            "🇦 About 10 years",
            "🇧 Over 350 years (since at least 1665)",
            "🇨 Exactly 50 years",
            "🇩 1,000 years"
        ],
        "answer": "🇧 Over 350 years (since at least 1665)",
        "explanation": "The Great Red Spot is a persistent anticyclonic storm larger than Earth, first continuously observed with telescopes in the 17th century by Giovanni Cassini and Robert Hooke.",
        "image": "https://images-assets.nasa.gov/image/PIA21980/PIA21980~medium.jpg"
    },
    {
        "id": "q_subsurface_ocean_enceladus",
        "category": "Ocean Worlds",
        "question": "Which moon of Saturn sprays plumes of water vapor and ice grains into space from a global subsurface ocean?",
        "options": [
            "🇦 Mimas",
            "🇧 Enceladus",
            "🇨 Rhea",
            "🇩 Iapetus"
        ],
        "answer": "🇧 Enceladus",
        "explanation": "NASA's Cassini spacecraft flew through Enceladus's south polar geysers, discovering hydrothermal activity, organic molecules, and a subsurface salty liquid ocean beneath its icy crust.",
        "image": "https://images-assets.nasa.gov/image/PIA17184/PIA17184~medium.jpg"
    },
    {
        "id": "q_gravitational_waves_ligo",
        "category": "General Relativity",
        "question": "In 2015, what major breakthrough observation directly confirmed Einstein's 100-year-old prediction of Gravitational Waves?",
        "options": [
            "🇦 LIGO detecting the merger of two binary black holes (GW150914)",
            "🇧 Hubble observing a pulsar glitch",
            "🇨 Voyager crossing the heliopause",
            "🇩 Event Horizon Telescope imaging Sag A*"
        ],
        "answer": "🇦 LIGO detecting the merger of two binary black holes (GW150914)",
        "explanation": "LIGO's laser interferometers detected ripples in spacetime caused by two black holes (36 and 29 solar masses) colliding 1.3 billion light-years away, winning the 2017 Nobel Prize in Physics.",
        "image": "https://images-assets.nasa.gov/image/PIA20027/PIA20027~medium.jpg"
    },
    {
        "id": "q_cosmic_microwave_background",
        "category": "Big Bang Cosmology",
        "question": "What is the Cosmic Microwave Background (CMB)?",
        "options": [
            "🇦 Radiation emitted by microwave ovens in orbit",
            "🇧 Thermal leftover radiation from the Big Bang (~380,000 years after creation)",
            "🇨 Light from the nearest spiral galaxy",
            "🇩 Solar wind particles impacting the ionosphere"
        ],
        "answer": "🇧 Thermal leftover radiation from the Big Bang (~380,000 years after creation)",
        "explanation": "Discovered accidentally by Penzias and Wilson in 1964, the CMB is the oldest light in the Universe, cooled by cosmic expansion to a faint 2.725 Kelvin microwave glow in all directions.",
        "image": "https://images-assets.nasa.gov/image/PIA04221/PIA04221~medium.jpg"
    }
]

def check_daily_quiz():
    print("Checking Space Quiz Core Engine (1-Year Anti-Repeat Mode)...")
    now_dt = datetime.now(timezone.utc)
    today_str = now_dt.strftime("%Y-%m-%d")
    daily_key = f"quiz_daily_{today_str}"

    # Strict Daily Execution Guard: Only 1 post allowed per calendar day
    if not TEST_MODE and is_already_asked(daily_key):
        print(f"[QUIZ GUARD] Already published Daily Space Quiz for today ({today_str}). Skipping.")
        return

    date_str = now_dt.strftime("%d %B %Y").upper()

    quiz_item = None
    try:
        from google_ai_helper import generate_ai_quiz
        ai_quiz = generate_ai_quiz()
        if ai_quiz and not is_already_asked(ai_quiz.get("id", "ai_q")):
            quiz_item = ai_quiz
            print(f"[GEMINI AI] Generated fresh quiz question: '{quiz_item.get('question')}'")
    except Exception as e:
        print(f"[GEMINI QUIZ NOTE] Using catalog fallback: {e}")

    # AI path: use stable content-hash ID (already set by google_ai_helper)
    if not quiz_item:
        available_questions = [q for q in QUIZ_CATALOG if TEST_MODE or not is_already_asked(q["id"])]
        if not available_questions:
            print("[QUIZ ENGINE NOTE] All questions asked within the past 1 year. Resetting catalog loop...")
            available_questions = QUIZ_CATALOG

        quiz_item = random.choice(available_questions)

    item_id = quiz_item.get("id", f"quiz_{now_dt.strftime('%Y%m%d')}")

    diff_badge = quiz_item.get("difficulty", "🟡 Intermediate")
    category_str = quiz_item.get("category", "Astrophysics").upper()
    title = f"🧠 DAILY SPACE QUIZ | {category_str}"
    options_str = "\n".join(quiz_item["options"])
    fun_fact_str = f"💡 **BONUS COSMIC CURIOSITY:**\n_{quiz_item['fun_fact']}_\n\n" if quiz_item.get("fun_fact") else ""

    description = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎯 **DIFFICULTY:** `{diff_badge}`\n\n"
        f"❓ **DAILY SPACE QUESTION ({date_str}):**\n"
        f"**{quiz_item['question']}**\n\n"
        f"📌 **MULTIPLE CHOICE OPTIONS:**\n"
        f"{options_str}\n\n"
        f"👉 *Cast your vote or react below before revealing the answer!*\n\n"
        f"🔒 **SOLUTION & SCIENTIFIC BRIEF (CLICK SPOILERS):**\n"
        f"||**Correct Answer:** {quiz_item['answer']}||\n"
        f"||📖 **Scientific Explanation:** {quiz_item['explanation']}|| \n\n"
        f"{fun_fact_str}"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    send_discord_embed(title, description, color=0xF1C40F, image_url=quiz_item.get("image"))
    if not TEST_MODE:
        mark_asked(item_id, ttl_hours=8760) # 8760 hours = 1 Full Year Anti-Repeat
        mark_asked(daily_key, ttl_hours=48)  # Lock today's calendar slot

def run_engine():
    print("==========================================================")
    print("INITIALIZING COSMIC NEXUS DAILY SPACE QUIZ CORE (ENGLISH)")
    print(f"Operating Mode: {'TEST_MODE (Dry-Run Alerts)' if TEST_MODE else 'PRODUCTION (Real Live Monitoring)'}")
    print("==========================================================")

    check_daily_quiz()

    print("==========================================================")
    print("Space Quiz Engine Execution Completed Successfully.")
    print("==========================================================")

if __name__ == "__main__":
    run_engine()
