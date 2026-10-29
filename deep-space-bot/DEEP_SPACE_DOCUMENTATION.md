# 🚀 Cosmic Nexus — Space Launches & Telescope Imagery Engine v2.0

> **Technical guide and architecture documentation for the space launches and telescope discoveries Discord bot.**

---

## 📋 1. Overview

**Cosmic Nexus Deep Space Engine** is a specialized module that connects to official **NASA, ESA, STScI, and Launch Library 2 APIs** to share major rocket launches and the latest discoveries from space telescopes in real time.

---

## 🛰️ 2. Main Modules

### 1. 🚀 Rocket Launches & Mission Stage Tracking (`check_upcoming_launches`)
* **Fixed T-0 UTC telemetry:** Calculates the exact launch T-0 and shares minute-by-minute schedules across 3 global regions.
* **Four-stage status formatting:**
  * 🟢 `Go for Launch (T-Minus Active)` (Before launch)
  * 🚀 `In-Flight / Orbital Insertion Active` (During launch)
  * ✅ `Launch Successful (Orbit Achieved)` (After a successful launch)
  * ❌ `Launch Anomaly / Failure Reported` (In case of a failure/anomaly)
* **Lunar/deep-space mission stage block (`📍 DEEP SPACE MISSION STAGE`):**
  * Tracks major stages for Artemis, Starship, or Europa Clipper:
    `🚀 [1/5] Countdown ➔ 🛰️ [2/5] Earth Orbit ➔ 🌖 [3/5] TLI Burn ➔ 🌕 [4/5] Lunar Orbit ➔ 👨‍🚀 [5/5] Landing`

### 2. 🔭 Live Space Telescope Collector (`check_deep_space_imagery`)
* **NASA APOD API (`api.nasa.gov`):** Automatically retrieves the Astronomy Picture of the Day.
* **NASA Image & Video Search API (`images-api.nasa.gov`):** Searches live for new releases from major telescopes:
  * **`JAMES WEBB SPACE TELESCOPE (JWST)`**
  * **`HUBBLE SPACE TELESCOPE (HST)`**
  * **`EUCLID SPACE TELESCOPE (ESA/NASA 3D MAP)`**
  * **`CHANDRA X-RAY OBSERVATORY`**
  * **`VERA C. RUBIN OBSERVATORY (LSST)`**
* **Title format:** **`🔭 [TELESCOPE NAME] | [IMAGE TITLE]`**

---

## 🗄️ 3. Architecture & SQLite Persistence

* **SQLite database (`deep_space.db`):** Prevents duplicate posts.
* **GitHub Actions cache:** Preserves the SQLite database between scheduled runs in `.github/workflows/astronomy_cron.yml`.
