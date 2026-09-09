import { describe, expect, test } from "bun:test";
import {
  projectDeviceTranscription,
  recordingListSpeech,
  recordingTranscriptSpeech,
} from "../src/device-transcriptions";

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

  test("completed empty text keeps later speech stored on segments", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "",
        segments: JSON.stringify([
          { start: 0, end: 0.1, text: "Recorded speech" },
        ]),
      })
    ).toMatchObject({
      state: "completed",
      text: "Recorded speech",
    });
  });

  test("completed NEXT LINE-only text keeps later speech stored on segments", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "\u0085",
        segments: JSON.stringify([
          { start: 0, end: 0.2, text: "\u0085" },
          { start: 0.2, end: 0.4, text: "Recorded speech" },
        ]),
      })
    ).toMatchObject({
      state: "completed",
      text: "\u0085 Recorded speech",
    });
  });

  test("completed omitted segment text keeps later speech stored on segments", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "",
        segments: JSON.stringify([
          { start: 0, end: 0.2 },
          { start: 0.2, end: 0.4, text: null },
          { start: 0.4, end: 0.6, text: "Recorded speech" },
        ]),
      })
    ).toMatchObject({
      state: "completed",
      text: "  Recorded speech",
    });
  });

  test("completed stored text stays when a later segment omits text", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "Stored speech",
        segments: JSON.stringify([
          { start: 0, end: 0.2 },
          { start: 0.2, end: 0.4, text: "Later speech" },
        ]),
      })
    ).toMatchObject({
      state: "completed",
      text: "Stored speech",
    });
  });

  test("completed empty text stays when a segment is not an object", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "",
        segments: JSON.stringify([
          "invalid",
          { start: 0.2, end: 0.4, text: "Recorded speech" },
        ]),
      })
    ).toMatchObject({
      state: "completed",
      text: "",
    });
  });

  test("completed empty text stays when a segment text is not a string", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "",
        segments: JSON.stringify([
          { start: 0, end: 0.2, text: 1 },
          { start: 0.2, end: 0.4, text: "Recorded speech" },
        ]),
      })
    ).toMatchObject({
      state: "completed",
      text: "",
    });
  });

  test("completed stored text stays when segments are empty", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "Stored speech",
        segments: JSON.stringify([]),
      })
    ).toMatchObject({
      state: "completed",
      text: "Stored speech",
    });
  });

  test("GET speech keeps interstitial NEXT LINE segments that list titles skip", () => {
    const segments = [
      { start: 0, end: 0.1, text: "First words" },
      ...Array.from({ length: 200 }, (_, index) => ({
        start: 0.1 + index,
        end: 0.2 + index,
        text: "\u0085",
      })),
      { start: 200, end: 201, text: "Later speech" },
    ];
    expect(recordingTranscriptSpeech("", segments)).toContain("\u0085");
    expect(recordingTranscriptSpeech("", segments)).toContain("Later speech");
    expect(recordingListSpeech("", segments)).toBe("First words Later speech");
    expect(recordingListSpeech("Stored speech", segments)).toBe(
      "Stored speech"
    );
  });
});
