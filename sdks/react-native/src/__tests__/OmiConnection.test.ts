import { BleManager } from 'react-native-ble-plx';
import { OmiConnection } from '../OmiConnection';
import { BleAudioCodec } from '../types';

jest.mock('react-native-ble-plx', () => ({
  BleManager: jest.fn(),
}));

describe('BLE characteristic values', () => {
  let connection: OmiConnection;
  let payload: string | null;

  beforeEach(async () => {
    const characteristic = (uuid: string) => ({
      uuid,
      read: jest.fn(async () => ({ value: payload })),
    });
    const device = {
      discoverAllServicesAndCharacteristics: jest.fn(async () => {}),
      onDisconnected: jest.fn(() => ({ remove: jest.fn() })),
      services: jest.fn(async () => [
        {
          uuid: '19b10000-e8f2-537e-4f6c-d104768a1214',
          characteristics: async () => [
            characteristic('19b10002-e8f2-537e-4f6c-d104768a1214'),
          ],
        },
        {
          uuid: '0000180f-0000-1000-8000-00805f9b34fb',
          characteristics: async () => [
            characteristic('00002a19-0000-1000-8000-00805f9b34fb'),
          ],
        },
      ]),
    };
    (BleManager as jest.Mock).mockImplementation(() => ({
      connectToDevice: jest.fn(async () => device),
    }));
    connection = new OmiConnection();
    expect(await connection.connect('test-device')).toBe(true);
  });

  it.each([
    [0, BleAudioCodec.PCM16],
    [1, BleAudioCodec.PCM8],
    [20, BleAudioCodec.OPUS],
  ])('decodes codec byte %i', async (byte, codec) => {
    payload = Buffer.from([byte]).toString('base64');
    expect(await connection.getAudioCodec()).toBe(codec);
  });

  it.each([0, 1, 20, 100])('preserves battery level %i', async (byte) => {
    payload = Buffer.from([byte]).toString('base64');
    expect(await connection.getBatteryLevel()).toBe(byte);
  });

  it.each(['', null])(
    'keeps defaults for missing payload %p',
    async (value) => {
      payload = value;
      expect(await connection.getAudioCodec()).toBe(BleAudioCodec.PCM8);
      expect(await connection.getBatteryLevel()).toBe(-1);
    }
  );
});
