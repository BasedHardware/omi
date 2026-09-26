import Foundation
import VoiceTurnDomain

/// Whether a microphone capture may be opened *before* the user presses
/// push-to-talk, so the press adopts a running IOProc instead of paying
/// CoreAudio's start latency inside the hold.
///
/// Pure and clock-free on purpose: the interesting part is the admission rule,
/// not the CoreAudio call it guards, and the rule is what regresses. A prewarm
/// turns on the system microphone indicator without the user having asked for
/// anything, so every gate here is load-bearing — this must never be the reason
/// a permission prompt appears, never run for a signed-out or un-onboarded
/// install, and never open a second capture beside one that already exists.
enum PTTWarmCaptureAdmission {
  /// Why a warm capture was requested. Recorded in the log line so a warm mic
  /// in the wild can be traced to the moment that asked for it.
  enum Trigger: String {
    /// Onboarding just completed. The first-real-app card follows within
    /// seconds, and ambient transcription has just displaced any parked capture.
    case onboardingCompleted
    /// The first-real-app card is on screen telling the user to hold ⌥. The
    /// press is predictable here, which is the whole reason the card exists.
    case firstRealAppCard
    /// Ambient transcription opened the shared input device and released the
    /// parked PTT capture on its way in. Re-arm behind it.
    case ambientCaptureStarted
    /// The previous turn was lost to capture-start latency. The retry the user
    /// is being told about is this one.
    case captureNotReady
  }

  struct Input: Equatable {
    var pttEnabled: Bool
    /// TCC microphone authorization, already granted. A prewarm must never be
    /// what triggers the system prompt: the user has to see that prompt
    /// attached to an action they took.
    var micPermissionGranted: Bool
    var onboardingComplete: Bool
    var isSignedIn: Bool
    /// The input-routing snapshot has landed *and* proves the device this would
    /// open is safe to hold open unattended — see
    /// `PTTInputDeviceRouting.Snapshot.unattendedWarmCaptureRoute`. A warm-up
    /// that runs before routing resolves opens the raw system default input,
    /// which on a Mac with AirPods connected is the headset microphone: the
    /// A2DP→HFP flap would collapse the user's audio for the whole keep-alive
    /// window, with nothing they did behind it.
    var routeIsSafeToWarmUnattended: Bool
    /// A turn is live. Its own capture owns the device.
    var hasActiveTurn: Bool
    /// A warm capture is already parked, running, or starting. Opening another
    /// would leave two IOProcs on one device — the exact hazard the parked-warm
    /// mechanism exists to avoid.
    var hasCaptureAlready: Bool
  }

  static func admits(_ input: Input) -> Bool {
    input.pttEnabled
      && input.micPermissionGranted
      && input.onboardingComplete
      && input.isSignedIn
      && input.routeIsSafeToWarmUnattended
      && !input.hasActiveTurn
      && !input.hasCaptureAlready
  }
}

/// Why a push-to-talk turn ended with too little audio to commit.
///
/// The minimum-audio gate is measured on *delivered* audio, so a hold whose
/// capture only became operational near the end of the press looks identical to
/// a tap: 0.01 s of audio from a 947 ms hold, discarded, and the user told to
/// "Hold longer to record". Charging capture-start latency to the press is the
/// single largest new-user failure class on macOS, and this is the rule that
/// stops doing it.
enum PTTTurnDiscardJudgement: Equatable {
  /// The user really did tap instead of holding. "Hold longer to record" is the
  /// right thing to say.
  case shortTap
  /// The hold was long enough to speak into, but capture delivered less audio
  /// than the gate needs. The missing seconds are capture-start latency, not the
  /// user's finger.
  case captureStartedLate
  /// Enough audio arrived to judge the turn on its content.
  case audioJudgeable

  /// - Parameters:
  ///   - holdSeconds: wall time from key-down to release. `nil` when no press
  ///     clock is available, which falls back to the pre-existing behavior of
  ///     judging on delivered audio alone.
  ///   - deliveredAudioSeconds: audio the capture actually handed over.
  ///   - minTurnAudioSeconds: the gate (`minTurnAudioSeconds` /
  ///     `hubMinTurnAudioSeconds`, both 0.35 s).
  static func judge(
    holdSeconds: Double?,
    deliveredAudioSeconds: Double,
    minTurnAudioSeconds: Double
  ) -> PTTTurnDiscardJudgement {
    if deliveredAudioSeconds >= minTurnAudioSeconds { return .audioJudgeable }
    guard let holdSeconds else { return .shortTap }
    return holdSeconds >= minTurnAudioSeconds ? .captureStartedLate : .shortTap
  }
}

/// How a discarded push-to-talk turn is reported and ended. Resolved once per
/// turn from its judgement, so the four discard paths (hub, buffered hub,
/// omni/batch, warm-wait fallback) cannot drift apart in what they tell the user
/// and what they tell PostHog — a `capture_never_operational` turn whose hint
/// still reads "Hold longer to record" is the exact defect this fixes.
struct PTTDiscardedTurnResolution: Equatable {
  let judgement: PTTTurnDiscardJudgement
  let disposition: PTTAttemptLifecycleRecorder.TurnDisposition
  let terminalReason: VoiceTurnTerminalReason

  /// True when the turn carried enough audio to be judged on its content.
  var judgeable: Bool { judgement == .audioJudgeable }
  var captureStartedLate: Bool { judgement == .captureStartedLate }

  init(_ judgement: PTTTurnDiscardJudgement) {
    self.judgement = judgement
    switch judgement {
    case .shortTap:
      self.disposition = .tooShort
      self.terminalReason = .tooShort
    case .captureStartedLate:
      // Not `.tooShort`: the press was long enough, the capture was not ready.
      // `captureNotReady` carries the honest hint and keeps the capture parked
      // so the retry it promises is instant.
      self.disposition = .silentRejected
      self.terminalReason = .captureNotReady
    case .audioJudgeable:
      self.disposition = .silentRejected
      self.terminalReason = .silentRejected
    }
  }
}
