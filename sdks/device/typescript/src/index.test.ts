import { describe, expect, test } from 'bun:test';
import { BleAudioCodec, mapCodecId } from './index.ts';

// Codec IDs are firmware-coupled: 20 is DevKit, 21 is Omi CV1 (opusFS320).
describe('mapCodecId', () => {
  test('maps known codec ids to enum members', () => {
    expect(mapCodecId(0)).toBe(BleAudioCodec.Pcm16);
    expect(mapCodecId(1)).toBe(BleAudioCodec.Pcm8);
    expect(mapCodecId(20)).toBe(BleAudioCodec.Opus);
    expect(mapCodecId(21)).toBe(BleAudioCodec.OpusFs320);
  });

  test('passes an unknown id through', () => {
    expect(mapCodecId(99)).toBe(99);
  });
});
