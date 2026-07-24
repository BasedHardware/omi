import { describe, expect, test } from 'bun:test';
import { stripPacketHeader, PACKET_HEADER_BYTES } from '../index.ts';
import { createNobleTransport, NOBLE_MISSING } from './index.ts';

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
  test('clear error or succeeds if noble present', async () => {
    expect(NOBLE_MISSING.includes('@stoprocent/noble')).toBe(true);
    try {
      await createNobleTransport('aa:bb:cc:dd:ee:ff');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      expect(
        msg.includes('Optional BLE dependency missing') || msg.includes('@stoprocent/noble') || msg.includes('noble')
      ).toBe(true);
    }
  });
});
