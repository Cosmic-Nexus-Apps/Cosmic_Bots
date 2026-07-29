# 🌌 Cosmic Nexus — Documentație Complete Ecosistem Bots Spațiali v2.0

> **Ghid Tehnic, Orar Transmisii și Arhitectură pentru Ecosistemul de Bots Astronomici & Spațiali.**

---

## 📋 1. Prezentare Generală a Ecosistemului

**Cosmic Nexus** este o platformă multi-bot complet automatizată, proiectată să monitorizeze universul, lansările spatiale, vremea spațială NOAA și descoperirile astronomice în timp real, distribuind informații spectaculoase și interactive pe Discord.

Ecosistemul funcționează **24/7** sub un orchestrator master (`main_orchestrator.py`) care rulează la fiecare **5 minute**, executând sarcini în timp real și sarcini programate pe parcursul celor 24 de ore.

---

## ⏰ 2. Orarul Master de Transmisie pe Server (Timetable)

Transmisiile pe server sunt împărțite în două categorii: **Alerte în Timp Real (Polling la 5 minute)** și **Sarcini Programate pe Slotturi Orare**.

### ⚡ Transmisii în Timp Real (Verificare la fiecare 5 minute)
| Modul / Alertă | Sursă Date | Descriere & Prag de Activare |
| :--- | :--- | :--- |
| 🚀 **Lansări de Rachete Live** | Launch Library 2 API | Numărătoare inversă la T-60 min, T-15 min și T-0 pentru lansările de rachete orbitale. |
| ☀️ **Furtuni Geomagnetice LIVE** | NOAA SWPC API | Notificare instantanee la $Kp \ge 5.0$ (Furtuni G1-G5) cu harta live a ovalului auroral. |
| 💥 **Flăcări Solare de Urgență** | NOAA GOES Satellite | Avertizări pentru erupții solare majore din clasa **M** și **X**. |

---

### 📅 Orarul Zilnic Programat (Cele 7 Sloturi Orare)

| Slot Orar | Ora UTC | Ora României (EEST / UTC+3) | Bot / Modul Responsabil | Conținut Transmis |
| :---: | :---: | :---: | :--- | :--- |
| **Slot 1** | **07:00 UTC** | **10:00 EEST** | `astro-events-bot` | 📰 **Știrile Dimineții:** Cea mai importantă știre spațială din ultimele 24h selectată de Gemini AI. |
| **Slot 2** | **09:00 UTC** | **12:00 EEST** | `astro-events-bot` | 🔭 **Evenimente Astronomice:** Conjuncții planetare (Skyfield JPL), Alinieri planetare ($\ge 4$ planete), Comete noi, Ploi de meteoriți & Supernove. |
| **Slot 3** | **12:00 UTC** | **15:00 EEST** | `space-quiz-bot` | 🧠 **Quiz-ul Spațial Zilnic:** Întrebare interactivă de astronomie generată dinamic cu Gemini AI (Fără repetări). |
| **Slot 4** | **14:00 UTC** | **17:00 EEST** | `astro-events-bot` | 📰 **Știrile După-Amiezii:** Știre spațială de top (excluzând știrile deja transmise). |
| **Slot 5** | **16:00 UTC** | **19:00 EEST** | `space-history-bot` | 📜 **A Azi în Istoria Spațiului:** Eveniment istoric major (Misiuni Apollo, Voyager, Hubble, etc.) cu poze arhivă NASA. |
| **Slot 6** | **18:00 UTC** | **21:00 EEST** | `deep-space-bot` | 📸 **Poza Zilei NASA (APOD) & Deep Space:** NASA APOD / JWST / Hubble + Echipajul de pe ISS + Exoplanete noi. *(Vezi mai jos logica de override pentru știri rare)*. |
| **Slot 7** | **20:00 UTC** | **23:00 EEST** | `astro-events-bot` | 📰 **Știrile Serii:** Sinteză cu cele mai noi descoperiri ale zilei. |

---

## 🤖 3. Descrierea Fiecărui Bot din Ecosistem

### 1. 🔭 Astro-Events Bot (`astro-events-bot/bot.py`)
* **Rol Main:** Calcul astronomic de înaltă precizie și agregare de știri spațiale.
* **Ce face:**
  - Calculează orbital separațiile dintre planete/Lună cu biblioteca **Skyfield** și fișierele NASA JPL (`DE440s.bsp`).
  - Trimite alerte de conjuncții ($\le 1.0^\circ$), alinieri planetare ($\ge 4$ planete în $\le 60^\circ$), opoziții planetare și ploi de meteoriți (notificare cu 7 zile și 24h înainte).
  - Prelucrează fluxuri RSS de la NASA, ESA, ESO și Space.com, folosind Gemini AI pentru a selecta și rezuma doar cea mai importantă știre din ultimele 24h.
  - Monitorizează vremea spațială NOAA (indicele Kp pentru aurore).

---

### 2. 🌌 Deep-Space Bot (`deep-space-bot/bot.py`)
* **Rol Main:** Explorarea universului îndepărtat, imagini de telescop și telemetrie spațială în timp real.
* **Ce face:**
  - Prelucrează **NASA APOD** (Astronomy Picture of the Day) și imagini HD din catalogul NASA (JWST, Hubble, Euclid, Chandra).
  - Interoghează API-ul OpenNotify / NASA pentru echipajul uman aflat în spațiu (pe ISS și Tiangong).
  - Caută descoperiri noi de exoplanete în arhiva NASA Exoplanet Archive.
  - Monitorizează countdown-ul pentru lansările rachetelor spațiale globale via Launch Library 2.
  - **Logica "Poza Zilei vs Știre Foarte Importantă":** În mod normal (99% din cazuri), la ora 18:00 UTC trimite **Poza Zilei de la NASA (APOD)**. În cazuri rare când apare o știre spațială de o importanță extraordinară (ex: detectare semnal extraterestru, furtună solară extremă, descoperire istorică JWST), Gemini AI declanșează un override și afișează știrea prioritară în loc de poză!

---

### 3. 🧠 Space-Quiz Bot (`space-quiz-bot/bot.py`)
* **Rol Main:** Gamification și testarea cunoștințelor comunității.
* **Ce face:**
  - Generează zilnic o întrebare de quiz unică, captivantă și 100% precisă folosind Google Gemini AI.
  - Acoperă 6 categorii majore (Sistemul Solar, Astrofizică Stelară, Găuri Negre & Găuri de Vierme, Cosmologie, Astrobiologie & Exoplanete, Istorie & Rachete).
  - Menține în baza de date SQLite (`quiz.db`) ultimele 100+ subiecte întrebate pentru a garanta că nicio întrebare nu se repetă.

---

### 4. 📜 Space-History Bot (`space-history-bot/bot.py`)
* **Rol Main:** Cultura generală istorică și arhivele misiunilor spațiale.
* **Ce face:**
  - Selectează evenimente istorice reale petrecute exact în ziua curentă (Luna.Zi) din explorarea spațiului.
  - Roteste inteligent între 4 ere istorice: *Pionieratul Căștinării Spațiului (1950-1969)*, *Era Navetelor Spațiale (1970-1999)*, *Era Stației Spațiale & Telescoapelor (2000-2015)* și *Era Modernă Commercial & Artemis (2016-Prezent)*.
  - Descarcă automat imagini istorice din arhiva Wikimedia Commons / NASA Image API.

---

## 🛠️ 4. Serviciile de Suport & Arhitectura Tehnică

### ⚙️ Orchestratorul Central (`main_orchestrator.py`)
- Execută toate modulele într-un mod securizat (`run_safe`), asigurându-se că dacă un API extern expiră (timeout), restul ecosistemului continuă să funcționeze fără crash.
- Folosește `scheduler.db` pentru a ține evidența ultimei rulări pentru fiecare modul, prevenind rulările premature.

### 🧠 Modulul Gemini AI (`google_ai_helper.py`)
- Conectat la modelele Google AI Studio (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-1.5-pro`).
- Curăță și rezumă știrile RSS.
- Clasifică urgența știrilor (`check_for_extraordinary_news`) pentru a decide dacă o știre depășește în importanță poza zilei APOD.

### 🗄️ Persistență & Baze de Date SQLite
- `events.db`: Previne trimiterea duplicat a alertelor astronomice.
- `deep_space.db`: Stochează cache-ul pentru lansări, telescoape și exoplanete.
- `history.db`: Cache pentru evenimentele istorice transmise.
- `quiz.db`: Cache pentru întrebările de quiz.
- `scheduler.db`: Orarul de rulare a sarcinilor orchestratorului.
- `published_history.json`: Persistență globală de până la 30-90 zile pentru titluri și chei de evenimente.

---

## 💬 6. Structura Recomandată de Canale & Roluri Discord (100% English Setup)

Pentru a se potrivi perfect cu serverul tău în limba engleză, structura exactă de canale și roluri este:

### 📢 Discord Channels (4 Dedicated Channels)
1. **`#sky-events`** (`EVENTS_BOT_DISCORD_WEBHOOK_URL`)
   - Real-time alerts for conjunctions, meteor showers, planetary alignments, solar storms, and geomagnetic aurora alerts ($Kp \ge 5$).
2. **`#deep-space-news`** (`DEEP_SPACE_BOT_DISCORD_WEBHOOK_URL`)
   - NASA APOD (Astronomy Picture of the Day), JWST/Hubble HD imagery, ISS crew telemetry, rocket launches, and Daily Space News (07:00, 14:00, 20:00 UTC).
3. **`#space-quiz`** (`SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL`)
   - Daily interactive space trivia & astronomy quiz with spoiler solutions (12:00 UTC / 15:00 EEST).
4. **`#space-history`** (`SPACE_HISTORY_BOT_DISCORD_WEBHOOK_URL`)
   - Today in Space History posts covering Apollo, Voyager, Shuttle missions (16:00 UTC / 19:00 EEST).

### 🔔 Discord Server Roles (.env Role IDs)
1. **`Sky Events`** $\rightarrow$ `EVENTS_BOT_DISCORD_ROLE_ID`
2. **`Deep Space News`** $\rightarrow$ `DEEP_SPACE_BOT_DISCORD_ROLE_ID`
3. **`Cosmic App Updates`** *(or Space Quiz)* $\rightarrow$ `SPACE_QUIZ_BOT_DISCORD_ROLE_ID`
4. **`Gear & Tech`** *(or Space History)* $\rightarrow$ `SPACE_HISTORY_BOT_DISCORD_ROLE_ID`

---

## 🚀 7. Cum Rulează Ecosistemul în Producție

1. **Rularea prin Cron / GitHub Actions:**
   La fiecare 5 minute, se apelează comanda:
   ```bash
   python main_orchestrator.py
   ```
2. **Gestionarea Webhook-urilor Discord:**
   Fiecare bot citește variabilele din fișierul `.env`:
   - `EVENTS_BOT_DISCORD_WEBHOOK_URL`
   - `DEEP_SPACE_BOT_DISCORD_WEBHOOK_URL`
   - `SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL`
   - `SPACE_HISTORY_BOT_DISCORD_WEBHOOK_URL`

