/**
 * The device capture query string.
 *
 * These parameters are the whole contract with the backend, and they fail
 * silently: a wrong codec name still opens the socket and then returns no
 * transcripts, which looks like a network problem rather than a formatting one.
 * Asserted here so the failure is a test rather than an empty transcript.
 */
import { omiStreamParams } from '@/services/omiBle';

describe('omiStreamParams', () => {
  it('sends the wire codec name, sample rate and channels', () => {
    expect(omiStreamParams('opusFS320')).toEqual({
      codec: 'opus_fs320',
      sample_rate: '16000',
      channels: '2',
      language: 'multi',
    });
  });

  it('sends one channel for pcm', () => {
    expect(omiStreamParams('pcm8')).toMatchObject({ codec: 'pcm8', channels: '1' });
  });

  it('returns null for a codec the backend cannot decode', () => {
    // null is load-bearing: the caller turns it into a visible error rather than
    // opening a socket that will never produce a transcript.
    expect(omiStreamParams('unknown')).toBeNull();
  });

  it('never sends a Dart enum name', () => {
    const p = omiStreamParams('opusFS320');
    // 'BleAudioCodec.opusFS320' is the Dart toString(). The backend expects the
    // mapCodecToName() form. Guarding the whole shape, not just this key.
    expect(JSON.stringify(p)).not.toMatch(/BleAudioCodec|opusFS320/);
  });
});