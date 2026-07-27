/** Glasses microphone PCM: normalising it, and describing it on a monochrome
 *  display.
 *
 *  The G2 mic array is delivered to the plugin as raw PCM16 LE / 16 kHz / mono
 *  on `event.audioEvent.audioPcm` — which is exactly the format the omi bridge
 *  wants, so the bytes go out over the socket untouched. Everything here is
 *  about the two things that are *not* pass-through: getting a real byte array
 *  out of whatever the host handed us, and turning it into something the user
 *  can look at to know the microphone is live.
 */
import { ASK_METER_WIDTH } from './config.ts'

const BASE64_ALPHABET = /^[A-Za-z0-9+/=\s]+$/

/**
 * Coerce one `audioPcm` payload into bytes.
 *
 * The SDK types this as `Uint8Array`, and that is what arrives in the
 * simulator. The host is a Flutter app sending a `Uint8List` through a JSON
 * channel though, so `AudioEvent.fromJson` has to cope with `number[]` and
 * base64 too — and the SDK's own doc comment says as much. Normalising here
 * rather than trusting the declared type means a host that picks a different
 * encoding degrades to "works" instead of "streams garbage to the bridge".
 *
 * Returns null for anything that is not audio, so callers can drop the frame.
 */
export function toPcmBytes(raw: unknown): Uint8Array | null {
  if (raw instanceof Uint8Array) return raw.length > 0 ? raw : null
  if (raw instanceof ArrayBuffer) return raw.byteLength > 0 ? new Uint8Array(raw) : null
  if (ArrayBuffer.isView(raw)) {
    const view = raw as ArrayBufferView
    return view.byteLength > 0 ? new Uint8Array(view.buffer, view.byteOffset, view.byteLength) : null
  }
  if (Array.isArray(raw)) {
    if (raw.length === 0) return null
    const out = new Uint8Array(raw.length)
    for (let i = 0; i < raw.length; i++) {
      const value = raw[i]
      if (typeof value !== 'number' || !Number.isFinite(value)) return null
      out[i] = value & 0xff
    }
    return out
  }
  if (typeof raw === 'string') {
    if (raw.length === 0 || !BASE64_ALPHABET.test(raw)) return null
    try {
      const binary = atob(raw)
      const out = new Uint8Array(binary.length)
      for (let i = 0; i < binary.length; i++) out[i] = binary.charCodeAt(i)
      return out.length > 0 ? out : null
    } catch {
      return null
    }
  }
  return null
}

/** Duration of a PCM16 mono buffer at 16 kHz, in seconds. */
export const SAMPLE_RATE = 16_000
export function pcmSeconds(bytes: number): number {
  return bytes / (SAMPLE_RATE * 2)
}

/**
 * Loudest sample in the buffer, 0..1. Read as int16 little-endian — the same
 * interpretation the bridge applies, so a meter that moves is real evidence the
 * bytes on the wire are speech and not silence or a byte-order mistake.
 */
export function peakLevel(pcm: Uint8Array): number {
  let peak = 0
  // Odd trailing byte cannot form a sample; the SDK always sends whole frames.
  for (let i = 0; i + 1 < pcm.length; i += 2) {
    let sample = pcm[i] | (pcm[i + 1] << 8)
    if (sample >= 0x8000) sample -= 0x10000
    const magnitude = sample < 0 ? -sample : sample
    if (magnitude > peak) peak = magnitude
  }
  return Math.min(1, peak / 32_768)
}

/**
 * ASCII level meter. The display is monochrome and 576px wide, so a row of
 * `#` is both the cheapest thing to draw and the least ambiguous: if it moves,
 * the microphone is live.
 *
 * Scaled with a square root because speech spends most of its time well below
 * full scale and a linear bar barely leaves the first block.
 */
export function meterBar(level: number, width: number = ASK_METER_WIDTH): string {
  const clamped = Math.max(0, Math.min(1, level))
  const filled = Math.round(Math.sqrt(clamped) * width)
  return `[${'#'.repeat(filled)}${'-'.repeat(width - filled)}]`
}

/** `m:ss`, for the recording timer. */
export function clock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}
