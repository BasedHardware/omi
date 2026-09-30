import { describe, expect, mock, test } from 'bun:test';
import { EventEmitter } from 'node:events';
import { stripPacketHeader, PACKET_HEADER_BYTES } from '../index.ts';
import { connectAndListen, createNobleTransport } from './index.ts';

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
  test('gives an install hint when the optional Noble import fails', () => {
    // Isolate the module cache: a throwing mock cannot replace an already loaded
    // module in Bun, and this path must not initialize a native Bluetooth adapter.
    const result = Bun.spawnSync([
      process.execPath,
      '--eval',
      `import { mock } from 'bun:test';
       import { createNobleTransport } from './index.ts';
       mock.module('@stoprocent/noble', () => {
         throw Object.assign(new Error("Cannot find module '@stoprocent/noble'"), { code: 'MODULE_NOT_FOUND' });
       });
       try {
         await createNobleTransport('omi');
         console.log('unexpected success');
       } catch (error) {
         console.log(error.message);
       }`,
    ], { cwd: import.meta.dir });

    expect(result.exitCode).toBe(0);
    expect(result.stdout.toString().trim()).toBe(
      'Optional BLE dependency missing. Install with: bun add @stoprocent/noble (or npm i @stoprocent/noble)'
    );
  });

  test('creates the transport before subscribing to audio', async () => {
    const { subscribe } = mockNobleDiscovery();
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
