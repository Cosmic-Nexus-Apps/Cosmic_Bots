// mpc.mjs — comets from the official MPC list (CometEls.txt).
// Uses the same selection logic as the app (src/lib/mpcComets.ts), so the bot
// announces exactly the comets that may appear in the catalog.

export const PERIHELION_PAST_MS = 365 * 24 * 3600000;
export const PERIHELION_FUTURE_MS = 730 * 24 * 3600000;
export const MAX_ABSOLUTE_MAGNITUDE = 12;
export const MAX_CANDIDATES = 20;

const MPC_URL = 'https://www.minorplanetcenter.net/iau/MPCORB/CometEls.txt';

function normalizeDesignation(designation) {
  return designation
    .toUpperCase()
    .replace(/\s+/g, ' ')
    .replace(/^[CPDIAX]\//, '')
    .trim();
}

function toJplDesignation(namePart) {
  const numbered = namePart.match(/^(\d+[PDI])\//);
  return numbered ? numbered[1] : namePart.trim();
}

function parsePerihelionMs(line) {
  const year = parseInt(line.slice(14, 18).trim(), 10);
  const month = parseInt(line.slice(19, 21).trim(), 10);
  const day = parseFloat(line.slice(22, 26));
  if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null;
  const ms = Date.UTC(year, month - 1, 1) + (day - 1) * 86400000;
  return Number.isFinite(ms) ? ms : null;
}

export async function fetchMpcComets(nowMs = Date.now()) {
  const response = await fetch(MPC_URL, {
    headers: { 'User-Agent': 'CosmicAtlasAlertsBot/1.0 (+https://cosmic-atlas.app)' },
  });
  if (!response.ok) throw new Error(`MPC HTTP ${response.status}`);
  const text = await response.text();
  const lines = text.split(/\r?\n/).filter(line => line.trim().length > 0);
  const candidates = [];

  for (const line of lines) {
    const magnitude = parseFloat(line.slice(91, 96));
    if (!Number.isFinite(magnitude) || magnitude > MAX_ABSOLUTE_MAGNITUDE) continue;

    const perihelionMs = parsePerihelionMs(line);
    if (perihelionMs === null) continue;
    if (perihelionMs < nowMs - PERIHELION_PAST_MS) continue;
    if (perihelionMs > nowMs + PERIHELION_FUTURE_MS) continue;

    const rawName = line.slice(102, 160).trim().split(/\s{2,}/)[0].trim();
    if (!rawName) continue;

    const parenIdx = rawName.indexOf(' (');
    const title = parenIdx >= 0 ? rawName.slice(0, parenIdx).trim() : rawName;
    const designation = toJplDesignation(title);
    if (!designation || !/[A-Za-z0-9]/.test(designation)) continue;

    const perihelionDate = new Date(perihelionMs).toISOString().slice(0, 10);
    candidates.push({
      designation,
      key: normalizeDesignation(designation),
      displayName: rawName,
      magnitude,
      perihelionDate,
    });
  }

  candidates.sort(
    (a, b) =>
      Math.abs(Date.parse(a.perihelionDate) - nowMs) - Math.abs(Date.parse(b.perihelionDate) - nowMs) ||
      a.magnitude - b.magnitude
  );
  const unique = new Map();
  for (const candidate of candidates) {
    if (!unique.has(candidate.key)) unique.set(candidate.key, candidate);
  }
  return [...unique.values()].slice(0, MAX_CANDIDATES);
}
