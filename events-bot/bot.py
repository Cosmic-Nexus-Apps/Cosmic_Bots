import os
import requests
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

def send_astronomical_alert(title, description, fields=None, image_url=None, color=0x4B0082):
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
                    "text": "Cosmic Nexus | Monitorizare Automatizată"
                }
            }
        ]
    }

    if fields:
        payload["embeds"][0]["fields"] = fields

    if image_url:
        payload["embeds"][0]["image"] = {"url": image_url}

    response = requests.post(WEBHOOK_URL, json=payload)
    
    if response.status_code == 24:
        print(f"Alertă trimisă cu succes: {title}")
    else:
        print(f"Eroare la trimiterea alertei: {response.status_code}, {response.text}")

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

if __name__ == "__main__":
    print("Se inițializează sistemul de monitorizare Cosmic Nexus...")
    
    # Execută verificările
    check_space_weather()
    calculate_lunar_extremes()
    
    print("Verificări finalizate.")  
