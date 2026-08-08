import test from 'node:test';
import assert from 'node:assert';
import { FakeDeviceTransport } from '../transport/FakeDeviceTransport.ts';
import type { TransportEvent } from '../transport/FakeDeviceTransport.ts';

test('FakeDeviceTransport - initializes with two simulated devices', () => {
  const transport = new FakeDeviceTransport();
  const devices = transport.getDevices();
  assert.strictEqual(devices.length, 2);
  const ids = devices.map(d => d.id);
  assert.ok(ids.includes('dev-001'));
  assert.ok(ids.includes('dev-002'));
});

test('FakeDeviceTransport - manages connection state toggles', () => {
  const transport = new FakeDeviceTransport();
  const events: TransportEvent[] = [];
  transport.subscribe(e => events.push(e));

  assert.strictEqual(transport.connect('dev-001'), true);
  assert.strictEqual(transport.getDevices().find(d => d.id === 'dev-001')?.connected, true);
  assert.strictEqual(events.some(e => e.type === 'device_connected' && e.deviceId === 'dev-001'), true);

  assert.strictEqual(transport.disconnect('dev-001'), true);
  assert.strictEqual(transport.getDevices().find(d => d.id === 'dev-001')?.connected, false);
  assert.strictEqual(events.some(e => e.type === 'device_disconnected' && e.deviceId === 'dev-001'), true);
});

test('FakeDeviceTransport - attribution of packets to specific device', () => {
  const transport = new FakeDeviceTransport();
  transport.connect('dev-001');
  transport.connect('dev-002');

  const events: TransportEvent[] = [];
  transport.subscribe(e => events.push(e));

  const packetData = new Uint8Array([0xAA, 0x55, 0x01, 0x02]);
  transport.sendPacket('dev-001', packetData);

  const packetEvents = events.filter(e => e.type === 'packet_received');
  assert.strictEqual(packetEvents.length, 1);
  assert.strictEqual(packetEvents[0].deviceId, 'dev-001');
  assert.deepStrictEqual(packetEvents[0].packet?.data, packetData);
});

test('FakeDeviceTransport - bounded retry mechanism', () => {
  const transport = new FakeDeviceTransport();
  const events: TransportEvent[] = [];
  transport.subscribe(e => events.push(e));

  // Bounded retry up to 3 attempts
  const success = transport.simulateRetry('dev-001', 3);
  assert.strictEqual(success, true);

  const retryEvents = events.filter(e => e.type === 'retry_attempted');
  assert.strictEqual(retryEvents.length, 3);
  assert.strictEqual(retryEvents[0].attempt, 1);
  assert.strictEqual(retryEvents[2].attempt, 3);

  // Exhausted retry test when maxRetries is exceeded
  events.length = 0;
  const exhausted = transport.simulateRetry('dev-002', 0);
  assert.strictEqual(exhausted, false);
  assert.strictEqual(events.some(e => e.type === 'retry_exhausted'), true);
});
