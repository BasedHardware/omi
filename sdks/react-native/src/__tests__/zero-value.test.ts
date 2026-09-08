/**
 * Regression tests for issue #12979:
 * A valid zero-valued BLE characteristic must not be treated as absent.
 *
 * - getAudioCodec() with codec byte 0x00 must report PCM16 (codec id 0), not PCM8
 * - getBatteryLevel() with battery byte 0x00 must report 0, not -1
 * - Missing/empty characteristic payloads must still fall back as before.
 */

jest.mock('react-native', () => ({
  Platform: { OS: 'ios' },
}));

type AnyChar = { uuid: string; read: jest.Mock };

let mockBleManagerImpl: Record<string, unknown> = {};

jest.mock('react-native-ble-plx', () => ({
  BleManager: jest.fn().mockImplementation(function BleManagerMock() {
    return { ...mockBleManagerImpl };
  }),
  Subscription: jest.fn(),
  Device: jest.fn(),
}));

import { OmiConnection } from '../OmiConnection';
import { BleAudioCodec } from '../types';

const OMI_SERVICE_UUID = '19b10000-e8f2-537e-4f6c-d104768a1214';
const AUDIO_CODEC_CHARACTERISTIC_UUID = '19b10002-e8f2-537e-4f6c-d104768a1214';
const BATTERY_SERVICE_UUID = '0000180f-0000-1000-8000-00805f9b34fb';
const BATTERY_LEVEL_CHARACTERISTIC_UUID = '00002a19-0000-1000-8000-00805f9b34fb';

const zeroByteBase64 = Buffer.from([0x00]).toString('base64'); // "AA=="

function makeCharacteristic(uuid: string, base64: string): AnyChar {
  return {
    uuid,
    read: jest.fn(() => Promise.resolve({ value: base64 })),
  };
}

/**
 * Install a fake Device with the requested service/characteristic tree and
 * make `new BleManager().connectToDevice()` return it.
 */
function installFakeDevice(serviceToChars: Record<string, AnyChar[]>) {
  const device = {
    id: 'test-device-id',
    name: 'Test Device',
    discoverAllServicesAndCharacteristics: jest.fn(() => Promise.resolve()),
    services: jest.fn(() =>
      Promise.resolve(
        Object.entries(serviceToChars).map(([uuid, chars]) => ({
          uuid,
          characteristics: () => Promise.resolve(chars),
        }))
      )
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

async function connectedConnection(): Promise<OmiConnection> {
  const conn = new OmiConnection();
  const ok = await conn.connect('test-device-id');
  expect(ok).toBe(true);
  return conn;
}

describe('zero-valued BLE characteristic readings (issue #12979)', () => {
  afterEach(() => {
    jest.clearAllMocks();
    mockBleManagerImpl = {};
  });

  it('reports PCM16 when the codec byte is 0 instead of falling back to PCM8', async () => {
    installFakeDevice({
      [OMI_SERVICE_UUID]: [
        makeCharacteristic(AUDIO_CODEC_CHARACTERISTIC_UUID, zeroByteBase64),
      ],
    });

    const conn = await connectedConnection();
    await expect(conn.getAudioCodec()).resolves.toBe(BleAudioCodec.PCM16);
  });

  it('reports battery level 0 instead of -1 when the battery byte is 0', async () => {
    installFakeDevice({
      [BATTERY_SERVICE_UUID]: [
        makeCharacteristic(BATTERY_LEVEL_CHARACTERISTIC_UUID, zeroByteBase64),
      ],
    });

    const conn = await connectedConnection();
    await expect(conn.getBatteryLevel()).resolves.toBe(0);
  });

  it('still falls back when the characteristic payload is empty', async () => {
    installFakeDevice({
      [OMI_SERVICE_UUID]: [
        makeCharacteristic(AUDIO_CODEC_CHARACTERISTIC_UUID, ''),
      ],
      [BATTERY_SERVICE_UUID]: [
        makeCharacteristic(BATTERY_LEVEL_CHARACTERISTIC_UUID, ''),
      ],
    });

    const conn = await connectedConnection();
    await expect(conn.getAudioCodec()).resolves.toBe(BleAudioCodec.PCM8);
    await expect(conn.getBatteryLevel()).resolves.toBe(-1);
  });

  it('still maps non-zero codec ids unchanged (no behavior regression)', async () => {
    installFakeDevice({
      [OMI_SERVICE_UUID]: [
        makeCharacteristic(
          AUDIO_CODEC_CHARACTERISTIC_UUID,
          Buffer.from([20]).toString('base64')
        ),
      ],
    });

    const conn = await connectedConnection();
    await expect(conn.getAudioCodec()).resolves.toBe(BleAudioCodec.OPUS);
  });
});
