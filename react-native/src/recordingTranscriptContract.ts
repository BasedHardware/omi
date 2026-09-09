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

function joinWellFormedSegmentTexts(segments: unknown[]): string | null {
  if (segments.length === 0) {
    return null;
  }
  const parts: string[] = [];
  for (const segment of segments) {
    if (
      segment === null ||
      typeof segment !== 'object' ||
      Array.isArray(segment)
    ) {
      return null;
    }
    const text = (segment as {text?: unknown}).text;
    if (text === undefined || text === null) {
      parts.push('');
      continue;
    }
    if (typeof text !== 'string') {
      return null;
    }
    parts.push(text);
  }
  return parts.join(' ');
}

function recordingTranscriptSpeech(
  storedText: string | null,
  segments: unknown[],
): string | null {
  const joined = joinWellFormedSegmentTexts(segments);
  return joined === null ? storedText : joined;
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
      text:
        value.state === 'completed'
          ? recordingTranscriptSpeech(
              value.text as string | null,
              value.segments,
            )
          : null,
      errorCode: value.errorCode as string | null,
      discardedLeadingPackets: value.discardedLeadingPackets as number,
    };
  } catch {
    return null;
  }
}
