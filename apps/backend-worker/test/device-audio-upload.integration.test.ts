import { env } from "cloudflare:workers";
import { beforeEach, expect, test } from "vitest";
import {
  appendDeviceSessionAudio,
  appendDeviceSessionAudioBatch,
  completeDeviceSession,
  openDeviceSession,
  parseDeviceSessionAudioBatch,
} from "../src/device-sessions";

beforeEach(async () => {
  await env.DB.prepare("DELETE FROM device_sessions").run();
});

const bytes = new Uint8Array([0, 0, 0, 128, 129]);

test("batch parsing rejects ambiguous base64, nonconsecutive indices and extra fields", () => {
  expect(
    parseDeviceSessionAudioBatch({
      chunks: [
        { chunkIndex: 0, bytesBase64: "AQ==" },
        { chunkIndex: 1, bytesBase64: "Ag==" },
      ],
    })
  ).toEqual([
    { chunkIndex: 0, bytes: Uint8Array.of(1) },
    { chunkIndex: 1, bytes: Uint8Array.of(2) },
  ]);
  for (const body of [
    { chunks: [{ chunkIndex: 0, bytesBase64: "AR==" }] },
    { chunks: [{ chunkIndex: 0, bytesBase64: "AQ==\n" }] },
    {
      chunks: [
        { chunkIndex: 0, bytesBase64: "AQ==" },
        { chunkIndex: 2, bytesBase64: "AQ==" },
      ],
    },
    { chunks: [] },
    { chunks: [{ chunkIndex: 0, bytesBase64: "AQ==" }], transcript: "text" },
  ])
    expect(parseDeviceSessionAudioBatch(body)).toBeNull();
});

test("batch claims are atomic across duplicate conflicts and preserve packet bytes", async () => {
  const session = await open();
  const chunks = Array.from({ length: 3 }, (_, chunkIndex) => ({
    chunkIndex,
    bytes: Uint8Array.of(0, chunkIndex, 0, 128 + chunkIndex),
  }));
  const append = (values = chunks, owner = "owner") =>
    appendDeviceSessionAudioBatch(
      env.DB,
      env.ATTACHMENTS,
      owner,
      session.id,
      values,
      2
    );
  expect((await append(chunks.slice(0, 2))).kind).toBe("ok");
  expect(
    (
      await append([
        chunks[0]!,
        { ...chunks[1]!, bytes: Uint8Array.of(255) },
        chunks[2]!,
      ])
    ).kind
  ).toBe("conflict");
  expect(
    await env.DB.prepare("SELECT chunk_count FROM device_sessions WHERE id=?")
      .bind(session.id)
      .first()
  ).toEqual({ chunk_count: 2 });
  const results = await Promise.all([append(), append(), append()]);
  expect(results.every((result) => result.kind === "ok")).toBe(true);
  expect((await append(chunks, "other")).kind).toBe("not_found");
  expect(
    await env.DB.prepare(
      "SELECT chunk_count,byte_count,uploaded_chunk_count FROM device_sessions WHERE id=?"
    )
      .bind(session.id)
      .first()
  ).toEqual({ chunk_count: 3, byte_count: 12, uploaded_chunk_count: 3 });
  for (const chunk of chunks) {
    const object = await env.ATTACHMENTS.get(
      `device-sessions/owner/${session.id}/${String(chunk.chunkIndex).padStart(
        6,
        "0"
      )}`
    );
    expect(new Uint8Array(await object!.arrayBuffer())).toEqual(chunk.bytes);
  }
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 3)).kind
  ).toBe("ok");
  expect((await append()).kind).toBe("ok");
  expect((await append([{ chunkIndex: 3, bytes }])).kind).toBe("conflict");
});

test("partial R2 batch writes remain pending until an exact retry completes every packet", async () => {
  const session = await open();
  const chunks = Array.from({ length: 8 }, (_, chunkIndex) => ({
    chunkIndex,
    bytes,
  }));
  const storage = {
    put: async (key: string, value: Uint8Array) => {
      if (key.endsWith("000001")) throw new Error("synthetic storage failure");
      return env.ATTACHMENTS.put(key, value);
    },
  } as unknown as R2Bucket;
  expect(
    (
      await appendDeviceSessionAudioBatch(
        env.DB,
        storage,
        "owner",
        session.id,
        chunks,
        2
      )
    ).kind
  ).toBe("unavailable");
  expect(
    await env.DB.prepare(
      "SELECT chunk_count,uploaded_chunk_count FROM device_sessions WHERE id=?"
    )
      .bind(session.id)
      .first()
  ).toEqual({ chunk_count: 8, uploaded_chunk_count: 0 });
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 3)).kind
  ).toBe("conflict");
  expect(
    (
      await appendDeviceSessionAudioBatch(
        env.DB,
        env.ATTACHMENTS,
        "owner",
        session.id,
        chunks,
        4
      )
    ).kind
  ).toBe("ok");
  expect(
    (await completeDeviceSession(env.DB, "owner", session.id, 5)).kind
  ).toBe("ok");
});

test("capture ID creates exactly one session concurrently and preserves immutable inputs and terminal state", async () => {
  const request = {
    captureId: crypto.randomUUID(),
    deviceId: "pendant",
    deviceName: "Omi",
    codec: 1,
  };
  const [first, retry] = await Promise.all([
    openDeviceSession(env.DB, "owner", request, 10),
    openDeviceSession(env.DB, "owner", request, 11),
  ]);
  expect(first).not.toBeNull();
  expect(retry).toEqual(first);
  expect(first!.id).not.toBe(request.captureId);
  for (const change of [
    { deviceId: "other" },
    { deviceName: null },
    { codec: 21 },
  ]) {
    expect(
      await openDeviceSession(env.DB, "owner", { ...request, ...change }, 12)
    ).toBeNull();
  }
  const other = await openDeviceSession(env.DB, "other-owner", request, 13);
  expect(other?.id).not.toBe(first!.id);
  const completed = await completeDeviceSession(env.DB, "owner", first!.id, 14);
  expect(completed.kind).toBe("ok");
  expect(await openDeviceSession(env.DB, "owner", request, 15)).toMatchObject({
    id: first!.id,
    state: "complete",
    endedAt: 14,
  });
  expect(
    await env.DB.prepare(
      "SELECT COUNT(*) AS count FROM device_sessions WHERE account_id = ?"
    )
      .bind("owner")
      .first()
  ).toEqual({ count: 1 });
});

test("legacy sessions without capture IDs remain untouched and cannot be adopted by a new capture", async () => {
  const request = {
    captureId: crypto.randomUUID(),
    deviceId: "pendant",
    deviceName: null,
    codec: 1,
  };
  const legacy = await openDeviceSession(env.DB, "owner", request, 1);
  expect(legacy).not.toBeNull();
  await env.DB.prepare(
    "UPDATE device_sessions SET capture_id = NULL WHERE id = ?"
  )
    .bind(legacy!.id)
    .run();
  const fresh = await openDeviceSession(env.DB, "owner", request, 2);
  expect(fresh?.id).not.toBe(legacy!.id);
  expect(
    await env.DB.prepare(
      "SELECT capture_id, state, started_at FROM device_sessions WHERE id = ?"
    )
      .bind(legacy!.id)
      .first()
  ).toEqual({ capture_id: null, state: "open", started_at: 1 });
});
const open = async () => {
  const session = await openDeviceSession(
    env.DB,
    "owner",
    {
      captureId: crypto.randomUUID(),
      deviceId: "pendant",
      deviceName: null,
      codec: 1,
    },
    1
  );
  if (session === null) throw new Error("Recording creation failed");
  return session;
};

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

test("capture time is immutable provenance across retries and completion without replacing server chronology", async () => {
  for (const capturedAtMs of [undefined, 0, 8640000000000000]) {
    const request = {
      captureId: crypto.randomUUID(),
      deviceId: "pendant",
      deviceName: null,
      codec: 1,
      ...(capturedAtMs === undefined ? {} : { capturedAtMs }),
    };
    const [first, replay] = await Promise.all([
      openDeviceSession(env.DB, "owner", request, 10),
      openDeviceSession(env.DB, "owner", request, 11),
    ]);
    expect(replay).toEqual(first);
    expect(first?.capturedAtMs).toBe(capturedAtMs);
    if (capturedAtMs === undefined)
      expect(first).not.toHaveProperty("capturedAtMs");
    expect(first?.startedAt).toBeGreaterThanOrEqual(10);
    expect(first?.startedAt).toBeLessThanOrEqual(11);
    expect(
      await openDeviceSession(
        env.DB,
        "owner",
        {
          captureId: request.captureId,
          deviceId: request.deviceId,
          deviceName: request.deviceName,
          codec: request.codec,
          ...(capturedAtMs === undefined ? { capturedAtMs: 0 } : {}),
        },
        12
      )
    ).toBeNull();
    const completed = await completeDeviceSession(
      env.DB,
      "owner",
      first!.id,
      14
    );
    expect(completed.kind).toBe("ok");
    expect(await openDeviceSession(env.DB, "owner", request, 20)).toMatchObject(
      { id: first!.id, startedAt: first!.startedAt, endedAt: 14 }
    );
    expect(
      (await openDeviceSession(env.DB, "other", request, 20))?.id
    ).not.toBe(first!.id);
  }
});
