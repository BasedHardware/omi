import assert from 'node:assert/strict';
import test from 'node:test';
import {
  AudioReassembler,
  BoundedFrameQueue,
  OMI_FORWARD_QUEUE_FRAMES,
  OMI_MAX_FRAME_BYTES,
  RelaySession,
  codecFromFirmwareId,
} from '../omi-parity/relay.ts';

function packet(id: number, index: number, ...payload: number[]): Uint8Array {
  return new Uint8Array([id & 0xff, (id >> 8) & 0xff, index, ...payload]);
}

test('Omi parity: decodes codec IDs and fails closed for unknown codecs', () => {
  assert.equal(codecFromFirmwareId(1), 'pcm8');
  assert.equal(codecFromFirmwareId(20), 'opus');
  assert.equal(codecFromFirmwareId(21), 'opus_fs320');
  assert.equal(codecFromFirmwareId(999), 'unknown');
});

test('Omi parity: reassembles 3-byte packets and flushes at the next frame', () => {
  const r = new AudioReassembler();
  assert.deepEqual(r.push(packet(10, 0, 1, 2)), []);
  assert.deepEqual(r.push(packet(11, 1, 3, 4)), []);
  const events = r.push(packet(12, 0, 5));
  assert.equal(events.length, 1);
  assert.equal(events[0].kind, 'frame');
  if (events[0].kind === 'frame') {
    assert.equal(events[0].firstPacketId, 10);
    assert.equal(events[0].lastPacketId, 11);
    assert.deepEqual([...events[0].payload], [1, 2, 3, 4]);
  }
});

test('Omi parity: supports 16-bit packet rollover', () => {
  const r = new AudioReassembler();
  r.push(packet(0xffff, 0, 1));
  r.push(packet(0, 1, 2));
  const events = r.push(packet(1, 0, 3));
  assert.equal(events[0]?.kind, 'frame');
});

test('Omi parity: emits a gap and never splices across a missing packet', () => {
  const r = new AudioReassembler();
  r.push(packet(30, 0, 1));
  const events = r.push(packet(32, 1, 2));
  assert.deepEqual(events, [{ kind: 'gap', previousPacketId: 30, nextPacketId: 32, reason: 'fragment_index' }]);
  assert.deepEqual(r.finish(), []);
});

test('Omi parity: rejects a frame over the 256 KiB bound', () => {
  const r = new AudioReassembler();
  r.push(packet(1, 0, 1));
  const oversized = new Uint8Array(OMI_MAX_FRAME_BYTES + 3);
  oversized[0] = 2;
  oversized[1] = 0;
  oversized[2] = 1;
  const events = r.push(oversized);
  assert.equal(events[0]?.kind, 'gap');
  assert.equal(events[0]?.reason, 'too_large');
});

test('Omi parity: bounds forwarding queue at eight frames', () => {
  const q = new BoundedFrameQueue();
  const frame = { kind: 'frame' as const, firstPacketId: 1, lastPacketId: 1, payload: new Uint8Array([1]) };
  for (let i = 0; i < OMI_FORWARD_QUEUE_FRAMES; i++) assert.equal(q.push(frame), true);
  assert.equal(q.push(frame), false);
  assert.equal(q.length, OMI_FORWARD_QUEUE_FRAMES);
  assert.equal(q.shift(), frame);
});

test('Omi parity: only mobile owner can control and reconnect keeps stream identity within grace', () => {
  const observer = new RelaySession('desktop_observer');
  assert.equal(observer.canControlDevice(), false);
  const owner = new RelaySession('mobile_owner');
  assert.equal(owner.canControlDevice(), true);
  owner.disconnect(1000);
  assert.deepEqual(owner.reconnect(1000 + 20_000), { accepted: true, streamGeneration: 0 });
  owner.disconnect(50_000);
  assert.deepEqual(owner.reconnect(70_001), { accepted: true, streamGeneration: 1 });
});
