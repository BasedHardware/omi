import { describe, expect, test } from "bun:test";
import { projectDeviceTranscription } from "../src/device-transcriptions";

const completed = {
  sessionId: "session-one",
  state: "completed" as const,
  text: "Recorded speech",
  segments: JSON.stringify([{ start: 0, end: 0.1, text: "Recorded speech" }]),
  language: null,
  discardedLeadingPackets: 0,
  errorCode: null,
  updatedAt: 123,
};

describe("device transcription client projection", () => {
  test("completed success keeps errorCode null and parsed segments", () => {
    expect(projectDeviceTranscription(completed)).toEqual({
      sessionId: "session-one",
      state: "completed",
      text: "Recorded speech",
      segments: [{ start: 0, end: 0.1, text: "Recorded speech" }],
      language: null,
      discardedLeadingPackets: 0,
      errorCode: null,
      updatedAt: 123,
    });
  });

  test("missing errorCode or unreadable segments cannot be served as success", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        errorCode: undefined as never,
      })
    ).toBeNull();
    expect(
      projectDeviceTranscription({ ...completed, segments: "{" })
    ).toBeNull();
    expect(
      projectDeviceTranscription({
        ...completed,
        segments: JSON.stringify({ invalid: true }),
      })
    ).toBeNull();
    expect(projectDeviceTranscription(null)).toBeNull();
  });
});
