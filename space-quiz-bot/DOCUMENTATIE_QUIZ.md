# 🧠 Cosmic Nexus — Engine-ul de Quiz & Trivia Astronomică v1.0

> **Ghid Tehnic & Documentație de Arhitectură pentru Botul de Quiz & Curiozități din Spațiu.**

---

## 📋 1. Viziune Generală

**Cosmic Nexus Space Quiz Engine** este un modul interactiv automatizat care trimite în fiecare zi pe Discord o întrebare spectaculoasă de astronomie și astrofizică în limba engleză.

---

## ❓ 2. Funcționalități Cheie

1. **Format Interactiv cu Spoiler pe Discord:**
   * Întrebare din astrofizică / explorare spațială.
   * 4 variante curate de răspuns (🇦, 🇧, 🇨, 🇩) fără cifre sau indicii care să dea răspunsul de gol.
   * Răspunsul corect și explicația științifică sunt ascunse sub **spoiler Discord (`|| ||`)**.
2. **Imagini HD asociate:** Fiecare întrebare este însoțită de o imagine oficială de la NASA.
3. **Garanție Anti-Repetare de 1 An (8760 Ore):** Baza de date SQLite (`quiz.db`) păstrează întrebările adresate timp de 365 de zile pline pentru a garanta că nicio întrebare nu se repetă.
4. **Automatizare Zilnică:** Workflow-ul `.github/workflows/space_quiz_cron.yml` trimite automat Întrebarea Zilei la ora 12:00 UTC.

---

## 🗄️ 3. Chei de Mediu (.env)

* `SPACE_QUIZ_BOT_DISCORD_WEBHOOK_URL`: URL-ul de Webhook de pe canalul de Discord dedicat (ex: `#quiz-astronomic`).
* `SPACE_QUIZ_BOT_DISCORD_ROLE_ID`: (Opțional) ID-ul rolei de Discord pentru notificări.
