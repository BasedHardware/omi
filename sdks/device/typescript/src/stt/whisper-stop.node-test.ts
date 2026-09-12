/**
 * Regression for #12964: a full Whisper batch already given to the runner
 * must still deliver after stop(). Audio appended after stop is ignored.
 */
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createWhisperTranscriber } from './index.ts';

test('delivers an in-flight full batch after stop and ignores later audio', async () => {
  const transcripts: string[] = [];
  const batches: Uint8Array[] = [];
  let finish!: (text: string) => void;
  const pending = new Promise<string>((resolve) => {
    finish = resolve;
  });
  const transcriber = createWhisperTranscriber({
    runner: (pcm) => {
      batches.push(pcm);
      return pending;
    },
    onTranscript: (text) => transcripts.push(text),
    batchSeconds: 1,
  });

  transcriber.appendPcm(new Uint8Array(32000).fill(7));
  transcriber.stop();
  transcriber.stop();
  transcriber.appendPcm(new Uint8Array(32000).fill(9));
  finish('accepted audio');
  await pending;
  await Promise.resolve();

  assert.equal(batches.length, 1);
  assert.deepEqual(batches[0], new Uint8Array(32000).fill(7));
  assert.deepEqual(transcripts, ['accepted audio']);
});

test('delivers both an in-flight batch and the buffered tail on stop', async () => {
  const transcripts: string[] = [];
  const completions: Array<(text: string) => void> = [];
  const pending: Promise<string>[] = [];
  const transcriber = createWhisperTranscriber({
    runner: () => {
      const result = new Promise<string>((resolve) => completions.push(resolve));
      pending.push(result);
      return result;
    },
    onTranscript: (text) => transcripts.push(text),
    batchSeconds: 1,
  });

  transcriber.appendPcm(new Uint8Array(32000));
  transcriber.appendPcm(new Uint8Array(2));
  transcriber.stop();
  completions[0]('full batch');
  await pending[0];
  completions[1]('tail');
  await pending[1];
  await Promise.resolve();

  assert.deepEqual(transcripts, ['full batch', 'tail']);
});

test('keeps input order when the tail completes before earlier batches', async () => {
  const transcripts: string[] = [];
  const completions: Array<(text: string) => void> = [];
  const pending: Promise<string>[] = [];
  const transcriber = createWhisperTranscriber({
    runner: () => {
      const result = new Promise<string>((resolve) => completions.push(resolve));
      pending.push(result);
      return result;
    },
    onTranscript: (text) => transcripts.push(text),
    batchSeconds: 1,
  });

  transcriber.appendPcm(new Uint8Array(32000));
  transcriber.appendPcm(new Uint8Array(32000));
  transcriber.appendPcm(new Uint8Array(2));
  transcriber.stop();
  completions[2]('tail');
  await pending[2];
  completions[1]('');
  await pending[1];
  assert.deepEqual(transcripts, []);
  completions[0]('first batch');
  await pending[0];
  await Promise.resolve();
  assert.deepEqual(transcripts, ['first batch', 'tail']);
});

test('still delivers a short buffered tail when stopped before a batch fills', async () => {
  const transcripts: string[] = [];
  const transcriber = createWhisperTranscriber({
    runner: () => 'final transcript',
    onTranscript: (text) => transcripts.push(text),
    batchSeconds: 5,
  });

  transcriber.appendPcm(new Uint8Array([1, 2, 3]));
  transcriber.stop();
  await Promise.resolve();
  await Promise.resolve();
  assert.deepEqual(transcripts, ['final transcript']);
});
