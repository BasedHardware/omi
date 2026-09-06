import { randomUUID } from "node:crypto";
import type { AuthorizedLedgerWriteContext } from "../../apps/service/auth/authorized-context";
import type { DeviceTranscriptionRecord } from "../../apps/service/listen/device-transcription";
import type { PrerecordedTranscriptionSource } from "../../apps/service/listen/prerecorded-transcription";
import { parsePrerecordedTranscription } from "../../apps/service/listen/prerecorded-transcription";
import { LISTEN_CAPTURE_FINALIZE_VERSION } from "../../apps/service/stores/listen-finalization-repository";
import { buildDeviceAudio, DeviceAudioError } from "../model/device-audio";
import { PrerecordedTranscriptionUnavailable } from "../model/deepgram-transcription";
import { createPostgresDeviceTranscriptionRepository, createPostgresListenFinalizationRepository } from "./listen-finalization-repository";
import type { PostgresTransactionPool } from "./connection";
import { PostgresRepositoryError } from "./transaction";

export async function transcribeDeviceSession(options: {
  readonly pool: PostgresTransactionPool;
  readonly authorize: (signal: AbortSignal) => Promise<AuthorizedLedgerWriteContext>;
  readonly sessionId: string;
  readonly source: PrerecordedTranscriptionSource;
  readonly signal: AbortSignal;
}): Promise<DeviceTranscriptionRecord | null> {
  const initial = await options.authorize(options.signal);
  const authorize = async (signal = options.signal) => {
    signal.throwIfAborted();
    const current = await options.authorize(signal);
    signal.throwIfAborted();
    if (current.account_id !== initial.account_id || current.principal_id !== initial.principal_id) throw new PostgresRepositoryError("authorization_state_denied");
    return current;
  };
  const bindPool = (signal: AbortSignal): PostgresTransactionPool => Object.freeze({
    withTransaction: (transaction, callback) => options.pool.withTransaction({ ...transaction, signal }, callback),
  });
  const requestPool = bindPool(options.signal);
  const repository = createPostgresDeviceTranscriptionRepository({ pool: requestPool });
  const token = randomUUID();
  const claimed = await repository.claim(initial, options.sessionId, token);
  if (claimed === null) return null;
  const { owned, ...snapshot } = claimed;
  let record: DeviceTranscriptionRecord = snapshot;
  if (record.state === "completed" || record.state === "failed") return record;
  if (record.providerResult === null) {
    if (!owned) return record;
    const packets = await repository.loadAudio(await authorize(), options.sessionId, token);
    let discarded = 0;
    let result;
    try {
      if (packets.length !== record.chunkCount || packets.reduce((sum, packet) => sum + packet.length, 0) !== record.byteCount) throw new DeviceAudioError("invalid_packet");
      const audio = buildDeviceAudio(record.codec, packets);
      discarded = audio.discardedLeadingPackets;
      result = parsePrerecordedTranscription(await options.source.transcribe({ audio: audio.bytes, contentType: audio.contentType, signal: options.signal }));
      if (Math.abs(result.durationSeconds - audio.durationSeconds) > 1) throw new TypeError("invalid_transcription_duration");
    } catch (cause) {
      options.signal.throwIfAborted();
      const code = cause instanceof DeviceAudioError ? "invalid_audio" : cause instanceof TypeError ? "invalid_transcript" : "transcription_unavailable";
      const retryable = cause instanceof PrerecordedTranscriptionUnavailable ? cause.retryable : !(cause instanceof DeviceAudioError || cause instanceof TypeError);
      return repository.save(await authorize(), options.sessionId, token, null, discarded, code, retryable);
    }
    const persistence = new AbortController();
    const timer = setTimeout(() => persistence.abort(), 10_000);
    try {
      const persistenceRepository = createPostgresDeviceTranscriptionRepository({ pool: bindPool(persistence.signal) });
      record = await persistenceRepository.save(await authorize(persistence.signal), options.sessionId, token, result, discarded, null, false);
    } finally { clearTimeout(timer); }
  }
  options.signal.throwIfAborted();
  const result = record.providerResult;
  if (result === null) throw new PostgresRepositoryError("persistence_failed");
  const finalization = createPostgresListenFinalizationRepository({ pool: requestPool });
  const endedAt = new Date(Date.parse(record.startedAt) + Math.ceil(Math.max(result.durationSeconds, ...result.segments.map(segment => segment.end)) * 1000)).toISOString();
  for (let start = 0; start < result.segments.length; start += 128) {
    await repository.appendSegments(await authorize(), options.sessionId, result.segments.slice(start, start + 128)
      .map((segment, index) => ({ ...segment, id: `transcription:${options.sessionId}:${start + index}`, is_user: false })), endedAt);
  }
  if (result.segments.length > 0) {
    await finalization.finalize(await authorize(), { version: LISTEN_CAPTURE_FINALIZE_VERSION, session_id: options.sessionId, terminal_status: "completed", ended_at: endedAt });
  }
  return repository.complete(await authorize(), options.sessionId);
}
