// tns.mjs — orchestrates public TNS lists (staged CSVs) for the app feed.
//
// The only data source is the staged CSV, officially recommended by TNS (see
// tnsCsv.mjs). No per-object queries are made: the complete catalog is downloaded
// once during bootstrap, then only daily and hourly deltas are applied.
//
// The result is one normalized record per public object, stored in the bot's
// local state and used to generate the feed consumed by the app.

import { fetchTnsCsv, parseTnsCsv, tnsConfigured } from './tnsCsv.mjs';

const DAY_MS = 24 * 3600000;
const HOUR_MS = 3600000;

/** Keep discoveries in the feed for 30 days (matching the app). */
export const TNS_FEED_MAX_AGE_DAYS = 30;
/** Practical limit: beyond mag ~20, objects are no longer realistic amateur targets. */
export const TNS_MAX_FEED_MAGNITUDE = 20;
/** Safety limit for the public feed size. */
export const TNS_MAX_FEED_OBJECTS = 300;
/** Number of daily deltas to download if the full-catalog bootstrap fails. */
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
 * Lists the files to download:
 *  - bootstrap: the complete catalog once (see `planTnsFallbackFiles`);
 *  - normal run: yesterday's delta plus the last 3 completed hourly deltas.
 * Files that have already been processed are not downloaded again.
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
 * Bootstrap fallback: if downloading the complete catalog fails, rebuild the
 * window from previous daily deltas.
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

/** TNS timestamps are in UT without a time-zone suffix; normalize them to ISO with "Z". */
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

/** Exclude non-optical sources (FRBs, gravitational waves, neutrinos, GRBs). */
export function isOpticalTransient(type) {
  const normalized = String(type || '').toLowerCase();
  if (!normalized) return true; // Unclassified AT: it could become anything, including an SN.
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

/** FCM topic: supernovae have a dedicated channel; other objects use the transient topic. */
export function tnsTopicFor(type) {
  return String(type || '').toUpperCase().includes('SN')
    ? 'alerts_supernova'
    : 'alerts_transient';
}

/**
 * Feed priority: classified supernovae first, then novae, then unclassified ATs.
 * Otherwise, dozens of faint mag 19–20 ATs (published daily) would push real
 * supernovae out of the feed window.
 */
export function transientPriority(record) {
  const type = String(record?.type || '').toUpperCase();
  const prefix = String(record?.namePrefix || '').toUpperCase();
  if (prefix === 'SN' || type.includes('SN')) return 0;
  if (type.includes('NOVA') || type.includes('ILRT') || type.includes('LBV')) return 1;
  return 2;
}

/** Normalize a TNS CSV row into a stable record. */
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
 * A record is included in the feed if it has coordinates, is an optical source,
 * meets the magnitude threshold, and falls within the 30-day window. Filter
 * early (including while parsing the full catalog) to keep memory and state small.
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
 * Downloads the planned files and returns normalized records.
 * Missing files (404) are marked as processed.
 */
export async function fetchTnsRecords(files, { onProgress, nowMs = Date.now() } = {}) {
  if (!tnsConfigured()) {
    return { records: [], processed: [] };
  }

  const records = [];
  const processed = [];

  for (const item of files) {
    try {
      // The full catalog is ~110 MB, so give it a longer timeout.
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

/** Builds the public feed consumed by the app. */
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

/** Removes objects older than the feed window from local state. */
export function pruneTnsRecords(records, nowMs = Date.now(), maxAgeDays = 60) {
  const cutoff = nowMs - maxAgeDays * DAY_MS;
  const pruned = {};
  for (const [name, record] of Object.entries(records || {})) {
    const ms = Date.parse(record?.discoveryDate);
    if (Number.isFinite(ms) && ms >= cutoff) pruned[name] = record;
  }
  return pruned;
}
