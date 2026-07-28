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
NASA_API_KEY = os.getenv("NASA_API_KEY", "DEMO_KEY")

# Active Gemini free-tier models (tried in order — fastest first)
PREFERRED_GEMINI_MODELS = [
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.5-flash"
]

def call_gemini_flash_multi_model(prompt_text, max_tokens=2048):
    """
    Tries Google AI Studio free-tier models in order until one succeeds:
    1. gemini-2.0-flash (fastest)
    2. gemini-1.5-flash
    3. gemini-1.5-pro
    4. gemini-2.5-flash
    Returns raw text response or None on failure.
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
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json"
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
                            print(f"[GEMINI AI] Responded using model '{model_name}'.")
                            return text_out
        except Exception as e:
            print(f"[GEMINI AI] Model '{model_name}' notice: {e}")
            continue

    return None

# ==============================================================================
# IMAGE SCORING: Relevance-based selection instead of "first result"
# ==============================================================================

# Words that indicate an irrelevant image (facility photos, portraits, ceremonies)
_IMAGE_NOISE_WORDS = [
    "facility", "ceremony", "portrait", "engineer", "technician", "clean room",
    "cleanroom", "press conference", "award", "building", "installation",
    "auditorium", "screening", "speech", "conference", "center", "laboratory",
    "office", "meeting", "workshop", "celebration", "unveiling", "groundbreaking"
]

def _score_nasa_image(item_data, keywords):
    """
    Scores relevance of a NASA Image API result against the desired keywords.
    Higher score = more relevant to the topic.
    """
    score = 0
    title = item_data.get("title", "").lower()
    desc  = item_data.get("description", "").lower()

    for kw in keywords:
        kw_low = kw.lower()
        if kw_low in title: score += 10   # Title match = highest relevance
        if kw_low in desc:  score += 3    # Description match = bonus

    # Penalize images that are clearly about facilities, people, not space objects
    for noise in _IMAGE_NOISE_WORDS:
        if noise in title: score -= 20
        if noise in desc:  score -= 3

    # Bonus for recent images (more visually striking)
    try:
        year = int(item_data.get("date_created", "1970")[:4])
        if year >= 2022: score += 8
        elif year >= 2020: score += 5
        elif year >= 2015: score += 2
    except Exception:
        pass

    return score

def fetch_best_nasa_image(keywords_list):
    """
    Queries NASA Image API and Wikimedia Commons with primary, backup, and alt keywords.
    Uses relevance scoring to return the most contextually accurate image.
    """
    if isinstance(keywords_list, str):
        keywords_list = [keywords_list]

    # 1. Collect candidates from NASA Image Library API (scored for relevance)
    scored_candidates = []
    for kw in keywords_list:
        if not kw:
            continue
        try:
            url = f"https://images-api.nasa.gov/search?q={requests.utils.quote(kw)}&media_type=image"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                items = res.json().get("collection", {}).get("items", [])
                for item in items[:15]:  # Check top 15 results per keyword
                    data_list = item.get("data", [])
                    links_list = item.get("links", [])
                    if not data_list or not links_list:
                        continue
                    item_data = data_list[0]
                    href = links_list[0].get("href", "")
                    if not href or not any(ext in href for ext in [".jpg", ".png", ".jpeg"]):
                        continue
                    score = _score_nasa_image(item_data, keywords_list)
                    scored_candidates.append((score, href))
        except Exception:
            continue

    # Return highest-scoring NASA image if any have positive score
    if scored_candidates:
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_url = scored_candidates[0]
        if best_score > 0:  # Only use if genuinely relevant
            return best_url

    # 2. Fallback to Wikimedia Commons API for historical subjects (e.g. Hipparchus, Galileo)
    for kw in keywords_list:
        if not kw:
            continue
        try:
            wiki_url = (
                f"https://commons.wikimedia.org/w/api.php"
                f"?action=query&generator=search&prop=imageinfo&iiprop=url"
                f"&gsrsearch={requests.utils.quote(kw + ' space astronomy')}"
                f"&gsrlimit=5&format=json"
            )
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

    # 3. Ultimate fallback — generic deep space image
    return "https://images-assets.nasa.gov/image/PIA12110/PIA12110~medium.jpg"

def get_recent_asked_topics(db_file, table_name, column_name, limit=100):
    """
    Fetches the last N asked titles/questions from SQLite database to inject into Gemini prompt.
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

def make_stable_content_id(prefix, content_str):
    """
    Generates a stable, deterministic ID from content so the same question/event
    always gets the same ID regardless of AI regeneration.
    """
    clean = re.sub(r'\W+', '', content_str.lower())
    return f"{prefix}_{hashlib.md5(clean.encode('utf-8')).hexdigest()[:12]}"

def extract_and_parse_json(raw_text):
    if not raw_text:
        return None
    # Strip markdown block wrappers
    clean = re.sub(r'```(?:json)?\s*', '', raw_text, flags=re.IGNORECASE)
    clean = re.sub(r'```', '', clean).strip()

    # Extract match between first { and last }
    match = re.search(r'(\{.*\})', clean, re.DOTALL)
    if match:
        clean = match.group(1)

    # Clean trailing commas inside lists or objects before parsing
    clean = re.sub(r',\s*([\]}])', r'\1', clean)

    try:
        return json.loads(clean)
    except Exception as e:
        print(f"[JSON PARSE WARNING] standard json.loads failed: {e}")
        try:
            clean_fixed = re.sub(r'(?<!\\)\n', ' ', clean)
            return json.loads(clean_fixed)
        except Exception as e2:
            print(f"[JSON PARSE ERROR] Second attempt failed: {e2}")
            return None

def generate_ai_quiz():
    """
    Generates a brand new 100% accurate astronomy quiz question using free Gemini models.
    Injects past 100 asked topics to ensure 0 repetition across Astrophysics, Astrobiology,
    Astrophotography, etc. Uses stable content-hash IDs to prevent duplicate detection bypass.
    """
    if not GEMINI_API_KEY:
        return None

    past_topics = get_recent_asked_topics("quiz.db", "quiz_cache", "question_id", limit=100)
    past_str = "; ".join(past_topics[:50]) if past_topics else "None"

    prompt = (
        "You are an elite NASA astrophysicist and science communicator creating content for the world's #1 astronomy channel.\n"
        "Generate a brand new, captivating space quiz question in raw JSON format.\n"
        "Cover the ENTIRE cosmic spectrum across all topics and difficulty levels:\n"
        "- Solar System: Planets, moons (Io, Titan, Europa, Enceladus), dwarf planets, asteroids, comets, Kuiper Belt, Oort Cloud.\n"
        "- Stellar Astrophysics: Main sequence, red giants, white dwarfs, neutron stars, pulsars, magnetars, supernovae.\n"
        "- Extremes & Black Holes: Supermassive black holes, accretion disks, Hawking radiation, event horizons, frame dragging.\n"
        "- High-Energy Cosmology: Quasars, dark matter, dark energy, gravitational lensing, CMB, Fast Radio Bursts (FRBs).\n"
        "- Astrobiology & Exoplanets: Habitable zones, biosignatures, extremophiles, transit photometry.\n"
        "- Spaceflight & Rocketry: Apollo, Voyager, Cassini, JWST, Hubble, Artemis, Starship, orbital mechanics.\n\n"
        f"CRITICAL CONSTRAINT - DO NOT REPEAT OR GENERATE QUESTIONS SIMILAR TO THESE PAST TOPICS: [{past_str}]\n\n"
        "Strict Requirements:\n"
        "1. Return ONLY valid JSON with keys: 'difficulty', 'category', 'question', 'options', 'answer', 'explanation', 'fun_fact', 'keywords'.\n"
        "   NOTE: Do NOT include an 'id' field — the system generates a stable ID automatically.\n"
        "2. 'difficulty' must be one of: '🟢 Beginner', '🟡 Intermediate', '🔴 Deep Space Mastermind'.\n"
        "3. 'category' must be the specific subdiscipline.\n"
        "4. 'options' must be a list of 4 strings starting with 🇦, 🇧, 🇨, 🇩 emojis.\n"
        "5. 'answer' must exactly match the correct option string.\n"
        "6. 'explanation' must be a clear, mind-blowing 2-sentence explanation.\n"
        "7. 'fun_fact' must be a captivating 1-sentence bonus curiosity.\n"
        "8. 'keywords' must be a list of 3 search phrases for finding high-resolution NASA photos.\n"
        "9. Output raw JSON strictly without markdown block formatting."
    )

    raw_text = call_gemini_flash_multi_model(prompt)
    q_data = extract_and_parse_json(raw_text)
    if q_data:
        # Generate a stable, deterministic ID from question content (prevents repeat bypass)
        question_text = q_data.get("question", "")
        q_data["id"] = make_stable_content_id("ai_quiz", question_text)
        keywords = q_data.get("keywords", [question_text or "astronomy"])
        q_data["image"] = fetch_best_nasa_image(keywords)
        return q_data
    return None

def generate_ai_history(date_str_mmdd, target_era=None):
    """
    Generates a historical space flight/astronomy milestone for today's date using free Gemini models.
    Supports targeted historical era rotation:
    - 'ancient': Ancient & Classical Astronomy (BCE - 1500s)
    - 'renaissance': Renaissance & Scientific Revolution (1600s - 1800s: Galileo, Kepler, Newton, Herschel)
    - 'space_race': Space Race Golden Era (1950s - 1970s: Apollo, Sputnik, Vostok, Mariner)
    - 'modern': Modern Deep Space & Observatories (1980s - Present: Hubble, JWST, Voyager, Mars rovers)
    Injects past 100 topics to ensure 0 repetition.
    """
    if not GEMINI_API_KEY:
        return None

    past_topics = get_recent_asked_topics("history.db", "history_cache", "event_id", limit=100)
    past_str = "; ".join(past_topics[:50]) if past_topics else "None"

    era_instruction = ""
    if target_era == "ancient":
        era_instruction = "CRITICAL ERA TARGET: The event MUST be from Ancient or Classical Astronomy (BCE to 1500s CE, e.g. Aristarchus, Eratosthenes, Hipparchus, Antikythera, Mayan/Babylonian/Greek star catalogs, Copernicus).\n"
    elif target_era == "renaissance":
        era_instruction = "CRITICAL ERA TARGET: The event MUST be from the Renaissance or Scientific Revolution (1600s to 1800s CE, e.g. Galileo discovering Jupiter's moons, Kepler's laws, Newton's telescope & gravity, Herschel discovering Uranus, predicting Neptune).\n"
    elif target_era == "space_race":
        era_instruction = "CRITICAL ERA TARGET: The event MUST be from the Space Race Golden Era (1950s to 1970s CE, e.g. Sputnik, Yuri Gagarin, Apollo 11, Mariner 4 flyby, Pioneer, Voyager).\n"
    elif target_era == "modern":
        era_instruction = "CRITICAL ERA TARGET: The event MUST be from Modern Deep Space & Observatories (1980s to Present, e.g. Hubble, JWST, Cassini, Mars Curiosity/Perseverance, Artemis).\n"

    prompt = (
        f"You are a master space storyteller and NASA historian. Generate a real historical space/astronomy milestone for date {date_str_mmdd}.\n"
        f"{era_instruction}\n"
        f"CRITICAL CONSTRAINT - DO NOT REPEAT THESE PAST EVENTS: [{past_str}]\n\n"
        "Strict Requirements:\n"
        "1. Return ONLY valid JSON with keys: 'year', 'title', 'agency', 'crew', 'hook', 'story', 'impact', 'fun_fact', 'keywords'.\n"
        "   NOTE: Do NOT include an 'id' field — the system generates a stable ID automatically.\n"
        "2. 'hook' must be an attention-grabbing, dramatic 1-sentence opening line.\n"
        "3. 'story' must be a gripping 2-3 sentence narrative of what actually happened.\n"
        "4. 'impact' must be a 1-sentence explanation of why it changed human history.\n"
        "5. 'fun_fact' must be an intriguing, little-known detail about the event.\n"
        "6. 'keywords' must be a list of 3 specific search phrases for finding historical photos.\n"
        "7. Output raw JSON strictly without codeblocks."
    )

    raw_text = call_gemini_flash_multi_model(prompt)
    h_data = extract_and_parse_json(raw_text)
    if h_data:
        # Generate stable, deterministic ID from title content
        title_text = h_data.get("title", "")
        h_data["id"] = make_stable_content_id(f"ai_hist_{date_str_mmdd}", title_text)
        h_data["date_mmdd"] = date_str_mmdd
        keywords = h_data.get("keywords", [title_text or "astronomy history"])
        h_data["image"] = fetch_best_nasa_image(keywords)
        return h_data
    return None

def select_top_space_news(candidate_articles):
    """
    Given a list of fresh candidate RSS news items published in the last 24 hours,
    asks Gemini AI to grade, rank, and select the single #1 most important, groundbreaking,
    and scientifically significant space news story.
    Returns the selected candidate dictionary or candidate_articles[0] on fallback.
    """
    if not candidate_articles:
        return None
    if len(candidate_articles) == 1 or not GEMINI_API_KEY:
        return candidate_articles[0]

    articles_summary = ""
    for idx, art in enumerate(candidate_articles[:10]):
        articles_summary += f"[{idx}] Source: {art.get('source')}\nTitle: {art.get('title')}\nTeaser: {art.get('summary')[:200]}\n\n"

    prompt = (
        "You are the Chief News Editor for the world's top astronomy broadcast network.\n"
        "Review the following candidate space news articles published in the last 24 hours and select ONLY the single #1 most important, groundbreaking, and scientifically significant space news story.\n"
        "Filter out minor press releases, administrative fluff, or routine non-groundbreaking items.\n\n"
        f"CANDIDATE ARTICLES:\n{articles_summary}\n"
        "Return ONLY valid JSON with keys:\n"
        "- 'selected_index': (integer, 0-based index of the single best article)\n"
        "- 'reason': (1 sentence explanation of why this story was chosen above the others)"
    )

    try:
        raw_text = call_gemini_flash_multi_model(prompt)
        res_data = extract_and_parse_json(raw_text)
        if res_data and "selected_index" in res_data:
            idx = int(res_data["selected_index"])
            if 0 <= idx < len(candidate_articles):
                print(f"[GEMINI NEWS CURATOR] Selected article [{idx}] '{candidate_articles[idx].get('title')}': {res_data.get('reason')}")
                return candidate_articles[idx]
    except Exception as e:
        print(f"[GEMINI NEWS CURATOR NOTE] Fallback to first article: {e}")

    return candidate_articles[0]

def enhance_news_summary(title, source_name, raw_summary):
    """
    Uses Gemini AI to expand short RSS teasers into rich, comprehensive 3-4 sentence summaries.
    Falls back to raw_summary if Gemini is unavailable or fails.
    """
    if not GEMINI_API_KEY:
        return raw_summary

    prompt = (
        f"You are a senior science communicator and astrophysicist writing for an elite astronomy news channel.\n"
        f"Rewrite and expand the following short RSS news teaser into a rich, captivating, highly informative, and scientifically precise summary of 3 to 4 sentences.\n"
        f"Explain what this event or discovery is, why it matters, and key scientific context.\n\n"
        f"Article Title: {title}\n"
        f"News Source: {source_name}\n"
        f"Original Teaser: {raw_summary}\n\n"
        f"Requirements:\n"
        f"1. Return ONLY the plain text summary (no markdown code blocks, no JSON, no headline repetition).\n"
        f"2. Make it sound exciting, professional, and full of context.\n"
        f"3. Keep length between 300 and 800 characters."
    )

    try:
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1024}
        }
        for model_name in PREFERRED_GEMINI_MODELS:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={GEMINI_API_KEY}"
            res = requests.post(url, json=payload, headers=headers, timeout=8)
            if res.status_code == 200:
                candidates = res.json().get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text_out = parts[0].get("text", "").strip()
                        if text_out and len(text_out) > 50:
                            clean_out = re.sub(r'^```[\w]*\n?', '', text_out)
                            clean_out = re.sub(r'\n?```$', '', clean_out).strip(' "')
                            return clean_out
    except Exception as e:
        print(f"[AI NEWS SUMMARY WARNING] {e}")

    return raw_summary

