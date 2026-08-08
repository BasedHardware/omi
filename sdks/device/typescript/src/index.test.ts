import { describe, expect, test } from 'bun:test';
import { BleAudioCodec, mapCodecId, stripPacketHeader } from './index.ts';

describe('stripPacketHeader', () => {
  test('strips 3-byte header', () => {
    expect(stripPacketHeader(new Uint8Array([1, 2]))).toEqual(new Uint8Array(0));
    expect(stripPacketHeader(new Uint8Array([0, 0, 0, 9, 8]))).toEqual(new Uint8Array([9, 8]));
  });
});

describe('mapCodecId', () => {
  test('maps known codec IDs', () => {
    expect(mapCodecId(0)).toBe(BleAudioCodec.Pcm16);
    expect(mapCodecId(1)).toBe(BleAudioCodec.Pcm8);
    expect(mapCodecId(20)).toBe(BleAudioCodec.Opus);
    expect(mapCodecId(21)).toBe(BleAudioCodec.OpusFs320);
    expect(mapCodecId(99)).toBe(99);
  });
});
