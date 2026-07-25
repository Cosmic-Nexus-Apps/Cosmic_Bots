# 🚀 Cosmic Nexus — Engine-ul de Lansări Spațiale & Imagini Telescoape v2.0

> **Ghid Tehnic & Documentație de Arhitectură pentru Botul de Discord de Lansări Spațiale & Descoperiri de la Telescoape.**

---

## 📋 1. Viziune Generală

**Cosmic Nexus Deep Space Engine** este un modul specializat în conectarea la **API-urile oficiale NASA, ESA, STScI și Launch Library 2** pentru a transmite în timp real lansările mari de rachete și cele mai noi descoperiri de la telescoapele spațiale.

---

## 🛰️ 2. Modulele Principale

### 1. 🚀 Lansări de Rachete & Urmărirea Etapei Misiunilor (`check_upcoming_launches`)
* **Telemetrie T-0 UTC Fixă:** Calculează momentul exact T-0 al lansării și transmite orarul pe minut pe 3 regiuni globale.
* **Formatare Status în 4 Etape:**
  * 🟢 `Go for Launch (T-Minus Active)` (Înainte de lansare)
  * 🚀 `In-Flight / Orbital Insertion Active` (În timpul lansării)
  * ✅ `Launch Successful (Orbit Achieved)` (După lansare reușită)
  * ❌ `Launch Anomaly / Failure Reported` (În caz de eșec/anomalie)
* **Bloc de Etapă a Misiunilor Lunare/Deep Space (`📍 DEEP SPACE MISSION STAGE`):**
  * Urmărește etapele mari pentru Artemis, Starship sau Europa Clipper:
    `🚀 [1/5] Countdown ➔ 🛰️ [2/5] Earth Orbit ➔ 🌖 [3/5] TLI Burn ➔ 🌕 [4/5] Lunar Orbit ➔ 👨‍🚀 [5/5] Landing`

### 2. 🔭 Colector Live de la Telescoape Spațiale (`check_deep_space_imagery`)
* **NASA APOD API (`api.nasa.gov`)**: Preluare automată zilnică a Imaginii Astronomice a Zilei.
* **NASA Image & Video Search API (`images-api.nasa.gov`)**: Căutare live a publicațiilor noi de la marile telescoape:
  * **`JAMES WEBB SPACE TELESCOPE (JWST)`**
  * **`HUBBLE SPACE TELESCOPE (HST)`**
  * **`EUCLID SPACE TELESCOPE (ESA/NASA 3D MAP)`**
  * **`CHANDRA X-RAY OBSERVATORY`**
  * **`VERA C. RUBIN OBSERVATORY (LSST)`**
* **Formatul Titlului:** **`🔭 [NUME TELESCOP] | [TITLU IMAGINE]`**

---

## 🗄️ 3. Arhitectură & Persistență SQLite

* **Bază de Date SQLite (`deep_space.db`):** Evită duplicarea postărilor.
* **GitHub Actions Cache:** Baza de date SQLite este păstrată între rulările de 6 ore prin `.github/workflows/deep_space_cron.yml`.
