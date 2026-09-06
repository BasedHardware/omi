import { expect, test } from "bun:test";
import { parsePrerecordedTranscription } from "./prerecorded-transcription";

const transcription = (texts: readonly string[]) => ({ durationSeconds: 1, segments: texts.map(text => ({ text, start: 0, end: 1 })) });

test("transcription preserves non-ASCII text up to the canonical PostgreSQL UTF-8 publication budget", () => {
  const texts = [...Array<string>(333).fill("文".repeat(1000)), "文".repeat(333) + "a"];
  expect(texts.reduce((sum, text) => sum + new TextEncoder().encode(text).length, 0)).toBe(1_000_000);
  const accepted = parsePrerecordedTranscription(transcription(texts));
  expect(accepted.segments.map(segment => segment.text)).toEqual(texts);
  expect(() => parsePrerecordedTranscription(transcription([...texts, "a"]))).toThrow("invalid_transcription");
  expect(() => parsePrerecordedTranscription(transcription(Array<string>(334).fill("文".repeat(1000))))).toThrow("invalid_transcription");
});

test("transcription rejects strings PostgreSQL cannot persist while preserving valid Unicode pairs", () => {
  for (const text of ["word\0word", "word\ud800word", "word\udfffword"]) {
    expect(() => parsePrerecordedTranscription(transcription([text]))).toThrow("invalid_transcription");
  }
  expect(parsePrerecordedTranscription(transcription(["Hello 🌍 中文"])).segments[0]?.text).toBe("Hello 🌍 中文");
});
