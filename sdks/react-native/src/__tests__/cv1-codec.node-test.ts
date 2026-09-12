/**
 * Regression for #13026: wire codec 21 (Omi CV1 Opus FS320) must not fall
 * through to PCM8. Native BLE is replaced; connect() → getAudioCodec() is the
 * production public path, including the SDK's own base64 decoder.
 */
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { dirname, join } from 'node:path';
import { afterEach, beforeEach, test } from 'node:test';
import { fileURLToPath, pathToFileURL } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const rnMock = pathToFileURL(join(here, 'mocks', 'react-native.mjs')).href;
const bleMock = pathToFileURL(join(here, 'mocks', 'react-native-ble-plx.mjs')).href;

registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier === 'react-native') {
      return { url: rnMock, shortCircuit: true };
    }
    if (specifier === 'react-native-ble-plx') {
      return { url: bleMock, shortCircuit: true };
    }
    // Source files omit extensions (Jest/RN). Node ESM needs them.
    if (
      specifier.startsWith('.') &&
      !/\.(ts|js|mjs|cjs|json)$/.test(specifier)
    ) {
      return nextResolve(`${specifier}.ts`, context);
    }
    return nextResolve(specifier, context);
  },
});

const { setEncodedCodec } = await import('./mocks/react-native-ble-plx.mjs');
const { OmiConnection } = await import('../OmiConnection.ts');
const { BleAudioCodec } = await import('../types.ts');
const { mapCodecToName } = await import('../codecs.ts');

let connection: InstanceType<typeof OmiConnection>;

beforeEach(async () => {
  setEncodedCodec('');
  connection = new OmiConnection();
  assert.equal(await connection.connect('synthetic-device'), true);
});

afterEach(async () => {
  await connection.disconnect();
});

test('CV1 wire codec 21 stays Opus FS320 instead of falling back to PCM8', async () => {
  setEncodedCodec(Buffer.from([21]).toString('base64'));
  assert.equal(await connection.getAudioCodec(), BleAudioCodec.OPUS_FS320);
  assert.equal(BleAudioCodec.OPUS_FS320, 'opus_fs320');
});

test('CV1 display name keeps the 20 ms frame-duration distinction', () => {
  assert.equal(mapCodecToName(BleAudioCodec.OPUS_FS320), 'Opus FS320 (20 ms)');
});

test('existing PCM8 wire codec 1 is unchanged', async () => {
  setEncodedCodec(Buffer.from([1]).toString('base64'));
  assert.equal(await connection.getAudioCodec(), BleAudioCodec.PCM8);
});

test('existing DevKit Opus wire codec 20 is unchanged', async () => {
  setEncodedCodec(Buffer.from([20]).toString('base64'));
  assert.equal(await connection.getAudioCodec(), BleAudioCodec.OPUS);
});

test('codec byte 0 still reports PCM16 (zero is a valid id, not a missing payload)', async () => {
  setEncodedCodec(Buffer.from([0]).toString('base64'));
  assert.equal(await connection.getAudioCodec(), BleAudioCodec.PCM16);
});

test('missing codec characteristic data retains its previous PCM8 fallback', async () => {
  assert.equal(await connection.getAudioCodec(), BleAudioCodec.PCM8);
});
