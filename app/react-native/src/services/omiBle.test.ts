/**
 * The codec vocabulary is the one place two naming schemes meet, and getting it
 * wrong fails quietly: the backend accepts a connection and then returns no
 * transcripts. The Dart enum is camelCase (opusFS320); the wire name is snake
 * case (opus_fs320), per mapCodecToName() in bt_device.dart.
 */
import { sttCodecName, sttChannels, SAMPLE_RATE, stripWearableAudioEnvelope, omiStreamParams, type OmiCodec } from './omiBle';

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

  it('uses mono channeling for wearable BLE audio streaming', () => {
    // Wearable BLE opus packets are mono and must not activate channel-ID protocol.
    expect(sttChannels('opusFS320')).toBe(1);
    expect(sttChannels('opus')).toBe(1);
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

  it('strips the 3-byte wearable transport envelope and drops malformed packets', () => {
    expect(stripWearableAudioEnvelope(new Uint8Array([17, 0, 0, 248, 255, 254]))).toEqual(
      new Uint8Array([248, 255, 254])
    );
    expect(stripWearableAudioEnvelope(new Uint8Array([1, 2, 3]))).toBeNull();
    expect(stripWearableAudioEnvelope(new Uint8Array([1, 2]))).toBeNull();
  });

  it('builds mono omi stream params for opus wearable capture', () => {
    expect(omiStreamParams('opus')).toEqual({
      codec: 'opus',
      sample_rate: '16000',
      channels: '1',
      language: 'multi',
    });
  });

  it('matches firmware-shaped wearable packet contract (strip header -> backend payload, mono params)', () => {
    // Firmware-shaped BLE notification: [packet_counter, transport_hi, transport_lo, ...opus payload]
    const firmwarePacket = new Uint8Array([17, 0, 0, 248, 255, 254, 0x4f, 0x70, 0x75, 0x73]);
    const payload = stripWearableAudioEnvelope(firmwarePacket);
    expect(payload).toEqual(new Uint8Array([248, 255, 254, 0x4f, 0x70, 0x75, 0x73]));

    // Backend receiver/listen contract for wearable opus stream: mono, 16kHz, opus wire name.
    expect(omiStreamParams('opusFS320')).toEqual({
      codec: 'opus_fs320',
      sample_rate: '16000',
      channels: '1',
      language: 'multi',
    });
  });
});