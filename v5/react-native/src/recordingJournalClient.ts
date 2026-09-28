import {decodeBase64} from './base64';
import {isOptionalCaptureTimestamp} from './captureTimestamp';
import type {
  OmiBackend,
  RecordingJournal,
  RecordingJournalInput,
} from './omiNativeTypes';

const uuid =
  /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const maxBytes = 8_388_608;
const maxPackets = 65_536;

export function hasRecordingJournal(backend: OmiBackend): boolean {
  return (
    typeof backend.createRecordingJournal === 'function' &&
    typeof backend.listRecordingJournals === 'function' &&
    typeof backend.readRecordingJournal === 'function' &&
    typeof backend.appendRecordingJournal === 'function' &&
    typeof backend.requestRecordingJournal === 'function' &&
    typeof backend.removeRecordingJournal === 'function'
  );
}

export function decodeJournalPacket(value: string): Uint8Array {
  if (value.length > Math.ceil(maxBytes / 3) * 4) {
    throw new Error('Saved recording packet is invalid');
  }
  const bytes = decodeBase64(value);
  if (bytes.length === 0) {
    throw new Error('Saved recording packet is empty');
  }
  return bytes;
}

export type RestoredRecording = {
  journal: RecordingJournal;
  pending: Uint8Array[];
  totalBytes: number;
  acknowledged: number;
};

export function restoreRecording(journal: RecordingJournal): RestoredRecording {
  if (
    !isOptionalCaptureTimestamp(journal.capturedAtMs) ||
    !uuid.test(journal.captureId) ||
    journal.handle !== journal.captureId ||
    (journal.sessionId !== null && !uuid.test(journal.sessionId)) ||
    typeof journal.deviceId !== 'string' ||
    journal.deviceId.length === 0 ||
    journal.deviceId.length > 256 ||
    !Number.isInteger(journal.codec) ||
    journal.codec < 0 ||
    journal.codec > 255 ||
    (journal.deviceName !== null && typeof journal.deviceName !== 'string') ||
    !Array.isArray(journal.entries)
  ) {
    throw new Error('Saved recording identity is invalid');
  }
  const packets: Uint8Array[] = [];
  let totalBytes = 0;
  let acknowledged = 0;
  let stopped = false;
  for (const entry of journal.entries) {
    const record: unknown = JSON.parse(entry);
    if (!Array.isArray(record)) {
      throw new Error('Saved recording entry is invalid');
    }
    if (
      record[0] === 'p' &&
      record.length === 2 &&
      typeof record[1] === 'string' &&
      !stopped
    ) {
      const bytes = decodeJournalPacket(record[1]);
      totalBytes += bytes.length;
      if (totalBytes > maxBytes || packets.length >= maxPackets) {
        throw new Error('Saved recording exceeds its limit');
      }
      packets.push(bytes);
    } else if (
      record[0] === 'a' &&
      record.length === 2 &&
      Number.isSafeInteger(record[1]) &&
      record[1] >= acknowledged &&
      record[1] <= packets.length &&
      journal.sessionId !== null
    ) {
      acknowledged = record[1];
    } else if (record[0] === 's' && record.length === 1 && !stopped) {
      stopped = true;
    } else {
      throw new Error('Saved recording order is invalid');
    }
  }
  return {
    journal,
    pending: packets.slice(acknowledged),
    totalBytes,
    acknowledged,
  };
}

export function recordingJournalBackend(
  backend: OmiBackend,
  handle: string,
): OmiBackend {
  if (!hasRecordingJournal(backend)) {
    throw new Error('Native recording journal is unavailable');
  }
  return {
    request: request => backend.requestRecordingJournal!(handle, request),
    generationEvents: (id, cursor) => backend.generationEvents(id, cursor),
    cancelGenerationEvents: id => backend.cancelGenerationEvents(id),
  };
}

export async function createRecordingJournal(
  backend: OmiBackend,
  input: RecordingJournalInput,
): Promise<RecordingJournal> {
  if (!hasRecordingJournal(backend)) {
    throw new Error('Native recording journal is unavailable');
  }
  if (!isOptionalCaptureTimestamp(input.capturedAtMs)) {
    throw new Error('Capture timestamp is invalid');
  }
  const journal = await backend.createRecordingJournal!(input);
  restoreRecording(journal);
  if (
    journal.capturedAtMs !== input.capturedAtMs ||
    journal.deviceId !== input.deviceId ||
    journal.deviceName !== (input.deviceName ?? null) ||
    journal.codec !== input.codec ||
    journal.entries.length !== 0 ||
    journal.sessionId !== null
  ) {
    throw new Error('Native recording journal acknowledgement is invalid');
  }
  return journal;
}
