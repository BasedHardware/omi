import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createWhisperTranscriber } from '../src/stt/whisper.ts';

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('stopping delivers the accepted final tail once and ignores later PCM', async () => {
  const calls = [];
  const transcripts = [];
  const t = createWhisperTranscriber({
    batchSeconds: 1,
    runner: async (pcm) => {
      calls.push([...pcm]);
      return 'tail';
    },
    onTranscript: (text) => transcripts.push(text),
  });
  t.appendPcm(new Uint8Array([1, 2]));
  t.stop();
  t.appendPcm(new Uint8Array([3, 4]));
  t.stop();
  await settle();
  assert.deepEqual(calls, [[1, 2]]);
  assert.deepEqual(transcripts, ['tail']);
});

test('stopping preserves a full batch already being decoded', async () => {
  const transcripts = [];
  let finish;
  const t = createWhisperTranscriber({
    batchSeconds: 1,
    runner: () => new Promise((resolve) => { finish = resolve; }),
    onTranscript: (text) => transcripts.push(text),
  });
  t.appendPcm(new Uint8Array(32000));
  t.stop();
  finish('full batch');
  await settle();
  assert.deepEqual(transcripts, ['full batch']);
});

test('stopping without audio does not invoke the runner', async () => {
  const t = createWhisperTranscriber({
    runner: () => assert.fail('no audio to decode'),
    onTranscript: () => assert.fail('no transcript expected'),
  });
  t.stop();
  t.stop();
  await settle();
});
