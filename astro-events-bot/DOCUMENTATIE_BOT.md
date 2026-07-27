# 🌌 Cosmic Nexus — Engine-ul Automat de Evenimente Astronomice v2.0

> **Ghid Tehnic & Documentație de Arhitectură pentru Botul de Discord #1 de Evenimente Astronomice Globale.**

---

## 📋 1. Viziune Generală

**Cosmic Nexus Events Engine** este un sistem automatizat dezvoltat în Python, proiectat să calculeze efemeride astronomice de înaltă precizie și să transmită notificări vizuale spectaculoase pe serverul de Discord.

Engine-ul operează **100% automatizat 24/7** prin GitHub Actions, folosind seturi de date profesionale furnizate gratuit de **NASA JPL**, **IAU Minor Planet Center**, **COBS** și **NOAA SWPC**.

---

## 🔭 2. Cele 8 Module Astronomice Implementate

### 1. 🌌 Conjuncții & Apropieri Vizuale (`check_conjunctions`)
* **Ce calculează:** Separația angulară reală dintre corpurile din Sistemul Solar (Lună, Mercur, Venus, Marte, Jupiter, Saturn) folosind efemeridele NASA JPL (`DE440s` / `DE421`).
* **Prag de Alertă:** Separație angulară $\le 1.0^\circ$.
* **Metrici Included:** Unghiul de separație minimă, ora de vârf fixată astronomic, iluminarea Lunii dinamică și recomandări optice.

### 2. ☄️ Ploi de Meteoriți cu Preaviz 2-Stage (`check_meteor_showers`)
* **Ce calculează:** Faza de maxim ZHR (Zenithal Hourly Rate) pentru ploile majore anuale (Perseide, Geminide, Quadrantide, Liride, Orionide, Leonide, Eta Aquariide, Urside).
* **Alerta 2-Stage:** Transmite o notificare cu **7 zile înainte** și o alertă finală cu **24 de ore înainte de maxim**.
* **Metrici Included:** Constelația radiantului, rata estimată de meteori/oră, faza Lunii dinamică și rollover automat de an pentru ploile din Ianuarie verificate în Decembrie.

### 3. 🔭 Alerte de Sezon Deep-Sky cu Clamping pe 31 ale Lunii (`check_deep_sky_seasons`)
* **Ce calculează:** Fereastra optimă de vizibilitate nocturnă și tranzitul la zenit pentru obiecte majore Deep-Sky.
* **Integrat cu Catalogul Personal (`CE-...`):**
  * `CE-N-243`: **M16 — Eagle Nebula** (*Forma distinctă de bot de craniu de câine & Stâlpii Creației*)
  * `CE-N-246`: **M42 — Orion Nebula** (*Regiunea centrală Trapezium & Gaz Ionizat*)
  * `CE-G-3`: **M31 — Andromeda Galaxy** (*Galaxia Spirală Gigantă cu M32 & M110*)
  * `CE-N-1758`: **M1 — Crab Nebula** (*Rămășița istorică de supernovă din Taurul & Pulsarul din 1054 d.Hr.*)
  * `CE-CORE`: **Centrul Căii Lactee** (*Sagittarius Core & norii denși de praf*)
* **Protecție Anti-Crash:** Folosește `calendar.monthrange` pentru a garanta calculul sigur pe data de 31 a oricărei luni.

### 4. 🪐 Alinieri Planetare Majore (`check_planetary_alignments`)
* **Ce calculează:** Longitudinile ecliptice ale tuturor celor 7 planete principale.
* **Prag de Alertă:** Detectează când **$\ge 4$ planete** sunt strânse într-un arc ecliptic $\le 60^\circ$.
* **Metrici Included:** Lista planetelor aliniate, dimensiunea arcului în grade, orarul pre-dawn.

### 5. 🪐 Opoziții Planetare la Perigeu (`check_planetary_oppositions`)
* **Ce calculează:** Alungirea Soare-Pământ-Planetă ($180^\circ$), distanța minimă în U.A. și iluminarea de 100% pentru planetelor exterioare (**Jupiter, Saturn, Marte**).
* **Metrici Included:** Distanța minimă în AU, iluminarea, recomandări pentru telescoape planetare și camere high-speed.

### 6. 🌒 Ocultații Lunare & Apropieri Strânse (`check_eclipses_and_occultations`)
* **Ce calculează:** Calcul orbital dinamic al distanței dintre discul lunar și planetele strălucitoare (Marte, Venus, Jupiter, Saturn).
* **Prag de Alertă:** Separație angulară $\le 0.75^\circ$.
* **Metrici Included:** Timpii de dispariție și reapariție pe marginea Lunii, recomandări optice.

### 7. ☀️ Furtuni Geomagnetice & Latitudini Aurorale LIVE (`check_noaa_space_weather`)
* **Ce calculează:** Indicele Kp planetar în timp real conectat la NOAA SWPC API (`planetary_k_index_1m.json`).
* **Prag de Alertă:** $Kp \ge 5.0$ (Furtună Geomagnetică G1-G3).
* **Metrici & Imagine Live:** Calculează latitudinea minimă vizibilă ($Kp 5 \Rightarrow 56^\circ\text{N}$, $Kp 7 \Rightarrow 50^\circ\text{N}$ vizibilă din România) și atașează **harta live a ovalului auroral de la NOAA**.

### 8. ☄️ Stream Live de Comete de la COBS & IAU MPC (`check_comets_and_interstellar`)
* **Ce calculează:** Telemetria cometelor noi (ex: C/2023 A3), magnitudinea observată live prin API-ul COBS (`cobs.si/api/comets`).
* **Metrici Included:** Perioada de vizibilitate, constelația curentă, recomandări pentru telescoape Wide-FOV (Refractoare APO).

---

## 🌐 3. Sistemul Strategic de Fuse Orare & Numărătoare Inversă Live

Orarul este împărțit pe **3 regiuni globale** (9 fuse orare strategice), conținând **numărătoare inversă live Discord (`<t:EPOCH:R>`)** și date curate la capătul rândului:

```text
⏳ LIVE COUNTDOWN: in 2 hours (Peak: Saturday, July 25, 2026 7:10 PM)
🇪🇺 EUROPE / EMEA (CANARIES, EAST EU & GULF HUBS):
└ [UTC+1]: Peak 18:10 (Win: 16:10 ➔ 19:10) (25 July)
└ [UTC+3]: Peak 19:10 (Win: 18:10 ➔ 20:10) (25 July)
└ [UTC+4]: Peak 20:10 (Win: 19:10 ➔ 21:10) (25 July)

🇺🇸 AMERICAS (PACIFIC, EASTERN & CHILE HUBS):
└ [UTC-8]: Peak 09:10 (Win: 08:10 ➔ 10:10) (25 July)
└ [UTC-5]: Peak 12:10 (Win: 11:10 ➔ 13:10) (25 July)
└ [UTC-3]: Peak 13:10 (Win: 12:10 ➔ 14:10) (25 July)

🇯🇵 ASIA / PACIFIC (INDIA, CHINA & AUSTRALIA HUBS):
└ [UTC+5.5]: Peak 21:40 (Win: 20:40 ➔ 22:40) (25 July)
└ [UTC+8]: Peak 00:10 (Win: 21:12 ➔ 01:12) (25-26 July)
└ [UTC+10]: Peak 02:10 (Win: 01:10 ➔ 03:10) (26 July)
```

---

## 🗄️ 4. Arhitectura Tehnică & Baza de Date

* **Bază de Date SQLite (`events.db`):** Stochează istoricul alertelor și previne duplicarea mesajelor.
* **Persistență prin GitHub Actions Cache:** Păstrează baza de date SQLite între rulările automate de la fiecare 3 ore prin `actions/cache@v4`.
* **NASA JPL Ephemeris:** Setul de date orbital de ultimă generație descărcat automat de modulul `skyfield`.
