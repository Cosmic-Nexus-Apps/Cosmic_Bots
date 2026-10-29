# Cosmic Alerts Bot

A bot that checks official astronomical discovery sources and sends push
notifications (FCM, data-only) to the Cosmic Atlas app. It **does not contact
the central server** and stores no personal data: it sends messages only to
topics, and the app decides locally whether to display a notification
(location, time, preferences).

## Repository location

The bot code does **not** belong in the app repository. Recommended locations:

- **Cosmic_Bots** repository → `cosmic-alerts/` folder
- Workflow → `Cosmic_Bots/.github/workflows/cosmic-alerts.yml`
  (copy `workflow/alerts.yml` to this path)

## What it does

| Source | What it tracks | Status |
|---|---|---|
| MPC (`CometEls.txt`) | New comets / comets at perihelion, absolute magnitude ≤ 12 | ✅ active |
| TNS (`wis-tns.org`) — **staged CSV** | Public supernovae, novae, and ATs (mag ≤ 20, with coordinates) | ✅ active (approved bot account) |

The bot runs every 10 minutes, compares the results with the last saved state
in `cosmic-alerts/.state/seen.json`, and sends notifications only for new objects.

> **TNS — why CSV instead of the API:** TNS officially recommends maintaining
> the list locally from staged files (`tns_public_objects.csv.zip`, plus daily
> and hourly deltas). The *search* API returns names only, not coordinates, and
> querying each object individually would require hundreds of requests. The bot
> downloads the complete catalog once, then only yesterday's delta and completed
> hourly deltas.
>
> CSV downloads do not use the TNS API, but they require an access marker. Two
> options are supported (the first is recommended for automation):
> - **bot** — `TNS_BOT_ID`, `TNS_BOT_NAME`, `TNS_API_KEY` (GitHub secrets);
> - **user** — `TNS_USER_ID`, `TNS_USER_NAME`, without an API key (exactly as in
>   the TNS documentation example for downloading CSV files).
> Credentials remain exclusively in GitHub Secrets.

## Local verification (without GitHub or Firebase)

```powershell
cd Cosmic_Bots/cosmic-alerts
$env:TNS_USER_ID="4590"          # Account ID (from the /user/<id>/edit URL)
$env:TNS_USER_NAME="username"    # TNS login name
node src/verify-tns.mjs
```

The script downloads only yesterday's/hourly deltas and prints the row count
and 3 examples. It never prints keys. `403` = unrecognized marker (incorrect
username or inactive bot); `404` = that day's/hour's file does not exist yet.

> `FIREBASE_SERVICE_ACCOUNT` is **optional**: without it, `feed.json` is still
> updated normally (so supernovae appear in the app); only push notifications
> are skipped.

## Installation

1. In the **Cosmic_Bots** repository, create the `cosmic-alerts/` folder and copy:
   - `package.json`, `package-lock.json`
   - `src/` (`index.mjs`, `mpc.mjs`, `tns.mjs`)
   - `.gitignore`
2. Copy `workflow/alerts.yml` to `Cosmic_Bots/.github/workflows/cosmic-alerts.yml`.
3. In the repository, open **Settings → Secrets and variables → Actions → New repository secret**:
   - `FIREBASE_SERVICE_ACCOUNT` = contents of the JSON file downloaded from
     Firebase Console → Project settings → Service accounts → Generate new private key.
   - (after TNS approval) `TNS_BOT_ID`, `TNS_BOT_NAME`, `TNS_API_KEY`.
4. Open **Actions → Cosmic Alerts → Run workflow** — the first run only records
   the current state; it does not send notifications for objects that are
   already in the sky.

## Secrets

Never put secrets in code. Use GitHub Secrets (for the bot) or the secured
`d:/projects/security/{test|prod}/` folder (for the app build).

## FCM topics

- `alerts_comet` — new comets / comets at perihelion
- `alerts_supernova` — supernovae (after TNS activation)
- `alerts_transient` — other transients (after TNS activation)

The app subscribes to the topics chosen by the user and displays a notification
locally only if the object is visible from their location.
