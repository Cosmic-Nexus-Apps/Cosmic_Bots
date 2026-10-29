# 🧠 Cosmic Nexus — Astronomy Quiz & Trivia Engine v1.0

> **Technical guide and architecture documentation for the space quiz and trivia Discord bot.**

---

## 📋 1. Overview

**Cosmic Nexus Space Quiz Engine** is an automated interactive module that posts a compelling astronomy and astrophysics question in English to Discord every day.

---

## ❓ 2. Key Features

1. **Interactive format with Discord spoilers:**
   * An astrophysics / space exploration question.
   * 4 clear answer choices (🇦, 🇧, 🇨, 🇩), without numbers or clues that reveal the answer.
   * The correct answer and scientific explanation are hidden in a **Discord spoiler (`|| ||`)**.
2. **Associated HD images:** Every question includes an official NASA image.
3. **One-year duplicate-prevention guarantee (8,760 hours):** The SQLite database (`quiz.db`) stores questions for a full 365 days to ensure no question is repeated.
4. **Daily automation:** The `.github/workflows/space_quiz_cron.yml` workflow automatically sends the Question of the Day at 12:00 UTC.

---

## 🗄️ 3. Environment Variables (.env)

* `SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL`: Webhook URL for the dedicated Discord channel (e.g., `#space-quiz`).
* `SPACE_QUIZ_BOT_DISCORD_ROLE_ID`: (Optional) Discord role ID for notifications.
