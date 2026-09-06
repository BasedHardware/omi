import type { PrerecordedTranscription, PrerecordedTranscriptionSource } from "../../apps/service/listen/prerecorded-transcription";
import { parsePrerecordedTranscription } from "../../apps/service/listen/prerecorded-transcription";
import { DEVICE_AUDIO_LIMITS } from "./device-audio";
import { LISTEN_FORMATION_MAX_SEGMENTS, LISTEN_FORMATION_MAX_TEXT_CODE_UNITS } from "../../apps/service/listen/formation-ingestion";

export class PrerecordedTranscriptionUnavailable extends Error {
  constructor(readonly retryable: boolean) { super("transcription_unavailable"); }
}
export function createDeepgramTranscriptionSource(options: {
  readonly apiKey: string;
  readonly model: string;
  readonly timeoutMilliseconds: number;
  readonly fetch?: typeof fetch;
}): PrerecordedTranscriptionSource {
  if (!/^[\x21-\x7e]{1,4096}$/.test(options.apiKey) || !/^[a-z0-9][a-z0-9.-]{0,63}$/.test(options.model)
    || !Number.isSafeInteger(options.timeoutMilliseconds) || options.timeoutMilliseconds < 1 || options.timeoutMilliseconds > 120000) throw new TypeError("invalid_transcription_configuration");
  const request = options.fetch ?? fetch;
  const endpoint = new URL("https://api.deepgram.com/v1/listen");
  endpoint.search = new URLSearchParams({ model: options.model, utterances: "true", punctuate: "true", smart_format: "true", detect_language: "true", mip_opt_out: "true" }).toString();
  const authorization = `Token ${options.apiKey}`;
  return Object.freeze({
    async transcribe(input: Parameters<PrerecordedTranscriptionSource["transcribe"]>[0]): Promise<PrerecordedTranscription> {
      if (!(input.audio instanceof Uint8Array) || input.audio.length < 1 || input.audio.length > DEVICE_AUDIO_LIMITS.maxOutputBytes
        || (input.contentType !== "audio/wav" && input.contentType !== "audio/ogg")) throw new PrerecordedTranscriptionUnavailable(false);
      const controller = new AbortController();
      const cancel = () => controller.abort();
      input.signal.addEventListener("abort", cancel, { once: true });
      if (input.signal.aborted) controller.abort();
      const timer = setTimeout(cancel, options.timeoutMilliseconds);
      try {
        controller.signal.throwIfAborted();
        const response = await request(endpoint, { method: "POST", redirect: "error", signal: controller.signal,
          headers: { authorization, "content-type": input.contentType }, body: new Uint8Array(input.audio),
        });
        if (response.status !== 200 || response.body === null) {
          await response.body?.cancel().catch(() => undefined);
          throw new PrerecordedTranscriptionUnavailable(response.status === 429 || response.status >= 500);
        }
        const reader = response.body.getReader();
        const abort = () => { void reader.cancel().catch(() => undefined); };
        controller.signal.addEventListener("abort", abort, { once: true });
        let size = 0, text = "";
        const decoder = new TextDecoder("utf-8", { fatal: true });
        try {
          controller.signal.throwIfAborted();
          while (true) {
            const chunk = await reader.read();
            controller.signal.throwIfAborted();
            if (chunk.done) break;
            size += chunk.value.length;
            if (size > 6_291_456) throw new PrerecordedTranscriptionUnavailable(false);
            try { text += decoder.decode(chunk.value, { stream: true }); }
            catch { throw new PrerecordedTranscriptionUnavailable(false); }
          }
          try { text += decoder.decode(); }
          catch { throw new PrerecordedTranscriptionUnavailable(false); }
        } finally {
          controller.signal.removeEventListener("abort", abort);
          await reader.cancel().catch(() => undefined);
        }
        try { return parseResponse(JSON.parse(text)); } catch { throw new PrerecordedTranscriptionUnavailable(false); }
      } catch (cause) {
        if (cause instanceof PrerecordedTranscriptionUnavailable) throw cause;
        throw new PrerecordedTranscriptionUnavailable(true);
      } finally {
        clearTimeout(timer);
        input.signal.removeEventListener("abort", cancel);
      }
    },
  });
}
function parseResponse(input: unknown): PrerecordedTranscription {
  const invalid = (): never => { throw new PrerecordedTranscriptionUnavailable(false); };
  const object = (value: unknown): Record<string, unknown> => {
    if (value === null || typeof value !== "object" || Array.isArray(value)) return invalid();
    return value as Record<string, unknown>;
  };
  const response = object(input);
  const duration = object(response.metadata).duration;
  if (typeof duration !== "number" || !Number.isFinite(duration) || duration <= 0 || duration > 3600) return invalid();
  const utterances = object(response.results).utterances;
  if (!Array.isArray(utterances) || utterances.length > LISTEN_FORMATION_MAX_SEGMENTS) return invalid();
  const segments: { text: string; start: number; end: number }[] = [];
  let totalText = 0;
  const append = (value: unknown, textField: string) => {
    const row = object(value), text = row[textField], start = row.start, end = row.end;
    if (typeof text !== "string" || !text.trim() || text.length > 1500
      || typeof start !== "number" || !Number.isFinite(start) || start < 0
      || typeof end !== "number" || !Number.isFinite(end) || end < start || end > duration + 0.1) return invalid();
    segments.push({ text, start, end });
    totalText += text.length;
    if (segments.length > LISTEN_FORMATION_MAX_SEGMENTS || totalText > LISTEN_FORMATION_MAX_TEXT_CODE_UNITS) return invalid();
  };
  for (const value of utterances) {
    const utterance = object(value);
    if (typeof utterance.transcript !== "string") return invalid();
    if (utterance.transcript.length <= 1500) { append(utterance, "transcript"); continue; }
    if (!Array.isArray(utterance.words) || utterance.words.length === 0) return invalid();
    let pending: { text: string; start: unknown; end: unknown } | undefined;
    for (const value of utterance.words) {
      const word = object(value), text = word.punctuated_word ?? word.word;
      if (typeof text !== "string" || !text.trim() || text.length > 1500
        || typeof word.start !== "number" || !Number.isFinite(word.start) || word.start < 0
        || typeof word.end !== "number" || !Number.isFinite(word.end) || word.end < word.start || word.end > duration + 0.1) return invalid();
      if (pending && pending.text.length + text.length + 1 > 1500) { append(pending, "text"); pending = undefined; }
      if (!pending) pending = { text, start: word.start, end: word.end };
      else { pending.text += ` ${text}`; pending.end = word.end; }
    }
    if (pending) append(pending, "text");
  }
  return parsePrerecordedTranscription({ durationSeconds: duration, segments });
}
