import assert from 'node:assert/strict';
import { stripPacketHeader, PACKET_HEADER_BYTES } from '../index.ts';
import { createNobleTransport, NOBLE_MISSING } from './index.ts';

// stripPacketHeader
{
  const packet = new Uint8Array([1, 2, 3, 10, 20, 30]);
  const payload = stripPacketHeader(packet);
  assert.deepEqual(payload, new Uint8Array([10, 20, 30]));
  assert.equal(payload.byteLength, packet.byteLength - PACKET_HEADER_BYTES);
  assert.equal(stripPacketHeader(new Uint8Array([1, 2, 3])).byteLength, 0);
  assert.equal(stripPacketHeader(new Uint8Array([1])).byteLength, 0);
  console.log('ok stripPacketHeader');
}

// createNobleTransport missing/failed noble → clear error (or ok if noble works)
{
  assert.ok(NOBLE_MISSING.includes('@stoprocent/noble'));
  try {
    await createNobleTransport('aa:bb:cc:dd:ee:ff');
    console.log('ok createNobleTransport (noble present)');
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    assert.ok(
      msg.includes('Optional BLE dependency missing') || msg.includes('@stoprocent/noble'),
      `expected clear noble error, got: ${msg}`
    );
    console.log('ok createNobleTransport missing-noble error');
  }
}
