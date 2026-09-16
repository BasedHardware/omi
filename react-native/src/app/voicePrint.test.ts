import {
  assertVoicePrintDuration,
  floatToPcm16,
  pcm16ToWav,
  wavDurationSeconds,
} from './voicePrint';

test('pcm16 wav is 16kHz mono with a valid header', () => {
  const pcm = new Int16Array(16000);
  const wav = pcm16ToWav(pcm);
  const view = new DataView(wav);
  expect(String.fromCharCode(...new Uint8Array(wav.slice(0, 4)))).toBe('RIFF');
  expect(view.getUint32(24, true)).toBe(16000);
  expect(view.getUint16(22, true)).toBe(1);
  expect(wav.byteLength).toBe(44 + pcm.byteLength);
});

test('duration rejects samples shorter than five seconds', () => {
  const pcm = floatToPcm16(new Float32Array(8000));
  expect(wavDurationSeconds(pcm)).toBe(0.5);
  expect(() => assertVoicePrintDuration(0.5)).toThrow(/5 seconds/);
  expect(() => assertVoicePrintDuration(5)).not.toThrow();
});
