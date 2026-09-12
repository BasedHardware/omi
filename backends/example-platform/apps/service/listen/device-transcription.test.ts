import { expect, test } from "bun:test";
import { deviceTranscriptionProjection } from "./device-transcription";

const completed = {
  sessionId: "session-one",
  state: "completed" as const,
  providerResult: {
    durationSeconds: 1,
    segments: [{ text: "Actual client wire qualification", start: 0, end: 1 }],
  },
  discardedLeadingPackets: 0,
  errorCode: null,
  updatedAt: 123,
  startedAt: "2026-09-07T00:00:00Z",
  codec: 21,
  chunkCount: 1,
  byteCount: 3,
};

test("completed Listen transcripts keep errorCode null for the recording client parser", () => {
  expect(deviceTranscriptionProjection(completed)).toEqual({
    sessionId: "session-one",
    state: "completed",
    text: "Actual client wire qualification",
    segments: [{ text: "Actual client wire qualification", start: 0, end: 1 }],
    language: null,
    discardedLeadingPackets: 0,
    errorCode: null,
    updatedAt: 123,
  });
});

test("completed empty segments join to empty text like production Listen GET", () => {
  expect(
    deviceTranscriptionProjection({
      ...completed,
      providerResult: { durationSeconds: 1, segments: [] },
    })
  ).toMatchObject({
    state: "completed",
    text: "",
    segments: [],
  });
});

test("completed SQL-null providerResult cannot be served as success", () => {
  expect(
    deviceTranscriptionProjection({
      ...completed,
      providerResult: null,
    }),
  ).toBeNull();
});

test("failed Listen transcripts keep the stored errorCode without inventing empty success text", () => {
  expect(
    deviceTranscriptionProjection({
      ...completed,
      state: "failed",
      providerResult: null,
      errorCode: "invalid_audio",
    })
  ).toEqual({
    sessionId: "session-one",
    state: "failed",
    text: null,
    segments: [],
    language: null,
    discardedLeadingPackets: 0,
    errorCode: "invalid_audio",
    updatedAt: 123,
  });
});
