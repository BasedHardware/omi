import { expect, test, spyOn } from "bun:test";
import { createDeepgramTranscriptionSource, PrerecordedTranscriptionUnavailable } from "./deepgram-transcription";

const options = { apiKey: "local-test-only", model: "nova-3", timeoutMilliseconds: 30000 };
const input = () => ({ audio: new Uint8Array([82, 73, 70, 70]), contentType: "audio/wav" as const, signal: new AbortController().signal });
const result = (utterances: unknown = [{ transcript: "Recorded words.", start: 0.1, end: 1.2 }]) => ({ metadata: { duration: 2 }, results: { utterances } });

test("prerecorded provider adapter submits original audio and preserves actual timed utterances", async () => {
  let request: Request | undefined;
  const source = createDeepgramTranscriptionSource({ ...options, fetch: async (url, init) => {
    request = new Request(url, init);
    return Response.json(result());
  } });
  const transcription = await source.transcribe(input());
  expect(transcription).toEqual({ durationSeconds: 2, segments: [{ text: "Recorded words.", start: 0.1, end: 1.2 }] });
  expect(Object.isFrozen(transcription.segments[0])).toBe(true);
  const sent = request!;
  const url = new URL(sent.url);
  expect(url.origin + url.pathname).toBe("https://api.deepgram.com/v1/listen");
  expect(url.searchParams.get("model")).toBe("nova-3");
  expect(url.searchParams.get("utterances")).toBe("true");
  expect(url.searchParams.get("mip_opt_out")).toBe("true");
  expect(sent.headers.get("authorization")).toBe("Token local-test-only");
  expect(sent.headers.get("content-type")).toBe("audio/wav");
  expect(sent.redirect).toBe("error");
  expect(new Uint8Array(await sent.arrayBuffer())).toEqual(input().audio);
});

test("long utterances split only at actual timed words; invalid intermediate word timestamps are rejected", async () => {
  const words = [{ word: "a".repeat(1000), start: 0, end: 0.4 }, { word: "b".repeat(1000), start: 0.4, end: 1.5 }];
  const source = (value: unknown) => createDeepgramTranscriptionSource({ ...options, fetch: async () => Response.json(result(value)) });
  expect((await source([{ transcript: "a".repeat(2001), start: 0, end: 1.5, words }]).transcribe(input())).segments).toEqual([
    { text: words[0]!.word, start: 0, end: 0.4 }, { text: words[1]!.word, start: 0.4, end: 1.5 },
  ]);
  await expect(source([{ transcript: "a".repeat(2001), words: [words[0], { word: "bad", start: -1, end: 100 }, words[1]] }]).transcribe(input())).rejects.toMatchObject({ retryable: false });
  expect((await source([]).transcribe(input())).segments).toEqual([]);
});

test("provider failures expose only sanitized retry classification and reject malformed success bodies", async () => {
  for (const [status, retryable] of [[401, false], [422, false], [429, true], [503, true]] as const) {
    const source = createDeepgramTranscriptionSource({ ...options, fetch: async () => new Response("sensitive provider message", { status }) });
    await expect(source.transcribe(input())).rejects.toMatchObject({ message: "transcription_unavailable", retryable });
  }
  for (const body of ["not json", JSON.stringify(result([{ transcript: "invalid", start: 0, end: 100 }])), JSON.stringify(result(null)), "x".repeat(6_291_457)]) {
    const source = createDeepgramTranscriptionSource({ ...options, fetch: async () => new Response(body) });
    await expect(source.transcribe(input())).rejects.toBeInstanceOf(PrerecordedTranscriptionUnavailable);
    await expect(source.transcribe(input())).rejects.toMatchObject({ retryable: false });
  }
  expect(() => createDeepgramTranscriptionSource({ ...options, apiKey: "key\r\ninjection" })).toThrow("invalid_transcription_configuration");
});

test("cancellation fences preflight and cancels a provider stream without leaking its body", async () => {
  const controller = new AbortController();
  controller.abort();
  let requests = 0;
  const source = createDeepgramTranscriptionSource({ ...options, fetch: async () => { requests += 1; return Response.json(result()); } });
  await expect(source.transcribe({ ...input(), signal: controller.signal })).rejects.toMatchObject({ retryable: true });
  expect(requests).toBe(0);
  const reading = new AbortController();
  let cancelled = 0;
  const streaming = createDeepgramTranscriptionSource({ ...options, fetch: async () => new Response(new ReadableStream({
    pull() { reading.abort(); }, cancel() { cancelled += 1; },
  })) });
  await expect(streaming.transcribe({ ...input(), signal: reading.signal })).rejects.toMatchObject({ retryable: true });
  expect(cancelled).toBe(1);
});

test("deadline cancels a response arriving after timeout before consuming its body", async () => {
  let timeout!: () => void;
  const timer = spyOn(globalThis, "setTimeout").mockImplementation(((callback: () => void) => { timeout = callback; return 0; }) as typeof setTimeout);
  let cancelled = 0, reads = 0;
  try {
    const source = createDeepgramTranscriptionSource({ ...options, fetch: async () => {
      timeout();
      return new Response(new ReadableStream({ pull() { reads += 1; }, cancel() { cancelled += 1; } }, { highWaterMark: 0 }));
    } });
    await expect(source.transcribe(input())).rejects.toMatchObject({ retryable: true });
    expect(cancelled).toBe(1);
    expect(reads).toBe(0);
  } finally { timer.mockRestore(); }
});
