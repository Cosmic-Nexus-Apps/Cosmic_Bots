// tnsCsv.mjs — citirea listelor publice TNS din CSV-urile staged (oficial recomandate).
//
// TNS (Ofer Yaron) recomandă explicit menținerea listei local, din fișierele
// "tns_public_objects*.csv.zip", în locul interogărilor repetate ale API-ului:
//   • tns_public_objects.csv.zip              — catalogul complet (rescris zilnic)
//   • tns_public_objects_YYYYMMDD.csv.zip     — delta zilei (disponibil a doua zi)
//   • tns_public_objects_HH.csv.zip           — delta orei (ciclu de 24 h)
//
// Descărcarea cere markerul de bot + api_key (POST, form-urlencoded). Implementarea
// de mai jos nu are dependențe: dezarhivarea ZIP se face cu `node:zlib`.

import { inflateRawSync } from 'node:zlib';

const TNS_CSV_BASE = 'https://www.wis-tns.org/system/files/tns_public_objects';

export function tnsAuthMode() {
  if (process.env.TNS_BOT_ID && process.env.TNS_BOT_NAME && process.env.TNS_API_KEY) {
    return 'bot';
  }
  // Alternativa documentată de TNS pentru descărcarea CSV: marker de user,
  // fără API key. Utilă dacă nu vrei să creezi un bot separat.
  if (process.env.TNS_USER_ID && process.env.TNS_USER_NAME) {
    return 'user';
  }
  return null;
}

export function tnsConfigured() {
  return tnsAuthMode() !== null;
}

export function tnsMarkerHeader() {
  const mode = tnsAuthMode();
  if (mode === 'bot') {
    return `tns_marker{"tns_id":${process.env.TNS_BOT_ID},"type": "bot", "name":"${process.env.TNS_BOT_NAME}"}`;
  }
  if (mode === 'user') {
    return `tns_marker{"tns_id":${process.env.TNS_USER_ID},"type": "user", "name":"${process.env.TNS_USER_NAME}"}`;
  }
  throw new Error('TNS nu este configurat (bot sau user).');
}

/**
 * Descarcă un CSV TNS (împachetat ZIP) și îl întoarce ca text.
 * Returnează `null` pentru 404 (fișier încă negenerat / expirat).
 *
 * Mod `bot`: marker de bot + `api_key` în body (recomandat pentru automatizări).
 * Mod `user`: doar marker de user, fără API key (exact ca exemplul din documentația TNS).
 */
export async function fetchTnsCsv(fileName, { timeoutMs = 120000 } = {}) {
  const mode = tnsAuthMode();
  if (!mode) {
    throw new Error(
      'TNS nu este configurat: setează fie TNS_BOT_ID + TNS_BOT_NAME + TNS_API_KEY, fie TNS_USER_ID + TNS_USER_NAME.'
    );
  }

  const headers = { 'User-Agent': tnsMarkerHeader() };
  let body;
  if (mode === 'bot') {
    headers['Content-Type'] = 'application/x-www-form-urlencoded';
    body = new URLSearchParams({ api_key: process.env.TNS_API_KEY }).toString();
  }

  const response = await fetch(`${TNS_CSV_BASE}/${fileName}`, {
    method: 'POST',
    headers,
    body,
    signal: AbortSignal.timeout(timeoutMs),
  });

  if (response.status === 404) return null;
  if (!response.ok) {
    throw new Error(`TNS CSV HTTP ${response.status} (${fileName})`);
  }

  const buffer = Buffer.from(await response.arrayBuffer());
  return unzipFirstFile(buffer);
}

const EOCD_SIGNATURE = 0x06054b50;
const CENTRAL_SIGNATURE = 0x02014b50;
const LOCAL_SIGNATURE = 0x04034b50;

function findEndOfCentralDirectory(buffer) {
  const min = Math.max(0, buffer.length - 0xffff - 22);
  for (let offset = buffer.length - 22; offset >= min; offset -= 1) {
    if (buffer.readUInt32LE(offset) === EOCD_SIGNATURE) return offset;
  }
  return -1;
}

function readCentralDirectory(buffer) {
  const eocd = findEndOfCentralDirectory(buffer);
  if (eocd < 0) throw new Error('ZIP invalid: lipsă EOCD');

  const count = buffer.readUInt16LE(eocd + 10);
  let offset = buffer.readUInt32LE(eocd + 16);
  const entries = [];

  for (let index = 0; index < count; index += 1) {
    if (buffer.readUInt32LE(offset) !== CENTRAL_SIGNATURE) break;
    const method = buffer.readUInt16LE(offset + 10);
    const compressedSize = buffer.readUInt32LE(offset + 20);
    const nameLength = buffer.readUInt16LE(offset + 28);
    const extraLength = buffer.readUInt16LE(offset + 30);
    const commentLength = buffer.readUInt16LE(offset + 32);
    const localOffset = buffer.readUInt32LE(offset + 42);
    const name = buffer.toString('utf8', offset + 46, offset + 46 + nameLength);
    entries.push({ name, method, compressedSize, localOffset });
    offset += 46 + nameLength + extraLength + commentLength;
  }

  return entries;
}

/** Extrage primul fișier CSV dintr-un ZIP cu o singură intrare (stored sau deflate). */
export function unzipFirstFile(buffer) {
  const entries = readCentralDirectory(buffer);
  if (entries.length === 0) throw new Error('ZIP gol');

  const entry =
    entries.find(item => item.name.toLowerCase().endsWith('.csv')) ?? entries[0];
  const headerOffset = entry.localOffset;
  if (buffer.readUInt32LE(headerOffset) !== LOCAL_SIGNATURE) {
    throw new Error('ZIP invalid: header local lipsă');
  }

  const nameLength = buffer.readUInt16LE(headerOffset + 26);
  const extraLength = buffer.readUInt16LE(headerOffset + 28);
  const dataStart = headerOffset + 30 + nameLength + extraLength;
  const raw = buffer.subarray(dataStart, dataStart + entry.compressedSize);

  if (entry.method === 0) return raw.toString('utf8');
  if (entry.method === 8) return inflateRawSync(raw).toString('utf8');
  throw new Error(`ZIP: metodă de compresie nesuportată (${entry.method})`);
}

/** Parser CSV cu suport pentru câmpuri între ghilimele (rapoarte, nume multiple). */
export function parseCsvLine(line) {
  const fields = [];
  let current = '';
  let quoted = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (quoted) {
      if (char === '"') {
        if (line[index + 1] === '"') {
          current += '"';
          index += 1;
        } else {
          quoted = false;
        }
      } else {
        current += char;
      }
    } else if (char === '"') {
      quoted = true;
    } else if (char === ',') {
      fields.push(current);
      current = '';
    } else {
      current += char;
    }
  }
  fields.push(current);
  return fields;
}

/**
 * Parsează un CSV TNS. Prima linie conține intervalul acoperit, a doua este
 * headerul (începe cu "objid"). Sunt tolerate linii goale / BOM.
 */
export function parseTnsCsv(text) {
  const lines = String(text || '')
    .replace(/^\uFEFF/, '')
    .split(/\r?\n/);

  // Prima linie conține intervalul; headerul începe cu "objid" și este pus
  // între ghilimele ("objid","name_prefix",...), deci îl detectăm pe celule.
  let headerIndex = -1;
  let header = [];
  const probeLimit = Math.min(lines.length, 5);
  for (let index = 0; index < probeLimit; index += 1) {
    const cells = parseCsvLine(lines[index]);
    const first = (cells[0] || '').replace(/^\uFEFF/, '').trim().toLowerCase();
    if (first === 'objid') {
      headerIndex = index;
      header = cells.map(name => name.trim().toLowerCase());
      break;
    }
  }
  if (headerIndex < 0) return [];
  const column = name => header.indexOf(name);

  const idx = {
    namePrefix: column('name_prefix'),
    name: column('name'),
    ra: column('ra'),
    dec: column('declination'),
    type: column('type'),
    discoveryDate: column('discoverydate'),
    discoveryMag: column('discoverymag'),
    lastModified: column('lastmodified'),
  };
  if (idx.name < 0) return [];

  const rows = [];
  for (let lineIndex = headerIndex + 1; lineIndex < lines.length; lineIndex += 1) {
    const line = lines[lineIndex];
    if (!line || !line.trim()) continue;
    const fields = parseCsvLine(line);
    const pick = key => (idx[key] >= 0 && fields[idx[key]] !== undefined ? fields[idx[key]].trim() : '');
    const name = pick('name');
    if (!name) continue;

    rows.push({
      name,
      namePrefix: pick('namePrefix'),
      ra: pick('ra'),
      dec: pick('dec'),
      type: pick('type'),
      discoveryDate: pick('discoveryDate'),
      discoveryMag: pick('discoveryMag'),
      lastModified: pick('lastModified'),
    });
  }
  return rows;
}
