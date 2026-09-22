// tns.mjs — clienți pentru Transient Name Server (supernove, nove, tranzienți).
//
// Necesită cont de bot aprobat de TNS (Wis-TNS/Bot Access) și următoarele variabile:
//   TNS_BOT_ID, TNS_BOT_NAME, TNS_API_KEY
//
// NOTĂ: implementarea folosește API-ul public documentat (get/search + get/object).
// Trebuie validată o dată cu credențiale reale înainte de activare în producție.

const TNS_BASE = 'https://www.wis-tns.org/api';

function configured() {
  return Boolean(process.env.TNS_BOT_ID && process.env.TNS_BOT_NAME && process.env.TNS_API_KEY);
}

function markerHeader() {
  return `tns_marker{"tns_id": ${process.env.TNS_BOT_ID}, "type": "bot", "name": "${process.env.TNS_BOT_NAME}"}`;
}

async function tnsPost(path, data) {
  const response = await fetch(`${TNS_BASE}${path}`, {
    method: 'POST',
    headers: {
      'User-Agent': markerHeader(),
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ api_key: process.env.TNS_API_KEY, data }),
  });
  if (!response.ok) throw new Error(`TNS HTTP ${response.status}`);
  return response.json();
}

function classify(objectType = '') {
  const type = objectType.toUpperCase();
  if (type.includes('SN')) return 'alerts_supernova';
  return 'alerts_transient';
}

/**
 * Obiecte publice raportate recent. Întoarce [] dacă TNS nu e configurat sau
 * nu răspunde — robotul de comete continuă să funcționeze independent.
 */
export async function fetchTnsTransients({ sinceMs = Date.now() - 24 * 3600000 } = {}) {
  if (!configured()) return [];
  try {
    const since = new Date(sinceMs).toISOString().slice(0, 10);
    const today = new Date().toISOString().slice(0, 10);
    const search = await tnsPost('/get/search', {
      public: 'yes',
      discovery_date_start: since,
      discovery_date_end: today,
    });
    const rows = search?.data?.reply ?? [];

    return rows
      .map(row => ({
        name: String(row.objname ?? row.name ?? '').trim(),
        type: String(row.object_type ?? row.type ?? '').trim(),
        magnitude: row.discoverymag != null ? Number(row.discoverymag) : null,
        raDeg: row.ra != null ? Number(row.ra) : null,
        decDeg: row.dec != null ? Number(row.dec) : null,
        discoveryDate: row.discoverydate ? String(row.discoverydate) : '',
        topic: classify(String(row.object_type ?? row.type ?? '')),
      }))
      .filter(row => row.name.length > 0);
  } catch (error) {
    console.error(`[tns] ${error.message}`);
    return [];
  }
}
