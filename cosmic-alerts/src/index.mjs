// index.mjs — robotul de alerte Cosmic Atlas.
//
// Flux: citește sursele (MPC; listele publice staged TNS) → compară cu starea
// salvată → trimite notificări FCM data-only la topic-uri → scrie feed-ul public
// citit de aplicație → salvează starea.
//
// Secretele vin EXCLUSIV din variabile de mediu (GitHub Secrets). Nimic nu se
// scrie în cod și nu se trimit date personale: doar topic-uri, fără token-uri.

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import admin from 'firebase-admin';
import { fetchMpcComets } from './mpc.mjs';
import {
  buildTnsFeed,
  fetchTnsRecords,
  planTnsFallbackFiles,
  planTnsFiles,
  pruneTnsRecords,
} from './tns.mjs';
import { tnsAuthMode, tnsConfigured } from './tnsCsv.mjs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const STATE_PATH = join(__dirname, '..', '.state', 'seen.json');
const FEED_PATH = join(__dirname, '..', 'alerts', 'feed.json');
const MAX_NOTIFICATIONS_PER_RUN = 5;
// Notificările push se trimit doar pentru descoperiri foarte recente.
const ALERT_MAX_AGE_MS = 48 * 3600000;
const MAX_PROCESSED_FILES = 400;

function loadState() {
  try {
    const parsed = JSON.parse(readFileSync(STATE_PATH, 'utf8'));
    // Migrare din formatul vechi, în care `transients` era doar o listă de nume.
    const legacyAlerted = Array.isArray(parsed.transients) ? parsed.transients : [];
    return {
      initialized: parsed.initialized === true,
      comets: Array.isArray(parsed.comets) ? parsed.comets : [],
      tns: parsed.tns && typeof parsed.tns === 'object' && !Array.isArray(parsed.tns)
        ? parsed.tns
        : {},
      alerted: Array.isArray(parsed.alerted)
        ? parsed.alerted
        : legacyAlerted,
      processedTnsFiles: Array.isArray(parsed.processedTnsFiles)
        ? parsed.processedTnsFiles
        : [],
    };
  } catch {
    return {
      initialized: false,
      comets: [],
      tns: {},
      alerted: [],
      processedTnsFiles: [],
    };
  }
}

function saveState(state) {
  mkdirSync(dirname(STATE_PATH), { recursive: true });
  writeFileSync(STATE_PATH, JSON.stringify(state, null, 2) + '\n');
}

/** Scrie feed-ul public citit de aplicație (fără secrete, doar date publice). */
function writeLiveFeed(feed) {
  mkdirSync(dirname(FEED_PATH), { recursive: true });
  writeFileSync(FEED_PATH, JSON.stringify(feed, null, 2) + '\n');
  console.log(`[feed] ${feed.transients.length} descoperiri scrise în alerts/feed.json`);
}

function initFirebase() {
  const raw = process.env.FIREBASE_SERVICE_ACCOUNT;
  if (!raw) {
    // Feed-ul public (supernove/comete în carusel) NU depinde de Firebase.
    // Notificările push sunt opționale: fără cheie, robotul doar nu le trimite.
    console.warn(
      '[firebase] FIREBASE_SERVICE_ACCOUNT lipsește: feed-ul se actualizează normal, dar nu se trimit notificări push.'
    );
    return null;
  }

  let credentials;
  try {
    credentials = JSON.parse(raw);
  } catch {
    try {
      credentials = JSON.parse(Buffer.from(raw, 'base64').toString('utf8'));
    } catch {
      throw new Error(
        'FIREBASE_SERVICE_ACCOUNT nu este JSON valid. Lipește conținutul COMPLET al ' +
          'fișierului descărcat din Firebase Console -> Project settings -> Service accounts ' +
          '-> Generate new private key.'
      );
    }
  }

  if (credentials?.type === 'service_account' && typeof credentials?.project_id === 'string') {
    // Cheia corectă.
  } else if (credentials?.project_info) {
    throw new Error(
      'FIREBASE_SERVICE_ACCOUNT conține google-services.json (configurația aplicației), ' +
        'NU cheia de service account. Deschide Firebase Console -> Project settings -> ' +
        'Service accounts -> Generate new private key și lipește acel fișier în secret.'
    );
  } else {
    throw new Error(
      'FIREBASE_SERVICE_ACCOUNT nu arată ca o cheie de service account validă ' +
        '(lipsește "type": "service_account" / "project_id"). Regenerează cheia din ' +
        'Firebase Console -> Project settings -> Service accounts -> Generate new private key.'
    );
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
    name: transient.namePrefix
      ? `${transient.namePrefix} ${transient.name}`
      : transient.name,
    objectType: transient.type,
    magnitude: transient.magnitude != null ? String(transient.magnitude) : '',
    ra: transient.ra != null ? String(transient.ra) : '',
    dec: transient.dec != null ? String(transient.dec) : '',
    discoveryDate: transient.discoveryDate,
  };
  await messaging.send({
    topic: transient.topic || 'alerts_transient',
    data,
    android: { priority: 'high' },
    apns: { payload: { aps: { contentAvailable: true } } },
  });
}

async function run() {
  const nowMs = Date.now();
  const state = loadState();

  // Preflight vizibil în log (fără valori secrete), ca diagnosticarea să fie imediată.
  console.log(
    `[env] FIREBASE_SERVICE_ACCOUNT: ${
      process.env.FIREBASE_SERVICE_ACCOUNT ? 'setat' : 'LIPSĂ'
    } | TNS: ${tnsAuthMode() ?? 'LIPSĂ (bot sau user)'}`
  );

  const messaging = initFirebase();

  const comets = await fetchMpcComets(nowMs);
  const seenComets = new Set(state.comets);
  const freshComets = comets.filter(comet => !seenComets.has(comet.key));

  // ── TNS: liste publice staged (CSV) ───────────────────────────────────────
  // Prima rulare descarcă tot catalogul public; apoi doar delta de ieri + orele
  // încheiate. Astfel nu se fac interogări per obiect și nu se încarcă API-ul.
  const hasTnsRecords = Object.keys(state.tns).length > 0;
  const bootstrap = !state.initialized || !hasTnsRecords;
  let tnsRecords = state.tns;
  let processedTnsFiles = state.processedTnsFiles;
  let tnsFetchNote = 'dezactivat (fără credențiale)';

  if (tnsConfigured()) {
    const files = planTnsFiles({
      nowMs,
      bootstrap,
      processed: state.processedTnsFiles,
    });
    let result = await fetchTnsRecords(files, {
      onProgress: message => console.log(`[tns] ${message}`),
    });

    // Catalogul complet poate fi indisponibil (mentenanță / timeout): reconstruim
    // fereastra de 30 de zile din delta zilelor anterioare.
    if (bootstrap && result.records.length === 0) {
      const fallback = planTnsFallbackFiles({
        nowMs,
        processed: [...state.processedTnsFiles, ...result.processed],
      });
      const fallbackResult = await fetchTnsRecords(fallback, {
        onProgress: message => console.log(`[tns:fallback] ${message}`),
      });
      result = {
        records: fallbackResult.records,
        processed: [...result.processed, ...fallbackResult.processed],
      };
    }

    tnsFetchNote = `${result.records.length} rânduri din ${result.processed.length} fișiere`;

    if (result.records.length > 0) {
      tnsRecords = { ...state.tns };
      for (const record of result.records) {
        tnsRecords[record.name] = record;
      }
    }
    if (result.processed.length > 0) {
      processedTnsFiles = [...state.processedTnsFiles, ...result.processed].slice(
        -MAX_PROCESSED_FILES
      );
    }
  }

  tnsRecords = pruneTnsRecords(tnsRecords, nowMs);
  const feed = buildTnsFeed(tnsRecords, nowMs);

  // Starea rămâne mica: păstrăm doar recordurile care intră în feed-ul public
  // (max 300). Altfel, catalogul complet ar însemna un fișier de stare de MB-uri
  // comis în git la fiecare rulare.
  const feedNames = new Set(feed.transients.map(transient => transient.name));
  tnsRecords = Object.fromEntries(
    Object.entries(tnsRecords).filter(([name]) => feedNames.has(name))
  );

  const alerted = new Set(state.alerted);
  const freshTransients = feed.transients.filter(transient => {
    if (alerted.has(transient.name)) return false;
    const discovered = Date.parse(transient.discoveryDate) || nowMs;
    return nowMs - discovered <= ALERT_MAX_AGE_MS;
  });

  writeLiveFeed(feed);

  if (!state.initialized || bootstrap) {
    // Prima rulare: doar înregistrăm starea, ca să nu trimitem alerte pentru
    // obiectele care sunt deja pe cer de mult timp.
    console.log(
      `[bootstrap] ${comets.length} comete, ${feed.transients.length} descoperiri TNS înregistrate, fără notificări.`
    );
  } else if (!messaging) {
    console.log('[alerts] Firebase indisponibil: feed-ul e actualizat, notificările sunt omise.');
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
        console.log(
          `[alert] tranzient: ${transient.namePrefix} ${transient.name} (${transient.type})`
        );
      } catch (error) {
        console.error(`[alert-fail] ${transient.name}: ${error.message}`);
      }
    }
  }

  const nextState = {
    initialized: true,
    comets: [...new Set([...state.comets, ...comets.map(comet => comet.key)])].slice(-500),
    tns: tnsRecords,
    alerted: [
      ...new Set([...state.alerted, ...feed.transients.map(transient => transient.name)]),
    ].slice(-2000),
    processedTnsFiles,
  };
  saveState(nextState);
  console.log(
    `[done] comete: ${comets.length}, comete noi: ${
      state.initialized ? freshComets.length : 0
    }, TNS: ${tnsFetchNote}, feed: ${feed.transients.length}, alerte noi: ${
      state.initialized ? freshTransients.length : 0
    }`
  );
}

run().catch(error => {
  console.error(`[fatal] ${error.stack || error.message}`);
  process.exit(1);
});
