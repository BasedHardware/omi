import type { DeviceSession, DeviceSessionState } from "@omi-core/contracts";

export const DEVICE_SESSION_CAPABILITIES = {
  maxSessionBytes: 26_214_400,
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
  ended_at: number | null;
  created_at: number;
  updated_at: number;
};

export type DeviceSessionCreateRequest = {
  deviceId: string;
  deviceName: string | null;
  codec: number;
};

export type DeviceSessionAudioRequest = {
  bytes: Uint8Array;
};

function isBoundedString(value: unknown, maxLength: number): value is string {
  return (
    typeof value === "string" && value.length > 0 && value.length <= maxLength
  );
}

function isSessionId(value: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/.test(
    value
  );
}

export function parseDeviceSessionCreate(
  body: unknown
): DeviceSessionCreateRequest | null {
  if (body === null || typeof body !== "object" || Array.isArray(body))
    return null;
  const item = body as Record<string, unknown>;
  if (
    Object.keys(item).some(
      (key) => !["deviceId", "deviceName", "codec"].includes(key)
    )
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
  if ("transcript" in item || "text" in item) return null;
  return {
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
  if (Object.keys(item).some((key) => key !== "bytesBase64")) return null;
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
    return { bytes };
  } catch {
    return null;
  }
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
    endedAt: row.ended_at,
  };
}

export async function openDeviceSession(
  db: D1Database,
  accountId: string,
  request: DeviceSessionCreateRequest,
  now: number
): Promise<DeviceSession> {
  const id = crypto.randomUUID();
  const r2Prefix = `device-sessions/${accountId}/${id}`;
  await db
    .prepare(
      `INSERT INTO device_sessions (
        id, account_id, device_id, device_name, codec, state, r2_prefix,
        byte_count, chunk_count, started_at, ended_at, created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, 'open', ?, 0, 0, ?, NULL, ?, ?)`
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
      now
    )
    .run();
  const row = await loadSession(db, accountId, id);
  if (row === null) throw new Error("device session insert failed");
  return toDeviceSession(row);
}

export type AppendResult =
  | { kind: "ok"; session: DeviceSession }
  | { kind: "not_found" }
  | { kind: "conflict" }
  | { kind: "too_large" };

export async function appendDeviceSessionAudio(
  db: D1Database,
  r2: R2Bucket,
  accountId: string,
  sessionId: string,
  bytes: Uint8Array,
  now: number
): Promise<AppendResult> {
  if (!isSessionId(sessionId)) return { kind: "not_found" };
  const row = await loadSession(db, accountId, sessionId);
  if (row === null) return { kind: "not_found" };
  if (row.state !== "open") return { kind: "conflict" };
  const nextBytes = row.byte_count + bytes.byteLength;
  if (nextBytes > DEVICE_SESSION_CAPABILITIES.maxSessionBytes)
    return { kind: "too_large" };
  const chunkIndex = row.chunk_count;
  const key = `${row.r2_prefix}/${String(chunkIndex).padStart(6, "0")}`;
  await r2.put(key, bytes, {
    httpMetadata: { contentType: "application/octet-stream" },
  });
  await db
    .prepare(
      `UPDATE device_sessions
       SET byte_count = ?, chunk_count = ?, updated_at = ?
       WHERE id = ? AND account_id = ? AND state = 'open'`
    )
    .bind(nextBytes, chunkIndex + 1, now, sessionId, accountId)
    .run();
  const updated = await loadSession(db, accountId, sessionId);
  if (updated === null) return { kind: "not_found" };
  return { kind: "ok", session: toDeviceSession(updated) };
}

export type CompleteResult =
  | { kind: "ok"; session: DeviceSession }
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
  if (row.state === "complete")
    return { kind: "ok", session: toDeviceSession(row) };
  await db
    .prepare(
      `UPDATE device_sessions
       SET state = 'complete', ended_at = ?, updated_at = ?
       WHERE id = ? AND account_id = ?`
    )
    .bind(now, now, sessionId, accountId)
    .run();
  const updated = await loadSession(db, accountId, sessionId);
  if (updated === null) return { kind: "not_found" };
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
