// Shared mic-capture primitives used by BOTH audio consumers (push-to-talk in
// lib/ptt/capture.ts and conversation recording in omiListenClient.ts), so
// format subtleties and device policy exist exactly once.

/** Convert a Web Audio Float32 buffer to 16-bit little-endian PCM. The
 *  asymmetric scaling (0x8000 negative / 0x7fff positive) matches the int16
 *  range exactly — keep it identical everywhere or lanes drift audibly. */
export function floatTo16BitPCM(f32: Float32Array): Int16Array<ArrayBuffer> {
  const i16 = new Int16Array(f32.length)
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]))
    i16[i] = s < 0 ? s * 0x8000 : s * 0x7fff
  }
  return i16
}

// Virtual/loopback input devices (VB-Audio Cable, VoiceMeeter, …) output pure
// silence unless something routes audio into them. If Windows' DEFAULT capture
// device is one of these, every consumer hears zeros — observed in the wild when
// a VB-Cable install grabbed the system default. Prefer a real microphone
// (macOS parity: its capture likewise avoids inputs that can't hear the user),
// and among real mics prefer non-Bluetooth — opening a BT mic drops the headset
// to HFP and degrades its output.
const VIRTUAL_INPUT_RE = /virtual|vb-audio|voicemeeter|loopback|\bcable\b|blackhole/i
const BLUETOOTH_RE = /bluetooth|hands-free/i

/** getUserMedia for the microphone, steering away from virtual/loopback devices
 *  when the system default is one. Falls back to the default stream if nothing
 *  better exists or the preferred device fails to open. */
export async function acquireMicStream(): Promise<MediaStream> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
  const label = stream.getAudioTracks()[0]?.label ?? ''
  if (!VIRTUAL_INPUT_RE.test(label)) return stream
  const inputs = (await navigator.mediaDevices.enumerateDevices()).filter(
    (d) =>
      d.kind === 'audioinput' &&
      d.deviceId !== 'default' &&
      d.deviceId !== 'communications' &&
      d.label &&
      !VIRTUAL_INPUT_RE.test(d.label)
  )
  const pick = inputs.find((d) => !BLUETOOTH_RE.test(d.label)) ?? inputs[0]
  if (!pick) return stream // nothing better exists — keep the default
  try {
    const better = await navigator.mediaDevices.getUserMedia({
      audio: { deviceId: { exact: pick.deviceId } }
    })
    console.warn(`[audio] default input "${label}" is a virtual device — capturing "${pick.label}" instead`)
    stream.getTracks().forEach((t) => t.stop())
    return better
  } catch {
    return stream
  }
}

/** Idempotent teardown of a mic capture graph — disconnect nodes, stop tracks,
 *  close the context, each step isolated so one failure can't leak the rest. */
export function teardownAudioGraph(parts: {
  nodes: AudioNode[]
  stream: MediaStream
  ctx: AudioContext
}): void {
  for (const node of parts.nodes) {
    try {
      node.disconnect()
    } catch {
      /* ignore */
    }
  }
  try {
    parts.stream.getTracks().forEach((t) => t.stop())
  } catch {
    /* ignore */
  }
  try {
    void parts.ctx.close()
  } catch {
    /* ignore */
  }
}
