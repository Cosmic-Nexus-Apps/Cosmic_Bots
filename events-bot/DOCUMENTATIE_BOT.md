# 🌌 Cosmic Nexus — Engine-ul Automat de Evenimente Astronomice v1.0

> **Ghid Tehnic & Documentație de Arhitectură pentru Botul de Discord #1 de Evenimente Astronomice Globale.**

---

## 📋 1. Viziune Generala

**Cosmic Nexus Events Engine** este un sistem automatizat dezvoltat în Python, proiectat să calculeze efemeride astronomice de înaltă precizie și să transmită notificări vizuale spectaculoase pe serverul de Discord.

Engine-ul operează **100% automatizat 24/7** prin GitHub Actions, folosind seturi de date profesionale furnizate gratuit de **NASA JPL**, **IAU Minor Planet Center**, **COBS** și **NOAA SWPC**.

---

## 🔭 2. Cele 8 Module Astronomice Implementate

### 1. 🌌 Conjuncții & Apropieri Vizuale (`check_conjunctions`)
* **Ce calculează:** Separația angulară reală dintre corpurile din Sistemul Solar (Lună, Mercur, Venus, Marte, Jupiter, Saturn) folosind efemeridele NASA JPL (`DE440s`).
* **Prag de Alertă:** Separație angulară $\le 1.0^\circ$.
* **Metrici Include:** Unghiul de separație minimă, data de vârf, orarul detaliat pe minut și recomandări optice.

### 2. ☄️ Ploi de Meteoriți cu Preaviz 24h (`check_meteor_showers`)
* **Ce calculează:** Faza de maxim ZHR (Zenithal Hourly Rate) pentru ploile majore anuale (Perseide, Geminide, Quadrantide, Liride, Orionide, Leonide, Eta Aquariide, Urside).
* **Prag de Alertă:** Notificare transmisă cu **exact 24 de ore înainte de faza de maxim**.
* **Metrici Include:** Constelația radiantului, rata estimată de meteori/oră, faza Lunii.

### 3. 🔭 Alerte de Sezon Deep-Sky cu Catalog Personal (`check_deep_sky_seasons`)
* **Ce calculează:** Fereastra optimă de vizibilitate nocturnă și transitul la zenit pentru obiecte majore Deep-Sky.
* **Integrat cu Catalogul Personal (`CE-...`):**
  * `CE-N-243`: **M16 — Eagle Nebula** (*Forma distinctă de bot de craniu de câine & Stâlpii Creației*)
  * `CE-N-246`: **M42 — Orion Nebula** (*Regiunea centrală Trapezium & Gaz Ionizat*)
  * `CE-G-3`: **M31 — Andromeda Galaxy** (*Galaxia Spirală Gigantă cu M32 & M110*)
  * `CE-N-1758`: **M1 — Crab Nebula** (*Rămășița istorică de supernovă din Taurul & Pulsarul din 1054 d.Hr.*)
  * `CE-CORE`: **Centrul Căii Lactee** (*Sagittarius Core & norii denși de praf*)
* **Metrici Include:** Anunțul continentelor în care deschide sezonul, filtre recomandate (H-Alpha / OIII).

### 4. 🪐 Alinieri Planetare Majore (`check_planetary_alignments`)
* **Ce calculează:** Longitudinile ecliptice ale tuturor celor 7 planete principale.
* **Prag de Alertă:** Detectează când **$\ge 4$ planete** sunt strânse într-un arc ecliptic $\le 60^\circ$.
* **Metrici Include:** Lista planetelor aliniate, dimensiunea arcului în grade, orarul pre-dawn.

### 5. 🪐 Opoziții Planetare la Perigeu (`check_planetary_oppositions`)
* **Ce calculează:** Alungirea Soare-Pământ-Planetă ($180^\circ$), distanța minimă în U.A. și iluminarea de 100% pentru planetelor exterioare (**Jupiter, Saturn, Marte**).
* **Metrici Include:** Distanța minimă în AU, iluminarea, recomandări pentru telescoape planetare și camere high-speed.

### 6. 🌒 Eclipse & Ocultații Lunare (`check_eclipses_and_occultations`)
* **Ce calculează:** Contactele și acoperirea discului lunar peste planete și stele strălucitoare (ex: Ocultația Lună-Marte).
* **Metrici Include:** Timpii de dispariție și reapariție pe marginea Lunii.

### 7. ☀️ Furtuni Geomagnetice & Pete Solare LIVE (`check_noaa_space_weather`)
* **Ce calculează:** Indicele Kp planetar în timp real conectat la NOAA SWPC API.
* **Prag de Alertă:** $Kp \ge 5.0$ (Furtună Geomagnetică G1-G3).
* **Metrici & Imagine Live:** Menționează regiunea activă de pete solare (ex: `AR3765`) și include **imaginea HD live a Soarelui de la satelitul NASA SDO (Solar Dynamics Observatory)**.

### 8. ☄️ Comete Noi & Outbursts de Magnitudine (`check_comets_and_interstellar`)
* **Ce calculează:** Telemetria cometei (ex: C/2023 A3), magnitudinea estimată live prin COBS & IAU Minor Planet Center Feed.
* **Metrici Include:** Perioada de vizibilitate (săptămâni), constelația, recomandări pentru telescoape Wide-FOV (Refractoare APO).

---

## 🌐 3. Sistemul Strategic de Fuse Orare (3 UTC-uri per Continent)

Pentru a oferi cea mai precisă informație astrofotografilor din întreaga lume, orarul este împărțit pe **3 regiuni globale**, fiecare conținând **3 fuse orare strategice** alese pe baza marilor observatoare astronomice (Bortle 1) și centrelor cu cea mai mare densitate de astrofotografi:

```text
🇪🇺 EUROPE / EMEA (CANARIES, EAST EU & GULF HUBS):
└ [UTC+1]: Insulele Canare (La Palma) & Europa de Vest
└ [UTC+3]: Europa de Est (România / EEST Dark Sky Hub)
└ [UTC+4]: Orientul Mijlociu & Observatoarele din Golf (UAE/Oman)

🇺🇸 AMERICAS (PACIFIC, EASTERN & CHILE HUBS):
└ [UTC-8]: Coasta de Vest SUA (California, Lick) & Chile (Atacama / ESO Paranal)
└ [UTC-5]: Coasta de Est & Midwest SUA (New York, Texas Dark Sky Parks)
└ [UTC-3]: America de Sud (Argentina, Brazilia, VLT Chile)

🇯🇵 ASIA / PACIFIC (INDIA, CHINA & AUSTRALIA HUBS):
└ [UTC+5.5]: India (Rezervația Astronomică de Cer Întunecat Hanle - Himalaya)
└ [UTC+8]: China (Xinglong Observatory) & Australia de Vest (Perth)
└ [UTC+10]: Australia de Est (Observatorul Siding Spring) & Japonia
```

---

## 🗄️ 4. Arhitectura Tehnică & Baza de Date

* **Bază de Date SQLite (`events.db`):** Stochează istoricul alertelor și previne duplicarea mesajelor, curățând automat înregistrările expirate.
* **NASA JPL DE440s Ephemeris:** Setul de date orbital de ultimă generație descărcat automat de modulul `skyfield`.
* **Rulare Automată 24/7 (GitHub Actions):** Fișierul `.github/workflows/astro_events_cron.yml` rulează botul la fiecare 3 ore direct în cloud.

---

## 💡 5. Ce ar mai fi de îmbunătățit în Viitor? (Roadmap)

Dacă dorești să extinzi botul pe viitor, iată cele 3 direcții principale:

1. **Comenzi Interactive Slash (pe canal privat):**
   * Crearea unui modul cu `discord.ext.commands` pentru răspunsuri la comenzi de tip `/evenimente-azi`, `/comete-live`, `/soare-azi`.
2. **Notificări de Supernove Transient (ZTF / TNS Feed):**
   * Conectarea unui feed pentru stele care explodează în galaxii apropiate.
3. **Mod Producție Live (`TEST_MODE = False`):**
   * Schimbarea flag-ului `TEST_MODE = False` în `bot.py` atunci când dorești ca botul să trimită alerte pe Discord **doar în momentul exact când un eveniment astronomic real are loc în spațiu**.

---

*Ghid creat pentru dezvoltarea și extinderea proiectului Cosmic Nexus.*
