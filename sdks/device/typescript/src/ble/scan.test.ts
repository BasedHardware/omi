import { afterEach, beforeEach, describe, expect, mock, spyOn, test } from 'bun:test';
import { EventEmitter } from 'node:events';
import { scanForDevices } from './noble.ts';

const adapter = Object.assign(new EventEmitter(), {
  state: 'poweredOn',
  startScanningAsync: mock(async () => {}),
  stopScanningAsync: mock(async () => {}),
  async *discoverAsync() { await new Promise(() => {}); },
});
mock.module('@stoprocent/noble', () => ({ default: adapter }));

describe('scanForDevices deadline ownership', () => {
  let expire: (() => void) | undefined;
  let started: Promise<void>;
  let timer: ReturnType<typeof spyOn>;

  beforeEach(() => {
    adapter.removeAllListeners();
    adapter.startScanningAsync.mockReset();
    started = new Promise<void>((resolve) => {
      adapter.startScanningAsync.mockImplementation(async () => { resolve(); });
    });
    adapter.stopScanningAsync.mockClear();
    expire = undefined;
    timer = spyOn(globalThis, 'setTimeout').mockImplementation(((callback: () => void) => {
      expire = callback;
      return 1;
    }) as typeof setTimeout);
  });
  afterEach(() => { timer.mockRestore(); adapter.removeAllListeners(); });

  test('returns an empty list and stops when no advertisements arrive', async () => {
    const result = scanForDevices(20);
    await started;
    await Promise.resolve();
    expect(expire).toBeDefined();
    expire!();
    expect(await result).toEqual([]);
    expect(adapter.stopScanningAsync).toHaveBeenCalledTimes(1);
    expect(adapter.listenerCount('discover')).toBe(0);
  });

  test('captures immediate advertisements, deduplicates, then stops during silence', async () => {
    const begin = adapter.startScanningAsync.getMockImplementation()!;
    adapter.startScanningAsync.mockImplementation(async () => {
      void begin();
      adapter.emit('discover', { id: 'a', advertisement: { localName: 'Omi' }, rssi: -70 });
    });
    const result = scanForDevices(20);
    await started;
    await Promise.resolve();
    expect(expire).toBeDefined();
    adapter.emit('discover', { id: 'a', advertisement: { localName: 'Omi' }, rssi: -50 });
    adapter.emit('discover', { address: 'b', advertisement: { name: 'Second' }, rssi: 0 });
    expire!();
    expect(await result).toEqual([
      { id: 'a', name: 'Omi', rssi: -50 },
      { id: 'b', name: 'Second', rssi: 0 },
    ]);
    expect(adapter.stopScanningAsync).toHaveBeenCalledTimes(1);
    expect(adapter.listenerCount('discover')).toBe(0);
  });

  test('cleans up and propagates scan-start errors', async () => {
    const failure = new Error('adapter rejected scan');
    adapter.startScanningAsync.mockRejectedValueOnce(failure);
    await expect(scanForDevices(20)).rejects.toBe(failure);
    expect(adapter.listenerCount('discover')).toBe(0);
    expect(adapter.stopScanningAsync).toHaveBeenCalledTimes(1);
  });

  test('resumes binding pauses without extending the original deadline', async () => {
    const result = scanForDevices(20);
    await started;
    await Promise.resolve();
    const originalExpiry = expire;
    let resumed!: () => void;
    const didResume = new Promise<void>(resolve => { resumed = resolve; });
    adapter.startScanningAsync.mockImplementation(async () => {
      adapter.emit('discover', { id: 'after-pause', rssi: -40 });
      resumed();
    });
    adapter.emit('scanStop');
    await Promise.resolve();
    expect(adapter.startScanningAsync).toHaveBeenCalledTimes(2);
    await didResume;
    expect(expire).toBe(originalExpiry);
    expire!();
    expect(await result).toEqual([{ id: 'after-pause', name: '', rssi: -40 }]);
    expect(adapter.startScanningAsync).toHaveBeenCalledTimes(2);
    expect(adapter.stopScanningAsync).toHaveBeenCalledTimes(1);
    expect(adapter.listenerCount('scanStop')).toBe(0);
    adapter.emit('scanStop');
    await Promise.resolve();
    expect(adapter.startScanningAsync).toHaveBeenCalledTimes(2);
  });

  test('propagates resume failure and releases both subscriptions', async () => {
    const result = scanForDevices(20);
    await started;
    await Promise.resolve();
    const failure = new Error('resume rejected');
    adapter.startScanningAsync.mockRejectedValueOnce(failure);
    const rejected = result.catch(error => error);
    adapter.emit('scanStop');
    await Promise.resolve();
    expect(adapter.startScanningAsync).toHaveBeenCalledTimes(2);
    expect(await rejected).toBe(failure);
    expect(adapter.listenerCount('discover')).toBe(0);
    expect(adapter.listenerCount('scanStop')).toBe(0);
    expect(adapter.stopScanningAsync).toHaveBeenCalledTimes(1);
  });
});
