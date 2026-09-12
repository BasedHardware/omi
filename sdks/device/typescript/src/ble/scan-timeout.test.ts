/**
 * Regression for #12989: scanForDevices must end when the adapter stays quiet.
 * Native Noble is replaced; the exported scan function is the production path.
 */
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const mockUrl = pathToFileURL(
  join(dirname(fileURLToPath(import.meta.url)), 'noble-scan-mock.mjs')
).href;

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === '@stoprocent/noble') {
      return { url: mockUrl, shortCircuit: true };
    }
    return nextResolve(specifier, context);
  },
});

const mock = await import('./noble-scan-mock.mjs');
const { scanForDevices } = await import('./noble.ts');

async function withDeadline(work, ms, label) {
  let timer;
  const timeout = new Promise((_, reject) => {
    timer = setTimeout(() => reject(new Error(label)), ms);
  });
  try {
    return await Promise.race([work, timeout]);
  } finally {
    clearTimeout(timer);
  }
}

test('quiet adapter still ends the scan and stops Noble', async () => {
  mock.resetAdapter();
  const devices = await withDeadline(scanForDevices(40), 1000, 'scan hung on a quiet adapter');
  assert.deepEqual(devices, []);
  assert.equal(mock.starts, 1);
  assert.equal(mock.stops, 1);
});

test('keeps advertisements found before the adapter goes quiet', async () => {
  mock.resetAdapter();
  mock.setDiscoverImpl(async function* () {
    yield { id: 'cv1', advertisement: { localName: 'Omi' }, rssi: -70 };
    await new Promise(() => {});
  });
  const devices = await withDeadline(
    scanForDevices(40),
    1000,
    'scan hung after the first advertisement'
  );
  assert.deepEqual(devices, [{ id: 'cv1', name: 'Omi', rssi: -70 }]);
  assert.equal(mock.stops, 1);
});

test('returns as soon as discovery ends without waiting for the unused deadline', async () => {
  mock.resetAdapter();
  mock.setDiscoverImpl(async function* () {
    yield { id: 'only', advertisement: { localName: 'Omi' }, rssi: -40 };
  });
  const started = Date.now();
  const devices = await withDeadline(
    scanForDevices(5000),
    1000,
    'scan waited on an unused 5s deadline'
  );
  assert.ok(Date.now() - started < 1000);
  assert.deepEqual(devices, [{ id: 'only', name: 'Omi', rssi: -40 }]);
  assert.equal(mock.stops, 1);
});
