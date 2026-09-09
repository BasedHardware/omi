import { env } from "cloudflare:workers";
import { beforeEach, expect, test } from "vitest";
import {
  openDeviceSession,
  appendDeviceSessionAudio,
  completeDeviceSession,
} from "../src/device-sessions";
import {
  processDeviceTranscriptions,
  projectDeviceTranscription,
  readDeviceTranscription,
} from "../src/device-transcriptions";
import { readConversations, toLegacyConversation } from "../src/conversations";

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM device_transcriptions").run();
  await env.DB.prepare("DELETE FROM device_sessions").run();
  await env.DB.prepare("DELETE FROM chat_messages").run();
});

async function recording(capturedAtMs?: number) {
  const session = await openDeviceSession(
    env.DB,
    "record-owner",
    {
      captureId: crypto.randomUUID(),
      deviceId: "pendant",
      deviceName: "Omi",
      codec: 1,
      ...(capturedAtMs === undefined ? {} : { capturedAtMs }),
    },
    100
  );
  if (session === null) throw new Error("Recording creation failed");
  await appendDeviceSessionAudio(
    env.DB,
    env.ATTACHMENTS,
    "record-owner",
    session.id,
    new Uint8Array([0, 0, 0, 128, 129, 127]),
    0,
    101
  );
  return session;
}

test("verified completion atomically queues once, persists transcription and projects a private owned conversation", async () => {
  const session = await recording();
  expect(
    await readDeviceTranscription(env.DB, "record-owner", session.id)
  ).toBeNull();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await completeDeviceSession(env.DB, "record-owner", session.id, 103);
  expect(
    (await readDeviceTranscription(env.DB, "record-owner", session.id))?.state
  ).toBe("queued");
  let calls = 0;
  const ai = {
    run: async (_model: string, input: { audio: string }) => {
      calls++;
      expect(atob(input.audio).slice(0, 4)).toBe("RIFF");
      return {
        text: "The meeting is tomorrow.",
        segments: [{ start: 0, end: 1, text: "The meeting is tomorrow." }],
        transcription_info: { language: "en" },
      };
    },
  };
  await processDeviceTranscriptions(env.DB, env.ATTACHMENTS, ai, 104);
  await processDeviceTranscriptions(env.DB, env.ATTACHMENTS, ai, 105);
  expect(calls).toBe(1);
  expect(
    await readDeviceTranscription(env.DB, "record-owner", session.id)
  ).toEqual({
    sessionId: session.id,
    state: "completed",
    text: "The meeting is tomorrow.",
    segments: JSON.stringify([
      { start: 0, end: 1, text: "The meeting is tomorrow." },
    ]),
    language: "en",
    discardedLeadingPackets: 0,
    errorCode: null,
    updatedAt: expect.any(Number),
  });
  expect(
    projectDeviceTranscription(
      await readDeviceTranscription(env.DB, "record-owner", session.id)
    )
  ).toMatchObject({ language: null });
  expect(
    await readDeviceTranscription(env.DB, "another-owner", session.id)
  ).toBeNull();
  const conversations = await readConversations(env.DB, "record-owner");
  expect(conversations).toHaveLength(1);
  expect(conversations[0]).toMatchObject({
    id: `recording:${session.id}`,
    overview: "The meeting is tomorrow.",
    source: "omi",
    status: "completed",
    visibility: "private",
  });
  expect(await readConversations(env.DB, "another-owner")).toEqual([]);
});

test("queued recordings stay visible without inventing a Recording title", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "",
    overview: "",
    source: "omi",
    status: "processing",
  });
});

test("NEXT LINE-only recording text stays visible without inventing a Recording title", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ? WHERE session_id = ?"
  )
    .bind("\u0085", session.id)
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "",
    overview: "",
    source: "omi",
    status: "completed",
  });
});

test("recording titles omit leading and trailing NEXT LINE", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ? WHERE session_id = ?"
  )
    .bind("\u0085Recorded words\u0085", session.id)
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "Recorded words",
    overview: "Recorded words",
    source: "omi",
    status: "completed",
  });
});

test("recording titles keep visible words after a NEXT LINE prefix longer than the excerpt budget", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ? WHERE session_id = ?"
  )
    .bind(`${"\u0085".repeat(241)}Recorded words`, session.id)
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "Recorded words",
    overview: "Recorded words",
    source: "omi",
    status: "completed",
  });
});

test("recording titles keep later speech stored on segments when text is empty", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ? WHERE session_id = ?"
  )
    .bind(
      "",
      JSON.stringify([{ start: 0, end: 1, text: "Recorded words" }]),
      session.id
    )
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "Recorded words",
    overview: "Recorded words",
    source: "omi",
    status: "completed",
  });
});

test("recording titles keep later speech when a stored segment omits text", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ? WHERE session_id = ?"
  )
    .bind(
      "",
      JSON.stringify([
        { start: 0, end: 0.2 },
        { start: 0.2, end: 1, text: "Recorded words" },
      ]),
      session.id
    )
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "Recorded words",
    overview: "Recorded words",
    source: "omi",
    status: "completed",
  });
});

test("recording titles skip empty-after-trim segment windows that would hide later speech", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ? WHERE session_id = ?"
  )
    .bind(
      "",
      JSON.stringify([
        { start: 0, end: 0.1, text: "First words" },
        ...Array.from({ length: 200 }, (_, index) => ({
          start: 0.1 + index,
          end: 0.2 + index,
          text: "\u0085",
        })),
        { start: 200, end: 201, text: "Later speech" },
      ]),
      session.id
    )
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "First words Later speech",
    overview: "First words Later speech",
    source: "omi",
    status: "completed",
  });
});

test("recording titles visible-trim kept Whisper segments before join", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ? WHERE session_id = ?"
  )
    .bind(
      "",
      JSON.stringify([
        { start: 0, end: 0.1, text: "First words\u0085" },
        { start: 0.1, end: 0.2, text: "\u0085Later speech" },
      ]),
      session.id
    )
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "First words Later speech",
    overview: "First words Later speech",
    source: "omi",
    status: "completed",
  });
  expect(rows[0]?.title).not.toContain("\u0085");
  expect(rows[0]?.overview).not.toContain("\u0085");
});

test("recording titles use skip-empty segment speech when stored text is also present", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ? WHERE session_id = ?"
  )
    .bind(
      "Stored speech",
      JSON.stringify([
        { start: 0, end: 0.1, text: "First words" },
        ...Array.from({ length: 200 }, (_, index) => ({
          start: 0.1 + index,
          end: 0.2 + index,
          text: "\u0085",
        })),
        { start: 200, end: 201, text: "Later speech" },
      ]),
      session.id
    )
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "First words Later speech",
    overview: "First words Later speech",
    source: "omi",
    status: "completed",
  });
  expect(rows[0]?.title).not.toContain("Stored speech");
  expect(rows[0]?.overview).not.toContain("Stored speech");
});

test("recording titles skip malformed segment windows like production Listen 0065", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ? WHERE session_id = ?"
  )
    .bind(
      "Stored speech",
      JSON.stringify([
        "invalid",
        { start: 0, end: 0.2, text: 1 },
        { start: 0.2, end: 0.4, text: "Recorded speech" },
      ]),
      session.id
    )
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "Recorded speech",
    overview: "Recorded speech",
    status: "completed",
  });
  expect(rows[0]?.title).not.toContain("Stored speech");
  expect(
    projectDeviceTranscription(
      await readDeviceTranscription(env.DB, "record-owner", session.id)
    )
  ).toMatchObject({
    state: "completed",
    text: "Stored speech",
  });
});

test("recording titles stay empty when a stored segment array has no visible speech", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ? WHERE session_id = ?"
  )
    .bind("Stored speech", JSON.stringify([]), session.id)
    .run();
  const empty = await readConversations(env.DB, "record-owner");
  expect(empty[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "",
    overview: "",
    status: "completed",
  });
  expect(empty[0]?.title).not.toContain("Stored speech");
  expect(
    projectDeviceTranscription(
      await readDeviceTranscription(env.DB, "record-owner", session.id)
    )
  ).toMatchObject({
    state: "completed",
    text: "",
    segments: [],
  });
  await env.DB.prepare(
    "UPDATE device_transcriptions SET segments = ? WHERE session_id = ?"
  )
    .bind(JSON.stringify([{ start: 0, end: 0.1, text: "\u0085" }]), session.id)
    .run();
  const padded = await readConversations(env.DB, "record-owner");
  expect(padded[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "",
    overview: "",
    status: "completed",
  });
  expect(padded[0]?.title).not.toContain("Stored speech");
});

test("recording overviews hard-slice 240 UTF-16 units without chat ellipsis", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'completed', text = ? WHERE session_id = ?"
  )
    .bind("a".repeat(241), session.id)
    .run();
  const rows = await readConversations(env.DB, "record-owner");
  expect(rows).toHaveLength(1);
  expect(rows[0]).toMatchObject({
    id: `recording:${session.id}`,
    title: "a".repeat(80),
    overview: "a".repeat(240),
    source: "omi",
    status: "completed",
  });
  expect(rows[0]?.overview.endsWith("...")).toBe(false);
  expect(
    projectDeviceTranscription(
      await readDeviceTranscription(env.DB, "record-owner", session.id)
    )
  ).toMatchObject({
    state: "completed",
    text: "a".repeat(241),
    segments: [],
  });
});

test("recording conversation preserves capture provenance separately from server times", async () => {
  for (const capturedAtMs of [undefined, 0, 8640000000000000]) {
    const session = await recording(capturedAtMs);
    await completeDeviceSession(env.DB, "record-owner", session.id, 102);
    const rows = await readConversations(env.DB, "record-owner");
    const projected = rows.find((row) => row.id === `recording:${session.id}`)!;
    const legacy = toLegacyConversation(projected);
    expect(projected.startedAt).toBe(100);
    expect(projected.finishedAt).toBe(102);
    expect(legacy.started_at).toBe(new Date(100).toISOString());
    if (capturedAtMs === undefined) {
      expect(projected).not.toHaveProperty("capturedAtMs");
      expect(legacy).not.toHaveProperty("captured_at_ms");
    } else {
      expect(projected.capturedAtMs).toBe(capturedAtMs);
      expect(legacy.captured_at_ms).toBe(capturedAtMs);
    }
  }
});

test("incomplete uploads never queue and malformed audio fails without provider work", async () => {
  const session = await recording();
  await env.DB.prepare(
    "UPDATE device_sessions SET uploaded_chunk_count = 0 WHERE id = ?"
  )
    .bind(session.id)
    .run();
  expect(
    (await completeDeviceSession(env.DB, "record-owner", session.id, 102)).kind
  ).toBe("conflict");
  expect(
    await readDeviceTranscription(env.DB, "record-owner", session.id)
  ).toBeNull();
  await env.DB.prepare(
    "UPDATE device_sessions SET uploaded_chunk_count = chunk_count, codec = 255 WHERE id = ?"
  )
    .bind(session.id)
    .run();
  await completeDeviceSession(env.DB, "record-owner", session.id, 103);
  let calls = 0;
  await processDeviceTranscriptions(
    env.DB,
    env.ATTACHMENTS,
    {
      run: async () => {
        calls++;
        return { text: "incorrect" };
      },
    },
    104
  );
  expect(calls).toBe(0);
  expect(
    await readDeviceTranscription(env.DB, "record-owner", session.id)
  ).toMatchObject({ state: "failed", errorCode: "invalid_audio" });
  expect(
    projectDeviceTranscription(
      await readDeviceTranscription(env.DB, "record-owner", session.id)
    )
  ).toMatchObject({ state: "failed", errorCode: "invalid_audio", text: null });
});

test("failed transcript GET hides leftover speech like production Listen", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await env.DB.prepare(
    "UPDATE device_transcriptions SET state = 'failed', text = ?, segments = ?, error_code = ? WHERE session_id = ?"
  )
    .bind(
      "Leftover speech",
      JSON.stringify([{ start: 0, end: 1, text: "Leftover speech" }]),
      "invalid_audio",
      session.id
    )
    .run();
  expect(
    projectDeviceTranscription(
      await readDeviceTranscription(env.DB, "record-owner", session.id)
    )
  ).toMatchObject({
    state: "failed",
    text: null,
    segments: [],
    errorCode: "invalid_audio",
  });
});

test("provider failures retry durably and expired leases fence late results", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await processDeviceTranscriptions(
    env.DB,
    env.ATTACHMENTS,
    {
      run: async () => {
        throw new Error("provider unavailable");
      },
    },
    103
  );
  expect(
    await readDeviceTranscription(env.DB, "record-owner", session.id)
  ).toMatchObject({ state: "queued", errorCode: "transcription_unavailable" });
  let resolveOld: (value: { text: string }) => void = () => undefined;
  let entered: () => void = () => undefined;
  const waiting = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const now = Date.now() + 2_000_000;
  const old = processDeviceTranscriptions(
    env.DB,
    env.ATTACHMENTS,
    {
      run: () => {
        entered();
        return new Promise((resolve) => {
          resolveOld = resolve;
        });
      },
    },
    now
  );
  await waiting;
  await processDeviceTranscriptions(
    env.DB,
    env.ATTACHMENTS,
    { run: async () => ({ text: "recovered" }) },
    now + 900_001
  );
  resolveOld({ text: "stale" });
  await old;
  expect(
    (await readDeviceTranscription(env.DB, "record-owner", session.id))?.text
  ).toBe("recovered");
});

test("non-ASCII oversized output terminates within D1 byte limits", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await processDeviceTranscriptions(
    env.DB,
    env.ATTACHMENTS,
    { run: async () => ({ text: "文".repeat(100_000) }) },
    103
  );
  expect(
    await readDeviceTranscription(env.DB, "record-owner", session.id)
  ).toMatchObject({
    state: "failed",
    errorCode: "invalid_transcript",
    text: null,
  });
});

test("malformed provider segments cannot publish a completed unreadable transcript", async () => {
  const session = await recording();
  await completeDeviceSession(env.DB, "record-owner", session.id, 102);
  await processDeviceTranscriptions(
    env.DB,
    env.ATTACHMENTS,
    { run: async () => ({ text: "valid text", segments: { invalid: true } }) },
    103
  );
  expect(
    await readDeviceTranscription(env.DB, "record-owner", session.id)
  ).toMatchObject({
    state: "queued",
    errorCode: "transcription_unavailable",
    text: null,
  });
});
