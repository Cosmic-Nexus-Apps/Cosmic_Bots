# 🌌 Cosmic Nexus — Automated Astronomy Events Engine v2.0

> **Technical guide and architecture documentation for the global astronomy events Discord bot.**

---

## 📋 1. Overview

**Cosmic Nexus Events Engine** is an automated Python system designed to calculate high-precision astronomical ephemerides and deliver visually rich notifications to a Discord server.

The engine runs **fully automatically, 24/7** through GitHub Actions, using professional datasets provided at no cost by **NASA JPL**, the **IAU Minor Planet Center**, **COBS**, and **NOAA SWPC**.

---

## 🔭 2. The Eight Implemented Astronomy Modules

### 1. 🌌 Conjunctions & Close Approaches (`check_conjunctions`)
* **What it calculates:** The true angular separation between Solar System bodies (the Moon, Mercury, Venus, Mars, Jupiter, and Saturn) using NASA JPL ephemerides (`DE440s` / `DE421`).
* **Alert threshold:** Angular separation $\le 1.0^\circ$.
* **Included metrics:** Minimum angular separation, astronomically calculated peak time, dynamic lunar illumination, and optical equipment recommendations.

### 2. ☄️ Meteor Showers with Two-Stage Advance Alerts (`check_meteor_showers`)
* **What it calculates:** The peak ZHR (Zenithal Hourly Rate) phase for major annual meteor showers (Perseids, Geminids, Quadrantids, Lyrids, Orionids, Leonids, Eta Aquariids, and Ursids).
* **Two-stage alerts:** Sends a notification **7 days before** the peak and a final alert **24 hours before the peak**.
* **Included metrics:** Radiant constellation, estimated meteors per hour, dynamic lunar phase, and automatic year rollover for January showers checked in December.

### 3. 🔭 Deep-Sky Season Alerts with Month-End Clamping (`check_deep_sky_seasons`)
* **What it calculates:** The optimal nighttime visibility window and meridian transit for major deep-sky objects.
* **Integrated with the personal catalog (`CE-...`):**
  * `CE-N-243`: **M16 — Eagle Nebula** (*The distinctive dog-skull shape & Pillars of Creation*)
  * `CE-N-246`: **M42 — Orion Nebula** (*The central Trapezium region & ionized gas*)
  * `CE-G-3`: **M31 — Andromeda Galaxy** (*The giant spiral galaxy with M32 & M110*)
  * `CE-N-1758`: **M1 — Crab Nebula** (*The historic supernova remnant in Taurus & the 1054 AD pulsar*)
  * `CE-CORE`: **Milky Way Core** (*Sagittarius Core & dense dust clouds*)
* **Crash protection:** Uses `calendar.monthrange` to ensure safe date calculations for the 31st of any month.

### 4. 🪐 Major Planetary Alignments (`check_planetary_alignments`)
* **What it calculates:** Ecliptic longitudes for all 7 major planets.
* **Alert threshold:** Detects when **$\ge 4$ planets** are clustered within an ecliptic arc of $\le 60^\circ$.
* **Included metrics:** List of aligned planets, arc width in degrees, and pre-dawn schedule.

### 5. 🪐 Planetary Oppositions at Perigee (`check_planetary_oppositions`)
* **What it calculates:** The Sun-Earth-planet elongation ($180^\circ$), minimum distance in AU, and 100% illumination for outer planets (**Jupiter, Saturn, and Mars**).
* **Included metrics:** Minimum distance in AU, illumination, and recommendations for planetary telescopes and high-speed cameras.

### 6. 🌒 Lunar Occultations & Close Approaches (`check_eclipses_and_occultations`)
* **What it calculates:** Dynamic orbital distance between the lunar disk and bright planets (Mars, Venus, Jupiter, and Saturn).
* **Alert threshold:** Angular separation $\le 0.75^\circ$.
* **Included metrics:** Disappearance and reappearance times at the lunar limb, plus optical equipment recommendations.

### 7. ☀️ Geomagnetic Storms & Live Aurora Latitudes (`check_noaa_space_weather`)
* **What it calculates:** The real-time planetary Kp index from the NOAA SWPC API (`planetary_k_index_1m.json`).
* **Alert threshold:** $Kp \ge 5.0$ (G1-G3 geomagnetic storm).
* **Metrics & live imagery:** Calculates the lowest visible latitude ($Kp 5 \Rightarrow 56^\circ\text{N}$, $Kp 7 \Rightarrow 50^\circ\text{N}$, visible from Romania) and attaches **NOAA's live auroral oval map**.

### 8. ☄️ Live Comet Stream from COBS & IAU MPC (`check_comets_and_interstellar`)
* **What it calculates:** Live telemetry for new comets (e.g., C/2023 A3), including observed magnitude via the COBS API (`cobs.si/api/comets`).
* **Included metrics:** Visibility period, current constellation, and recommendations for wide-field telescopes (APO refractors).

---

## 🌐 3. Strategic Time-Zone System & Live Countdown

The schedule is divided into **3 global regions** (9 strategic time zones), with **live Discord countdowns (`<t:EPOCH:R>`)** and clean date information at the end of each row:

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

## 🗄️ 4. Technical Architecture & Database

* **SQLite database (`events.db`):** Stores alert history and prevents duplicate messages.
* **Persistence through GitHub Actions cache:** Preserves the SQLite database between scheduled runs (6 slots per day) using `actions/cache@v4`.
* **NASA JPL ephemeris:** The latest-generation orbital dataset, automatically downloaded by the `skyfield` module.
