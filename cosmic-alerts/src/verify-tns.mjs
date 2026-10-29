// verify-tns.mjs — local test without Firebase or GitHub.
//
// Checks whether the TNS marker (user or bot) is accepted for downloading
// staged CSVs and reports how many rows are returned. Never prints keys.
//
// Usage (PowerShell, from the cosmic-alerts/ folder):
//   $env:TNS_USER_ID="4590"; $env:TNS_USER_NAME="username"; node src/verify-tns.mjs
// Or, for a bot:
//   $env:TNS_BOT_ID="..."; $env:TNS_BOT_NAME="..."; $env:TNS_API_KEY="..."; node src/verify-tns.mjs

import { fetchTnsCsv, parseTnsCsv, tnsAuthMode } from './tnsCsv.mjs';

const HOUR_MS = 3600000;
const DAY_MS = 24 * HOUR_MS;

const pad = value => String(value).padStart(2, '0');
const dayKey = date =>
  `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}`;

const mode = tnsAuthMode();
if (!mode) {
  console.error(
    'TNS nu este configurat. Setează fie TNS_USER_ID + TNS_USER_NAME, fie TNS_BOT_ID + TNS_BOT_NAME + TNS_API_KEY.'
  );
  process.exit(1);
}

const now = Date.now();
const candidates = [
  `tns_public_objects_${dayKey(new Date(now - DAY_MS))}.csv.zip`, // yesterday's delta
  `tns_public_objects_${pad(new Date(now - 2 * HOUR_MS).getUTCHours())}.csv.zip`, // hourly delta
  `tns_public_objects_${pad(new Date(now - HOUR_MS).getUTCHours())}.csv.zip`,
];

console.log(`[verify] mod autentificare: ${mode}`);
console.log(`[verify] marker: ${mode === 'user' ? 'user' : 'bot'} (fără afișarea cheii)`);

let success = false;

for (const file of candidates) {
  try {
    const csv = await fetchTnsCsv(file);
    if (!csv) {
      console.log(`[verify] ${file}: 404 (fișier încă negenerat pentru această zi/oră)`);
      continue;
    }

    const rows = parseTnsCsv(csv);
    console.log(`[verify] ${file}: ${rows.length} rânduri`);
    for (const row of rows.slice(0, 3)) {
      console.log(
        `  ${row.namePrefix} ${row.name} · ${row.type || 'AT'} · mag ${row.discoveryMag || '—'} · ${row.ra}, ${row.dec}`
      );
    }
    success = true;
    break;
  } catch (error) {
    console.log(`[verify] ${file}: ${error.message}`);
  }
}

if (!success) {
  console.error(
    '\n[verify] Niciun fișier nu a putut fi descărcat.\n' +
      '  • HTTP 403 → markerul nu este recunoscut: verifică TNS_USER_NAME (numele de login),\n' +
      '    respectiv TNS_USER_ID, sau (la bot) că botul este activ și API key-ul e corect.\n' +
      '  • Eroare de rețea / timeout → încearcă din nou.'
  );
  process.exit(1);
}

console.log('\n[verify] OK — accesul la CSV-urile TNS funcționează.');
