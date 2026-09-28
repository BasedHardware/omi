import { expect, test } from "bun:test";

import {
  createScriptedTranscriptionSource,
  SCRIPTED_LOCAL_TRANSCRIPT_CONNECTED,
  SCRIPTED_LOCAL_TRANSCRIPT_TEXTS,
  SCRIPTED_LOCAL_TRANSCRIPT_TIMING,
} from "./transcription-source";

test("default scripted STT lines are the canned pair, not empty or user speech", () => {
  expect(SCRIPTED_LOCAL_TRANSCRIPT_TEXTS).toEqual([
    SCRIPTED_LOCAL_TRANSCRIPT_CONNECTED,
    SCRIPTED_LOCAL_TRANSCRIPT_TIMING,
  ]);
  expect(SCRIPTED_LOCAL_TRANSCRIPT_CONNECTED).toBe("Local transcription is connected.");
  expect(SCRIPTED_LOCAL_TRANSCRIPT_TIMING).toBe("This segment arrived with real timing.");
});

test("scripted STT accepts real PCM then drops it after the canned pair", async () => {
  const texts: string[] = [];
  const connection = createScriptedTranscriptionSource().connect({
    sessionId: "session-scripted-drop",
    sampleRate: 16_000,
    codec: "pcm16",
    channels: 1,
    onEmission: (emission) => {
      texts.push(emission.segment.text);
    },
    onError: (error) => {
      throw error;
    },
  });
  const pcm = new Uint8Array(3_200);
  connection.writeAudio(pcm);
  connection.writeAudio(pcm);
  connection.writeAudio(pcm);
  await Bun.sleep(80);
  expect(texts).toEqual([
    SCRIPTED_LOCAL_TRANSCRIPT_CONNECTED,
    SCRIPTED_LOCAL_TRANSCRIPT_TIMING,
  ]);
  // red-proof: a third writeAudio that still emitted would mean the adapter
  // no longer explains David's two harness rows and then silence.
});
