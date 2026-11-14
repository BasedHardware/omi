/**
 * Omi DevKit 2 speaker over BLE.
 *
 * The wire protocol lives in `omi/firmware/devkit/src/speaker.c` speak() and the
 * write handler in transport.c. Four firmware behaviours shape this client:
 *
 *  1. A 4-byte write is a length header (little-endian uint32, total mono bytes
 *     still to come). Everything else is audio. A trailing packet that happens
 *     to land on exactly 4 bytes would be re-read as a header, so sends are
 *     padded to avoid it.
 *  2. Firmware accounts in units of exactly 400 bytes regardless of the actual
 *     packet length, so every packet but the last must be exactly PACKET_SIZE.
 *  3. Release firmware through 2.0.10 buffers one clip into a 10,000-byte
 *     stereo block (= 5,000 mono bytes) per transmission and stalls 4 s after
 *     the last chunk. Streaming firmware (>= 2.0.11, see
 *     MAX_STREAMING_MONO_BYTES_PER_TRANSMISSION) accepts up to 7 blocks in one
 *     continuous stream. Transmission caps and silence padding here are chosen
 *     so the SAME client is correct on both firmware generations.
 *  4. Every write earns exactly one pump notify (the handler notifies before
 *     processing), which is the "send next" signal.
 *
 * Audio format: signed 16-bit little-endian mono PCM at 8 kHz. The firmware
 * duplicates each sample into both I2S channels itself.
 */
import { omiBle } from './omiBle';

export const PACKET_SIZE = 400;
export const SPEAKER_SAMPLE_RATE = 8000;
/**
 * 4,800 mono bytes = 300 ms. Release firmware through 2.0.13 buffers one clip
 * per 5,000-byte mono transmission; 4,800 + the worst-case 8 bytes of padding
 * stays under that ceiling, which is what keeps this client correct there too.
 */
export const MAX_MONO_BYTES_PER_TRANSMISSION = 4800;
/**
 * Streaming firmware (the PR that queues all blocks before a single I2S
 * START, first released as 2.0.11; the 2.0.9x lab builds sort above it
 * numerically): the driver's TX queue is CONFIG_I2S_NRFX_TX_BLOCK_COUNT=8
 * slots of 5,000 mono bytes, and 7 blocks (~2.2 s) were verified continuous
 * on a live board. We cap at 6 blocks for headroom; longer text is split at
 * clause boundaries (`splitSpeechChunks`) so the per-stream stop/start lands
 * where a breath would be anyway.
 */
export const MAX_STREAMING_MONO_BYTES_PER_TRANSMISSION = 30000;

/** First firmware revision whose scheduler takes multi-block streams. */
const MIN_STREAMING_FW: readonly [number, number, number] = [2, 0, 11];

/** True when `firmware` (a "x.y.z" DIS string) queues blocks before START. */
export function firmwareSupportsStreaming(firmware: string | null | undefined): boolean {
  const m = firmware?.match(/^(\d+)\.(\d+)\.(\d+)/);
  if (!m) return false;
  const [major, minor, patch] = [Number(m[1]), Number(m[2]), Number(m[3])];
  const [a, b, c] = MIN_STREAMING_FW;
  return major > a || (major === a && (minor > b || (minor === b && patch >= c)));
}

/**
 * Pad a transmission with silence so its length is not ambiguous to speak().
 * A multiple of 400 was also the old firmware's stall condition (the final
 * packet fell between the `> 400` and `< 400` branches); a 4-byte remainder is
 * misread as a new header.
 */
export function padForFirmware(pcm: Uint8Array): Uint8Array {
  const r = pcm.length % PACKET_SIZE;
  const add = r === 0 ? 8 : r === 4 ? 2 : 0;
  if (add === 0) return pcm;
  const out = new Uint8Array(pcm.length + add);
  out.set(pcm);
  return out;
}

/** Split PCM into protocol-safe transmissions (each <= the per-stream byte cap). */
export function planTransmissions(
  pcm: Uint8Array,
  maxMonoBytes: number = MAX_MONO_BYTES_PER_TRANSMISSION
): Uint8Array[] {
  const sends: Uint8Array[] = [];
  for (let o = 0; o < pcm.length; o += maxMonoBytes) {
    sends.push(padForFirmware(pcm.slice(o, o + maxMonoBytes)));
  }
  return sends;
}

/**
 * Rough mono-PCM bytes per spoken word on this TTS pipeline, measured from the
 * device: "I can talk all day now" (6 words) streamed as 33,600 bytes.
 */
const ESTIMATED_BYTES_PER_WORD = 5600;

/**
 * Split reply text into chunks estimated to fit ONE continuous stream, cutting
 * at sentence boundaries first and comma-level clauses second. On streaming
 * firmware each chunk plays gap-free and the chunk boundary is a natural
 * pause; verified on-device as intelligible where a mid-word split is not.
 * Returns [text] unchanged when it already fits or has no word to cut.
 */
export function splitSpeechChunks(
  text: string,
  maxMonoBytes: number = MAX_STREAMING_MONO_BYTES_PER_TRANSMISSION
): string[] {
  const maxWords = Math.max(1, Math.floor(maxMonoBytes / ESTIMATED_BYTES_PER_WORD));
  const keep = (re: RegExp, src: string): string[] =>
    (src.match(re) ?? []).map((p) => p.trim()).filter((p) => p.length > 0);

  // Sentence > clause > word granularity, each level only for what the level
  // above still cannot fit.
  const units: string[] = [];
  for (const sentence of keep(/[^.!?\n]+[.!?\n]*/g, text)) {
    if (wordCount(sentence) <= maxWords) {
      units.push(sentence);
      continue;
    }
    for (const clause of keep(/[^,;:\-]+[,;:\-]*/g, sentence)) {
      if (wordCount(clause) <= maxWords) {
        units.push(clause);
        continue;
      }
      const words = clause.split(/\s+/).filter((w) => w.length > 0);
      for (let o = 0; o < words.length; o += maxWords) {
        units.push(words.slice(o, o + maxWords).join(' '));
      }
    }
  }

  // Greedily pack units while the estimate stays under one stream.
  const chunks: string[] = [];
  let current: string[] = [];
  for (const unit of units) {
    if (current.length && wordCount(current.join(' ')) + wordCount(unit) > maxWords) {
      chunks.push(current.join(' ').trim());
      current = [];
    }
    current.push(unit);
  }
  if (current.length) chunks.push(current.join(' ').trim());
  return chunks.length ? chunks : [text.trim()];
}

function wordCount(s: string): number {
  return s.split(/\s+/).filter((w) => w.length > 0).length;
}

export function lengthHeader(totalMonoBytes: number): Uint8Array {
  return new Uint8Array([
    totalMonoBytes & 0xff,
    (totalMonoBytes >>> 8) & 0xff,
    (totalMonoBytes >>> 16) & 0xff,
    (totalMonoBytes >>> 24) & 0xff,
  ]);
}

/** The transport seam: everything this module needs from BLE, injectable for tests. */
export interface SpeakerIo {
  ensureMtu(): Promise<number>;
  write(bytes: Uint8Array): Promise<void>;
  /** Subscribe to pump notifications; returns the teardown. */
  subscribe(onPump: () => void, onError: (e: unknown) => void): () => void;
}

const omiBleIo: SpeakerIo = {
  ensureMtu: () => omiBle.ensureSpeakerMtu(),
  write: (bytes) => omiBle.writeSpeaker(bytes),
  subscribe: (onPump, onError) => {
    omiBle.onSpeakerNotify(onPump, onError);
    return () => omiBle.stopSpeakerNotify();
  },
};

export interface PlayOptions {
  io?: SpeakerIo;
  /** Max wait for a pump notify before declaring the stream stalled. */
  pumpTimeoutMs?: number;
  /** Per-stream byte cap; defaults to the release-firmware-safe 4,800. */
  maxMonoBytesPerTransmission?: number;
  onTransmission?: (sending: number, of: number) => void;
}

export async function playPcm16Mono8k(pcm: Uint8Array, opts: PlayOptions = {}): Promise<void> {
  if (pcm.length === 0) return;
  if (pcm.length % 2 !== 0) throw new Error('omiSpeaker: PCM length must be whole int16 samples');

  const io = opts.io ?? omiBleIo;
  const mtu = await io.ensureMtu();
  if (mtu < PACKET_SIZE + 3) {
    throw new Error(
      `omiSpeaker: negotiated MTU ${mtu} cannot carry ${PACKET_SIZE}-byte packets (need >= ${PACKET_SIZE + 3})`
    );
  }

  const sends = planTransmissions(pcm, opts.maxMonoBytesPerTransmission);
  for (const [i, send] of sends.entries()) {
    opts.onTransmission?.(i + 1, sends.length);
    await playOneTransmission(send, io, opts.pumpTimeoutMs ?? 15_000);
  }
}

async function playOneTransmission(mono: Uint8Array, io: SpeakerIo, pumpTimeoutMs: number): Promise<void> {
  const chunks: Uint8Array[] = [];
  for (let o = 0; o < mono.length; o += PACKET_SIZE) {
    chunks.push(mono.slice(o, o + PACKET_SIZE));
  }

  const pump = new PumpWaiter();
  const teardown = io.subscribe(
    () => pump.notify(),
    (e) => pump.fail(e)
  );
  try {
    await io.write(lengthHeader(mono.length));
    for (const chunk of chunks) {
      // The notify precedes the device processing the write, so credits from
      // write N are legitimately spent on write N+1. Writes themselves stay
      // serialized: ATT allows only one outstanding write request.
      await pump.wait(pumpTimeoutMs);
      await io.write(chunk);
    }
  } finally {
    teardown();
  }
}

/** Credits of pump notifications, matched against waiting sends. */
class PumpWaiter {
  private credits = 0;
  private pending: { resolve: () => void; reject: (e: unknown) => void; timer: ReturnType<typeof setTimeout> } | null =
    null;
  private error: unknown = null;

  notify(): void {
    if (this.pending) {
      const p = this.pending;
      this.pending = null;
      clearTimeout(p.timer);
      p.resolve();
    } else {
      this.credits++;
    }
  }

  fail(e: unknown): void {
    this.error = e;
    if (this.pending) {
      const p = this.pending;
      this.pending = null;
      clearTimeout(p.timer);
      p.reject(e);
    }
  }

  wait(timeoutMs: number): Promise<void> {
    if (this.error) return Promise.reject(this.error);
    if (this.credits > 0) {
      this.credits--;
      return Promise.resolve();
    }
    return new Promise<void>((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending = null;
        reject(new Error('omiSpeaker: stream stalled, no pump notification'));
      }, timeoutMs);
      this.pending = { resolve, reject, timer };
    });
  }
}

/** Sine burst in the device's own format: 8 kHz mono int16 LE. */
export function makeTonePcm(frequencyHz: number, durationMs: number, amplitude = 12_000): Uint8Array {
  const n = Math.round((SPEAKER_SAMPLE_RATE * durationMs) / 1000);
  const view = new DataView(new ArrayBuffer(n * 2));
  for (let i = 0; i < n; i++) {
    view.setInt16(i * 2, Math.round(amplitude * Math.sin((2 * Math.PI * frequencyHz * i) / SPEAKER_SAMPLE_RATE)), true);
  }
  return new Uint8Array(view.buffer);
}

const ULAW_EXP_LUT = [0, 132, 396, 924, 1980, 4092, 8316, 16764];

/** Decode G.711 mu-law bytes (what `ulaw_8000` returns) to int16 LE PCM. */
export function ulawToPcm16(encoded: Uint8Array): Uint8Array {
  const view = new DataView(new ArrayBuffer(encoded.length * 2));
  for (let i = 0; i < encoded.length; i++) {
    const u = ~encoded[i]! & 0xff;
    const sign = u & 0x80;
    const exponent = (u >> 4) & 0x07;
    const mantissa = u & 0x0f;
    let sample = ULAW_EXP_LUT[exponent]! + (mantissa << (exponent + 3));
    if (sign) sample = -sample;
    view.setInt16(i * 2, sample, true);
  }
  return new Uint8Array(view.buffer);
}

/**
 * True when the bytes look like MP3 (ID3 tag or frame sync) rather than the
 * mu-law we asked for. The backend currently proxies to an upstream that reads
 * output_format from the query string; a body-only request comes back as MP3
 * whatever we asked, and feeding that to ulawToPcm16 produces a loud buzz
 * rather than speech. Detect and refuse instead.
 */
export function looksLikeMp3(bytes: Uint8Array): boolean {
  if (bytes.length < 3) return false;
  const id3 = bytes[0] === 0x49 && bytes[1] === 0x44 && bytes[2] === 0x33;
  const sync = bytes[0] === 0xff && (bytes[1]! & 0xe0) === 0xe0;
  return id3 || sync;
}
