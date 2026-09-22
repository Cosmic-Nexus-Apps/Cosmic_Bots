# Cosmic Alerts Bot

Robot care verifică sursele oficiale de descoperiri astronomice și trimite
notificări push (FCM, data-only) către aplicația Cosmic Atlas. **Nu atinge serverul
central** și nu stochează date personale: trimite doar la topic-uri, iar aplicația
decide local dacă afișează notificarea (locație, oră, preferințe).

## Unde stă

Codul robotului **nu** stă în repo-ul aplicației. Locul recomandat:

- repo-ul **Cosmic_Bots** → folderul `cosmic-alerts/`
- workflow-ul → `Cosmic_Bots/.github/workflows/cosmic-alerts.yml`
  (copiază `workflow/alerts.yml` cu acest nume)

## Ce face

| Sursă | Ce urmărește | Stare |
|---|---|---|
| MPC (CometEls.txt) | comete noi / la periheliu, magnitudine absolută ≤ 12 | ✅ activ |
| TNS (`wis-tns.org`) | supernove, nove, tranzienți noi | ⏳ după aprobarea contului de bot |

Robotul rulează la fiecare 10 minute, compară lista cu ultima stare salvată în
`cosmic-alerts/.state/seen.json` și trimite notificări doar pentru obiectele noi.

## Instalare

1. În repo-ul **Cosmic_Bots**, creează folderul `cosmic-alerts/` și copiază:
   - `package.json`, `package-lock.json`
   - `src/` (index.mjs, mpc.mjs, tns.mjs)
   - `.gitignore`
2. Copiază `workflow/alerts.yml` → `Cosmic_Bots/.github/workflows/cosmic-alerts.yml`.
3. În repo: **Settings → Secrets and variables → Actions → New repository secret**:
   - `FIREBASE_SERVICE_ACCOUNT` = conținutul fișierului JSON descărcat din
     Firebase Console → Project settings → Service accounts → Generate new private key.
   - (după aprobarea TNS) `TNS_BOT_ID`, `TNS_BOT_NAME`, `TNS_API_KEY`.
4. **Actions → Cosmic Alerts → Run workflow** — prima rulare doar înregistrează
   starea, nu trimite nimic (nu spam-ează cu ce e deja pe cer).

## Secrete

Niciodată în cod. Doar GitHub Secrets (pentru robot) sau folderul securizat
`d:/projects/security/{test|prod}/` (pentru build-ul aplicației).

## Topic-uri FCM

- `alerts_comet` — comete noi / la periheliu
- `alerts_supernova` — supernove (după activarea TNS)
- `alerts_transient` — alte tranzienți (după activarea TNS)

Aplicația se abonează la topic-urile alese de utilizator și afișează notificarea
local doar dacă obiectul e vizibil de la locația lui.
