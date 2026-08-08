import test from 'node:test';
import assert from 'node:assert';
import { MockNativeBoundary } from '../cpp-bridge/MockNativeBoundary.ts';

test('NativeBoundaryContract - calculates CRC32 checksum correctly', () => {
  const boundary = new MockNativeBoundary();
  const data = new Uint8Array([0x01, 0x02, 0x03, 0x04]);
  const checksum = boundary.calculateChecksum(data);
  assert.strictEqual(typeof checksum, 'number');
  assert.notStrictEqual(checksum, 0);

  // Checksum of same data should be deterministic
  assert.strictEqual(boundary.calculateChecksum(data), checksum);
});

test('NativeBoundaryContract - normalizes valid framed packet', () => {
  const boundary = new MockNativeBoundary();
  const payload = new Uint8Array([0xDE, 0xAD, 0xBE, 0xEF]);
  const crc = boundary.calculateChecksum(payload);

  // Sync (2) + payload (4) + CRC (4 big endian)
  const rawPacket = new Uint8Array([
    0xAA, 0x55,
    0xDE, 0xAD, 0xBE, 0xEF,
    (crc >>> 24) & 0xFF,
    (crc >>> 16) & 0xFF,
    (crc >>> 8) & 0xFF,
    crc & 0xFF,
  ]);

  const result = boundary.normalizePacket(rawPacket);
  assert.strictEqual(result.status, 'SUCCESS');
  assert.ok(result.payload);
  assert.deepStrictEqual(Array.from(result.payload), Array.from(payload));
  assert.strictEqual(result.checksum, crc);
});

test('NativeBoundaryContract - detects corrupt sync header and invalid checksum', () => {
  const boundary = new MockNativeBoundary();
  const badSync = new Uint8Array([0x00, 0x00, 0x01, 0x02, 0x00, 0x00, 0x00, 0x00]);
  assert.strictEqual(boundary.normalizePacket(badSync).status, 'ERR_SYNC_BYTES');

  const badCrc = new Uint8Array([0xAA, 0x55, 0x01, 0x02, 0x99, 0x99, 0x99, 0x99]);
  assert.strictEqual(boundary.normalizePacket(badCrc).status, 'ERR_CHECKSUM');
});

test('NativeBoundaryContract - queries native capabilities', () => {
  const boundary = new MockNativeBoundary();
  const caps = boundary.getCapabilities();
  assert.strictEqual(caps.simd, true);
  assert.strictEqual(caps.abiVersion, 1);
  assert.ok(caps.maxPacketBytes > 0);
});
