export type RecordingTranscriptSegment = {
  text: string;
  speaker: string | number | null;
  isUser: boolean;
};

export type RecordingTranscript = {
  sessionId: string;
  state: 'queued' | 'running' | 'completed' | 'failed';
  text: string | null;
  segments: RecordingTranscriptSegment[];
  errorCode: string | null;
  discardedLeadingPackets: number;
};

function record(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function parseWellFormedSegments(
  segments: unknown[],
): RecordingTranscriptSegment[] | null {
  if (segments.length === 0) {
    return [];
  }
  const parsed: RecordingTranscriptSegment[] = [];
  for (const segment of segments) {
    if (
      segment === null ||
      typeof segment !== 'object' ||
      Array.isArray(segment)
    ) {
      return null;
    }
    const row = segment as Record<string, unknown>;
    const text = row.text;
    if (text !== undefined && text !== null && typeof text !== 'string') {
      return null;
    }
    parsed.push({
      text: typeof text === 'string' ? text : '',
      speaker:
        typeof row.speaker === 'number' && Number.isSafeInteger(row.speaker)
          ? row.speaker
          : typeof row.speaker === 'string'
          ? row.speaker
          : null,
      isUser: row.is_user === true,
    });
  }
  return parsed;
}

function recordingTranscriptSpeech(
  storedText: string | null,
  segments: RecordingTranscriptSegment[] | null,
): string | null {
  if (segments === null) {
    return storedText;
  }
  return segments.length === 0
    ? storedText
    : segments.map(segment => segment.text).join(' ');
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
    const segments =
      value.state === 'completed'
        ? parseWellFormedSegments(value.segments)
        : [];
    return {
      sessionId,
      state: value.state as RecordingTranscript['state'],
      text:
        value.state === 'completed'
          ? recordingTranscriptSpeech(value.text as string | null, segments)
          : null,
      segments: segments ?? [],
      errorCode: value.errorCode as string | null,
      discardedLeadingPackets: value.discardedLeadingPackets as number,
    };
  } catch {
    return null;
  }
}
