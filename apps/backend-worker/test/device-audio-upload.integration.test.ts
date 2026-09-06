import { env } from "cloudflare:workers";
import { beforeEach, expect, test } from "vitest";
import {
  appendDeviceSessionAudio,
  completeDeviceSession,
  openDeviceSession,
} from "../src/device-sessions";

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM device_sessions").run();
});

const bytes = new Uint8Array([0, 0, 0, 128, 129]);
const open = () =>
  openDeviceSession(
    env.DB,
    "owner",
    { deviceId: "pendant", deviceName: null, codec: 1 },
    1
  );

test("indexed upload replay changes counters once and rejects changed bytes, gaps and other accounts", async () => {
  const session = await open();
  const append = (payload = bytes, index = 0, owner = "owner") =>
    appendDeviceSessionAudio(
      env.DB,
      env.ATTACHMENTS,
      owner,
      session.id,
      payload,
      index,
      2
    );
  expect((await append(bytes, 1)).kind).toBe("conflict");
  expect((await append()).kind).toBe("ok");
  expect((await append()).kind).toBe("ok");
  expect((await append(new Uint8Array([0, 0, 0, 128, 130]))).kind).toBe(
    "conflict"
  );
  expect((await append(bytes, 0, "other")).kind).toBe("not_found");
  const row = await env.DB.prepare(
    "SELECT byte_count, chunk_count, uploaded_chunk_count FROM device_sessions WHERE id = ?"
  )
    .bind(session.id)
    .first();
  expect(row).toEqual({
    byte_count: bytes.length,
    chunk_count: 1,
    uploaded_chunk_count: 1,
  });
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 3)).kind
  ).toBe("ok");
  expect((await append()).kind).toBe("ok");
  expect((await append(bytes, 1)).kind).toBe("conflict");
});

test("transient R2 failure leaves recoverable reservation and cannot complete before retry", async () => {
  const session = await open();
  const unavailable = {
    put: async () => {
      throw new Error("temporary R2 outage");
    },
  } as unknown as R2Bucket;
  expect(
    (
      await appendDeviceSessionAudio(
        env.DB,
        unavailable,
        "owner",
        session.id,
        bytes,
        0,
        2
      )
    ).kind
  ).toBe("unavailable");
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 3)).kind
  ).toBe("conflict");
  expect(
    (
      await appendDeviceSessionAudio(
        env.DB,
        env.ATTACHMENTS,
        "owner",
        session.id,
        bytes,
        0,
        4
      )
    ).kind
  ).toBe("ok");
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 5)).kind
  ).toBe("ok");
  expect(
    await env.DB.prepare(
      "SELECT state, chunk_count, uploaded_chunk_count FROM device_sessions WHERE id = ?"
    )
      .bind(session.id)
      .first()
  ).toEqual({ state: "complete", chunk_count: 1, uploaded_chunk_count: 1 });
});

test("concurrent identical retries publish once and a late identical put cannot corrupt completed audio", async () => {
  const session = await open();
  let entered: () => void = () => undefined;
  let release: () => void = () => undefined;
  const waiting = new Promise<void>((resolve) => {
    entered = resolve;
  });
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  const slow = {
    put: async (key: string, value: Uint8Array) => {
      entered();
      await gate;
      return env.ATTACHMENTS.put(key, value);
    },
  } as unknown as R2Bucket;
  const first = appendDeviceSessionAudio(
    env.DB,
    slow,
    "owner",
    session.id,
    bytes,
    0,
    2
  );
  await waiting;
  expect(
    (
      await appendDeviceSessionAudio(
        env.DB,
        env.ATTACHMENTS,
        "owner",
        session.id,
        new Uint8Array([0, 0, 0, 130, 131]),
        0,
        3
      )
    ).kind
  ).toBe("conflict");
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 3)).kind
  ).toBe("conflict");
  expect(
    (
      await appendDeviceSessionAudio(
        env.DB,
        env.ATTACHMENTS,
        "owner",
        session.id,
        bytes,
        0,
        4
      )
    ).kind
  ).toBe("ok");
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 5)).kind
  ).toBe("ok");
  release();
  expect((await first).kind).toBe("ok");
  const row = await env.DB.prepare(
    "SELECT r2_prefix, chunk_count, uploaded_chunk_count FROM device_sessions WHERE id = ?"
  )
    .bind(session.id)
    .first<{
      r2_prefix: string;
      chunk_count: number;
      uploaded_chunk_count: number;
    }>();
  expect(row?.chunk_count).toBe(1);
  expect(row?.uploaded_chunk_count).toBe(1);
  const object = await env.ATTACHMENTS.get(`${row!.r2_prefix}/000000`);
  expect(new Uint8Array(await object!.arrayBuffer())).toEqual(bytes);
});

test("historical unindexed chunks cannot be overwritten and the transcription size cap is enforced", async () => {
  const session = await open();
  await env.DB.prepare(
    "UPDATE device_sessions SET chunk_count = 1, uploaded_chunk_count = 1, byte_count = 8388608 WHERE id = ?"
  )
    .bind(session.id)
    .run();
  expect(
    (
      await appendDeviceSessionAudio(
        env.DB,
        env.ATTACHMENTS,
        "owner",
        session.id,
        bytes,
        0,
        2
      )
    ).kind
  ).toBe("conflict");
  expect(
    (
      await appendDeviceSessionAudio(
        env.DB,
        env.ATTACHMENTS,
        "owner",
        session.id,
        bytes,
        1,
        2
      )
    ).kind
  ).toBe("too_large");
  expect(
    (
      await appendDeviceSessionAudio(
        env.DB,
        env.ATTACHMENTS,
        "owner",
        session.id,
        bytes,
        65536,
        2
      )
    ).kind
  ).toBe("too_large");
  expect(
    await env.DB.prepare(
      "SELECT COUNT(*) AS count FROM device_audio_chunks WHERE session_id = ?"
    )
      .bind(session.id)
      .first()
  ).toEqual({ count: 0 });
});
