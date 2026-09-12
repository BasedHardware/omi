import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { test } from 'node:test';

import { listenOnConnectedPeripheral } from './noble.ts';

const AUDIO_UUID = '19b10001e8f2537e4f6cd104768a1214';

function fixture(overrides: Record<string, unknown> = {}) {
  const characteristic = Object.assign(new EventEmitter(), {
    uuid: AUDIO_UUID,
    subscribeAsync: async () => {},
    unsubscribeAsync: async () => {},
  });
  const peripheral = {
    state: 'connected',
    discoverSomeServicesAndCharacteristicsAsync: async () => ({ characteristics: [characteristic] }),
    disconnectAsync: async () => {},
    ...overrides,
  };
  return { characteristic, peripheral };
}

test('releases the peripheral when connectAsync fails', async () => {
  let disconnected = 0;
  const { peripheral } = fixture({
    state: 'disconnected',
    connectAsync: async () => {
      throw new Error('synthetic connect error');
    },
    disconnectAsync: async () => {
      disconnected += 1;
    },
  });
  await assert.rejects(() => listenOnConnectedPeripheral(peripheral, 'test-device', () => {}), /connect error/);
  assert.equal(disconnected, 1);
});

test('releases the peripheral when discovery fails', async () => {
  let disconnected = 0;
  const { characteristic, peripheral } = fixture({
    discoverSomeServicesAndCharacteristicsAsync: async () => {
      throw new Error('synthetic discovery error');
    },
    disconnectAsync: async () => {
      disconnected += 1;
    },
  });
  await assert.rejects(() => listenOnConnectedPeripheral(peripheral, 'test-device', () => {}), /discovery error/);
  characteristic.emit('data', new Uint8Array([1, 2, 3]));
  assert.equal(disconnected, 1);
});

test('releases the peripheral when the audio characteristic is missing', async () => {
  let disconnected = 0;
  const { peripheral } = fixture({
    discoverSomeServicesAndCharacteristicsAsync: async () => ({ characteristics: [] }),
    disconnectAsync: async () => {
      disconnected += 1;
    },
  });
  await assert.rejects(() => listenOnConnectedPeripheral(peripheral, 'test-device', () => {}), /not found/);
  assert.equal(disconnected, 1);
});

test('unsubscribes and disconnects when subscribe fails', async () => {
  let disconnected = 0;
  let unsubscribed = 0;
  const { characteristic, peripheral } = fixture({
    disconnectAsync: async () => {
      disconnected += 1;
    },
  });
  characteristic.subscribeAsync = async () => {
    throw new Error('synthetic subscribe error');
  };
  characteristic.unsubscribeAsync = async () => {
    unsubscribed += 1;
  };
  await assert.rejects(() => listenOnConnectedPeripheral(peripheral, 'test-device', () => {}), /subscribe error/);
  assert.equal(characteristic.listenerCount('data'), 0);
  assert.equal(unsubscribed, 1);
  assert.equal(disconnected, 1);
});

test('cleanup failures preserve the setup error', async () => {
  const { characteristic, peripheral } = fixture();
  characteristic.subscribeAsync = async () => {
    throw new Error('subscribe failed');
  };
  characteristic.unsubscribeAsync = async () => {
    throw new Error('unsubscribe failed');
  };
  peripheral.disconnectAsync = async () => {
    throw new Error('disconnect failed');
  };
  await assert.rejects(() => listenOnConnectedPeripheral(peripheral, 'test-device', () => {}), /subscribe failed/);
});

test('successful session shares one cleanup operation', async () => {
  let disconnected = 0;
  let unsubscribed = 0;
  const packets: number[][] = [];
  const { characteristic, peripheral } = fixture({
    disconnectAsync: async () => {
      disconnected += 1;
    },
  });
  characteristic.unsubscribeAsync = async () => {
    unsubscribed += 1;
  };
  const session = await listenOnConnectedPeripheral(peripheral, 'test-device', (packet) => packets.push([...packet]));
  characteristic.emit('data', new Uint8Array([3, 4]));
  assert.deepEqual(packets, [[3, 4]]);
  await Promise.all([session.disconnect(), session.disconnect()]);
  characteristic.emit('data', new Uint8Array([5]));
  assert.deepEqual(packets, [[3, 4]]);
  assert.equal(unsubscribed, 1);
  assert.equal(disconnected, 1);
});
