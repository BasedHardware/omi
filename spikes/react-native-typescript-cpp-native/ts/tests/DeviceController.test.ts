import test from 'node:test';
import assert from 'node:assert';
import { DeviceController } from '../domain/DeviceController.ts';
import { FakeDeviceTransport } from '../transport/FakeDeviceTransport.ts';
import { MockNativeBoundary } from '../cpp-bridge/MockNativeBoundary.ts';
import { renderDeviceListScreenSketch } from '../ui/DeviceListScreenSketch.ts';

test('DeviceController - connects and normalizes incoming native packets', () => {
  const transport = new FakeDeviceTransport();
  const nativeBoundary = new MockNativeBoundary();
  const controller = new DeviceController(transport, nativeBoundary);

  let updatedDevices = controller.getDevices();
  assert.strictEqual(updatedDevices.length, 2);

  // Connect dev-001
  controller.connectDevice('dev-001');
  assert.strictEqual(controller.getDevices().find(d => d.id === 'dev-001')?.status, 'connected');

  // Prepare framed valid packet
  const payload = new Uint8Array([0x10, 0x20, 0x30]);
  const crc = nativeBoundary.calculateChecksum(payload);
  const rawPacket = new Uint8Array([
    0xAA, 0x55,
    0x10, 0x20, 0x30,
    (crc >>> 24) & 0xFF,
    (crc >>> 16) & 0xFF,
    (crc >>> 8) & 0xFF,
    crc & 0xFF,
  ]);

  // Receive packet
  controller.receivePacket('dev-001', rawPacket);
  const dev1State = controller.getDevices().find(d => d.id === 'dev-001');
  assert.strictEqual(dev1State?.validPacketCount, 1);
  assert.strictEqual(dev1State?.corruptPacketCount, 0);
  assert.strictEqual(dev1State?.lastChecksum, crc);
});

test('DeviceController - handles corrupt packets via native boundary', () => {
  const transport = new FakeDeviceTransport();
  const nativeBoundary = new MockNativeBoundary();
  const controller = new DeviceController(transport, nativeBoundary);

  controller.connectDevice('dev-002');
  const badPacket = new Uint8Array([0xAA, 0x55, 0x10, 0x20, 0x99, 0x99, 0x99, 0x99]);

  controller.receivePacket('dev-002', badPacket);
  const dev2State = controller.getDevices().find(d => d.id === 'dev-002');
  assert.strictEqual(dev2State?.validPacketCount, 0);
  assert.strictEqual(dev2State?.corruptPacketCount, 1);
});

test('DeviceController & UI Screen Sketch integration', () => {
  const transport = new FakeDeviceTransport();
  const nativeBoundary = new MockNativeBoundary();
  const controller = new DeviceController(transport, nativeBoundary);

  controller.connectDevice('dev-001');
  const sketchOutput = renderDeviceListScreenSketch({ controller });

  assert.ok(sketchOutput.includes('[React Native Screen Sketch: Device List]'));
  assert.ok(sketchOutput.includes('Omi Headset Alpha'));
  assert.ok(sketchOutput.includes('CONNECTED'));
});
