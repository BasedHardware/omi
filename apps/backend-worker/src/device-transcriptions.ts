import { Buffer } from "node:buffer";
import {
  buildDeviceAudio,
  DeviceAudioError,
} from "../../../backends/example-platform/drivers/model/device-audio";

export const TRANSCRIPTION_MODEL = "@cf/openai/whisper-large-v3-turbo";
export type TranscriptionAI = {
  run(
    model: typeof TRANSCRIPTION_MODEL,
    input: {
      audio: string;
      task: "transcribe";
      vad_filter: boolean;
    }
  ): Promise<unknown>;
};

class TranscriptionInputError extends Error {
  constructor(readonly code: string) {
    super(code);
  }
}

type Job = {
  session_id: string;
  account_id: string;
  attempts: number;
};

export async function processDeviceTranscriptions(
  db: D1Database,
  r2: R2Bucket,
  ai: TranscriptionAI,
  now = Date.now(),
  target?: { accountId: string; sessionId: string }
): Promise<void> {
  // ponytail: one claim per minute; use a queue above 60 recordings per hour.
  const due = await db
    .prepare(
      "SELECT session_id, account_id, attempts FROM device_transcriptions WHERE state IN ('queued', 'running') AND available_at <= ?" +
        (target ? " AND account_id = ? AND session_id = ?" : "") +
        " ORDER BY available_at, session_id LIMIT 1"
    )
    .bind(...(target ? [now, target.accountId, target.sessionId] : [now]))
    .all<Job>();
  for (const candidate of due.results) {
    const token = crypto.randomUUID();
    const job = await db
      .prepare(
        "UPDATE device_transcriptions SET state = 'running', attempts = attempts + 1, lease_token = ?, available_at = ?, updated_at = ? WHERE session_id = ? AND account_id = ? AND state IN ('queued', 'running') AND available_at <= ? RETURNING session_id, account_id, attempts"
      )
      .bind(
        token,
        now + 900_000,
        now,
        candidate.session_id,
        candidate.account_id,
        now
      )
      .first<Job>();
    if (job === null) continue;
    try {
      if (job.attempts > 5) throw new TranscriptionInputError("attempt_limit");
      const session = await db
        .prepare(
          "SELECT codec, r2_prefix, chunk_count, byte_count FROM device_sessions WHERE id = ? AND account_id = ? AND state = 'complete' AND uploaded_chunk_count = chunk_count"
        )
        .bind(job.session_id, job.account_id)
        .first<{
          codec: number;
          r2_prefix: string;
          chunk_count: number;
          byte_count: number;
        }>();
      if (session === null)
        throw new TranscriptionInputError("invalid_session");
      if (
        !Number.isSafeInteger(session.byte_count) ||
        session.byte_count < 1 ||
        !Number.isSafeInteger(session.chunk_count) ||
        session.chunk_count < 1
      ) {
        throw new TranscriptionInputError("invalid_audio_size");
      }
      if (session.byte_count > 8_388_608 || session.chunk_count > 65_536) {
        throw new DeviceAudioError("audio_too_large");
      }
      const packets: Uint8Array[] = [];
      let byteCount = 0;
      for (let start = 0; start < session.chunk_count; start += 6) {
        const batch = await Promise.all(
          Array.from(
            { length: Math.min(6, session.chunk_count - start) },
            async (_, offset) => {
              const index = start + offset;
              const object = await r2.get(
                `${session.r2_prefix}/${String(index).padStart(6, "0")}`
              );
              if (object === null)
                throw new TranscriptionInputError("missing_audio");
              if (
                object.size > 1_048_576 ||
                byteCount + object.size > session.byte_count
              )
                throw new TranscriptionInputError("invalid_audio_size");
              byteCount += object.size;
              const bytes = new Uint8Array(await object.arrayBuffer());
              if (bytes.byteLength !== object.size)
                throw new TranscriptionInputError("invalid_audio_size");
              return bytes;
            }
          )
        );
        packets.push(...batch);
      }
      if (byteCount !== session.byte_count)
        throw new TranscriptionInputError("invalid_audio_size");
      const audio = buildDeviceAudio(session.codec, packets);
      const result = await ai.run(TRANSCRIPTION_MODEL, {
        audio: Buffer.from(audio.bytes).toString("base64"),
        task: "transcribe",
        vad_filter: true,
      });
      if (
        result === null ||
        typeof result !== "object" ||
        !("text" in result) ||
        typeof result.text !== "string" ||
        ("segments" in result && !Array.isArray(result.segments))
      ) {
        throw new Error("Invalid transcription response");
      }
      if (new TextEncoder().encode(result.text).byteLength > 262_144) {
        throw new TranscriptionInputError("transcript_too_large");
      }
      const segments =
        "segments" in result ? JSON.stringify(result.segments) : null;
      if (
        segments !== null &&
        segments !== undefined &&
        new TextEncoder().encode(segments).byteLength > 1_048_576
      ) {
        throw new TranscriptionInputError("transcript_too_large");
      }
      const info =
        "transcription_info" in result ? result.transcription_info : null;
      const language =
        info !== null &&
        typeof info === "object" &&
        "language" in info &&
        typeof info.language === "string"
          ? info.language.slice(0, 32)
          : null;
      await db
        .prepare(
          "UPDATE device_transcriptions SET state = 'completed', text = ?, segments = ?, language = ?, discarded_leading_packets = ?, error_code = NULL, lease_token = NULL, updated_at = ? WHERE session_id = ? AND account_id = ? AND state = 'running' AND lease_token = ?"
        )
        .bind(
          result.text.trim(),
          segments ?? null,
          language,
          audio.discardedLeadingPackets,
          Date.now(),
          job.session_id,
          job.account_id,
          token
        )
        .run();
    } catch (error) {
      const terminal =
        error instanceof DeviceAudioError ||
        error instanceof TranscriptionInputError ||
        job.attempts >= 5;
      await db
        .prepare(
          "UPDATE device_transcriptions SET state = ?, error_code = ?, lease_token = NULL, available_at = ?, updated_at = ? WHERE session_id = ? AND account_id = ? AND state = 'running' AND lease_token = ?"
        )
        .bind(
          terminal ? "failed" : "queued",
          error instanceof DeviceAudioError ||
            error instanceof TranscriptionInputError
            ? error.code
            : "transcription_unavailable",
          Date.now() + Math.min(900_000, 30_000 * 2 ** job.attempts),
          Date.now(),
          job.session_id,
          job.account_id,
          token
        )
        .run();
    }
  }
}

export type DeviceTranscriptionRow = {
  sessionId: string;
  state: string;
  text: string | null;
  segments: string | null;
  language: string | null;
  discardedLeadingPackets: number;
  errorCode: string | null;
  updatedAt: number;
};

export type DeviceTranscriptionProjection = {
  sessionId: string;
  state: "queued" | "running" | "completed" | "failed";
  text: string | null;
  segments: unknown[];
  language: string | null;
  discardedLeadingPackets: number;
  errorCode: string | null;
  updatedAt: number;
};

export function projectDeviceTranscription(
  row: DeviceTranscriptionRow | null
): DeviceTranscriptionProjection | null {
  if (row === null) return null;
  if (
    typeof row.sessionId !== "string" ||
    (row.state !== "queued" &&
      row.state !== "running" &&
      row.state !== "completed" &&
      row.state !== "failed") ||
    !(row.text === null || typeof row.text === "string") ||
    (row.state === "completed" && typeof row.text !== "string") ||
    !(row.language === null || typeof row.language === "string") ||
    !(row.errorCode === null || typeof row.errorCode === "string") ||
    !Number.isSafeInteger(row.updatedAt) ||
    row.updatedAt < 0 ||
    !Number.isSafeInteger(row.discardedLeadingPackets) ||
    row.discardedLeadingPackets < 0
  ) {
    return null;
  }
  let segments: unknown = [];
  if (row.segments !== null) {
    if (typeof row.segments !== "string") return null;
    try {
      segments = JSON.parse(row.segments);
    } catch {
      return null;
    }
  }
  if (!Array.isArray(segments)) return null;
  return {
    sessionId: row.sessionId,
    state: row.state,
    text: row.text,
    segments,
    language: row.language,
    discardedLeadingPackets: row.discardedLeadingPackets,
    errorCode: row.errorCode,
    updatedAt: row.updatedAt,
  };
}

export async function readDeviceTranscription(
  db: D1Database,
  accountId: string,
  sessionId: string
) {
  return db
    .prepare(
      "SELECT session_id AS sessionId, state, text, segments, language, discarded_leading_packets AS discardedLeadingPackets, error_code AS errorCode, updated_at AS updatedAt FROM device_transcriptions WHERE session_id = ? AND account_id = ?"
    )
    .bind(sessionId, accountId)
    .first<DeviceTranscriptionRow>();
}
