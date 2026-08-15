import { describe, expect, test } from 'bun:test';
import { BleAudioCodec, mapCodecId } from './index.ts';

// Numeric enum members are plain numbers at runtime, so `mapCodecId(21) === 21`
// whether or not the codec is named. The checkable contract is the reverse map.
describe('BleAudioCodec', () => {
  test('names the codec ids firmware reports', () => {
    expect(BleAudioCodec[BleAudioCodec.Pcm16]).toBe('Pcm16');
    expect(BleAudioCodec[BleAudioCodec.Pcm8]).toBe('Pcm8');
    // 20 is DevKit, 21 is Omi CV1 (opusFS320).
    expect(BleAudioCodec.Opus).toBe(20);
    expect(BleAudioCodec[BleAudioCodec.Opus]).toBe('Opus');
    expect(BleAudioCodec.OpusFs320).toBe(21);
    expect(BleAudioCodec[BleAudioCodec.OpusFs320]).toBe('OpusFs320');
  });
});

describe('mapCodecId', () => {
  test('resolves every known id to a named member', () => {
    for (const id of [0, 1, 20, 21]) {
      expect(BleAudioCodec[mapCodecId(id)]).toBeDefined();
    }
  });

  test('passes an unknown id through unnamed', () => {
    expect(mapCodecId(99)).toBe(99);
    expect(BleAudioCodec[99]).toBeUndefined();
  });
});
