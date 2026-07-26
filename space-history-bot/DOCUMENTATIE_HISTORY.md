# 🗓️ Cosmic Nexus — Engine-ul de Istoria Spațiului (Today in Space History) v1.0

> **Ghid Tehnic & Documentație de Arhitectură pentru Botul de Discord de Istoria Spațiului.**

---

## 📋 1. Viziune Generală

**Cosmic Nexus Space History Engine** este un modul educativ automatizat care transmite în fiecare zi pe Discord povestea unui eveniment istoric marcant din explorarea spațială (misiuni Apollo, astronauți pionieri, telescoape spațiale, sonde spațiale interstelare) petrecut în aceeași zi sau perioadă a anului.

Fiecare postare este însoțită de **imaginea oficială istorică HD 100% potrivită cu evenimentul** din arhivele oficiale NASA/ESA.

---

## ❓ 2. Funcționalități Cheie

1. **Format Micro-Blog Captivant:**
   * 📅 **Data & Anul istoric.**
   * 🚀 **Titlul Evenimentului / Misiunii.**
   * 👨‍🚀 **Echipajul & Agenția Spațială.**
   * 📖 **Rezumat Istoric & Impactul asupra Omenirii.**
2. **Imagine Istorică HD 100% Contextuală:** Poza oficială din arhivele NASA pentru misiunea respectivă.
3. **Persistență & Anti-Repetare SQLite (`history.db`):** Salvează istoricul postărilor pentru a nu repeta evenimentele.
4. **Automatizare Zilnică:** Workflow-ul `.github/workflows/space_history_cron.yml` trimite automat fișa istorică la ora 09:00 UTC.

---

## 🗄️ 3. Chei de Mediu (.env) / GitHub Secrets

* `SPACE_HISTORY_BOT_DISCORD_WEBHOOK_URL`: URL-ul Webhook-ului Discord pentru canalul de Istoria Spațiului.
* `SPACE_HISTORY_BOT_DISCORD_ROLE_ID`: (Opțional) ID-ul rolei de Discord de notificat.
