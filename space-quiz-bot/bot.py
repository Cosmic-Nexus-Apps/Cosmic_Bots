import os
import sys
import io
import sqlite3
import requests
import random
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

if sys.stdout and hasattr(sys.stdout, 'buffer'):
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    except Exception:
        pass

load_dotenv()

WEBHOOK_URL = os.getenv("SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK_URL")
ROLE_ID = os.getenv("SPACE_QUIZ_BOT_DISCORD_ROLE_ID") or os.getenv("DISCORD_ROLE_ID")
DB_FILE = "quiz.db"

TEST_MODE = os.getenv("TEST_MODE", "FALSE").upper() == "TRUE"

def init_db():
    """Initializes SQLite database for quiz question tracking to avoid duplicates."""
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

def mark_asked(question_id, ttl_hours=720):
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
# ASTRONOMY & SPACE QUIZ CATALOG
# ==============================================================================
QUIZ_CATALOG = [
    {
        "id": "q_black_hole_event_horizon",
        "category": "Astrophysics & Black Holes",
        "question": "Ce se întâmplă cu timpul pe măsură ce un obiect se apropie de Orizontul Evenimentului al unei găuri negre?",
        "options": [
            "🇦 Timpul trece mult mai rapid pentru obiect",
            "🇧 Timpul pare că încetinește până când obiectul pare înghețat în timp pentru un observator exterior",
            "🇨 Timpul se dă înapoi cu viteza luminii",
            "🇩 Timpul nu este afectat de gravitația găurii negre"
        ],
        "answer": "🇧 Timpul pare că încetinește până când obiectul pare înghețat în timp pentru un observator exterior",
        "explanation": "Datorită dilatării gravitaționale a timpului (Relativitatea Generală a lui Einstein), câmpul gravitațional extrem al unei găuri negre încetinește timpul. Un observator aflat departe va vedea obiectul încetinind la infinit pe orizontul evenimentului.",
        "image": "https://images-assets.nasa.gov/image/PIA23122/PIA23122~medium.jpg"
    },
    {
        "id": "q_coldest_place_universe",
        "category": "Deep Space Extremes",
        "question": "Care este cel mai rece loc natural cunoscut din Universul observabil?",
        "options": [
            "🇦 Polul Sud al planetei Pluto (-230°C)",
            "🇧 Nebula Boomerang (-272°C / 1 Kelvin)",
            "🇨 Centrul Galaxiei Andromeda (-260°C)",
            "🇩 Suprafața lunii Titan (-180°C)"
        ],
        "answer": "🇧 Nebula Boomerang (-272°C / 1 Kelvin)",
        "explanation": "Nebula Boomerang (situată la 5.000 ani lumină în constelația Centaurus) se extinde atât de rapid încât gazul său s-a răcit la doar 1 Kelvin (-272°C), fiind mai rece decât radiția cosmică de fundal a Universului (2.7 Kelvin).",
        "image": "https://images-assets.nasa.gov/image/PIA04215/PIA04215~medium.jpg"
    },
    {
        "id": "q_jwst_orbit_l2",
        "category": "Space Telescopes & Orbits",
        "question": "În ce punct orbital special se află Telescopul Spațial James Webb (JWST)?",
        "options": [
            "🇦 Pe o orbita joasă în jurul Pământului (LEO) la 500 km altitudine",
            "🇧 În Punctul de Lagrange L2 Pământ-Soare (la 1.5 milioane km de Pământ)",
            "🇨 Pe o orbită eliptică în jurul Lunii",
            "🇩 În Punctul L1 dintre Soare și Mercur"
        ],
        "answer": "🇧 În Punctul de Lagrange L2 Pământ-Soare (la 1.5 milioane km de Pământ)",
        "explanation": "Punctul L2 permite telescopului JWST să rămână aliniat cu Pământul în timp ce orbitează Soarele, menținând scutul solar îndreptat permanent spre Soare, Pământ și Lună pentru a-și păstra instrumentele la -233°C.",
        "image": "https://images-assets.nasa.gov/image/carina_nebula/carina_nebula~medium.jpg"
    },
    {
        "id": "q_sun_light_time",
        "category": "Solar System Physics",
        "question": "Cât timp îi ia luminii emise de Soare să ajungă pe Pământ?",
        "options": [
            "🇦 Aproximativ 8 minute și 20 de secunde",
            "🇧 1 secundă (viteza luminii)",
            "🇨 Exact 1 oră",
            "🇩 24 de ore"
        ],
        "answer": "🇦 Aproximativ 8 minute și 20 de secunde",
        "explanation": "Distanța medie dintre Soare și Pământ este de ~149.6 milioane km (1 Unitate Astronomică). Împărțind această distanță la viteza luminii (~300.000 km/s), obținem aproximativ 500 de secunde (8 min 20 sec).",
        "image": "https://images-assets.nasa.gov/image/GSFC_20171208_Archive_e000842/GSFC_20171208_Archive_e000842~medium.jpg"
    },
    {
        "id": "q_highest_volcano_solar_system",
        "category": "Planetary Geology",
        "question": "Care este cel mai înalt vulcan cunoscut din întregul Sistem Solar?",
        "options": [
            "🇦 Mauna Kea pe Pământ (10 km de la bază)",
            "🇧 Olympus Mons pe Marte (21.9 km înălțime)",
            "🇨 Caloris Montes pe Mercur (15 km)",
            "🇩 Maxwell Montes pe Venus (11 km)"
        ],
        "answer": "🇧 Olympus Mons pe Marte (21.9 km înălțime)",
        "explanation": "Olympus Mons este un vulcan gigantic de tip scut pe Marte, având o înălțime de aproape 22 km (de 2.5 ori mai înalt decât Muntele Everest) și o suprafață comparabilă cu întreaga țară a Poloniei.",
        "image": "https://images-assets.nasa.gov/image/PIA02406/PIA02406~medium.jpg"
    }
]

def check_daily_quiz():
    print("Checking Space Quiz Core Engine...")
    now_dt = datetime.now(timezone.utc)
    date_str = now_dt.strftime("%d %B %Y").upper()

    available_questions = [q for q in QUIZ_CATALOG if TEST_MODE or not is_already_asked(q["id"])]
    if not available_questions:
        print("[QUIZ ENGINE NOTE] All questions asked recently. Resetting loop...")
        available_questions = QUIZ_CATALOG

    quiz_item = random.choice(available_questions)
    item_id = quiz_item["id"]

    title = f"🧠 DAILY SPACE QUIZ | {quiz_item['category'].upper()}"
    options_str = "\n".join(quiz_item["options"])

    description = (
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"❓ **ÎNTREBAREA ZILEI DIN SPAȚIU ({date_str}):**\n"
        f"**{quiz_item['question']}**\n\n"
        f"📌 **OPȚIUNI DE RĂSPUNS:**\n"
        f"{options_str}\n\n"
        f"🔒 **RĂSPUNSUL CORECT & EXPLICAȚIA (CLICK SPOILER):**\n"
        f"||**Răspuns Corect:** {quiz_item['answer']}\n\n"
        f"📖 **Explicație Științifică:** {quiz_item['explanation']}||\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

    send_discord_embed(title, description, color=0xF1C40F, image_url=quiz_item.get("image"))
    if not TEST_MODE:
        mark_asked(item_id, ttl_hours=720)

def run_engine():
    print("==========================================================")
    print("INITIALIZING COSMIC NEXUS DAILY SPACE QUIZ CORE")
    print(f"Operating Mode: {'TEST_MODE (Dry-Run Alerts)' if TEST_MODE else 'PRODUCTION (Real Live Monitoring)'}")
    print("==========================================================")

    check_daily_quiz()

    print("==========================================================")
    print("Space Quiz Engine Execution Completed Successfully.")
    print("==========================================================")

if __name__ == "__main__":
    run_engine()
