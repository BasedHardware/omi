import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";
import type { PrerecordedTranscription } from "./prerecorded-transcription";
import type { ListenTranscriptSegment } from "../stores/listen-store";

export interface DeviceTranscriptionRecord {
  readonly sessionId: string;
  readonly state: "queued" | "running" | "completed" | "failed";
  readonly providerResult: PrerecordedTranscription | null;
  readonly discardedLeadingPackets: number;
  readonly errorCode: string | null;
  readonly updatedAt: number;
  readonly startedAt: string;
  readonly codec: number;
  readonly chunkCount: number;
  readonly byteCount: number;
}
export interface DeviceTranscriptionRepository {
  read(context: AuthorizedLedgerWriteContext, sessionId: string): Promise<DeviceTranscriptionRecord | null>;
  claim(context: AuthorizedLedgerWriteContext, sessionId: string, token: string): Promise<(DeviceTranscriptionRecord & { readonly owned: boolean }) | null>;
  loadAudio(context: AuthorizedLedgerWriteContext, sessionId: string, token: string): Promise<readonly Uint8Array[]>;
  save(context: AuthorizedLedgerWriteContext, sessionId: string, token: string, result: PrerecordedTranscription | null, discarded: number, error: string | null, retryable: boolean): Promise<DeviceTranscriptionRecord>;
  complete(context: AuthorizedLedgerWriteContext, sessionId: string): Promise<DeviceTranscriptionRecord>;
  appendSegments(context: AuthorizedLedgerWriteContext, sessionId: string, segments: readonly ListenTranscriptSegment[], appendedAt: string): Promise<void>;
}

export function deviceTranscriptionProjection(record: DeviceTranscriptionRecord) {
  if (record.state === "completed" && record.providerResult === null) return null;
  const result = record.state === "completed" ? record.providerResult : null;
  return Object.freeze({ sessionId: record.sessionId, state: record.state,
    text: result === null ? null : result.segments.map(segment => segment.text).join(" "),
    segments: result?.segments ?? [], language: null, discardedLeadingPackets: record.discardedLeadingPackets,
    errorCode: record.errorCode, updatedAt: record.updatedAt,
  });
}
