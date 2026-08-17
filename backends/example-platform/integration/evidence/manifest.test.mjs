import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { recordEvidence, readLedger, summarize, LEDGER_FILENAME } from './manifest.mjs';

async function tempDir() {
  return mkdtemp(path.join(tmpdir(), 'omi-evidence-manifest-'));
}

function baseEntry(overrides = {}) {
  return {
    class: 'window_composite',
    path: '/tmp/window_composite-shot.png',
    sha256: 'a'.repeat(64),
    bytes: 12000,
    capturedAt: '2026-08-08T05:00:00.000Z',
    label: 'after-launch',
    notes: null,
    ...overrides,
  };
}

describe('manifest.recordEvidence', () => {
  // red-proof: write pretty-printed JSON (array) instead of one JSON object per line
  it('appends a single JSON object per call as a JSONL line with required fields', async () => {
    const dir = await tempDir();
    const entry = baseEntry({
      class: 'webview_snapshot',
      path: '/tmp/webview_snapshot-home.png',
      sha256: 'b'.repeat(64),
      bytes: 9999,
      label: 'surface',
      notes: 'WKWebView.takeSnapshot',
    });

    const written = await recordEvidence(dir, entry);
    assert.equal(written.class, 'webview_snapshot');
    assert.equal(written.notes, 'WKWebView.takeSnapshot');

    const raw = await readFile(path.join(dir, LEDGER_FILENAME), 'utf8');
    const lines = raw.split('\n').filter(Boolean);
    assert.equal(lines.length, 1);
    // Exactly one JSON value on the line — not a wrapped array.
    const parsed = JSON.parse(lines[0]);
    assert.equal(parsed.class, 'webview_snapshot');
    assert.equal(parsed.path, '/tmp/webview_snapshot-home.png');
    assert.equal(parsed.sha256, 'b'.repeat(64));
    assert.equal(parsed.bytes, 9999);
    assert.equal(parsed.capturedAt, '2026-08-08T05:00:00.000Z');
    assert.equal(parsed.label, 'surface');
    assert.equal(parsed.notes, 'WKWebView.takeSnapshot');
    assert.equal(Object.prototype.hasOwnProperty.call(parsed, 'label'), true);
    assert.equal(Object.prototype.hasOwnProperty.call(parsed, 'notes'), true);
  });

  // red-proof: open the ledger with 'w' (truncate) instead of append
  it('is append-only — a second record leaves the first line intact', async () => {
    const dir = await tempDir();
    await recordEvidence(dir, baseEntry({ class: 'window_composite', sha256: '1'.repeat(64) }));
    await recordEvidence(dir, baseEntry({ class: 'simulator_capture', sha256: '2'.repeat(64) }));

    const raw = await readFile(path.join(dir, LEDGER_FILENAME), 'utf8');
    const lines = raw.split('\n').filter(Boolean);
    assert.equal(lines.length, 2);
    assert.equal(JSON.parse(lines[0]).sha256, '1'.repeat(64));
    assert.equal(JSON.parse(lines[0]).class, 'window_composite');
    assert.equal(JSON.parse(lines[1]).sha256, '2'.repeat(64));
    assert.equal(JSON.parse(lines[1]).class, 'simulator_capture');
  });

  // red-proof: drop the required-field check for `class`
  it('rejects an entry missing evidence class — unclassified artifacts are useless', async () => {
    const dir = await tempDir();
    const bad = baseEntry();
    delete bad.class;
    await assert.rejects(() => recordEvidence(dir, bad), /missing required field: class/);
  });
});

describe('manifest.readLedger', () => {
  // red-proof: return [] even when the ledger has rows
  it('round-trips every recorded row including class and sha256', async () => {
    const dir = await tempDir();
    await recordEvidence(
      dir,
      baseEntry({ class: 'webview_snapshot', sha256: 'c'.repeat(64), label: 'a' }),
    );
    await recordEvidence(
      dir,
      baseEntry({ class: 'window_composite', sha256: 'd'.repeat(64), label: 'b' }),
    );

    const rows = await readLedger(dir);
    assert.equal(rows.length, 2);
    assert.equal(rows[0].class, 'webview_snapshot');
    assert.equal(rows[0].sha256, 'c'.repeat(64));
    assert.equal(rows[1].class, 'window_composite');
    assert.equal(rows[1].sha256, 'd'.repeat(64));
  });

  // red-proof: throw on missing ledger instead of returning []
  it('returns an empty array when no ledger exists yet', async () => {
    const dir = await tempDir();
    assert.deepEqual(await readLedger(dir), []);
  });
});

describe('manifest.summarize', () => {
  // red-proof: count every row under a single 'unknown' key instead of grouping by entry.class
  it('groups counts by the recorded evidence class field', async () => {
    const dir = await tempDir();
    await recordEvidence(dir, baseEntry({ class: 'webview_snapshot', sha256: 'e'.repeat(64) }));
    await recordEvidence(dir, baseEntry({ class: 'webview_snapshot', sha256: 'f'.repeat(64) }));
    await recordEvidence(dir, baseEntry({ class: 'window_composite', sha256: '0'.repeat(64) }));
    await recordEvidence(dir, baseEntry({ class: 'simulator_capture', sha256: '9'.repeat(64) }));

    // Hand-check the raw ledger classes so summarize cannot fake a constant.
    const rawLines = (await readFile(path.join(dir, LEDGER_FILENAME), 'utf8'))
      .split('\n')
      .filter(Boolean)
      .map((l) => JSON.parse(l).class);
    assert.deepEqual(rawLines, [
      'webview_snapshot',
      'webview_snapshot',
      'window_composite',
      'simulator_capture',
    ]);

    const summary = await summarize(dir);
    assert.equal(summary.total, 4);
    assert.deepEqual(summary.byClass, {
      webview_snapshot: 2,
      window_composite: 1,
      simulator_capture: 1,
    });
  });
});

describe('manifest ledger integrity', () => {
  // red-proof: JSON.parse each line without surfacing corruption
  it('throws on a corrupt JSONL line rather than silently skipping', async () => {
    const dir = await tempDir();
    await writeFile(path.join(dir, LEDGER_FILENAME), '{"class":"x"}\nNOT-JSON\n', 'utf8');
    await assert.rejects(() => readLedger(dir), /corrupt evidence ledger line 2/);
  });
});
