import { env } from "cloudflare:workers";
import { beforeEach, expect, test } from "vitest";
import {
  openDeviceSession,
  appendDeviceSessionAudio,
  completeDeviceSession,
} from "../src/device-sessions";
import {
  processDeviceTranscriptions,
  readDeviceTranscription,
} from "../src/device-transcriptions";
import { readConversations } from "../src/conversations";

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM device_transcriptions").run();
  await env.DB.prepare("DELETE FROM device_sessions").run();
  await env.DB.prepare("DELETE FROM chat_messages").run();
});

async function recording() {
  const session = await openDeviceSession(
    env.DB,
    "record-owner",
    {
      captureId: crypto.randomUUID(),
      deviceId: "pendant",
      deviceName: "Omi",
      codec: 1,
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
    (await readDeviceTranscription(env.DB, "record-owner", session.id))?.text
  ).toBe("The meeting is tomorrow.");
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
  ).toMatchObject({ state: "failed", errorCode: "unsupported_codec" });
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
    errorCode: "transcript_too_large",
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
