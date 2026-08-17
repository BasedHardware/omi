import { appendFile, mkdir, readFile } from 'node:fs/promises';
import path from 'node:path';

export const LEDGER_FILENAME = 'evidence.jsonl';

const REQUIRED_FIELDS = ['class', 'path', 'sha256', 'bytes', 'capturedAt'];

/**
 * @typedef {{
 *   class: string,
 *   path: string,
 *   sha256: string,
 *   bytes: number,
 *   capturedAt: string,
 *   label?: string|null,
 *   notes?: string|null,
 * }} EvidenceEntry
 */

function ledgerPath(dir) {
  return path.join(dir, LEDGER_FILENAME);
}

/**
 * Append one evidence entry to the JSONL ledger in `dir`.
 * Creates the directory and ledger file if needed.
 *
 * @param {string} dir
 * @param {EvidenceEntry} entry
 * @returns {Promise<EvidenceEntry>}
 */
export async function recordEvidence(dir, entry) {
  if (!dir) throw new Error('recordEvidence requires dir');
  if (!entry || typeof entry !== 'object') {
    throw new Error('recordEvidence requires an entry object');
  }
  for (const field of REQUIRED_FIELDS) {
    if (entry[field] === undefined || entry[field] === null || entry[field] === '') {
      throw new Error(`recordEvidence entry missing required field: ${field}`);
    }
  }
  if (typeof entry.bytes !== 'number' || !Number.isFinite(entry.bytes)) {
    throw new Error('recordEvidence entry.bytes must be a finite number');
  }

  /** @type {EvidenceEntry} */
  const row = {
    class: entry.class,
    path: entry.path,
    sha256: entry.sha256,
    bytes: entry.bytes,
    capturedAt: entry.capturedAt,
    label: entry.label ?? null,
    notes: entry.notes ?? null,
  };

  await mkdir(dir, { recursive: true });
  await appendFile(ledgerPath(dir), `${JSON.stringify(row)}\n`, 'utf8');
  return row;
}

/**
 * Read every evidence row from the ledger (empty array if missing).
 *
 * @param {string} dir
 * @returns {Promise<EvidenceEntry[]>}
 */
export async function readLedger(dir) {
  let raw;
  try {
    raw = await readFile(ledgerPath(dir), 'utf8');
  } catch (err) {
    if (err && err.code === 'ENOENT') return [];
    throw err;
  }
  const lines = raw.split('\n').filter((line) => line.length > 0);
  return lines.map((line, i) => {
    try {
      return JSON.parse(line);
    } catch {
      throw new Error(`corrupt evidence ledger line ${i + 1} in ${ledgerPath(dir)}`);
    }
  });
}

/**
 * Group ledger counts by evidence class.
 *
 * @param {string} dir
 * @returns {Promise<{total: number, byClass: Record<string, number>}>}
 */
export async function summarize(dir) {
  const entries = await readLedger(dir);
  /** @type {Record<string, number>} */
  const byClass = {};
  for (const entry of entries) {
    const key = entry.class;
    byClass[key] = (byClass[key] ?? 0) + 1;
  }
  return { total: entries.length, byClass };
}
