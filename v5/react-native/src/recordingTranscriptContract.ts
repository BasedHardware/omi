export type RecordingTranscript = {
  sessionId: string;
  state: 'queued' | 'running' | 'completed' | 'failed';
  text: string | null;
  errorCode: string | null;
  discardedLeadingPackets: number;
};

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

export function parseRecordingTranscript(
  body: string | null,
  sessionId: string,
): RecordingTranscript | null {
  if (body === null || body.length > 3_000_000) {
    return null;
  }
  try {
    const envelope: unknown = JSON.parse(body);
    if (!record(envelope) || !record(envelope.transcription)) {
      return null;
    }
    const value = envelope.transcription;
    if (
      value.sessionId !== sessionId ||
      !['queued', 'running', 'completed', 'failed'].includes(
        value.state as string,
      ) ||
      !(value.text === null || typeof value.text === 'string') ||
      (value.state === 'completed' && typeof value.text !== 'string') ||
      !Array.isArray(value.segments) ||
      !(value.language === null || typeof value.language === 'string') ||
      !(value.errorCode === null || typeof value.errorCode === 'string') ||
      !Number.isSafeInteger(value.updatedAt) ||
      (value.updatedAt as number) < 0 ||
      !Number.isSafeInteger(value.discardedLeadingPackets) ||
      (value.discardedLeadingPackets as number) < 0
    ) {
      return null;
    }
    return {
      sessionId,
      state: value.state as RecordingTranscript['state'],
      text: value.text as string | null,
      errorCode: value.errorCode as string | null,
      discardedLeadingPackets: value.discardedLeadingPackets as number,
    };
  } catch {
    return null;
  }
}
