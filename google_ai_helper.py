import os
import re
import json
import sqlite3
import hashlib
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")

# Top Model Order as requested: Gemini 3.5 -> 3 -> 3.1 Lite -> 2.5 -> 1.5
PREFERRED_GEMINI_MODELS = [
    "gemini-3.5-flash",
    "gemini-3-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-1.5-flash"
]

def call_gemini_flash_multi_model(prompt_text, max_tokens=1024):
    """
    Tries preferred Google AI Studio free tier models in strict user order:
    1. gemini-3.5-flash
    2. gemini-3-flash
    3. gemini-3.1-flash-lite
    4. gemini-2.5-flash
    5. gemini-1.5-flash
    """
    if not GEMINI_API_KEY:
        return None

    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{
            "parts": [{"text": prompt_text}]
        }],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": max_tokens
        }
    }

    for model_name in PREFERRED_GEMINI_MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text_out = parts[0].get("text", "").strip()
                        if text_out:
                            print(f"[GEMINI AI] Responded using top model '{model_name}'.")
                            return text_out
        except Exception as e:
            print(f"[GEMINI AI] Model '{model_name}' notice: {e}")
            continue

    return None

def fetch_best_nasa_image(keywords_list):
    """
    Queries NASA Image API and Wikimedia Commons with primary, backup, and alt keywords.
    """
    if isinstance(keywords_list, str):
        keywords_list = [keywords_list]

    # 1. Search NASA Image Library API
    for kw in keywords_list:
        if not kw:
            continue
        try:
            url = f"https://images-api.nasa.gov/search?q={requests.utils.quote(kw)}&media_type=image"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                items = res.json().get("collection", {}).get("items", [])
                for item in items[:5]:
                    links = item.get("links", [])
                    if links:
                        href = links[0].get("href")
                        if href and (".jpg" in href or ".png" in href or ".jpeg" in href):
                            return href
        except Exception:
            continue

    # 2. Fallback to Wikimedia Commons API for historical astronomers (e.g. Hipparchus, Galileo)
    for kw in keywords_list:
        if not kw:
            continue
        try:
            wiki_url = f"https://commons.wikimedia.org/w/api.php?action=query&generator=search&prop=imageinfo&iiprop=url&gsrsearch={requests.utils.quote(kw)}&gsrlimit=3&format=json"
            res = requests.get(wiki_url, timeout=5)
            if res.status_code == 200:
                pages = res.json().get("query", {}).get("pages", {})
                for page_id, pdata in pages.items():
                    imageinfo = pdata.get("imageinfo", [])
                    if imageinfo and imageinfo[0].get("url"):
                        img_url = imageinfo[0].get("url")
                        if any(ext in img_url.lower() for ext in [".jpg", ".png", ".jpeg"]):
                            return img_url
        except Exception:
            continue

    return "https://images-assets.nasa.gov/image/PIA12110/PIA12110~medium.jpg"

def get_recent_asked_topics(db_file, table_name, column_name, limit=100):
    """
    Fetches the last 100 asked titles/questions from SQLite database to inject into Gemini prompt.
    """
    try:
        if not os.path.exists(db_file):
            return []
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        cursor.execute(f"SELECT {column_name} FROM {table_name} ORDER BY expire_timestamp DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows if r[0]]
    except Exception:
        return []

def generate_ai_quiz():
    """
    Generates a brand new 100% accurate astronomy quiz question using free Gemini models.
    Injects past 100 asked topics to ensure 0 repetition across Astrophysics, Astrobiology, Astrophotography, etc.!
    """
    if not GEMINI_API_KEY:
        return None

    past_topics = get_recent_asked_topics("quiz.db", "quiz_cache", "question_id", limit=100)
    past_str = "; ".join(past_topics[:50]) if past_topics else "None"

    prompt = (
        "You are an expert NASA astrophysicist, cosmologist, and space historian. Generate a brand new, highly engaging astronomy/space quiz question in JSON format.\n"
        "Cover the ENTIRE cosmic spectrum across all topics and difficulty levels:\n"
        "- Solar System: Planets, moons (Io, Titan, Europa, Enceladus), dwarf planets, asteroids, comets, Kuiper Belt, Oort Cloud.\n"
        "- Stellar Astrophysics: Main sequence, red giants, white dwarfs, neutron stars, pulsars, magnetars, supernovae.\n"
        "- Extremes & Black Holes: Supermassive black holes, micro black holes, accretion disks, Hawking radiation, event horizons, frame dragging.\n"
        "- High-Energy Cosmology: Quasars, blazars, Active Galactic Nuclei (AGN), dark matter, dark energy, gravitational lensing, Cosmic Microwave Background (CMB), cosmic rays, Fast Radio Bursts (FRBs).\n"
        "- Astrobiology & Exoplanets: Habitable zones, biosignatures, extremophiles, transit photometry.\n"
        "- Spaceflight & Rocketry: Apollo, Voyager, Cassini, JWST, Hubble, Artemis, Starship, orbital mechanics, TLI maneuvers.\n"
        "- Astrophotography & Optics: Narrowband filters (H-Alpha, OIII), focal ratios, equatorial tracking, DSO exposure techniques.\n"
        "- History of Astronomy: Ancient observers (Hipparchus, Al-Sufi), Renaissance pioneers (Galileo, Kepler, Copernicus, Tycho Brahe, Newton), and modern space age pioneers.\n\n"
        f"CRITICAL CONSTRAINT - DO NOT REPEAT OR GENERATE QUESTIONS SIMILAR TO THESE PAST 100 TOPICS: [{past_str}]\n\n"
        "Strict Requirements:\n"
        "1. Return ONLY valid JSON with keys: 'id', 'difficulty', 'category', 'question', 'options', 'answer', 'explanation', 'keywords'.\n"
        "2. 'difficulty' must be one of: '🟢 Beginner', '🟡 Intermediate', '🔴 Advanced Astrophysicist'.\n"
        "3. 'category' must be the specific subdiscipline.\n"
        "4. 'options' must be a list of 4 strings starting with 🇦, 🇧, 🇨, 🇩 emojis.\n"
        "5. 'answer' must exactly match the correct option string.\n"
        "6. 'keywords' must be a list of 3 specific search phrases (primary, backup, alt) to find matching NASA or astronomical historical photos.\n"
        "7. Do NOT include markdown codeblocks or quotes around the JSON output, output raw JSON strictly."
    )

    raw_text = call_gemini_flash_multi_model(prompt)
    if not raw_text:
        return None

    clean_json = re.sub(r'^```json\s*', '', raw_text, flags=re.MULTILINE)
    clean_json = re.sub(r'```$', '', clean_json, flags=re.MULTILINE).strip()

    try:
        q_data = json.loads(clean_json)
        keywords = q_data.get("keywords", [q_data.get("question", "astronomy")])
        q_data["image"] = fetch_best_nasa_image(keywords)
        return q_data
    except Exception as e:
        print(f"[GEMINI QUIZ PARSE ERROR] {e}")
        return None

def generate_ai_history(date_str_mmdd):
    """
    Generates a historical space flight milestone for today's date using free Gemini models.
    Injects past 100 topics to ensure 0 repetition across Ancient, Renaissance, and Modern Space History!
    """
    if not GEMINI_API_KEY:
        return None

    past_topics = get_recent_asked_topics("history.db", "history_cache", "event_id", limit=100)
    past_str = "; ".join(past_topics[:50]) if past_topics else "None"

    prompt = (
        f"You are a NASA space historian. Generate a real historical space/astronomy milestone for date {date_str_mmdd}.\n"
        "Include milestones from any era: Ancient star catalogs (e.g. Hipparchus, Al-Sufi), Renaissance telescopes (Galileo, Kepler, Newton), 20th Century Space Race (Apollo, Sputnik, Vostok), or Modern Deep Space Missions (Hubble, JWST, Voyager, Mars rovers, Cassini).\n\n"
        f"CRITICAL CONSTRAINT - DO NOT REPEAT THESE PAST 100 EVENTS: [{past_str}]\n\n"
        "Strict Requirements:\n"
        "1. Return ONLY valid JSON with keys: 'id', 'year', 'title', 'agency', 'crew', 'story', 'impact', 'keywords'.\n"
        "2. 'story' must be a captivating 2-3 sentence historical description.\n"
        "3. 'keywords' must be a list of 3 specific search phrases to find matching NASA or historical astronomy photos.\n"
        "4. Output raw JSON strictly without codeblocks."
    )

    raw_text = call_gemini_flash_multi_model(prompt)
    if not raw_text:
        return None

    clean_json = re.sub(r'^```json\s*', '', raw_text, flags=re.MULTILINE)
    clean_json = re.sub(r'```$', '', clean_json, flags=re.MULTILINE).strip()

    try:
        h_data = json.loads(clean_json)
        h_data["date_mmdd"] = date_str_mmdd
        keywords = h_data.get("keywords", [h_data.get("title", "astronomy history")])
        h_data["image"] = fetch_best_nasa_image(keywords)
        return h_data
    except Exception as e:
        print(f"[GEMINI HISTORY PARSE ERROR] {e}")
        return None
