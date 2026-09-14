import { createWhisperTranscriber } from '../stt/whisper';

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

describe('createWhisperTranscriber stop', () => {
  test('delivers the leftover buffer after stop', async () => {
    const got: string[] = [];
    const transcriber = createWhisperTranscriber({
      runner: () => 'last words',
      onTranscript: (text) => {
        got.push(text);
      },
      batchSeconds: 1,
    });
    transcriber.appendPcm(new Uint8Array(100));
    transcriber.stop();
    await wait(30);
    expect(got).toEqual(['last words']);
  });

  test('delivers an in-flight full batch after stop', async () => {
    const got: string[] = [];
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    const transcriber = createWhisperTranscriber({
      runner: async () => {
        await held;
        return 'in flight';
      },
      onTranscript: (text) => {
        got.push(text);
      },
      batchSeconds: 1,
    });
    transcriber.appendPcm(new Uint8Array(16000 * 2));
    await wait(10);
    transcriber.stop();
    expect(got).toEqual([]);
    release();
    await wait(30);
    expect(got).toEqual(['in flight']);
  });

  test('ignores audio appended after stop', async () => {
    const got: string[] = [];
    const transcriber = createWhisperTranscriber({
      runner: () => 'should not fire',
      onTranscript: (text) => {
        got.push(text);
      },
      batchSeconds: 1,
    });
    transcriber.stop();
    transcriber.appendPcm(new Uint8Array(16000 * 2));
    await wait(20);
    expect(got).toEqual([]);
  });
});
