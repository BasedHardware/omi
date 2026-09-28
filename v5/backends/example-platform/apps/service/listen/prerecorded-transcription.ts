export interface PrerecordedTranscription {
  readonly durationSeconds: number;
  readonly segments: readonly { readonly text: string; readonly start: number; readonly end: number }[];
}
export interface PrerecordedTranscriptionSource {
  transcribe(input: {
    readonly audio: Uint8Array;
    readonly contentType: "audio/wav" | "audio/ogg";
    readonly signal: AbortSignal;
  }): Promise<PrerecordedTranscription>;
}

export function parsePrerecordedTranscription(value: unknown): PrerecordedTranscription {
  if (value === null || typeof value !== "object" || Array.isArray(value)) throw new TypeError("invalid_transcription");
  const row = value as Record<string, unknown>;
  if (typeof row.durationSeconds !== "number" || !Number.isFinite(row.durationSeconds) || row.durationSeconds <= 0 || row.durationSeconds > 3600
    || !Array.isArray(row.segments) || row.segments.length > 4096) throw new TypeError("invalid_transcription");
  let length = 0, bytes = 0;
  const encoder = new TextEncoder();
  const segments = row.segments.map((value: unknown) => {
    if (value === null || typeof value !== "object" || Array.isArray(value)) throw new TypeError("invalid_transcription");
    const segment = value as Record<string, unknown>;
    if (typeof segment.text !== "string" || !segment.text.trim() || segment.text.length > 1500
      || typeof segment.start !== "number" || !Number.isFinite(segment.start) || segment.start < 0
      || typeof segment.end !== "number" || !Number.isFinite(segment.end) || segment.end < segment.start
      || segment.end > (row.durationSeconds as number) + 0.1) throw new TypeError("invalid_transcription");
    length += segment.text.length;
    bytes += encoder.encode(segment.text).byteLength;
    if (length > 1_000_000 || bytes > 1_000_000 || segment.text.includes("\0")) throw new TypeError("invalid_transcription");
    for (const character of segment.text) {
      const codePoint = character.codePointAt(0)!;
      if (codePoint >= 0xd800 && codePoint <= 0xdfff) throw new TypeError("invalid_transcription");
    }
    return Object.freeze({ text: segment.text, start: segment.start, end: segment.end });
  });
  return Object.freeze({ durationSeconds: row.durationSeconds, segments: Object.freeze(segments) });
}
