import { expect, mock, test } from 'bun:test';
import { EventEmitter } from 'node:events';

let peripheral: any;
mock.module('@stoprocent/noble', () => ({
  default: {
    startScanningAsync: async () => {},
    waitForPoweredOnAsync: async () => {},
    connectAsync: async () => peripheral,
  },
}));
const { connectAndListen } = await import('./noble.ts');

function fixture() {
  const characteristic = Object.assign(new EventEmitter(), {
    uuid: '19b10001e8f2537e4f6cd104768a1214',
    subscribeAsync: mock(async () => {}),
    unsubscribeAsync: mock(async () => {}),
  });
  peripheral = {
    state: 'connected',
    discoverSomeServicesAndCharacteristicsAsync: mock(async () => ({ characteristics: [characteristic] })),
    disconnectAsync: mock(async () => {}),
  };
  return characteristic;
}

for (const stage of ['connect', 'discovery', 'missing', 'subscribe']) {
  test(`releases acquired resources when ${stage} fails`, async () => {
    const characteristic = fixture();
    const failure = new Error(`synthetic ${stage} error`);
    if (stage === 'connect') {
      peripheral.state = 'disconnected';
      peripheral.connectAsync = async () => { throw failure; };
    } else if (stage === 'discovery') {
      peripheral.discoverSomeServicesAndCharacteristicsAsync = async () => { throw failure; };
    } else if (stage === 'missing') {
      peripheral.discoverSomeServicesAndCharacteristicsAsync = async () => ({ characteristics: [] });
    } else {
      characteristic.subscribeAsync.mockImplementation(async () => { throw failure; });
    }
    const packet = mock(() => {});
    await expect(connectAndListen('test-device', packet)).rejects.toThrow(stage === 'missing' ? 'not found' : failure.message);
    characteristic.emit('data', new Uint8Array([1, 2, 3]));
    expect(packet).not.toHaveBeenCalled();
    expect(characteristic.listenerCount('data')).toBe(0);
    expect(peripheral.disconnectAsync).toHaveBeenCalledTimes(1);
    expect(characteristic.unsubscribeAsync).toHaveBeenCalledTimes(stage === 'subscribe' ? 1 : 0);
  });
}

test('cleanup failures preserve the setup error', async () => {
  const characteristic = fixture();
  characteristic.subscribeAsync.mockImplementation(async () => { throw new Error('subscribe failed'); });
  characteristic.unsubscribeAsync.mockImplementation(async () => { throw new Error('unsubscribe failed'); });
  peripheral.disconnectAsync.mockImplementation(async () => { throw new Error('disconnect failed'); });
  await expect(connectAndListen('test-device', () => {})).rejects.toThrow('subscribe failed');
  expect(peripheral.disconnectAsync).toHaveBeenCalledTimes(1);
  expect(characteristic.listenerCount('data')).toBe(0);
});

test('successful session shares one cleanup operation', async () => {
  const characteristic = fixture();
  const packets: number[][] = [];
  const session = await connectAndListen('test-device', packet => packets.push([...packet]));
  characteristic.emit('data', new Uint8Array([3, 4]));
  expect(packets).toEqual([[3, 4]]);
  await Promise.all([session.disconnect(), session.disconnect()]);
  characteristic.emit('data', new Uint8Array([5]));
  expect(packets).toEqual([[3, 4]]);
  expect(characteristic.unsubscribeAsync).toHaveBeenCalledTimes(1);
  expect(peripheral.disconnectAsync).toHaveBeenCalledTimes(1);
});
