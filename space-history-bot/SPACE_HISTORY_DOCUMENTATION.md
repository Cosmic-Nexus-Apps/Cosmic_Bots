# 🗓️ Cosmic Nexus — Space History Engine (Today in Space History) v1.0

> **Technical guide and architecture documentation for the Space History Discord bot.**

---

## 📋 1. Overview

**Cosmic Nexus Space History Engine** is an automated educational module that shares a story on Discord each day about a major event in space exploration (Apollo missions, pioneering astronauts, space telescopes, and interstellar probes) that occurred on the same calendar date or during the same time of year.

Every post includes an **official HD historical image that matches the event** from NASA/ESA archives.

---

## ❓ 2. Key Features

1. **Engaging micro-blog format:**
   * 📅 **Date & historical year.**
   * 🚀 **Event / mission title.**
   * 👨‍🚀 **Crew & space agency.**
   * 📖 **Historical summary & impact on humanity.**
2. **Fully contextual HD historical image:** An official NASA archive image for the relevant mission.
3. **SQLite persistence & duplicate prevention (`history.db`):** Saves post history to prevent events from repeating.
4. **Daily automation:** The `.github/workflows/space_history_cron.yml` workflow automatically sends the historical feature at 09:00 UTC.

---

## 🗄️ 3. Environment Variables (.env) / GitHub Secrets

* `SPACE_HISTORY_BOT_DISCORD_WEBHOOK_URL`: Discord webhook URL for the Space History channel.
* `SPACE_HISTORY_BOT_DISCORD_ROLE_ID`: (Optional) Discord role ID to notify.
