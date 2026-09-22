// index.mjs — robotul de alerte Cosmic Atlas.
//
// Flux: citește sursele (MPC; TNS când există credențiale) → compară cu starea
// salvată → trimite notificări FCM data-only la topic-uri → salvează starea.
//
// Secretele vin EXCLUSIV din variabile de mediu (GitHub Secrets). Nimic nu se
// scrie în cod și nu se trimit date personale: doar topic-uri, fără token-uri.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import admin from 'firebase-admin';
import { fetchMpcComets } from './mpc.mjs';
import { fetchTnsTransients } from './tns.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATE_PATH = join(__dirname, '..', '.state', 'seen.json');
const MAX_NOTIFICATIONS_PER_RUN = 5;

function loadState() {
  try {
    const parsed = JSON.parse(readFileSync(STATE_PATH, 'utf8'));
    return {
      initialized: parsed.initialized === true,
      comets: Array.isArray(parsed.comets) ? parsed.comets : [],
      transients: Array.isArray(parsed.transients) ? parsed.transients : [],
    };
  } catch {
    return { initialized: false, comets: [], transients: [] };
  }
}

function saveState(state) {
  mkdirSync(dirname(STATE_PATH), { recursive: true });
  writeFileSync(STATE_PATH, JSON.stringify(state, null, 2) + '\n');
}

function initFirebase() {
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT;
  if (!raw) throw new Error('FIREBASE_SERVICE_ACCOUNT is missing');
  let credentials;
  try {
    credentials = JSON.parse(raw);
  } catch {
    credentials = JSON.parse(Buffer.from(raw, 'base64').toString('utf8'));
  }
  admin.initializeApp({ credential: admin.credential.cert(credentials) });
  return admin.messaging();
}

async function sendCometAlert(messaging, comet) {
  // Data-only: aplicația decide local dacă afișează notificarea (locație, oră, prefs).
  const data = {
    type: 'comet_alert',
    source: 'MPC',
    designation: comet.designation,
    name: comet.displayName,
    magnitude: comet.magnitude.toFixed(1),
    perihelion: comet.perihelionDate,
  };
  await messaging.send({
    topic: 'alerts_comet',
    data,
    android: { priority: 'high' },
    apns: { payload: { aps: { contentAvailable: true } } },
  });
}

async function sendTransientAlert(messaging, transient) {
  const data = {
    type: 'transient_alert',
    source: 'TNS',
    name: transient.name,
    objectType: transient.type,
    magnitude: transient.magnitude != null ? String(transient.magnitude) : '',
    ra: transient.raDeg != null ? String(transient.raDeg) : '',
    dec: transient.decDeg != null ? String(transient.decDeg) : '',
    discoveryDate: transient.discoveryDate,
  };
  await messaging.send({
    topic: transient.topic,
    data,
    android: { priority: 'high' },
    apns: { payload: { aps: { contentAvailable: true } } },
  });
}

async function run() {
  const nowMs = Date.now();
  const state = loadState();
  const messaging = initFirebase();

  const comets = await fetchMpcComets(nowMs);
  const seenComets = new Set(state.comets);
  const freshComets = comets.filter(comet => !seenComets.has(comet.key));

  // Tranzienții TNS (supernove/nove) — activi doar după aprobarea contului de bot.
  const transients = await fetchTnsTransients({ sinceMs: nowMs - 24 * 3600000 });
  const seenTransients = new Set(state.transients);
  const freshTransients = transients.filter(transient => !seenTransients.has(transient.name));

  if (!state.initialized) {
    // Prima rulare: doar înregistrăm starea, ca să nu trimitem alerte pentru
    // obiectele care sunt deja pe cer de mult timp.
    console.log(`[bootstrap] ${comets.length} comete înregistrate, fără notificări.`);
  } else {
    for (const comet of freshComets.slice(0, MAX_NOTIFICATIONS_PER_RUN)) {
      try {
        await sendCometAlert(messaging, comet);
        console.log(`[alert] cometă: ${comet.displayName} (${comet.designation})`);
      } catch (error) {
        console.error(`[alert-fail] ${comet.displayName}: ${error.message}`);
      }
    }

    for (const transient of freshTransients.slice(0, MAX_NOTIFICATIONS_PER_RUN)) {
      try {
        await sendTransientAlert(messaging, transient);
        console.log(`[alert] tranzient: ${transient.name} (${transient.type})`);
      } catch (error) {
        console.error(`[alert-fail] ${transient.name}: ${error.message}`);
      }
    }
  }

  const nextState = {
    initialized: true,
    comets: [...new Set([...state.comets, ...comets.map(comet => comet.key)])].slice(-500),
    transients: [
      ...new Set([...state.transients, ...transients.map(transient => transient.name)]),
    ].slice(-1000),
  };
  saveState(nextState);
  console.log(
    `[done] comete: ${comets.length}, comete noi: ${
      state.initialized ? freshComets.length : 0
    }, tranzienți: ${transients.length}, noi: ${state.initialized ? freshTransients.length : 0}`
  );
}

run().catch(error => {
  console.error(`[fatal] ${error.stack || error.message}`);
  process.exit(1);
});
