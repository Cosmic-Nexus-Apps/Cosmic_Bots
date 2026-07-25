# 🚀 Cosmic Nexus — Deep Space & Rocket Launch Engine v1.0

> **Ghid Tehnic & Documentație pentru Botul de Discord #2 (Dedicat rolului `@Deep Space News`).**

---

## 📋 1. Viziune Generala

**Deep Space & Rocket Launch Engine** este cel de-al doilea bot din suita Cosmic Nexus, conceput special pentru rolul de Discord **`@Deep Space News`**. 

Engine-ul operează **100% automatizat 24/7** prin GitHub Actions, monitorizând lansările majore de rachete la nivel mondial și descoperirile spectaculoase ale telescoapelor spațiale (James Webb, Hubble, Euclid, Vera C. Rubin Observatory).

---

## 🚀 2. Cele 2 Module Principale

### 1. 🚀 Lansări de Rachete de Înalt Impact (`check_upcoming_launches`)
* **Ce monitorizează:** Lansări spațiale de profil înalt conectate în timp real la **The Space Devs / Launch Library 2 API** (`ll.thespacedevs.com`).
* **Filtru de Lansări Istorice & Majore:**
  * **SpaceX Starship & Super Heavy** (Teste orbitale, misiuni spre Lună/Marte)
  * **NASA Artemis Program** (Lansări SLS către Lună)
  * **Misiuni Științifice Deep Space** (Europa Clipper, Nancy Grace Roman, Euclid, JWST)
  * **Zboruri Umane & Misiuni Interplanetare** (Crew Dragon, Starliner, Gaganyaan India, JAXA MMX)
* **Metrici Include:** Numele misiunii, platforma de lansare (ex: Starbase Texas, Kennedy Space Center LC-39A), statusul numărătorii inverse, poza HD a rachetei și **link direct către transmisia LIVE pe YouTube/X**.

### 2. 🔭 Descoperiri & Imagini HD de la Telescoape Spațiale (`check_deep_space_imagery`)
* **Ce monitorizează:** Fluxul zilnic de imagini 4K și spectrografie recentă oferit de NASA APOD (Astronomy Picture of the Day) și STScI (James Webb / Hubble / Euclid Stream).
* **Metrici Include:** Titlul descoperirii, observatory credit (NASA/ESA/CSA), rezumatul științific și imaginea HD atașată direct în embed-ul Discord.

---

## 🔑 3. Cheile de Mediu dedicate pe GitHub

Pentru ca Botul #2 să ruleze independent de Botul #1, pe GitHub Secrets (în **Settings ➔ Secrets and variables ➔ Actions**) se adaugă două chei dedicate:

1. **`DEEP_SPACE_BOT_DISCORD_WEBHOOK_URL`**: Webhook-ul canalului de știri spațiale.
2. **`DEEP_SPACE_BOT_DISCORD_ROLE_ID`**: ID-ul rolului **`@Deep Space News`**.

---

## ⚙️ 4. Automatizare Cloud 24/7

* Workflow-ul [.github/workflows/deep_space_cron.yml](file:///d:/projects/Cosmic_Bots/.github/workflows/deep_space_cron.yml) rulează automat botul în cloud din **6 în 6 ore** (`0 */6 * * *`).
* Folosește baza de date SQLite (`deep_space.db`) pentru prevenirea notificărilor duble.
