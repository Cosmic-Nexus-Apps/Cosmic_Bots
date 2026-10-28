// tns.mjs — orchestrarea listelor publice TNS (CSV staged) pentru feed-ul aplicației.
//
// Sursa de date este exclusiv CSV-ul staged, recomandat oficial de TNS (vezi
// tnsCsv.mjs). Nu se fac interogări per obiect: catalogul complet se descarcă o
// singură dată (bootstrap), iar apoi se aplică doar delta zilei + delta orelor.
//
// Rezultatul este un "record" normalizat per obiect public, ținut local în starea
// robotului, din care se generează feed-ul citit de aplicație.

import { fetchTnsCsv, parseTnsCsv, tnsConfigured } from './tnsCsv.mjs';

const DAY_MS = 24 * 3600000;
const HOUR_MS = 3600000;

/** Feed-ul păstrează descoperirile 30 de zile (ca în aplicație). */
export const TNS_FEED_MAX_AGE_DAYS = 30;
/** Cap practic: dincolo de mag ~20 nu mai e realist pentru echipamente amatoare. */
export const TNS_MAX_FEED_MAGNITUDE = 20;
/** Limită de siguranță pentru dimensiunea feed-ului public. */
export const TNS_MAX_FEED_OBJECTS = 300;
/** Câte zile de delta se descarcă dacă bootstrap-ul pe catalogul complet eșuează. */
const BOOTSTRAP_FALLBACK_DAYS = 14;

function pad(value) {
  return String(value).padStart(2, '0');
}

function dayKey(date) {
  return `${date.getUTCFullYear()}${pad(date.getUTCMonth() + 1)}${pad(date.getUTCDate())}`;
}

function hourKey(date) {
  return `${dayKey(date)}T${pad(date.getUTCHours())}`;
}

function dailyFile(date) {
  return `tns_public_objects_${dayKey(date)}.csv.zip`;
}

function hourlyFile(date) {
  return `tns_public_objects_${pad(date.getUTCHours())}.csv.zip`;
}

const FULL_FILE = 'tns_public_objects.csv.zip';

/**
 * Listează fișierele de descărcat:
 *  - bootstrap: catalogul complet o singură dată (vezi `planTnsFallbackFiles`);
 *  - rulare normală: delta de ieri + delta ultimelor 3 ore încheiate.
 * Cheile deja procesate nu se mai descarcă.
 */
export function planTnsFiles({ nowMs = Date.now(), bootstrap = false, processed = [] } = {}) {
  const processedSet = new Set(processed);
  const files = [];

  const push = (key, file) => {
    if (!processedSet.has(key)) files.push({ key, file });
  };

  if (bootstrap) {
    push(`full:${dayKey(new Date(nowMs))}`, FULL_FILE);
    return files;
  }

  const yesterday = new Date(nowMs - DAY_MS);
  push(`daily:${dayKey(yesterday)}`, dailyFile(yesterday));

  for (let hoursBack = 1; hoursBack <= 3; hoursBack += 1) {
    const date = new Date(nowMs - hoursBack * HOUR_MS);
    push(`hourly:${hourKey(date)}`, hourlyFile(date));
  }

  return files;
}

/**
 * Rezervă pentru bootstrap: dacă descărcarea catalogului complet eșuează,
 * reconstruim fereastra din delta zilelor anterioare.
 */
export function planTnsFallbackFiles({ nowMs = Date.now(), processed = [] } = {}) {
  const processedSet = new Set(processed);
  const files = [];
  for (let daysBack = 1; daysBack <= BOOTSTRAP_FALLBACK_DAYS; daysBack += 1) {
    const date = new Date(nowMs - daysBack * DAY_MS);
    const key = `daily:${dayKey(date)}`;
    if (!processedSet.has(key)) files.push({ key, file: dailyFile(date) });
  }
  return files;
}

/** TNS trimite timpii în UT, fără fus: îi normalizăm la ISO cu "Z". */
function toIsoUtc(value) {
  const raw = String(value || '').trim();
  if (!raw) return '';
  const iso = raw.includes('T') ? raw : raw.replace(' ', 'T');
  const withZone = /(?:Z|[+-]\d{2}:?\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const ms = Date.parse(withZone);
  return Number.isFinite(ms) ? new Date(ms).toISOString() : '';
}

function toNumberOrNull(value) {
  const raw = String(value ?? '').trim();
  if (!raw || raw.toLowerCase() === 'nan') return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) ? parsed : null;
}

/** Exclude sursele ne-optice (FRB, unde gravitaționale, neutrini, GRB). */
export function isOpticalTransient(type) {
  const normalized = String(type || '').toLowerCase();
  if (!normalized) return true; // AT neclasificat: poate deveni orice, inclusiv SN
  if (
    normalized.includes('frb') ||
    normalized.includes('gravitational') ||
    normalized.includes('neutrino') ||
    normalized.includes('grb')
  ) {
    return false;
  }
  return (
    normalized.includes('sn') ||
    normalized.includes('nova') ||
    normalized.includes('ilrt') ||
    normalized.includes('lbv') ||
    normalized === 'at' ||
    normalized.startsWith('at ')
  );
}

/** Topic FCM: supernovele au canal dedicat, restul intră pe tranzienți. */
export function tnsTopicFor(type) {
  return String(type || '').toUpperCase().includes('SN')
    ? 'alerts_supernova'
    : 'alerts_transient';
}

/**
 * Prioritatea în feed: supernovele clasificate primele, apoi novele, apoi
 * AT-urile neclasificate. Fără asta, zecile de AT-uri slabe de mag 19–20
 * (publicate zilnic) ar împinge supernovele reale în afara ferestrei feed-ului.
 */
export function transientPriority(record) {
  const type = String(record?.type || '').toUpperCase();
  const prefix = String(record?.namePrefix || '').toUpperCase();
  if (prefix === 'SN' || type.includes('SN')) return 0;
  if (type.includes('NOVA') || type.includes('ILRT') || type.includes('LBV')) return 1;
  return 2;
}

/** Normalizează un rând CSV TNS într-un record stabil. */
export function normalizeTnsRecord(row, nowIso = new Date().toISOString()) {
  const name = String(row?.name || '').trim();
  if (!name) return null;

  const discoveryDate = toIsoUtc(row.discoveryDate);
  if (!discoveryDate) return null;

  const type = String(row.type || '').trim();
  return {
    name,
    namePrefix: String(row.namePrefix || '').trim().toUpperCase(),
    type,
    magnitude: toNumberOrNull(row.discoveryMag),
    ra: toNumberOrNull(row.ra),
    dec: toNumberOrNull(row.dec),
    discoveryDate,
    updatedAt: toIsoUtc(row.lastModified) || nowIso,
    topic: tnsTopicFor(type),
  };
}

/**
 * Un record intră în feed dacă: are coordonate, e sursă optică, respectă pragul
 * de magnitudine și fereastra de 30 zile. Filtrarea se face devreme (și în timpul
 * parsării catalogului complet), ca memoria și starea să rămână mici.
 */
export function isFeedEligible(record, nowMs = Date.now()) {
  if (!record || !record.name) return false;
  if (record.ra === null || record.dec === null) return false;
  if (!isOpticalTransient(record.type)) return false;
  if (record.magnitude !== null && record.magnitude > TNS_MAX_FEED_MAGNITUDE) return false;
  const ms = Date.parse(record.discoveryDate);
  return Number.isFinite(ms) && ms >= nowMs - TNS_FEED_MAX_AGE_DAYS * DAY_MS;
}

/**
 * Descarcă fișierele planificate și întoarce recordurile normalizate.
 * Fișierele inexistente (404) sunt marcate ca procesate.
 */
export async function fetchTnsRecords(files, { onProgress, nowMs = Date.now() } = {}) {
  if (!tnsConfigured()) {
    return { records: [], processed: [] };
  }

  const records = [];
  const processed = [];

  for (const item of files) {
    try {
      // Catalogul complet are ~110 MB: îi dăm un timeout mai mare.
      const isFullCatalog = item.file === FULL_FILE;
      const csv = await fetchTnsCsv(item.file, {
        timeoutMs: isFullCatalog ? 300000 : 120000,
      });
      processed.push(item.key);
      if (!csv) {
        onProgress?.(`${item.file}: indisponibil (404)`);
        continue;
      }

      const rows = parseTnsCsv(csv);
      let kept = 0;
      for (const row of rows) {
        const record = normalizeTnsRecord(row);
        if (isFeedEligible(record, nowMs)) {
          records.push(record);
          kept += 1;
        }
      }
      onProgress?.(`${item.file}: ${rows.length} rânduri, ${kept} relevante`);
    } catch (error) {
      onProgress?.(`${item.file}: eroare (${error.message})`);
    }
  }

  return { records, processed };
}

/** Construiește feed-ul public citit de aplicație. */
export function buildTnsFeed(records, nowMs = Date.now()) {
  const list = Object.values(records || {})
    .filter(record => isFeedEligible(record, nowMs))
    .sort(
      (a, b) =>
        transientPriority(a) - transientPriority(b) ||
        (a.magnitude ?? 99) - (b.magnitude ?? 99) ||
        Date.parse(b.discoveryDate) - Date.parse(a.discoveryDate)
    )
    .slice(0, TNS_MAX_FEED_OBJECTS);

  return {
    generatedAt: new Date(nowMs).toISOString(),
    transients: list.map(record => ({
      name: record.name,
      namePrefix: record.namePrefix,
      type: record.type,
      magnitude: record.magnitude,
      ra: record.ra,
      dec: record.dec,
      discoveryDate: record.discoveryDate,
    })),
  };
}

/** Elimină din starea locală obiectele mai vechi decât fereastra feed-ului. */
export function pruneTnsRecords(records, nowMs = Date.now(), maxAgeDays = 60) {
  const cutoff = nowMs - maxAgeDays * DAY_MS;
  const pruned = {};
  for (const [name, record] of Object.entries(records || {})) {
    const ms = Date.parse(record?.discoveryDate);
    if (Number.isFinite(ms) && ms >= cutoff) pruned[name] = record;
  }
  return pruned;
}
