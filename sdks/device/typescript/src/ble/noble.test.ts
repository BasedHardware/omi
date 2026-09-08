import { describe, expect, mock, test } from 'bun:test';
import { EventEmitter } from 'node:events';
import { stripPacketHeader, PACKET_HEADER_BYTES } from '../index.ts';
import { connectAndListen, createNobleTransport, NOBLE_MISSING } from './index.ts';

describe('stripPacketHeader', () => {
  test('strips 3-byte header', () => {
    const packet = new Uint8Array([1, 2, 3, 10, 20, 30]);
    const payload = stripPacketHeader(packet);
    expect([...payload]).toEqual([10, 20, 30]);
    expect(payload.byteLength).toBe(packet.byteLength - PACKET_HEADER_BYTES);
  });
  test('empty when too short', () => {
    expect(stripPacketHeader(new Uint8Array([1, 2, 3])).byteLength).toBe(0);
    expect(stripPacketHeader(new Uint8Array([1])).byteLength).toBe(0);
  });
});

describe('createNobleTransport', () => {
  test('creates the transport before subscribing to audio', async () => {
    const { subscribe } = mockNobleDiscovery();
    expect(NOBLE_MISSING.includes('@stoprocent/noble')).toBe(true);
    const transport = await createNobleTransport('omi');
    expect(typeof transport.startAudioNotifications).toBe('function');
    expect(typeof transport.stopAudioNotifications).toBe('function');
    expect(subscribe).not.toHaveBeenCalled();
  });
});

function mockNobleDiscovery(hasAudio = true) {
  const audio = new EventEmitter();
  const subscribe = mock(async () => {});
  const unsubscribe = mock(async () => {});
  const disconnect = mock(async () => {});
  const characteristic = Object.assign(audio, {
    uuid: '19b10001e8f2537e4f6cd104768a1214',
    subscribeAsync: subscribe,
    unsubscribeAsync: unsubscribe,
  });
  const peripheral = {
    state: 'connected',
    disconnectAsync: disconnect,
    async discoverSomeServicesAndCharacteristicsAsync(services: string[], characteristics: string[]) {
      // Noble's HCI GATT decoder returns undashed UUIDs and filters by exact
      // membership (stoprocent/noble lib/hci-socket/gatt.js).
      if (!services.includes('19b10000e8f2537e4f6cd104768a1214')) {
        throw new Error('Could not find all requested services');
      }
      return {
        characteristics: hasAudio && characteristics.includes(characteristic.uuid) ? [characteristic] : [],
      };
    },
  };
  mock.module('@stoprocent/noble', () => ({
    default: {
      state: 'poweredOn',
      startScanningAsync: async () => {},
      stopScanningAsync: async () => {},
      connectAsync: async () => peripheral,
    },
  }));
  return { audio, subscribe, unsubscribe, disconnect };
}

describe('connectAndListen discovery', () => {
  test('discovers Omi with Noble UUID filters and receives audio', async () => {
    const { audio, subscribe, unsubscribe, disconnect } = mockNobleDiscovery();
    const packets: number[][] = [];
    const connection = await connectAndListen('omi', (packet) => packets.push([...packet]));

    expect(subscribe).toHaveBeenCalledTimes(1);
    audio.emit('data', Buffer.from([1, 2, 3, 10, 20]));
    expect(packets).toEqual([[1, 2, 3, 10, 20]]);

    await connection.disconnect();
    audio.emit('data', Buffer.from([1, 2, 3, 30]));
    expect(packets).toHaveLength(1);
    expect(unsubscribe).toHaveBeenCalledTimes(1);
    expect(disconnect).toHaveBeenCalledTimes(1);
  });

  test('rejects a device without the audio characteristic', async () => {
    const { subscribe, disconnect } = mockNobleDiscovery(false);

    await expect(connectAndListen('omi', () => {})).rejects.toThrow('Audio characteristic');
    expect(subscribe).not.toHaveBeenCalled();
    expect(disconnect).toHaveBeenCalledTimes(1);
  });
});
