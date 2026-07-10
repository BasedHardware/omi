// Silero VAD (via @ricky0123/vad-web) wrapped as a per-source process singleton.
// The ONLY module that pulls in onnxruntime — keep it imported from the capture
// window only, never the main renderer bundle.
//
// Wiring (done by the capture window): run one engine per audio source; route its
// verdicts into a VadGate that gates the SEPARATE high-quality PCM stream from
// pcmPipeline:
//   vadEngine callbacks: onSpeechStart → gate.push({type:'speech',active:true})
//                        onSpeechEnd   → gate.push({type:'speech',active:false})
//   pcmPipeline.onChunk  → gate.push({type:'frame', pcm})
// If init fails (asset 404 / wasm throw), the handle resolves with fallbackReason
// set — the caller runs the gate in 'passthrough' so audio still flows unfiltered.
//
// LIFECYCLE: the MicVAD is created ONCE per source and reused via start()/pause().
// It is NEVER destroyed — onnxruntime-web leaks native memory on session release,
// so a create/destroy per session would grow RSS unbounded. Callbacks are held in
// a mutable ref so each new session rebinds without rebuilding the model.
import { MicVAD } from '@ricky0123/vad-web'
import { trackEvent } from '../analytics'
import { classifyVadFailure } from './vadFallback'

/** Which audio source an engine detects on. Keyed so mic + loopback each get one. */
export type VadEngineKey = 'mic' | 'loopback'

export type VadEngineCallbacks = {
  onSpeechStart?: () => void
  onSpeechEnd?: () => void
  /** Per-frame verdict + raw isSpeech probability (0..1), for finer control. */
  onFrame?: (isSpeech: boolean, probability: number) => void
}

export type VadEngineOptions = {
  /** Returns the session's mic/loopback stream. vad-web must NEVER open its own —
   *  we always steer/own the stream elsewhere (acquireMicStream / getSystemAudioStream). */
  getStream: () => Promise<MediaStream>
  callbacks?: VadEngineCallbacks
  /** isSpeech ≥ this counts as speech for onFrame (vad-web default 0.3). */
  positiveSpeechThreshold?: number
}

export type VadEngineHandle = {
  key: VadEngineKey
  /** Non-null when init failed → run the gate in passthrough. */
  readonly fallbackReason: string | null
  /** Begin/resume detection (call at session start). */
  start: () => Promise<void>
  /** Pause detection (call at session end) — never destroys the model. */
  pause: () => Promise<void>
  /** Rebind callbacks for a new session without rebuilding the model. */
  setCallbacks: (cb: VadEngineCallbacks) => void
}

type EngineState = {
  vad: MicVAD | null
  fallbackReason: string | null
  callbacks: VadEngineCallbacks
}

const engines = new Map<VadEngineKey, EngineState>()

// v5 frames are 512 samples @16kHz = 32ms. Pad/redemption mirror the capture design
// (≈400ms pre-speech pad, ≈600ms redemption hangover). vad-web 0.0.30 takes these
// as MILLISECONDS (preSpeechPadMs/redemptionMs) — the frame-count form the plan
// referenced (preSpeechPadFrames/redemptionFrames) is not this version's API.
const PRE_SPEECH_PAD_MS = 400
const REDEMPTION_MS = 600

/** Get (creating once) the VAD engine for a source. Idempotent per key: a repeat
 *  call rebinds callbacks and returns the same underlying model. */
export async function getVadEngine(
  key: VadEngineKey,
  opts: VadEngineOptions
): Promise<VadEngineHandle> {
  let state = engines.get(key)
  if (!state) {
    state = { vad: null, fallbackReason: null, callbacks: opts.callbacks ?? {} }
    engines.set(key, state)
    const threshold = opts.positiveSpeechThreshold ?? 0.3
    try {
      state.vad = await MicVAD.new({
        model: 'v5',
        baseAssetPath: '/vad/',
        onnxWASMBasePath: '/vad/',
        preSpeechPadMs: PRE_SPEECH_PAD_MS,
        redemptionMs: REDEMPTION_MS,
        startOnLoad: false, // create idle; the caller start()s at session begin
        getStream: opts.getStream,
        ortConfig: (ort) => {
          ort.env.wasm.numThreads = 1 // single-threaded: no COOP/COEP cross-origin-isolation needed
          ort.env.logLevel = 'error'
        },
        onSpeechStart: () => state?.callbacks.onSpeechStart?.(),
        onSpeechEnd: () => state?.callbacks.onSpeechEnd?.(),
        onFrameProcessed: (probs) =>
          state?.callbacks.onFrame?.(probs.isSpeech >= threshold, probs.isSpeech)
      })
    } catch (e) {
      state.fallbackReason = (e as Error)?.message || 'VAD initialization failed'
      console.warn(
        `[vad] ${key} engine init failed — gating disabled (passthrough): ${state.fallbackReason}`
      )
      // Silent UX healing (audio still flows via passthrough), but NOT silent ops:
      // report the gated→passthrough transition through the shared analytics helper
      // per AGENTS.md fallback telemetry. Emitted once per source per process (this
      // catch runs only on first creation — the engine is cached thereafter).
      trackEvent('fallback_triggered', {
        component: 'vad_gate',
        from: 'gated',
        to: 'passthrough',
        reason: classifyVadFailure(state.fallbackReason),
        outcome: 'degraded',
        source: key
      })
    }
  } else if (opts.callbacks) {
    state.callbacks = opts.callbacks
  }

  const s = state
  return {
    key,
    get fallbackReason() {
      return s.fallbackReason
    },
    setCallbacks: (cb) => {
      s.callbacks = cb
    },
    start: async () => {
      if (s.vad) await s.vad.start()
    },
    pause: async () => {
      if (s.vad) await s.vad.pause()
    }
  }
}

/** Test/teardown seam — forget cached engines. Does NOT destroy the underlying
 *  MicVAD (ORT release leak); only for unit tests that stub MicVAD. */
export function __resetVadEnginesForTest(): void {
  engines.clear()
}
