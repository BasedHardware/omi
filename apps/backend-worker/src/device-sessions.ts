import type { DeviceSession, DeviceSessionState } from "@omi-core/contracts";

export const DEVICE_SESSION_CAPABILITIES = {
  maxSessionBytes: 8_388_608,
  maxChunks: 65_536,
  maxChunkBytes: 1_048_576,
  maxDeviceIdLength: 128,
  maxDeviceNameLength: 256,
} as const;

type StoredSession = {
  id: string;
  account_id: string;
  device_id: string;
  device_name: string | null;
  codec: number;
  state: DeviceSessionState;
  r2_prefix: string;
  byte_count: number;
  chunk_count: number;
  started_at: number;
  captured_at_ms: number | null;
  ended_at: number | null;
  created_at: number;
  updated_at: number;
};

export type DeviceSessionCreateRequest = {
  captureId: string;
  capturedAtMs?: number;
  deviceId: string;
  deviceName: string | null;
  codec: number;
};

export type DeviceSessionAudioRequest = {
  chunkIndex: number;
  bytes: Uint8Array;
};

function isBoundedString(value: unknown, maxLength: number): value is string {
  return (
    typeof value === "string" && value.length > 0 && value.length <= maxLength
  );
}

export const DEVICE_SESSION_ID =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function isSessionId(value: string): boolean {
  return DEVICE_SESSION_ID.test(value);
}

export function parseDeviceSessionCreate(
  body: unknown
): DeviceSessionCreateRequest | null {
  if (body === null || typeof body !== "object" || Array.isArray(body))
    return null;
  const item = body as Record<string, unknown>;
  if (
    Object.keys(item).some(
      (key) =>
        ![
          "captureId",
          "deviceId",
          "deviceName",
          "codec",
          "capturedAtMs",
        ].includes(key)
    )
  )
    return null;
  if (
    typeof item["captureId"] !== "string" ||
    !DEVICE_SESSION_ID.test(item["captureId"])
  )
    return null;
  if (
    !isBoundedString(
      item["deviceId"],
      DEVICE_SESSION_CAPABILITIES.maxDeviceIdLength
    )
  )
    return null;
  if (
    item["deviceName"] !== undefined &&
    item["deviceName"] !== null &&
    !isBoundedString(
      item["deviceName"],
      DEVICE_SESSION_CAPABILITIES.maxDeviceNameLength
    )
  )
    return null;
  if (
    typeof item["codec"] !== "number" ||
    !Number.isInteger(item["codec"]) ||
    item["codec"] < 0 ||
    item["codec"] > 255
  )
    return null;
  if (
    item["capturedAtMs"] !== undefined &&
    (!Number.isSafeInteger(item["capturedAtMs"]) ||
      (item["capturedAtMs"] as number) < 0 ||
      (item["capturedAtMs"] as number) > 8_640_000_000_000_000)
  )
    return null;
  if ("transcript" in item || "text" in item) return null;
  return {
    captureId: item["captureId"],
    ...(item["capturedAtMs"] === undefined
      ? {}
      : { capturedAtMs: item["capturedAtMs"] as number }),
    deviceId: item["deviceId"],
    deviceName:
      typeof item["deviceName"] === "string" ? item["deviceName"] : null,
    codec: item["codec"],
  };
}

export function parseDeviceSessionAudio(
  body: unknown
): DeviceSessionAudioRequest | null {
  if (body === null || typeof body !== "object" || Array.isArray(body))
    return null;
  const item = body as Record<string, unknown>;
  if (
    Object.keys(item).some(
      (key) => !["bytesBase64", "chunkIndex"].includes(key)
    )
  )
    return null;
  const chunkIndex = item["chunkIndex"];
  if (
    typeof chunkIndex !== "number" ||
    !Number.isSafeInteger(chunkIndex) ||
    chunkIndex < 0 ||
    chunkIndex >= DEVICE_SESSION_CAPABILITIES.maxChunks
  )
    return null;
  if (!isBoundedString(item["bytesBase64"], 1_572_864)) return null;
  if ("transcript" in item || "text" in item) return null;
  try {
    const binary = atob(item["bytesBase64"]);
    if (binary.length === 0) return null;
    if (binary.length > DEVICE_SESSION_CAPABILITIES.maxChunkBytes) return null;
    const bytes = new Uint8Array(binary.length);
    for (let index = 0; index < binary.length; index += 1) {
      bytes[index] = binary.charCodeAt(index);
    }
    return { bytes, chunkIndex };
  } catch {
    return null;
  }
}

export function parseDeviceSessionAudioBatch(
  body: unknown
): readonly DeviceSessionAudioRequest[] | null {
  if (body === null || typeof body !== "object" || Array.isArray(body))
    return null;
  const item = body as Record<string, unknown>;
  if (
    Object.keys(item).join(",") !== "chunks" ||
    !Array.isArray(item["chunks"]) ||
    item["chunks"].length < 1 ||
    item["chunks"].length > 128
  )
    return null;
  const chunks: DeviceSessionAudioRequest[] = [];
  let total = 0;
  for (const value of item["chunks"]) {
    const chunk = parseDeviceSessionAudio(value);
    if (
      chunk === null ||
      (chunks.length > 0 && chunk.chunkIndex !== chunks.at(-1)!.chunkIndex + 1)
    )
      return null;
    const encoded = (value as Record<string, unknown>)["bytesBase64"] as string;
    if (
      !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(
        encoded
      ) ||
      btoa(atob(encoded)) !== encoded
    )
      return null;
    total += chunk.bytes.byteLength;
    if (total > DEVICE_SESSION_CAPABILITIES.maxChunkBytes) return null;
    chunks.push(chunk);
  }
  return chunks;
}

export function toDeviceSession(row: StoredSession): DeviceSession {
  return {
    id: row.id,
    deviceId: row.device_id,
    deviceName: row.device_name,
    codec: row.codec,
    state: row.state,
    byteCount: row.byte_count,
    chunkCount: row.chunk_count,
    startedAt: row.started_at,
    ...(row.captured_at_ms == null ? {} : { capturedAtMs: row.captured_at_ms }),
    endedAt: row.ended_at,
  };
}

export async function openDeviceSession(
  db: D1Database,
  accountId: string,
  request: DeviceSessionCreateRequest,
  now: number
): Promise<DeviceSession | null> {
  if (parseDeviceSessionCreate(request) === null) return null;
  const id = crypto.randomUUID();
  const r2Prefix = `device-sessions/${accountId}/${id}`;
  await db
    .prepare(
      `INSERT INTO device_sessions (
        id, account_id, device_id, device_name, codec, state, r2_prefix,
        byte_count, chunk_count, started_at, ended_at, created_at, updated_at, capture_id, captured_at_ms
      ) VALUES (?, ?, ?, ?, ?, 'open', ?, 0, 0, ?, NULL, ?, ?, ?, ?)
      ON CONFLICT(account_id, capture_id) DO NOTHING`
    )
    .bind(
      id,
      accountId,
      request.deviceId,
      request.deviceName,
      request.codec,
      r2Prefix,
      now,
      now,
      now,
      request.captureId,
      request.capturedAtMs ?? null
    )
    .run();
  const row = await db
    .prepare(
      "SELECT * FROM device_sessions WHERE account_id = ? AND capture_id = ?"
    )
    .bind(accountId, request.captureId)
    .first<StoredSession>();
  if (row === null) throw new Error("device session insert failed");
  if (
    row.device_id !== request.deviceId ||
    row.device_name !== request.deviceName ||
    row.codec !== request.codec ||
    (row.captured_at_ms ?? null) !== (request.capturedAtMs ?? null)
  )
    return null;
  return toDeviceSession(row);
}

export type AppendResult =
  | { kind: "ok"; session: DeviceSession }
  | { kind: "not_found" }
  | { kind: "conflict" }
  | { kind: "too_large" }
  | { kind: "unavailable" };

export async function appendDeviceSessionAudioBatch(
  db: D1Database,
  r2: R2Bucket,
  accountId: string,
  sessionId: string,
  chunks: readonly DeviceSessionAudioRequest[],
  now: number
): Promise<AppendResult> {
  if (!isSessionId(sessionId)) return { kind: "not_found" };
  if (!Array.isArray(chunks) || chunks.length < 1 || chunks.length > 128)
    return { kind: "too_large" };
  let total = 0;
  for (let position = 0; position < chunks.length; position += 1) {
    const chunk = chunks[position];
    if (
      !chunk ||
      !Number.isSafeInteger(chunk.chunkIndex) ||
      chunk.chunkIndex < 0 ||
      chunk.chunkIndex >= DEVICE_SESSION_CAPABILITIES.maxChunks ||
      !(chunk.bytes instanceof Uint8Array) ||
      chunk.bytes.byteLength < 1 ||
      (position > 0 &&
        chunk.chunkIndex !== chunks[position - 1]!.chunkIndex + 1)
    )
      return { kind: "conflict" };
    total += chunk.bytes.byteLength;
    if (total > DEVICE_SESSION_CAPABILITIES.maxChunkBytes)
      return { kind: "too_large" };
  }
  const session = await loadSession(db, accountId, sessionId);
  if (session === null) return { kind: "not_found" };
  if (session.state === "failed") return { kind: "conflict" };
  const claims = await Promise.all(
    chunks.map(async (chunk) => ({
      index: chunk.chunkIndex,
      size: chunk.bytes.byteLength,
      hash: Array.from(
        new Uint8Array(await crypto.subtle.digest("SHA-256", chunk.bytes)),
        (value) => value.toString(16).padStart(2, "0")
      ).join(""),
    }))
  );
  const encoded = JSON.stringify(claims);
  await db
    .prepare(
      `WITH incoming AS MATERIALIZED (
    SELECT json_extract(value,'$.index') AS chunk_index,json_extract(value,'$.size') AS size_bytes,
      json_extract(value,'$.hash') AS sha256 FROM json_each(?)
  ), eligible AS MATERIALIZED (
    SELECT s.id FROM device_sessions s WHERE s.id=? AND s.account_id=? AND s.state<>'failed'
      AND (SELECT min(chunk_index) FROM incoming)<=s.chunk_count
      AND NOT EXISTS(SELECT 1 FROM incoming i LEFT JOIN device_audio_chunks c
        ON c.session_id=s.id AND c.chunk_index=i.chunk_index
        WHERE (c.chunk_index IS NOT NULL AND (c.sha256<>i.sha256 OR c.size_bytes<>i.size_bytes))
          OR (c.chunk_index IS NULL AND (i.chunk_index<s.chunk_count OR s.state<>'open')))
      AND s.byte_count+coalesce((SELECT sum(i.size_bytes) FROM incoming i WHERE NOT EXISTS(
        SELECT 1 FROM device_audio_chunks c WHERE c.session_id=s.id AND c.chunk_index=i.chunk_index)),0)<=?
  ) INSERT INTO device_audio_chunks(session_id,chunk_index,sha256,size_bytes)
    SELECT e.id,i.chunk_index,i.sha256,i.size_bytes FROM eligible e CROSS JOIN incoming i
    WHERE true ORDER BY i.chunk_index ON CONFLICT(session_id,chunk_index) DO NOTHING`
    )
    .bind(
      encoded,
      sessionId,
      accountId,
      DEVICE_SESSION_CAPABILITIES.maxSessionBytes
    )
    .run();
  const stored = await db
    .prepare(
      `SELECT c.chunk_index,c.sha256,c.size_bytes,c.uploaded
    FROM device_audio_chunks c JOIN device_sessions s ON s.id=c.session_id
    WHERE s.id=? AND s.account_id=? AND c.chunk_index BETWEEN ? AND ? ORDER BY c.chunk_index`
    )
    .bind(sessionId, accountId, claims[0]!.index, claims.at(-1)!.index)
    .all<{
      chunk_index: number;
      sha256: string;
      size_bytes: number;
      uploaded: number;
    }>();
  if (
    stored.results.some((row) => {
      const claim = claims[row.chunk_index - claims[0]!.index];
      return (
        !claim || row.sha256 !== claim.hash || row.size_bytes !== claim.size
      );
    })
  )
    return { kind: "conflict" };
  if (stored.results.length !== claims.length) {
    const current = await loadSession(db, accountId, sessionId);
    if (current === null) return { kind: "not_found" };
    const missing = claims.filter(
      (claim) => !stored.results.some((row) => row.chunk_index === claim.index)
    );
    if (
      current.state === "open" &&
      claims[0]!.index <= current.chunk_count &&
      missing.every((claim) => claim.index >= current.chunk_count) &&
      current.byte_count + missing.reduce((sum, claim) => sum + claim.size, 0) >
        DEVICE_SESSION_CAPABILITIES.maxSessionBytes
    )
      return { kind: "too_large" };
    return { kind: "conflict" };
  }
  let failed = false;
  for (let offset = 0; offset < chunks.length; offset += 6) {
    const results = await Promise.allSettled(
      chunks.slice(offset, offset + 6).map(async (chunk, position) => {
        if (stored.results[offset + position]!.uploaded === 1) return;
        await r2.put(
          session.r2_prefix + "/" + String(chunk.chunkIndex).padStart(6, "0"),
          chunk.bytes,
          { httpMetadata: { contentType: "application/octet-stream" } }
        );
      })
    );
    if (results.some((result) => result.status === "rejected")) {
      failed = true;
      break;
    }
  }
  if (failed) return { kind: "unavailable" };
  await db.batch([
    db
      .prepare(
        `UPDATE device_audio_chunks SET uploaded=1 WHERE session_id=? AND uploaded=0
      AND chunk_index BETWEEN ? AND ? AND EXISTS(SELECT 1 FROM device_sessions WHERE id=? AND account_id=?)`
      )
      .bind(
        sessionId,
        claims[0]!.index,
        claims.at(-1)!.index,
        sessionId,
        accountId
      ),
    db
      .prepare(
        "UPDATE device_sessions SET updated_at=? WHERE id=? AND account_id=? AND state='open'"
      )
      .bind(now, sessionId, accountId),
  ]);
  const uploaded = await loadSession(db, accountId, sessionId);
  if (uploaded === null) return { kind: "not_found" };
  if (uploaded.state === "failed") return { kind: "conflict" };
  return { kind: "ok", session: toDeviceSession(uploaded) };
}

export async function appendDeviceSessionAudio(
  db: D1Database,
  r2: R2Bucket,
  accountId: string,
  sessionId: string,
  bytes: Uint8Array,
  chunkIndex: number,
  now: number
): Promise<AppendResult> {
  if (!isSessionId(sessionId)) return { kind: "not_found" };
  if (
    !Number.isSafeInteger(chunkIndex) ||
    chunkIndex < 0 ||
    chunkIndex >= DEVICE_SESSION_CAPABILITIES.maxChunks ||
    bytes.byteLength === 0 ||
    bytes.byteLength > DEVICE_SESSION_CAPABILITIES.maxChunkBytes
  )
    return { kind: "too_large" };
  const session = await loadSession(db, accountId, sessionId);
  if (session === null) return { kind: "not_found" };
  if (session.state === "failed") return { kind: "conflict" };
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", bytes));
  const hash = Array.from(digest, (value) =>
    value.toString(16).padStart(2, "0")
  ).join("");
  await db
    .prepare(
      "INSERT INTO device_audio_chunks (session_id, chunk_index, sha256, size_bytes) SELECT id, ?, ?, ? FROM device_sessions WHERE id = ? AND account_id = ? AND state = 'open' AND chunk_count = ? AND byte_count + ? <= ? ON CONFLICT(session_id, chunk_index) DO NOTHING"
    )
    .bind(
      chunkIndex,
      hash,
      bytes.byteLength,
      sessionId,
      accountId,
      chunkIndex,
      bytes.byteLength,
      DEVICE_SESSION_CAPABILITIES.maxSessionBytes
    )
    .run();
  const chunk = await db
    .prepare(
      "SELECT c.sha256, c.size_bytes, c.uploaded FROM device_audio_chunks c JOIN device_sessions s ON s.id = c.session_id WHERE c.session_id = ? AND c.chunk_index = ? AND s.account_id = ?"
    )
    .bind(sessionId, chunkIndex, accountId)
    .first<{ sha256: string; size_bytes: number; uploaded: number }>();
  if (chunk === null) {
    const row = await loadSession(db, accountId, sessionId);
    if (row === null) return { kind: "not_found" };
    if (
      row.state === "open" &&
      row.chunk_count === chunkIndex &&
      row.byte_count + bytes.byteLength >
        DEVICE_SESSION_CAPABILITIES.maxSessionBytes
    )
      return { kind: "too_large" };
    return { kind: "conflict" };
  }
  if (chunk.sha256 !== hash || chunk.size_bytes !== bytes.byteLength)
    return { kind: "conflict" };
  if (chunk.uploaded === 0) {
    const key = session.r2_prefix + "/" + String(chunkIndex).padStart(6, "0");
    try {
      await r2.put(key, bytes, {
        httpMetadata: { contentType: "application/octet-stream" },
      });
    } catch {
      return { kind: "unavailable" };
    }
    await db
      .prepare(
        "UPDATE device_audio_chunks SET uploaded = 1 WHERE session_id = ? AND chunk_index = ? AND sha256 = ? AND uploaded = 0"
      )
      .bind(sessionId, chunkIndex, hash)
      .run();
    await db
      .prepare(
        "UPDATE device_sessions SET updated_at = ? WHERE id = ? AND account_id = ? AND state = 'open'"
      )
      .bind(now, sessionId, accountId)
      .run();
  }
  const uploaded = await loadSession(db, accountId, sessionId);
  if (uploaded === null) return { kind: "not_found" };
  if (uploaded.state === "failed") return { kind: "conflict" };
  return { kind: "ok", session: toDeviceSession(uploaded) };
}

export type CompleteResult =
  | { kind: "ok"; session: DeviceSession }
  | { kind: "conflict" }
  | { kind: "not_found" };

export async function completeDeviceSession(
  db: D1Database,
  accountId: string,
  sessionId: string,
  now: number
): Promise<CompleteResult> {
  if (!isSessionId(sessionId)) return { kind: "not_found" };
  const row = await loadSession(db, accountId, sessionId);
  if (row === null) return { kind: "not_found" };
  if (row.state === "failed") return { kind: "conflict" };
  if (row.state === "complete")
    return { kind: "ok", session: toDeviceSession(row) };
  await db
    .prepare(
      `UPDATE device_sessions
       SET state = 'complete', ended_at = ?, updated_at = ?
       WHERE id = ? AND account_id = ? AND state = 'open'
         AND uploaded_chunk_count = chunk_count`
    )
    .bind(now, now, sessionId, accountId)
    .run();
  const updated = await loadSession(db, accountId, sessionId);
  if (updated === null) return { kind: "not_found" };
  if (updated.state !== "complete") return { kind: "conflict" };
  return { kind: "ok", session: toDeviceSession(updated) };
}

export async function listDeviceSessions(
  db: D1Database,
  accountId: string
): Promise<DeviceSession[]> {
  const result = await db
    .prepare(
      `SELECT id, account_id, device_id, device_name, codec, state, r2_prefix,
              byte_count, chunk_count, started_at, ended_at, created_at, updated_at
       FROM device_sessions
       WHERE account_id = ?
       ORDER BY started_at DESC, id DESC`
    )
    .bind(accountId)
    .all<StoredSession>();
  return result.results.map((row) => toDeviceSession(row));
}

async function loadSession(
  db: D1Database,
  accountId: string,
  sessionId: string
): Promise<StoredSession | null> {
  return db
    .prepare(
      `SELECT id, account_id, device_id, device_name, codec, state, r2_prefix,
              byte_count, chunk_count, started_at, ended_at, created_at, updated_at
       FROM device_sessions
       WHERE id = ? AND account_id = ?`
    )
    .bind(sessionId, accountId)
    .first<StoredSession>();
}
