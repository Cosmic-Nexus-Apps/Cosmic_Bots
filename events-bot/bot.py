import os
import requests
import itertools
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

def send_astronomical_alert(title, description, fields=None, image_url=None, color=0x4B0082, role_id=None):
    """
    Trimite o alertă structurată pe Discord folosind un design premium minimalist.
    """
    if not WEBHOOK_URL:
        print("Eroare: DISCORD_WEBHOOK_URL nu este configurat în fișierul .env")
        return

    payload = {
        "embeds": [
            {
                "title": title,
                "description": description,
                "color": color,
                "timestamp": datetime.utcnow().isoformat(),
                "footer": {
                    "text": "Cosmic Nexus | Automated Systems"
                }
            }
        ]
    }

    if fields:
        payload["embeds"][0]["fields"] = fields

    if image_url:
        payload["embeds"][0]["image"] = {"url": image_url}

    # Adăugăm ping-ul pentru rol (ex: @Deep Space News)
    if role_id:
        payload["content"] = f"<@&{role_id}>"

    response = requests.post(WEBHOOK_URL, json=payload)
    
    # Corectat la codul HTTP 204 specific pentru Webhooks Discord
    if response.status_code == 204:
        print(f"Alertă trimisă cu succes: {title}")
    else:
        print(f"Eroare la trimiterea alertei: {response.status_code}, {response.text}")

def generate_ai_description(raw_data):
    """
    Folosește modelul Gemini pentru a genera o descriere tehnică, în engleză, 
    pentru un eveniment astronomic.
    """
    model = genai.GenerativeModel('gemini-1.5-flash')
    
    prompt = f"""
    Write a highly professional and technical Discord announcement description in English based on this data: {raw_data}.
    
    RULES:
    - Do NOT use any emojis. Maintain a strictly technical and minimalist tone.
    - Use Markdown formatting (bold text for key parameters, bullet points if necessary).
    - Provide ONLY the final announcement text. No introductory filler words.
    - Limit the text to maximum 3 paragraphs. Focus on observational parameters (e.g., FOV, angular separation, magnitude).
    """
    
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Eroare la generarea textului AI: {e}")
        return "Technical description currently unavailable."

from skyfield.api import load, Topos
from skyfield.almanac import moon_phases

def check_space_weather():
    """
    Interoghează API-ul NOAA pentru a detecta furtuni geomagnetice de clasă G3 sau mai mare.
    """
    url = "https://services.swpc.noaa.gov/products/alerts.json"
    try:
        response = requests.get(url)
        data = response.json()
        
        # Filtrare pentru alerte de tip K-Index major (Furtuni geomagnetice)
        for alert in data:
            if "Geomagnetic Storm Watch" in alert.get("message", ""):
                # Logica de analiză a textului pentru a identifica clasa (G3, G4, G5)
                if any(x in alert["message"] for x in ["G3", "G4", "G5"]):
                    fields = [
                        {"name": "Tip Eveniment", "value": "Furtună Geomagnetică Majoră", "inline": True},
                        {"name": "Impact Latitudini Medii", "value": "Vizibilitate crescută pentru aurore", "inline": True}
                    ]
                    send_astronomical_alert(
                        title="ALERTĂ: Activitate Solară Intensă",
                        description=alert["message"][:500] + "...",
                        fields=fields,
                        color=0x9400D3 # Violet intens pentru evenimente energetice
                    )
                    break
    except Exception as e:
        print(f"Eroare la verificarea vremii spațiale: {e}")

def calculate_lunar_extremes():
    """
    Calculează poziția Lunii pentru a determina momentele de Perigeu (Superlună) și Apogeu.
    """
    ts = load.timescale()
    t = ts.now()
    eph = load('de421.bsp') # Descărcare efemeride NASA JPL
    
    earth = eph['earth']
    moon = eph['moon']
    
    # Calculul distanței curente
    astrometric = earth.at(t).observe(moon)
    distance_km = astrometric.distance().km
    
    # Valori de referință aproximative pentru extreme
    if distance_km < 357000:
        send_astronomical_alert(
            title="EVENIMENT: Perigeu Lunar (Superlună)",
            description=f"Luna se află la distanța minimă față de Pământ: {int(distance_km):,} km. Discul lunar va părea mai mare și mai strălucitor decât în mod uzual.",
            color=0x4B0082
        )
    elif distance_km > 406000:
        send_astronomical_alert(
            title="EVENIMENT: Apogeu Lunar (Minilună)",
            description=f"Luna a atins distanța maximă față de Pământ: {int(distance_km):,} km. Ideal pentru teste de rezoluție și calibrare contrast.",
            color=0x4B0082
        )

def check_conjunctions():
    """
    Verifică distanța angulară dintre corpurile majore și trimite alerte
    dacă separația scade sub 1 grad.
    """
    ts = load.timescale()
    t = ts.now()
    eph = load('de421.bsp')
    earth = eph['earth']
    
    # Definim țintele principale pentru astrofotografie
    bodies = {
        'Luna': eph['moon'],
        'Venus': eph['venus'],
        'Marte': eph['mars'],
        'Jupiter': eph['jupiter barycenter'],
        'Saturn': eph['saturn barycenter']
    }
    
    # Generăm toate perechile posibile (ex: Luna-Venus, Jupiter-Saturn etc.)
    for (name1, body1), (name2, body2) in itertools.combinations(bodies.items(), 2):
        
        # Calculăm poziția aparentă de pe Pământ la momentul curent
        astrometric1 = earth.at(t).observe(body1).apparent()
        astrometric2 = earth.at(t).observe(body2).apparent()
        
        # Obținem distanța angulară (separația) dintre ele
        separation = astrometric1.separation_from(astrometric2)
        
        # Dacă sunt la sub 1 grad distanță, e o conjuncție strânsă
        if separation.degrees < 1.0:
            fields = [
                {"name": "Corp stelar 1", "value": name1, "inline": True},
                {"name": "Corp stelar 2", "value": name2, "inline": True},
                {"name": "Separație Angulară", "value": f"{separation.degrees:.2f}°", "inline": False},
                {"name": "Tip Echipament", "value": "Ideal pentru FOV restrâns (Telescop/Smart Setup)", "inline": False}
            ]
            
            send_astronomical_alert(
                title=f"EVENIMENT: Conjuncție Strânsă {name1} - {name2}",
                description=f"Apropiere vizuală majoră pe cerul nopții. Obiectele se află la o distanță mai mică de 1 grad, putând fi capturate în același cadru.",
                fields=fields,
                color=0x4B0082
            )

if __name__ == "__main__":
    print("Se inițializează sistemul de monitorizare Cosmic Nexus...")
    
    # Mesaj de test temporar (îl vom șterge când tot sistemul e gata)
    send_astronomical_alert(
        title="SISTEM ONLINE: Test de Conexiune Cloud",
        description="Structura GitHub Actions funcționează perfect și comunică securizat cu serverul.",
        color=0x4B0082
    )
    
    check_space_weather()
    calculate_lunar_extremes()
    check_conjunctions() # <-- Am activat modulul nou aici
    
    print("Verificări finalizate.")
