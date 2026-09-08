import { afterEach, beforeEach, expect, mock, test } from 'bun:test';

let encodedCodec = '';
const device = {
  discoverAllServicesAndCharacteristics: async () => {},
  onDisconnected: () => {},
  cancelConnection: async () => {},
  services: async () => [{
    uuid: '19b10000-e8f2-537e-4f6c-d104768a1214',
    characteristics: async () => [{
      uuid: '19b10002-e8f2-537e-4f6c-d104768a1214',
      read: async () => ({ value: encodedCodec }),
    }],
  }],
};

// Only the native transport is replaced; discovery, base64 decoding and codec
// selection all execute the production public SDK path. No device or network.
mock.module('react-native', () => ({ Platform: { OS: 'ios' } }));
mock.module('react-native-ble-plx', () => ({
  BleManager: class {
    async connectToDevice() { return device; }
  },
}));

const { OmiConnection } = await import('../../sdks/react-native/src/OmiConnection');
const { BleAudioCodec } = await import('../../sdks/react-native/src/types');
const { mapCodecToName } = await import('../../sdks/react-native/src/codecs');
let connection: InstanceType<typeof OmiConnection>;

beforeEach(async () => {
  encodedCodec = '';
  connection = new OmiConnection();
  expect(await connection.connect('synthetic-device')).toBe(true);
});

afterEach(async () => {
  await connection.disconnect();
});

test('CV1 wire codec 21 stays Opus FS320 instead of falling back to PCM8', async () => {
  // sdks/device/PROTOCOL.md: CV1 reports 21, 320 samples per 20 ms frame.
  encodedCodec = Buffer.from([21]).toString('base64');
  expect(await connection.getAudioCodec()).toBe('opus_fs320');
  expect(BleAudioCodec.OPUS_FS320).toBe('opus_fs320');
});

test('CV1 has a codec name that preserves its frame-duration distinction', () => {
  expect(mapCodecToName('opus_fs320' as typeof BleAudioCodec.OPUS_FS320)).toBe('Opus FS320 (20 ms)');
});

test.each([
  [1, 'pcm8'],
  [20, 'opus'],
])('existing codec %i remains %s', async (wire, expected) => {
  encodedCodec = Buffer.from([Number(wire)]).toString('base64');
  expect(await connection.getAudioCodec()).toBe(expected);
});

test('missing codec characteristic data retains its previous fallback', async () => {
  expect(await connection.getAudioCodec()).toBe('pcm8');
});
