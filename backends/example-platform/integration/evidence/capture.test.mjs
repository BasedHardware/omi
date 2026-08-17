import { describe, it } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, writeFile, access } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import {
  captureWindow,
  captureSimulator,
  bakeClassIntoFilename,
  sidecarPathFor,
  EVIDENCE_CLASS,
} from './capture.mjs';
import { describeImage, sha256File } from './identity.mjs';

function crc32(buf) {
  let c = 0xffffffff;
  for (let i = 0; i < buf.length; i++) {
    c ^= buf[i];
    for (let k = 0; k < 8; k++) {
      c = c & 1 ? (0xedb88320 ^ (c >>> 1)) : c >>> 1;
    }
  }
  return (c ^ 0xffffffff) >>> 0;
}

function buildPng({ width, height, padBytes = 0 }) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const ihdrData = Buffer.alloc(13);
  ihdrData.writeUInt32BE(width, 0);
  ihdrData.writeUInt32BE(height, 4);
  ihdrData[8] = 8;
  ihdrData[9] = 2;
  ihdrData[10] = 0;
  ihdrData[11] = 0;
  ihdrData[12] = 0;
  const type = Buffer.from('IHDR');
  const len = Buffer.alloc(4);
  len.writeUInt32BE(13, 0);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(Buffer.concat([type, ihdrData])), 0);
  const core = Buffer.concat([signature, len, type, ihdrData, crc]);
  if (padBytes <= 0) return core;
  return Buffer.concat([core, Buffer.alloc(padBytes, 0xcd)]);
}

async function tempDir() {
  return mkdtemp(path.join(tmpdir(), 'omi-evidence-capture-'));
}

/**
 * Fake runner that materializes a PNG at the last argv path when the
 * capture binary is invoked — no real screencapture/simctl.
 */
function fakeRunner({ windowIdStdout = '', windowIdCode = 1, capturePayload } = {}) {
  const calls = [];
  const runCommand = async (command, args) => {
    calls.push({ command, args: [...args] });
    if (command === '/usr/bin/swift') {
      return { stdout: windowIdStdout, stderr: '', code: windowIdCode };
    }
    if (command === '/usr/sbin/screencapture' || command === '/usr/bin/xcrun') {
      const outFile = args[args.length - 1];
      await writeFile(outFile, capturePayload ?? buildPng({ width: 64, height: 48, padBytes: 100 }));
      return { stdout: '', stderr: '', code: 0 };
    }
    return { stdout: '', stderr: `unexpected command ${command}`, code: 127 };
  };
  return { runCommand, calls };
}

describe('capture.bakeClassIntoFilename', () => {
  // red-proof: return outPath unchanged even when class is absent from basename
  it('prefixes the basename with the evidence class when missing', () => {
    const out = bakeClassIntoFilename('/tmp/shot.png', 'window_composite');
    assert.equal(path.basename(out), 'window_composite-shot.png');
  });

  // red-proof: always double-prefix even when class is already present
  it('leaves the path alone when the class is already in the basename', () => {
    const input = '/tmp/window_composite-shot.png';
    assert.equal(bakeClassIntoFilename(input, 'window_composite'), input);
  });
});

describe('capture.captureWindow', () => {
  // red-proof: set targeting to 'window' even when resolveWindowId returns null
  it('records targeting:display_fallback and class window_composite when no window id resolves', async () => {
    const dir = await tempDir();
    const outPath = path.join(dir, 'desk.png');
    const payload = buildPng({ width: 80, height: 60, padBytes: 50 });
    const { runCommand, calls } = fakeRunner({
      windowIdCode: 1,
      windowIdStdout: '',
      capturePayload: payload,
    });

    const result = await captureWindow({
      appName: 'Omi Dev',
      outPath,
      runCommand,
      resolveWindowId: async () => null,
    });

    assert.equal(result.class, EVIDENCE_CLASS.WINDOW_COMPOSITE);
    assert.equal(result.targeting, 'display_fallback');
    assert.ok(path.basename(result.path).includes('window_composite'));
    assert.equal(result.bytes, payload.length);
    assert.equal(result.sha256, await sha256File(result.path));
    assert.match(result.capturedAt, /^\d{4}-\d{2}-\d{2}T/);

    const screencapture = calls.find((c) => c.command === '/usr/sbin/screencapture');
    assert.ok(screencapture, 'screencapture must be invoked');
    assert.deepEqual(screencapture.args, ['-x', result.path]);
    assert.ok(!screencapture.args.includes('-l'), 'fallback must not claim -l window targeting');

    const sidecar = JSON.parse(await readFile(sidecarPathFor(result.path), 'utf8'));
    assert.equal(sidecar.class, 'window_composite');
    assert.equal(sidecar.targeting, 'display_fallback');
    assert.equal(sidecar.sha256, result.sha256);
    assert.equal(sidecar.appName, 'Omi Dev');
  });

  // red-proof: omit -l from screencapture args even when a window id is resolved
  it('targets -l <windowId> and records targeting:window when a CGWindowID resolves', async () => {
    const dir = await tempDir();
    const outPath = path.join(dir, 'win.png');
    const payload = buildPng({ width: 100, height: 70, padBytes: 20 });
    const { runCommand, calls } = fakeRunner({ capturePayload: payload });

    const result = await captureWindow({
      appName: 'Omi Dev',
      outPath,
      runCommand,
      resolveWindowId: async () => 4242,
    });

    assert.equal(result.class, 'window_composite');
    assert.equal(result.targeting, 'window');

    const screencapture = calls.find((c) => c.command === '/usr/sbin/screencapture');
    assert.ok(screencapture);
    assert.deepEqual(screencapture.args, ['-x', '-l', '4242', result.path]);

    const onDisk = await readFile(result.path);
    assert.ok(onDisk.equals(payload));
    const dims = await describeImage(result.path);
    assert.deepEqual(dims, { width: 100, height: 70, format: 'png' });

    const sidecar = JSON.parse(await readFile(sidecarPathFor(result.path), 'utf8'));
    assert.equal(sidecar.targeting, 'window');
    assert.equal(sidecar.class, 'window_composite');
  });

  // red-proof: swallow non-zero screencapture exit codes
  it('throws when screencapture exits non-zero', async () => {
    const dir = await tempDir();
    const runCommand = async (command, args) => {
      if (command === '/usr/sbin/screencapture') {
        return { stdout: '', stderr: 'permission denied', code: 1 };
      }
      return { stdout: '', stderr: '', code: 0 };
    };
    await assert.rejects(
      () =>
        captureWindow({
          appName: 'Omi Dev',
          outPath: path.join(dir, 'fail.png'),
          runCommand,
          resolveWindowId: async () => null,
        }),
      /screencapture failed/i,
    );
  });
});

describe('capture.captureSimulator', () => {
  // red-proof: write class 'window_composite' into the simulator result
  it('invokes simctl io screenshot, bakes simulator_capture into path+sidecar', async () => {
    const dir = await tempDir();
    const outPath = path.join(dir, 'sim.png');
    const payload = buildPng({ width: 1170, height: 2532, padBytes: 10 });
    const { runCommand, calls } = fakeRunner({ capturePayload: payload });

    const result = await captureSimulator({
      udid: 'AAAA-BBBB-CCCC',
      outPath,
      runCommand,
    });

    assert.equal(result.class, EVIDENCE_CLASS.SIMULATOR_CAPTURE);
    assert.equal(result.targeting, 'simulator');
    assert.ok(path.basename(result.path).includes('simulator_capture'));
    assert.equal(result.bytes, payload.length);
    assert.equal(result.sha256, await sha256File(result.path));

    const simctl = calls.find((c) => c.command === '/usr/bin/xcrun');
    assert.ok(simctl);
    assert.deepEqual(simctl.args, [
      'simctl',
      'io',
      'AAAA-BBBB-CCCC',
      'screenshot',
      result.path,
    ]);

    const sidecar = JSON.parse(await readFile(sidecarPathFor(result.path), 'utf8'));
    assert.equal(sidecar.class, 'simulator_capture');
    assert.equal(sidecar.udid, 'AAAA-BBBB-CCCC');
    assert.equal(sidecar.targeting, 'simulator');
    await access(result.path);
  });
});
