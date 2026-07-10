// Push-to-talk tuning constants — the single source of truth shared by the app,
// the unit tests, and the fixture generator's manifest stats. Values marked
// (macOS) mirror the proven macOS PushToTalkManager/TranscriptionService tuning.

/** How long Space must be held before it flips from "type a space" to push-to-talk.
 *  Above a fast keypress (~80–150ms) so typing never trips it; a deliberate hold
 *  still feels instant. */
export const HOLD_THRESHOLD_MS = 350

/** After release, keep the capture alive this long so the final ScriptProcessor
 *  window (4096 samples @16kHz ≈ 256ms) lands in the buffer — otherwise the last
 *  syllable of short words ("one", "hey") is clipped. Speech past this tail is
 *  discarded: the released key is the source of truth. */
export const DRAIN_MS = 300

/** Minimum total captured audio to trust STT with (macOS minTurnAudioSeconds).
 *  Below this the release beat the capture — show "Hold longer to record". */
export const MIN_TOTAL_AUDIO_SEC = 0.35

/** Minimum voiced audio for a turn to be worth transcribing (macOS
 *  minVoicedSeconds). A held-but-silent turn is discarded silently — STT models
 *  hallucinate phrases from silence, so it must never be sent. */
export const MIN_VOICED_SEC = 0.2

/** A 20ms frame whose int16 RMS meets this counts as voiced (macOS
 *  voicedRMSThreshold, ~-41 dBFS): above quiet-room mic noise, below soft speech. */
export const VOICED_RMS_THRESHOLD = 300

/** Samples per voiced-measurement frame: 20ms @ 16kHz (macOS parity). */
export const VOICED_FRAME_SAMPLES = 320

/** Per-hold PCM buffer cap: 4.5 min of 16kHz mono int16 (macOS maxBatchAudioBytes)
 *  — bounds RSS and stays under the backend's ~5-minute 413 limit. The capture
 *  keeps running when hit (existing audio is retained); the user is warned once. */
export const MAX_BUFFER_BYTES = 4.5 * 60 * 16000 * 2

/** After sending 'finalize' on a CONNECTED stream, wait at most this long for the
 *  trailing segment before falling back to batch (macOS live-finalization
 *  timeout). A segment arriving sooner short-circuits immediately. */
export const STREAM_FINALIZE_DEADLINE_MS = 3000

/** Abort the batch POST after this long. Long enough for a multi-minute buffer
 *  upload + transcription (live baseline: 80s of audio ≈ 7-9s round-trip), short
 *  enough that a dead network resolves visibly instead of hanging the gesture. */
export const BATCH_TIMEOUT_MS = 20000

/** How long the "Hold longer to record" hint stays up (macOS: 2s). Never blocks a
 *  new hold — state returns to idle the moment the hint shows. */
export const HINT_MS = 2000

/** How long the "Recording too long" warning stays up (macOS: 4s). */
export const TOO_LONG_HINT_MS = 4000

/** Error strip auto-clear (macOS shows batch errors ~3s then resets). */
export const ERROR_STRIP_MS = 3000

/** Last-resort escape hatch: no capture may hold non-idle UI longer than this
 *  (macOS thinkingWatchdogDelay). Every inner wait is far shorter — this catches
 *  bugs, not flows; a stuck "Transcribing…" is impossible. */
export const WATCHDOG_MS = 25000
