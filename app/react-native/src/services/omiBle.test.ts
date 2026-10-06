/**
 * The codec vocabulary is the one place two naming schemes meet, and getting it
 * wrong fails quietly: the backend accepts a connection and then returns no
 * transcripts. The Dart enum is camelCase (opusFS320); the wire name is snake
 * case (opus_fs320), per mapCodecToName() in bt_device.dart.
 */
import { sttCodecName, sttChannels, SAMPLE_RATE, type OmiCodec } from './omiBle';

describe('STT codec mapping', () => {
  it('uses the wire names the backend expects, not the Dart enum names', () => {
    expect(sttCodecName('opusFS320')).toBe('opus_fs320');
    expect(sttCodecName('opus')).toBe('opus');
    expect(sttCodecName('pcm8')).toBe('pcm8');
    expect(sttCodecName('pcm16')).toBe('pcm16');
  });

  it('refuses a codec it cannot name rather than guessing', () => {
    // An unmapped codec has to be null: the caller turns null into a visible
    // error, whereas a plausible-looking wrong name becomes a socket that opens
    // and never returns a transcript.
    expect(sttCodecName('unknown')).toBeNull();
  });

  it('matches the channel count the backend was written against', () => {
    // capture_controller.dart sends 2 for opus and 1 for pcm. It is a quirk, not
    // a derivation, but matching it is what works.
    expect(sttChannels('opusFS320')).toBe(2);
    expect(sttChannels('opus')).toBe(2);
    expect(sttChannels('pcm8')).toBe(1);
    expect(sttChannels('pcm16')).toBe(1);
  });

  it('is 16 kHz for every codec the firmware reports', () => {
    // mapCodecToSampleRate returns 16000 for pcm8, pcm16, opus and opusFS320.
    expect(SAMPLE_RATE).toBe(16000);
  });

  it('names every codec it declares a channel count for', () => {
    const declared: OmiCodec[] = ['pcm8', 'pcm16', 'opus', 'opusFS320'];
    for (const c of declared) {
      expect(sttCodecName(c)).not.toBeNull();
      expect([1, 2]).toContain(sttChannels(c));
    }
  });
});