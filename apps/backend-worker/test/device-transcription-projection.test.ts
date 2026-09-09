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

  test("failed GET hides leftover speech like production Listen", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        state: "failed",
        errorCode: "invalid_audio",
      })
    ).toMatchObject({
      state: "failed",
      text: null,
      segments: [],
      errorCode: "invalid_audio",
    });
    expect(
      projectDeviceTranscription({
        ...completed,
        state: "queued",
        segments: "{",
        errorCode: "transcription_unavailable",
      })
    ).toMatchObject({
      state: "queued",
      text: null,
      segments: [],
      errorCode: "transcription_unavailable",
    });
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

  test("completed GET uses production Listen segment join when stored text disagrees", () => {
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
      text: " Later speech",
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

  test("completed empty segments hide leftover stored text like production Listen GET", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        text: "Stored speech",
        segments: JSON.stringify([]),
      })
    ).toMatchObject({
      state: "completed",
      text: "",
      segments: [],
    });
    expect(recordingTranscriptSpeech("Stored speech", [])).toBe("");
    expect(recordingListSpeech("Stored speech", [])).toBe("");
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
      "First words Later speech"
    );
    expect(recordingTranscriptSpeech("Stored speech", segments)).toContain(
      "\u0085"
    );
    expect(recordingTranscriptSpeech("Stored speech", segments)).toContain(
      "Later speech"
    );
    expect(recordingListSpeech("Stored speech", segments)).not.toBe(
      "Stored speech"
    );
    expect(recordingTranscriptSpeech("Stored speech", segments)).not.toBe(
      "Stored speech"
    );
  });

  test("list titles do not fall back to stored text when a segment array is present", () => {
    expect(recordingListSpeech("Stored speech", [])).toBe("");
    expect(
      recordingListSpeech("Stored speech", [
        { start: 0, end: 0.1, text: "\u0085" },
      ])
    ).toBe("");
    expect(recordingListSpeech("Stored speech", null)).toBe("Stored speech");
  });

  test("list titles skip malformed segment windows like production Listen 0065", () => {
    const segments = [
      "invalid",
      { start: 0, end: 0.2, text: 1 },
      { start: 0.2, end: 0.4, text: "Recorded speech" },
    ];
    expect(recordingListSpeech("Stored speech", segments)).toBe(
      "Recorded speech"
    );
    expect(recordingTranscriptSpeech("Stored speech", segments)).toBe(
      "Stored speech"
    );
    expect(recordingTranscriptSpeech("", segments)).toBe("");
  });

  test("list titles visible-trim kept Whisper segments before join", () => {
    const segments = [
      { start: 0, end: 0.1, text: "First words\u0085" },
      { start: 0.1, end: 0.2, text: "\u0085Later speech" },
    ];
    expect(recordingTranscriptSpeech("", segments)).toBe(
      "First words\u0085 \u0085Later speech"
    );
    expect(recordingListSpeech("", segments)).toBe("First words Later speech");
  });

  test("list titles scan the first 240 Whisper segments like production Listen 0065", () => {
    const segments = [
      { start: 0, end: 0.1, text: "First words" },
      ...Array.from({ length: 239 }, (_, index) => ({
        start: 0.1 + index,
        end: 0.2 + index,
        text: "\u0085",
      })),
      { start: 240, end: 241, text: "Hidden later" },
    ];
    expect(recordingListSpeech("", segments)).toBe("First words");
    expect(recordingListSpeech("", segments)).not.toContain("Hidden later");
    expect(recordingTranscriptSpeech("", segments)).toContain("Hidden later");
  });

  test("GET maps DeviceAudioError codes to invalid_audio like production Listen", () => {
    const failed = {
      ...completed,
      state: "failed" as const,
      text: null,
      segments: null,
    };
    expect(
      projectDeviceTranscription({
        ...failed,
        errorCode: "unsupported_codec",
      })
    ).toMatchObject({
      state: "failed",
      text: null,
      errorCode: "invalid_audio",
    });
    expect(
      projectDeviceTranscription({
        ...failed,
        errorCode: "audio_too_large",
      })?.errorCode
    ).toBe("invalid_audio");
    expect(
      projectDeviceTranscription({
        ...failed,
        errorCode: "invalid_audio_size",
      })?.errorCode
    ).toBe("invalid_audio");
  });

  test("GET maps oversized transcripts to invalid_transcript like production TypeError", () => {
    expect(
      projectDeviceTranscription({
        ...completed,
        state: "failed",
        text: null,
        segments: null,
        errorCode: "transcript_too_large",
      })?.errorCode
    ).toBe("invalid_transcript");
  });

  test("GET keeps production Listen error codes and does not leak unknown codes", () => {
    const failed = {
      ...completed,
      state: "failed" as const,
      text: null,
      segments: null,
    };
    expect(
      projectDeviceTranscription({
        ...failed,
        errorCode: "attempt_limit",
      })?.errorCode
    ).toBe("attempt_limit");
    expect(
      projectDeviceTranscription({
        ...failed,
        errorCode: "invalid_audio",
      })?.errorCode
    ).toBe("invalid_audio");
    expect(
      projectDeviceTranscription({
        ...failed,
        errorCode: "transcription_unavailable",
      })?.errorCode
    ).toBe("transcription_unavailable");
    expect(
      projectDeviceTranscription({
        ...failed,
        errorCode: "private unknown upstream detail",
      })?.errorCode
    ).toBe("transcription_unavailable");
  });
});
