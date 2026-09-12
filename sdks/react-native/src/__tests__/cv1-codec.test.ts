/**
 * Regression tests for issue #13026:
 * Wire codec 21 (Omi CV1 Opus FS320) must not fall through to PCM8.
 *
 * Native BLE is replaced; connect() → getAudioCodec() is the production path.
 */

jest.mock('react-native', () => ({
  Platform: { OS: 'ios' },
}));

type AnyChar = { uuid: string; read: jest.Mock };

let mockBleManagerImpl: Record<string, unknown> = {};
let encodedCodec = '';

jest.mock('react-native-ble-plx', () => ({
  BleManager: jest.fn().mockImplementation(function BleManagerMock() {
    return { ...mockBleManagerImpl };
  }),
  Subscription: jest.fn(),
  Device: jest.fn(),
}));

import { OmiConnection } from '../OmiConnection';
import { BleAudioCodec } from '../types';
import { mapCodecToName } from '../codecs';

const OMI_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214';
const AUDIO_CODEC_CHARACTERISTIC_UUID = '19b10002-e8f2-537e-4f6c-d104768a1214';

function makeCharacteristic(uuid: string, base64: string): AnyChar {
  return {
    uuid,
    read: jest.fn(() => Promise.resolve({ value: base64 })),
  };
}

function installFakeDevice(base64: string) {
  encodedCodec = base64;
  const device = {
    id: 'synthetic-device',
    name: 'Synthetic',
    discoverAllServicesAndCharacteristics: jest.fn(() => Promise.resolve()),
    services: jest.fn(() =>
      Promise.resolve([
        {
          uuid: OMI_SERVICE_UUID,
          characteristics: () =>
            Promise.resolve([
              makeCharacteristic(AUDIO_CODEC_CHARACTERISTIC_UUID, encodedCodec),
            ]),
        },
      ])
    ),
    cancelConnection: jest.fn(() => Promise.resolve()),
    onDisconnected: jest.fn(() => ({ remove: jest.fn() })),
  };
  mockBleManagerImpl = {
    startDeviceScan: jest.fn(),
    stopDeviceScan: jest.fn(),
    connectToDevice: jest.fn(() => Promise.resolve(device)),
    state: jest.fn(() => Promise.resolve('PoweredOn')),
  };
  return device;
}

describe('CV1 codec 21 (issue #13026)', () => {
  afterEach(() => {
    jest.clearAllMocks();
    mockBleManagerImpl = {};
    encodedCodec = '';
  });

  it('reports Opus FS320 for wire codec 21 instead of falling back to PCM8', async () => {
    installFakeDevice(Buffer.from([21]).toString('base64'));
    const conn = new OmiConnection();
    await expect(conn.connect('synthetic-device')).resolves.toBe(true);
    await expect(conn.getAudioCodec()).resolves.toBe(BleAudioCodec.OPUS_FS320);
    expect(BleAudioCodec.OPUS_FS320).toBe('opus_fs320');
  });

  it('keeps a display name that preserves the 20 ms frame duration', () => {
    expect(mapCodecToName(BleAudioCodec.OPUS_FS320)).toBe('Opus FS320 (20 ms)');
  });

  it('leaves existing PCM8 and DevKit Opus mappings unchanged', async () => {
    installFakeDevice(Buffer.from([1]).toString('base64'));
    const pcm8 = new OmiConnection();
    await expect(pcm8.connect('synthetic-device')).resolves.toBe(true);
    await expect(pcm8.getAudioCodec()).resolves.toBe(BleAudioCodec.PCM8);

    installFakeDevice(Buffer.from([20]).toString('base64'));
    const opus = new OmiConnection();
    await expect(opus.connect('synthetic-device')).resolves.toBe(true);
    await expect(opus.getAudioCodec()).resolves.toBe(BleAudioCodec.OPUS);
  });

  it('still reports PCM16 for codec byte 0', async () => {
    installFakeDevice(Buffer.from([0]).toString('base64'));
    const conn = new OmiConnection();
    await expect(conn.connect('synthetic-device')).resolves.toBe(true);
    await expect(conn.getAudioCodec()).resolves.toBe(BleAudioCodec.PCM16);
  });

  it('still falls back to PCM8 when the characteristic payload is empty', async () => {
    installFakeDevice('');
    const conn = new OmiConnection();
    await expect(conn.connect('synthetic-device')).resolves.toBe(true);
    await expect(conn.getAudioCodec()).resolves.toBe(BleAudioCodec.PCM8);
  });
});
