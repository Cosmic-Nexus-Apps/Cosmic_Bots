# 🌌 Cosmic Nexus — Complete Space Bots Ecosystem Documentation v2.0

> **Technical guide, broadcast schedule, and architecture for the astronomy and space bots ecosystem.**

---

## 📋 1. Ecosystem Overview

**Cosmic Nexus** is a fully automated multi-bot platform designed to monitor the universe, space launches, NOAA space weather, and astronomical discoveries in real time, delivering engaging and interactive information to Discord.

The ecosystem runs automatically through **GitHub Actions**, using **6 fixed daily slots** (07:00, 09:00, 12:00, 14:00, 16:00, and 18:00 UTC). "Real-time" checks (launches, geomagnetic storms, solar flares, comets/transients) run whenever the orchestrator is triggered, with duplicate prevention through `scheduler.db`.

---

## ⏰ 2. Master Server Broadcast Schedule

Server broadcasts are divided into two categories: **Real-Time Alerts (polling every 5 minutes)** and **scheduled tasks at fixed time slots**.

### ⚡ Real-Time Broadcasts (checked every 5 minutes)
| Module / Alert | Data Source | Description & Trigger Threshold |
| :--- | :--- | :--- |
| 🚀 **Live Rocket Launches** | Launch Library 2 API | T-60 min, T-15 min, and T-0 countdowns for orbital rocket launches. |
| ☀️ **LIVE Geomagnetic Storms** | NOAA SWPC API | Instant notification at $Kp \ge 5.0$ (G1-G5 storms), with the live auroral oval map. |
| 💥 **Emergency Solar Flares** | NOAA GOES Satellite | Warnings for major class **M** and **X** solar flares. |

---

### 📅 Daily Schedule (Six Time Slots)

| Time Slot | UTC Time | Romania Time (EEST / UTC+3) | Responsible Bot / Module | Broadcast Content |
| :---: | :---: | :---: | :---: | :--- |
| **Slot 1** | **07:00 UTC** | **10:00 EEST** | `deep-space-bot` | 📸 **NASA Picture of the Day (APOD):** NASA's Astronomy Picture of the Day. |
| **Slot 2** | **09:00 UTC** | **12:00 EEST** | `astro-events-bot` | 🔭 **Astronomical Events:** Planetary conjunctions (Skyfield JPL), planetary alignments (≥ 4 planets), new comets, meteor showers, and supernovae. |
| **Slot 3** | **12:00 UTC** | **15:00 EEST** | `space-quiz-bot` | 🧠 **Daily Space Quiz:** An interactive astronomy question generated with Gemini AI, plus relevant image search via the Wikipedia API. |
| **Slot 4** | **14:00 UTC** | **17:00 EEST** | `space-history-bot` | 📜 **Today in Space History:** A historical event (Apollo, Voyager, Kepler, Galileo) with verified portraits/images via the Wikipedia API. |
| **Slot 5** | **16:00 UTC** | **19:00 EEST** | `deep-space-bot` | 🌌 **ISS Telemetry & Exoplanets:** Crew aboard the ISS/Tiangong and new exoplanet discoveries. |
| **Slot 6** | **18:00 UTC** | **21:00 EEST** | `astro-events-bot` | 📰 **Daily Top Story:** The day's most important space news story, selected and summarized by Gemini AI. |

---

## 🤖 3. Ecosystem Bots

### 1. 🔭 Astro-Events Bot (`astro-events-bot/bot.py`)
* **Main role:** High-precision astronomical calculations and space news aggregation.
* **What it does:**
  - Calculates orbital separations between planets/the Moon using the **Skyfield** library and NASA JPL ephemeris files (`DE440s.bsp`).
  - Sends alerts for conjunctions ($\le 1.0^\circ$), planetary alignments ($\ge 4$ planets within $\le 60^\circ$), planetary oppositions, and meteor showers (7-day and 24-hour notices).
  - Processes RSS feeds from NASA, ESA, ESO, and Space.com, using Gemini AI to select and summarize only the most important story from the last 24 hours.
  - Monitors NOAA space weather (Kp index for auroras).

---

### 2. 🌌 Deep-Space Bot (`deep-space-bot/bot.py`)
* **Main role:** Deep-universe exploration, telescope imagery, and real-time space telemetry.
* **What it does:**
  - Processes **NASA APOD** (Astronomy Picture of the Day) and HD images from the NASA catalog (JWST, Hubble, Euclid, Chandra).
  - Queries the OpenNotify / NASA API for the human crew in space (aboard the ISS and Tiangong).
  - Searches the NASA Exoplanet Archive for new exoplanet discoveries.
  - Tracks global rocket launch countdowns via Launch Library 2.
  - **"Picture of the Day vs. Major News" logic:** Normally (99% of the time), at 18:00 UTC it sends **NASA's Picture of the Day (APOD)**. In the rare case of exceptionally important space news (e.g., detection of an extraterrestrial signal, an extreme solar storm, or a historic JWST discovery), Gemini AI triggers an override and displays the breaking story instead of the picture.

---

### 3. 🧠 Space-Quiz Bot (`space-quiz-bot/bot.py`)
* **Main role:** Gamification and testing the community's knowledge.
* **What it does:**
  - Generates a unique, engaging, and accurate daily quiz question using Google Gemini AI.
  - Covers 6 major categories (Solar System, stellar astrophysics, black holes and wormholes, cosmology, astrobiology and exoplanets, history and rockets).
  - Keeps the latest 100+ quiz topics in the SQLite database (`quiz.db`) to prevent questions from repeating.

---

### 4. 📜 Space-History Bot (`space-history-bot/bot.py`)
* **Main role:** General historical knowledge and space-mission archives.
* **What it does:**
  - Selects real historical events from space exploration that happened on the current calendar date (month and day).
  - Intelligently rotates between 4 historical eras: *The Early Space Race (1950–1969)*, *The Space Shuttle Era (1970–1999)*, *The Space Station & Telescope Era (2000–2015)*, and *The Modern Commercial & Artemis Era (2016–present)*.
  - Automatically downloads historical images from the Wikimedia Commons / NASA Image API archive.

---

## 🛠️ 4. Support Services & Technical Architecture

### ⚙️ Central Orchestrator (`main_orchestrator.py`)
- Runs all modules safely (`run_safe`), ensuring that if an external API times out, the rest of the ecosystem continues without crashing.
- Uses `scheduler.db` to track each module's last run and prevent premature execution.

### 🧠 Gemini AI Module (`google_ai_helper.py`)
- Connected to the Google AI Studio free-tier models: `gemini-3.8-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` (fallback chain; the first one can be overridden with `GEMINI_MODEL`).
- Cleans and summarizes RSS news.
- Classifies news urgency (`check_for_extraordinary_news`) to decide whether a story is more important than the APOD picture of the day.

### 🗄️ Persistence & SQLite Databases
- `events.db`: Prevents duplicate astronomical alerts.
- `deep_space.db`: Stores the cache for launches, telescopes, and exoplanets.
- `history.db`: Cache for published historical events.
- `quiz.db`: Cache for quiz questions.
- `scheduler.db`: The orchestrator's task schedule.
- `published_history.json`: Global persistence for up to 30–90 days of titles and event keys.

---

## 💬 6. Recommended Discord Channels & Roles (100% English Setup)

To match your English-language server, the recommended channel and role structure is:

### 📢 Discord Channels (4 Dedicated Channels)
1. **`#sky-events`** (`EVENTS_BOT_DISCORD_WEBHOOK_URL`)
   - Real-time alerts for conjunctions, meteor showers, planetary alignments, solar storms, and geomagnetic aurora alerts ($Kp \ge 5$).
2. **`#deep-space-news`** (`DEEP_SPACE_BOT_DISCORD_WEBHOOK_URL`)
   - NASA APOD (Astronomy Picture of the Day), JWST/Hubble HD imagery, ISS crew telemetry, rocket launches, and Daily Space News (07:00, 14:00, 20:00 UTC).
3. **`#space-quiz`** (`SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL`)
   - Daily interactive space trivia and astronomy quiz with spoiler solutions (12:00 UTC / 15:00 EEST).
4. **`#space-history`** (`SPACE_HISTORY_BOT_DISCORD_WEBHOOK_URL`)
   - Today in Space History posts covering Apollo, Voyager, and Shuttle missions (16:00 UTC / 19:00 EEST).

### 🔔 Discord Server Roles (.env Role IDs)
1. **`Sky Events`** $\rightarrow$ `EVENTS_BOT_DISCORD_ROLE_ID`
2. **`Deep Space News`** $\rightarrow$ `DEEP_SPACE_BOT_DISCORD_ROLE_ID`
3. **`Cosmic App Updates`** *(or Space Quiz)* $\rightarrow$ `SPACE_QUIZ_BOT_DISCORD_ROLE_ID`
4. **`Gear & Tech`** *(or Space History)* $\rightarrow$ `SPACE_HISTORY_BOT_DISCORD_ROLE_ID`

---

## 🚀 7. Running the Ecosystem in Production

1. **Running with Cron / GitHub Actions:**
   At the top of every hour (`0 * * * *`), run:
   ```bash
   python main_orchestrator.py
   ```
2. **Managing Discord Webhooks:**
   Each bot reads the following variables from the `.env` file:
   - `EVENTS_BOT_DISCORD_WEBHOOK_URL`
   - `DEEP_SPACE_BOT_DISCORD_WEBHOOK_URL`
   - `SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL`
   - `SPACE_HISTORY_BOT_DISCORD_WEBHOOK_URL`

---

## 🔄 8. Golden Rule for Updates & Git Workflow (AI Prompt & Best Practices)

When modifying bot code locally or through an AI assistant:
1. **Always run `git pull --rebase` before editing/pushing:** GitHub Actions continuously saves post history to `published_history.json`, so synchronize your local copy with the remote before committing or pushing.
2. **Preserve `published_history.json`:** This file ensures that no story, comet, supernova, or quiz is repeated on Discord.

### 📝 Prompt for the AI Assistant Before Any Update:
> *"Before making changes or running git push, run `git pull --rebase` to retrieve the latest version of `published_history.json`, which is automatically updated by GitHub Actions. Do not delete or reset `published_history.json`; it prevents messages from being repeated on Discord."*
