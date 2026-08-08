import test from 'node:test';
import assert from 'node:assert';
import {
  CurrentTsAdapter,
  ReactNativeNativeModuleAdapter,
  WebTypescriptAdapter,
  buildSyntheticPacket,
} from '../benchmark/adapters.ts';

// ─── Synthetic packet generation ─────────────────────────────────────────────

test('buildSyntheticPacket - produces deterministic framed packets', () => {
  const pkt1 = buildSyntheticPacket(8);
  const pkt2 = buildSyntheticPacket(8);
  assert.deepStrictEqual(pkt1, pkt2, 'Same size → identical packets');
  assert.strictEqual(pkt1[0], 0xaa, 'Sync byte 0');
  assert.strictEqual(pkt1[1], 0x55, 'Sync byte 1');
  assert.strictEqual(pkt1.length, 2 + 8 + 4, 'Frame = sync(2) + payload(8) + crc(4)');
});

// ─── (A) Current TS Adapter ──────────────────────────────────────────────────

test('CurrentTsAdapter - normalizes valid synthetic packet', () => {
  const adapter = new CurrentTsAdapter();
  const packet = buildSyntheticPacket(16);
  const result = adapter.normalizePacket(packet);
  assert.strictEqual(result.status, 'SUCCESS');
  assert.ok(result.payload);
  assert.strictEqual(result.payload.length, 16);
  assert.strictEqual(typeof result.checksum, 'number');
  assert.notStrictEqual(result.checksum, 0);
});

test('CurrentTsAdapter - checksum matches normalize result', () => {
  const adapter = new CurrentTsAdapter();
  const packet = buildSyntheticPacket(32);
  const result = adapter.normalizePacket(packet);
  assert.strictEqual(result.status, 'SUCCESS');
  const directCrc = adapter.calculateChecksum(result.payload!);
  assert.strictEqual(directCrc, result.checksum);
});

test('CurrentTsAdapter - reports capabilities', () => {
  const adapter = new CurrentTsAdapter();
  const caps = adapter.getCapabilities();
  assert.strictEqual(caps.abiVersion, 1);
  assert.ok(caps.maxPacketBytes > 0);
});

// ─── (B) React Native Native-Module Bridge Path ─────────────────────────────

test('ReactNativeNativeModuleAdapter - normalizes valid synthetic packet', () => {
  const adapter = new ReactNativeNativeModuleAdapter();
  const packet = buildSyntheticPacket(16);
  const result = adapter.normalizePacket(packet);
  assert.strictEqual(result.status, 'SUCCESS');
  assert.ok(result.payload);
  assert.strictEqual(result.payload.length, 16);
});

test('ReactNativeNativeModuleAdapter - checksum matches current adapter', () => {
  const current = new CurrentTsAdapter();
  const rnAdapter = new ReactNativeNativeModuleAdapter();
  const payload = new Uint8Array([0x01, 0x02, 0x03, 0x04]);
  assert.strictEqual(
    rnAdapter.calculateChecksum(payload),
    current.calculateChecksum(payload),
    'Bridge adapter produces same CRC32 as current adapter'
  );
});

test('ReactNativeNativeModuleAdapter - capabilities match current adapter', () => {
  const current = new CurrentTsAdapter();
  const rnAdapter = new ReactNativeNativeModuleAdapter();
  assert.deepStrictEqual(rnAdapter.getCapabilities(), current.getCapabilities());
});

// ─── (C) Web TypeScript Adapter (crepuscularity + Moonshine boundary) ───────

test('WebTypescriptAdapter - normalizes valid synthetic packet', () => {
  const adapter = new WebTypescriptAdapter();
  const packet = buildSyntheticPacket(16);
  const result = adapter.normalizePacket(packet);
  assert.strictEqual(result.status, 'SUCCESS');
  assert.ok(result.payload);
  assert.strictEqual(result.payload.length, 16);
});

test('WebTypescriptAdapter - checksum matches current adapter', () => {
  const current = new CurrentTsAdapter();
  const webAdapter = new WebTypescriptAdapter();
  const payload = new Uint8Array([0xDE, 0xAD, 0xBE, 0xEF]);
  assert.strictEqual(
    webAdapter.calculateChecksum(payload),
    current.calculateChecksum(payload),
    'Web adapter produces same CRC32 as current adapter'
  );
});

test('WebTypescriptAdapter - Moonshine boundary stub is not available', () => {
  const adapter = new WebTypescriptAdapter();
  assert.strictEqual(adapter.moonshine.available, false,
    'Moonshine is an external boundary, not a dependency');
  const result = adapter.moonshine.dispatchAudioFrame(new Uint8Array([0x00]));
  assert.strictEqual(result.accepted, false);
  assert.ok(result.boundaryLabel.includes('not-a-dependency'));
});

test('WebTypescriptAdapter - render cache resets between runs', () => {
  const adapter = new WebTypescriptAdapter();
  const packet = buildSyntheticPacket(8);
  adapter.normalizePacket(packet);
  adapter.resetRenderCache();
  // Should not throw after reset
  const result = adapter.normalizePacket(packet);
  assert.strictEqual(result.status, 'SUCCESS');
});

// ─── Cross-adapter equivalence ───────────────────────────────────────────────

test('All three adapters produce identical normalization for same input', () => {
  const adapters = [
    new CurrentTsAdapter(),
    new ReactNativeNativeModuleAdapter(),
    new WebTypescriptAdapter(),
  ];

  for (const size of [8, 64, 256]) {
    const packet = buildSyntheticPacket(size);
    const results = adapters.map(a => a.normalizePacket(packet));

    // All should succeed
    for (const r of results) {
      assert.strictEqual(r.status, 'SUCCESS', `size=${size}`);
    }

    // All should produce same payload
    const payloads = results.map(r => Array.from(r.payload!));
    assert.deepStrictEqual(payloads[0], payloads[1], `RN bridge matches current at size=${size}`);
    assert.deepStrictEqual(payloads[0], payloads[2], `Web adapter matches current at size=${size}`);

    // All should produce same checksum
    const checksums = results.map(r => r.checksum);
    assert.strictEqual(checksums[0], checksums[1], `CRC32 bridge match at size=${size}`);
    assert.strictEqual(checksums[0], checksums[2], `CRC32 web match at size=${size}`);
  }
});
