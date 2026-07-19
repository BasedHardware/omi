// Voice loudness → orb display level: the ONE adaptive transfer chain feeding
// the orb's waveform bars and blob wobble.
//
// Why this exists (both historical failure modes were structural):
//   • "Maxed out constantly even with quiet input" (pre-2026-07-12): the raw
//     level was an AnalyserNode byte-frequency RMS — a dB-DOMAIN quantity whose
//     room-silence floor sits around half of the speech band — mapped through an
//     ungated exponential. Silence read 58%+ bars, speech pinned high.
//   • "A lot worse / inconsistent" (post hub default-ON): the 2026-07-12 fix
//     gated + calibrated the curve to that dB-ish scale (gate 0.66 raw), but the
//     warm-hub turn driver ships a LINEAR PCM peak (0..1, speech ≈ 0.1–0.4) as
//     `orbLevel`. Linear speech peaks sat mostly BELOW the dB-scale gate, so the
//     default voice path barely moved the bars except on loud plosives.
// Root cause both times: a fixed curve hard-calibrated to one producer's unit
// and one mic's gain. The fix is structural: every producer now emits the SAME
// canonical unit — linear amplitude 0..1 of full scale (peak of the recent
// window; the hub's pcmPeakLevel and the capture window's time-domain peak both
// are) — and this mapper adapts to the mic/room within BOUNDED ranges.
//
// The chain (all level tracking in dBFS, where speech dynamics are ~linear):
//   raw linear 0..1
//     → dBFS                       20·log10(raw)
//     → adaptive noise-floor gate  slow-rise/fast-fall floor tracker + margin,
//                                  clamped so it can never climb into speech
//     → bounded AGC ceiling        tracks the session's speech peaks (fast up,
//                                  slow down) but clamped to an absolute band
//                                  AND never closer than CEIL_MIN_SPAN_DB to the
//                                  gate — a quiet room or a whisper-only session
//                                  can NEVER be normalized up to full range
//                                  (this is what structurally prevents the old
//                                  "maxed out constantly" era from returning)
//     → normalize                  u = (db − gate) / (ceiling − gate), clamp 0..1
//     → perceptual curve           u^GAMMA (gentle low-end lift; dB already
//                                  handles most of the perceptual mapping)
//     → output ceiling             × OUT_CEIL (< 1) so even the loudest input
//                                  APPROACHES the bar maximum, never slams it.
// Downstream, the animator's fast-attack/slow-release envelope
// (choreography.stepAmplitudeEnvelope) provides the feel; this mapper is the
// level calibration only. Everything is stepped with explicit dt (exponential
// coefficients derived per step), so the response is identical at 30 or 60fps —
// the constant-rate rule.
//
// Typical mapping on a normal mic (floor ≈ -50 dBFS → floor+margin -40, clamped
// to the gate band's top: gate -44; ceiling ≈ -13):
//   room silence / breath  (< -44 dB) → 0        resting dots
//   quiet speech           (≈ -32 dB) → ~0.4     clearly visible, well below max
//   normal speech syllables(-25..-13) → ~0.55–0.92  mid-to-high, live dynamics
//   loud speech            (≥ ceiling) → 0.92    near max, never pinned at 1

/** Raw linear levels at/below this (≈ −80 dBFS) are "no signal": output 0 and
 *  hold the trackers (Orb feeds literal 0 while speech is inactive — that must
 *  not teach the floor tracker a fictitious digital-silence room). */
export const AMP_NO_SIGNAL = 1e-4

/** Floor of the dB conversion — everything quieter is treated as −80 dBFS. */
export const AMP_DB_MIN = -80

// --- Adaptive noise floor (the gate) ---------------------------------------
/** Initial floor estimate (dBFS) — a typical quiet room on a normal mic. */
export const FLOOR_INIT_DB = -55
/** Tau (s) when the observed level is BELOW the floor — falls (deliberately not
 *  instantly: a brief quieter-than-room dip must not drop the gate under normal
 *  room noise) toward the true quiet between words. */
export const FLOOR_FALL_TAU = 1.0
/** Tau (s) when the observed level is ABOVE the floor — rises slowly, so held
 *  speech contaminates the floor as little as possible (and the gate clamp
 *  below makes any contamination harmless). */
export const FLOOR_RISE_TAU = 12
/** Gate margin above the tracked floor (dB): breath/hiss just over the floor
 *  still reads as rest. */
export const GATE_MARGIN_DB = 10
/** Hard gate band (dBFS). The STRUCTURAL guarantee lives here, not in the floor
 *  tracker: the CLAMP itself is what makes the gate unable to fully eat speech,
 *  no matter what the floor tracker learned (held speech, whisper marathons).
 *  GATE_HI (−44) is set below where speech peaks land on any workable mic —
 *  plausibility cross-check: the PTT pipeline's own voiced heuristic expects
 *  frame RMS ≥ ~−41 dBFS (ptt/constants VOICED_RMS_THRESHOLD; measured on the
 *  processed stream, so an approximate reference for this AGC-free peak lane,
 *  not a hard bound). And GATE_LO (−52) keeps mic hiss/digital silence from
 *  ever drawing bars. */
export const GATE_LO_DB = -52
export const GATE_HI_DB = -44

// --- Bounded AGC ceiling ----------------------------------------------------
/** Initial ceiling (dBFS) — normal-speech peaks on a typical mic. */
export const CEIL_INIT_DB = -14
/** Tau (s) pulling the ceiling UP toward a louder observation (fast, so the
 *  first loud sentence recalibrates within a breath). */
export const CEIL_ATTACK_TAU = 0.25
/** Tau (s) letting the ceiling decay DOWN toward quieter speech (slow, so one
 *  soft sentence doesn't crush the range). */
export const CEIL_DECAY_TAU = 12
/** The ceiling never comes closer than this (dB) to the gate — the bounded-gain
 *  guarantee: maximum normalization gain is capped, so near-floor input can
 *  never be stretched to full range. */
export const CEIL_MIN_SPAN_DB = 18
/** Absolute ceiling band (dBFS): adapts to mic gain within this range only. */
export const CEIL_ABS_MIN_DB = -22
export const CEIL_ABS_MAX_DB = -4
/** Headroom (dB) above the tracked ceiling that maps to full range: the
 *  SESSION-TYPICAL peak reads high-but-not-top (~0.83), so ordinary speech
 *  lives mid-range and only louder-than-recent moments approach OUT_CEIL —
 *  "approaches, never slams" as a property of the curve, not luck. */
export const CEIL_HEADROOM_DB = 4

// --- Output shaping ---------------------------------------------------------
/** Perceptual exponent on the normalized level (dB normalization already does
 *  most of the work; this adds a gentle low-end lift). */
export const AMP_GAMMA = 0.85
/** Display ceiling (< 1): the loudest input approaches, never slams, the bar
 *  maximum (waveform max height needs level 1). */
export const AMP_OUT_CEIL = 0.92

const clamp = (x: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, x))

/** Per-step exponential smoothing coefficient for a time constant tau (s). */
const k = (dt: number, tau: number): number => 1 - Math.exp(-dt / Math.max(1e-6, tau))

/**
 * Stateful adaptive mapper: raw linear amplitude (0..1 full scale) → display
 * level [0, AMP_OUT_CEIL]. One instance per orb animator; state persists across
 * utterances (that's the point — it remembers the mic/room between holds).
 * Deterministic given (raw, dt) sequences — the unit tests replay scripted
 * sessions through it.
 */
export class AmplitudeMapper {
  private floorDb = FLOOR_INIT_DB
  private ceilDb = CEIL_INIT_DB

  /** Tracker snapshot, for tests and the opt-in [orb-amp] diagnostics tap. */
  get trackers(): { floorDb: number; ceilDb: number; gateDb: number } {
    return { floorDb: this.floorDb, ceilDb: this.ceilDb, gateDb: this.gateDb() }
  }

  private gateDb(): number {
    return clamp(this.floorDb + GATE_MARGIN_DB, GATE_LO_DB, GATE_HI_DB)
  }

  /** Advance the trackers by dt (s) with the observed raw level and return the
   *  display level. Rate-independent: N small steps ≈ one big step. */
  step(raw: number, dt: number): number {
    if (!(raw > AMP_NO_SIGNAL)) return 0 // no signal: hold trackers, rest level
    const db = clamp(20 * Math.log10(raw), AMP_DB_MIN, 0)

    // Noise floor: fall toward true quiet, rise slowly under speech. No clamp
    // needed here — gateDb() clamps to the hard gate band.
    const floorTau = db < this.floorDb ? FLOOR_FALL_TAU : FLOOR_RISE_TAU
    this.floorDb = Math.max(this.floorDb + (db - this.floorDb) * k(dt, floorTau), AMP_DB_MIN)
    const gate = this.gateDb()

    // Ceiling: learns only from gated (speech-band) signal; fast up, slow down.
    if (db > gate) {
      const ceilTau = db > this.ceilDb ? CEIL_ATTACK_TAU : CEIL_DECAY_TAU
      this.ceilDb += (db - this.ceilDb) * k(dt, ceilTau)
    }
    const ceilMin = Math.max(gate + CEIL_MIN_SPAN_DB, CEIL_ABS_MIN_DB)
    this.ceilDb = clamp(this.ceilDb, ceilMin, CEIL_ABS_MAX_DB)

    if (db <= gate) return 0
    const u = Math.min(1, (db - gate) / (this.ceilDb + CEIL_HEADROOM_DB - gate))
    return AMP_OUT_CEIL * Math.pow(u, AMP_GAMMA)
  }
}
