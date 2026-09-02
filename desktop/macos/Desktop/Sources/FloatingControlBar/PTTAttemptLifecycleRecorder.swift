import Foundation

/// Privacy-bounded capture-lifecycle correlation model for a single push-to-talk
/// (PTT) attempt and any recovery it triggers.
///
/// The existing `recordPTTSilentTurn` path records a *late* snapshot — it sees
/// peak/RMS/seconds at finalization but cannot answer *why* a turn was silent:
/// did capture ever start? did it deliver frames? was the key released before the
/// first usable audio arrived? did a capture rebuild restore the next turn? Those
/// questions are unanswerable from product telemetry alone, so a repeatable
/// "floating_bar_ptt_ended had_transcript=false, zero audio" incident cannot be
/// classified into one of the four causally distinct boundaries.
///
/// This recorder accumulates the *boundaries that already exist* in the capture
/// lifecycle (press, capture-start requested/accepted/failed, first audio
/// callback, first usable frame, release/disposition, recovery) into one redacted
/// per-attempt snapshot and emits it through `DesktopDiagnosticsManager` when the
/// attempt terminates. Every field is a bounded, low-cardinality bucket or safe
/// classification — never raw audio, device names, hardware IDs, paths, or error
/// strings.
///
/// Privacy boundary (mirrors `DesktopDiagnosticsManager`):
/// - raw audio frames are never retained; only a peak amplitude is reduced to an
///   energy bucket while searching for the first usable frame, then scanning stops;
/// - device identity is reduced to a transport class + default-vs-override flag;
/// - capture-start OSStatus / error text is reduced to a status class.
@MainActor
final class PTTAttemptLifecycleRecorder {
  /// What a bounded millisecond duration collapses into for remote querying.
  enum MillisecondsBucket: String {
    case none
    case lt50 = "lt_50"
    case lt100 = "lt_100"
    case lt200 = "lt_200"
    case lt500 = "lt_500"
    case ge500 = "ge_500"

    static func bucket(fromMs ms: Int?) -> MillisecondsBucket {
      guard let ms else { return .none }
      if ms < 50 { return .lt50 }
      if ms < 100 { return .lt100 }
      if ms < 200 { return .lt200 }
      if ms < 500 { return .lt500 }
      return .ge500
    }
  }

  /// Energy class of the first received audio chunks — distinguishes a capture
  /// that delivers real samples from one that delivers only zeros.
  enum FirstChunksEnergyBucket: String {
    case none
    case zero
    case nearZero = "near_zero"
    case audible
  }

  enum CaptureStartOutcome: String {
    case notRequested = "not_requested"
    case requested
    case accepted
    case failed
  }

  /// Sanitized capture-start status class. Derived from `AudioCaptureError`, never
  /// from the raw `OSStatus` or the unrestricted error description.
  enum CaptureStartStatusClass: String {
    case none
    case ok
    case noInput = "no_input"
    case engineStartFailed = "engine_start_failed"
    case permissionDenied = "permission_denied"
    case otherError = "other_error"

    static func from(error: Error?) -> CaptureStartStatusClass {
      guard let error else { return .none }
      // Match by the typed `AudioCaptureService.AudioCaptureError` cases so the raw
      // OSStatus code and localized description never enter the payload.
      if let capture = error as? AudioCaptureService.AudioCaptureError {
        switch capture {
        case .noInputAvailable: return .noInput
        case .engineStartFailed: return .engineStartFailed
        case .permissionDenied: return .permissionDenied
        case .converterCreationFailed: return .otherError
        }
      }
      return .otherError
    }
  }

  /// Peak/RMS at or below this count as "no real signal". Mirrors
  /// `PTTSilentMicRecoveryPolicy.deadMicPeakThreshold`, which gates dead-mic recovery.
  static let nearZeroAmplitude = 5

  enum InputRouteClass: String {
    case builtIn = "built_in"
    case external
    case bluetooth
    case virtual
    case unknown

    static func from(deviceDescription: String?, isBluetooth: Bool = false) -> InputRouteClass {
      // Bluetooth is the A2DP/HFP silent-capture case the recovery code targets;
      // prefer the CoreAudio transport flag over substring-matching the redacted
      // `id=` description (which never carries "bluetooth").
      if isBluetooth { return .bluetooth }
      let lower = (deviceDescription ?? "").lowercased()
      if lower.contains("built-in") { return .builtIn }
      if lower.contains("virtual") || lower.contains("aggregate") { return .virtual }
      if lower.isEmpty || lower == "?" { return .unknown }
      return .external
    }
  }

  enum InputRouteSource: String {
    case `default`
    case override
  }

  enum TurnDisposition: String {
    case committed
    case silentRejected = "silent_rejected"
    case tooShort = "too_short"
    case cancelled
  }

  enum RecoveryAction: String {
    case none
    case captureRebuild = "capture_rebuild"
    case switchToBuiltInMic = "switch_to_built_in_mic"
  }

  /// The four causally distinct failure boundaries the schema exists to separate,
  /// plus the success / non-judgeable terminations. `recovery_outcome_*` is set on
  /// the *next judgeable* attempt that resolves a prior capture rebuild, so a query
  /// joins triggering and resolving attempts on `recovery_attempt_id`.
  enum FailureClass: String {
    case captureNeverOperational = "capture_never_operational"
    case zeroOrNearZeroSamples = "zero_or_near_zero_samples"
    case releasedBeforeUsableAudio = "released_before_usable_audio"
    case recoveryOutcomeRecovered = "recovery_outcome_recovered"
    case recoveryOutcomeStillSilent = "recovery_outcome_still_silent"
    case recoveryOutcomeNotJudgeable = "recovery_outcome_not_judgeable"
    case committed
    case tooShortAudible = "too_short_audible"
    case cancelled
  }

  enum RecoveryOutcomeOfNextTurn: String {
    case none
    case recovered
    case stillSilent = "still_silent"
    case notJudgeable = "not_judgeable"
  }

  /// The redacted, joinable terminal snapshot handed to `DesktopDiagnosticsManager`.
  struct Snapshot {
    var attemptId: String
    var failureClass: FailureClass
    var captureStartOutcome: CaptureStartOutcome
    var captureStartStatusClass: CaptureStartStatusClass
    var msToFirstAudioBucket: MillisecondsBucket
    var msToFirstUsableFrameBucket: MillisecondsBucket
    var firstChunksEnergyBucket: FirstChunksEnergyBucket
    var turnDisposition: TurnDisposition
    var inputRouteClass: InputRouteClass
    var inputRouteSource: InputRouteSource
    var routeChangedDuringAttempt: Bool
    var recoveryTriggered: Bool
    var recoveryAction: RecoveryAction
    var recoveryAttemptId: String?
    var recoveryOutcomeOfNextTurn: RecoveryOutcomeOfNextTurn
    // Reused safe context also carried by the late silent-turn snapshot, so the two
    // can be correlated without re-sending raw audio or device identity.
    var mode: String
    var source: String
    var hubActive: Bool
    var micPermissionGranted: Bool
    /// Audio measurements are optional because some terminal paths genuinely do
    /// not hold the turn's PCM (e.g. `sendTranscript`, which runs after the buffer
    /// was consumed). Those paths omit the properties rather than reporting a
    /// literal `0`: a fake zero is indistinguishable from a real dead mic and
    /// silently poisons every admitted-vs-rejected energy comparison built on
    /// this event — which is exactly the comparison PTT speech-gate tuning needs.
    var turnAudioSeconds: Double?
    var voicedAudioSeconds: Double?
    var peak: Int?
    var rms: Int?
    var isNearZero: Bool?
    var judgeable: Bool
    var telemetrySchemaVersion: Int

    /// Low-cardinality `[String: Any]` for the PostHog / ring-buffer path. All
    /// values are bounded strings, booleans, or small numbers.
    var properties: [String: Any] {
      var dict: [String: Any] = [
        "attempt_id": attemptId,
        "failure_class": failureClass.rawValue,
        "capture_start_outcome": captureStartOutcome.rawValue,
        "capture_start_status_class": captureStartStatusClass.rawValue,
        "ms_to_first_audio_bucket": msToFirstAudioBucket.rawValue,
        "ms_to_first_usable_frame_bucket": msToFirstUsableFrameBucket.rawValue,
        "first_chunks_energy_bucket": firstChunksEnergyBucket.rawValue,
        "turn_disposition": turnDisposition.rawValue,
        "input_route_class": inputRouteClass.rawValue,
        "input_route_source": inputRouteSource.rawValue,
        "route_changed_during_attempt": routeChangedDuringAttempt,
        "recovery_triggered": recoveryTriggered,
        "recovery_action": recoveryAction.rawValue,
        "recovery_outcome_of_next_turn": recoveryOutcomeOfNextTurn.rawValue,
        "mode": mode,
        "source": source,
        "hub_active": hubActive,
        "tcc_microphone_granted": micPermissionGranted,
        "judgeable": judgeable,
        "telemetry_schema_version": telemetrySchemaVersion,
      ]
      if let turnAudioSeconds {
        dict["turn_audio_seconds"] = rounded(turnAudioSeconds)
      }
      if let voicedAudioSeconds {
        dict["voiced_audio_seconds"] = rounded(voicedAudioSeconds)
      }
      if let peak {
        dict["peak"] = peak
      }
      if let rms {
        dict["rms"] = rms
      }
      if let isNearZero {
        dict["is_near_zero"] = isNearZero
      }
      if let recoveryAttemptId {
        dict["recovery_attempt_id"] = recoveryAttemptId
      }
      return dict
    }

    private func rounded(_ value: Double) -> Double {
      (value * 100).rounded() / 100
    }
  }

  /// Sink for emitted snapshots. Default routes through the diagnostics manager;
  /// tests inject a capturing closure so the classification is verifiable in
  /// isolation without touching the shared PostHog/Sentry singleton.
  var emit: (Snapshot) -> Void = { DesktopDiagnosticsManager.shared.recordPTTAttemptLifecycle($0) }

  /// Injectable clock so timing buckets are deterministic in tests.
  var now: () -> Date = { Date() }

  private var attemptSequence: UInt64 = 0
  private var recoverySequence: UInt64 = 0

  // Per-attempt accumulation state. Reset on every `beginAttempt`.
  private var attemptId: String = "0"
  private var attemptStartedAt: Date?
  private var releasedAt: Date?
  private var captureStartOutcome: CaptureStartOutcome = .notRequested
  private var captureStartStatusClass: CaptureStartStatusClass = .none
  private var firstAudioCallbackAt: Date?
  private var firstUsableFrameAt: Date?
  private var firstChunksEnergy: FirstChunksEnergyBucket = .none
  private var inputRouteClass: InputRouteClass = .unknown
  private var inputRouteSource: InputRouteSource = .default
  private var routeChangedDuringAttempt = false
  private var recoveryTriggered = false
  private var recoveryAction: RecoveryAction = .none

  /// A capture rebuild requested on a *prior* attempt, awaiting its next judgeable
  /// turn to record whether it restored capture. Joined on `recovery_attempt_id`.
  private var pendingRecoveryAttemptId: String?

  // Cached attempt context set in beginAttempt, read at terminate.
  private var cachedMode: String = ""
  private var cachedHubActive: Bool = false
  private var cachedMicPermissionGranted: Bool = false

  init() {}

  // MARK: - Per-attempt boundaries

  /// PTT press / attempt start. The transcription route `source` (hub / omni_stt /
  /// batch_stt …) is resolved at finalization, not at press.
  func beginAttempt(mode: String, hubActive: Bool, micPermissionGranted: Bool) {
    attemptSequence &+= 1
    attemptId = String(attemptSequence)
    attemptStartedAt = now()
    releasedAt = nil
    captureStartOutcome = .notRequested
    captureStartStatusClass = .none
    firstAudioCallbackAt = nil
    firstUsableFrameAt = nil
    firstChunksEnergy = .none
    inputRouteClass = .unknown
    inputRouteSource = .default
    routeChangedDuringAttempt = false
    recoveryTriggered = false
    recoveryAction = .none
    cachedMode = mode
    cachedHubActive = hubActive
    cachedMicPermissionGranted = micPermissionGranted
  }

  /// Capture-start requested (the async CoreAudio start is now in flight).
  func captureStartRequested() {
    guard captureStartOutcome == .notRequested else { return }
    captureStartOutcome = .requested
  }

  /// Capture-start resolved — accepted (IOProc running) or failed.
  func captureStartResolved(outcome: CaptureStartOutcome, statusClass: CaptureStartStatusClass) {
    guard outcome == .accepted || outcome == .failed else { return }
    captureStartOutcome = outcome
    captureStartStatusClass = outcome == .accepted ? .ok : statusClass
  }

  /// Record the input route at the moment capture was configured.
  func noteInputRoute(class routeClass: InputRouteClass, source: InputRouteSource) {
    inputRouteClass = routeClass
    inputRouteSource = source
  }

  /// A HAL device/format change was observed during the attempt (user plugged a
  /// headset, a Bluetooth profile flipped, etc.). This is a known precursor of
  /// silent capture and is recorded as a boolean flag, never the device identity.
  func noteRouteChanged() {
    routeChangedDuringAttempt = true
  }

  /// An audio chunk arrived from the capture callback. The peak is reduced to an
  /// energy bucket and scanning stops once the first usable frame is found, so a
  /// long successful turn does not pay a per-chunk cost. Raw PCM is not retained.
  func ingestAudioChunk(_ pcm16k: Data) {
    if firstAudioCallbackAt == nil {
      firstAudioCallbackAt = now()
    }
    classifyFirstChunkEnergy(pcm16k)
  }

  private func classifyFirstChunkEnergy(_ pcm16k: Data) {
    guard firstUsableFrameAt == nil else { return }
    let peak = Self.peakAmplitude(pcm16k: pcm16k)
    // Bucket the leading energy so a capture delivering only zeros is separable
    // from one delivering real speech. `5` is the same boundary the silent-mic
    // watchdog and dead-mic recovery use (peak ≤ 5 ≈ -76 dBFS is silent).
    if peak > 50 {
      firstChunksEnergy = .audible
      firstUsableFrameAt = now()
    } else if peak > 5 {
      if firstChunksEnergy != .audible { firstChunksEnergy = .nearZero }
    } else {
      if firstChunksEnergy == .none { firstChunksEnergy = .zero }
    }
  }

  /// The user let go. Latched, because finalization is not always prompt: a turn
  /// that arrives while the realtime hub is still warming holds its buffered
  /// audio and is judged a second or more later, on the hub warm deadline or on
  /// the connection landing. Measuring the hold as "now minus the press" there
  /// would count that wait as part of the user's press and turn every accidental
  /// tap on a cold hub into a capture failure.
  ///
  /// Idempotent: the first call wins, so a re-entered finalization cannot extend
  /// a hold that already ended.
  func noteRelease() {
    guard attemptStartedAt != nil, releasedAt == nil else { return }
    releasedAt = now()
  }

  /// Whether a capture start was ever asked for. A turn that never requested one
  /// has no capture-start latency to charge, so it must not be judged as though
  /// it did — the automation bridge drives real PTT turns with the microphone
  /// deliberately bypassed, and their "hold" is however long the harness took
  /// between two HTTP calls.
  var captureWasRequested: Bool { captureStartOutcome != .notRequested }

  /// How long the user actually held the key, in seconds — not how much audio the
  /// capture managed to deliver inside it. `nil` before `beginAttempt`. Read by
  /// the discard paths so capture-start latency is charged to capture rather than
  /// to the user's finger.
  var holdSeconds: Double? {
    guard let attemptStartedAt else { return nil }
    return max(0, (releasedAt ?? now()).timeIntervalSince(attemptStartedAt))
  }

  /// A recovery was requested for this attempt. Mints a bounded correlation id
  /// that the *next judgeable* attempt resolves.
  ///
  /// If a prior recovery is still pending (a non-judgeable turn left it
  /// unresolved), the new id supersedes it: the prior triggering event already
  /// recorded its own id, so only its *resolution* outcome becomes unknowable —
  /// a rare two-recoveries-in-succession case where the prior outcome is
  /// genuinely superseded by the fresh rebuild.
  func recoveryTriggered(action: RecoveryAction) {
    guard action != .none else { return }
    recoveryTriggered = true
    recoveryAction = action
    recoverySequence &+= 1
    pendingRecoveryAttemptId = "r\(recoverySequence)"
  }

  // MARK: - Termination

  /// Classify the attempt and emit one redacted snapshot. Resolves any pending
  /// recovery from a prior attempt against this turn's outcome.
  @discardableResult
  func terminate(
    disposition: TurnDisposition,
    source: String,
    peak: Int?,
    rms: Int?,
    turnAudioSeconds: Double?,
    voicedAudioSeconds: Double?,
    judgeable: Bool,
    captureStartedLate: Bool = false
  ) -> Snapshot {
    // Derived here, never supplied: a caller that passes its own near-zero verdict
    // can contradict the peak/rms it reported in the same call. Unknown energy
    // yields an unknown verdict rather than a confident `false`.
    let isNearZero: Bool? =
      if let peak, let rms { peak <= Self.nearZeroAmplitude && rms <= Self.nearZeroAmplitude } else { nil }
    let msToFirstAudio = milliseconds(since: attemptStartedAt, to: firstAudioCallbackAt)
    let msToFirstUsable = milliseconds(since: attemptStartedAt, to: firstUsableFrameAt)
    let firstEnergy = finalizeFirstChunksEnergy(
      hadCallbacks: firstAudioCallbackAt != nil, isNearZero: isNearZero ?? false, judgeable: judgeable)

    // Resolve a recovery requested on a *prior* attempt: this turn is the "next
    // judgeable turn" whose outcome proves whether the rebuild restored capture.
    // A turn that itself triggers a fresh rebuild mints its own id and does not
    // resolve the prior one (its own failure_class still records the trigger).
    let priorRecoveryId = pendingRecoveryAttemptId
    var resolvedOutcome = RecoveryOutcomeOfNextTurn.none
    if priorRecoveryId != nil, !recoveryTriggered {
      if !judgeable {
        resolvedOutcome = .notJudgeable
      } else if firstUsableFrameAt == nil {
        resolvedOutcome = .stillSilent
      } else {
        resolvedOutcome = .recovered
      }
      // A non-judgeable turn carries no evidence — leave the recovery pending so the
      // next truly judgeable turn resolves it instead of masking it.
      if resolvedOutcome != .notJudgeable {
        pendingRecoveryAttemptId = nil
      }
    }

    let failureClass = Self.classify(
      disposition: disposition,
      captureStartOutcome: captureStartOutcome,
      hadFirstAudioCallback: firstAudioCallbackAt != nil,
      hadFirstUsableFrame: firstUsableFrameAt != nil,
      judgeable: judgeable,
      captureStartedLate: captureStartedLate,
      resolvedRecoveryOutcome: resolvedOutcome)

    let snapshot = Snapshot(
      attemptId: attemptId,
      failureClass: failureClass,
      captureStartOutcome: captureStartOutcome,
      captureStartStatusClass: captureStartStatusClass,
      msToFirstAudioBucket: MillisecondsBucket.bucket(fromMs: msToFirstAudio),
      msToFirstUsableFrameBucket: MillisecondsBucket.bucket(fromMs: msToFirstUsable),
      firstChunksEnergyBucket: firstEnergy,
      turnDisposition: disposition,
      inputRouteClass: inputRouteClass,
      inputRouteSource: inputRouteSource,
      routeChangedDuringAttempt: routeChangedDuringAttempt,
      recoveryTriggered: recoveryTriggered,
      recoveryAction: recoveryAction,
      recoveryAttemptId: recoveryTriggered ? pendingRecoveryAttemptId : priorRecoveryId,
      recoveryOutcomeOfNextTurn: resolvedOutcome,
      mode: cachedMode,
      source: source,
      hubActive: cachedHubActive,
      micPermissionGranted: cachedMicPermissionGranted,
      turnAudioSeconds: turnAudioSeconds,
      voicedAudioSeconds: voicedAudioSeconds,
      peak: peak,
      rms: rms,
      isNearZero: isNearZero,
      judgeable: judgeable,
      telemetrySchemaVersion: 2)

    emit(snapshot)
    return snapshot
  }

  // MARK: - Classification

  /// Pure precedence over the causally distinct boundaries. Order matters: a
  /// recovery outcome (resolved by this turn) dominates, then capture-start
  /// failure / no-callback, then released-before-usable-audio, then zero samples.
  static func classify(
    disposition: TurnDisposition,
    captureStartOutcome: CaptureStartOutcome,
    hadFirstAudioCallback: Bool,
    hadFirstUsableFrame: Bool,
    judgeable: Bool,
    captureStartedLate: Bool = false,
    resolvedRecoveryOutcome: RecoveryOutcomeOfNextTurn
  ) -> FailureClass {
    if resolvedRecoveryOutcome == .recovered { return .recoveryOutcomeRecovered }
    if resolvedRecoveryOutcome == .stillSilent { return .recoveryOutcomeStillSilent }
    if resolvedRecoveryOutcome == .notJudgeable { return .recoveryOutcomeNotJudgeable }

    if disposition == .cancelled { return .cancelled }

    // (1) Capture never became operational for this press: the start failed, it
    // was requested but never delivered a callback before the turn ended
    // (startup race), or it came up so late in the hold that it delivered less
    // audio than the commit gate needs. The last case used to land in
    // `too_short_audible`, which reads as a user who tapped — it is the same
    // capture defect as the other two and belongs in the same class so one query
    // sizes the whole first-press gap.
    if captureStartOutcome == .failed || !hadFirstAudioCallback || captureStartedLate {
      return .captureNeverOperational
    }

    // (3) Released before the first usable audio arrived — the key came up before
    // any audible frame, even though callbacks were flowing.
    if !hadFirstUsableFrame {
      if disposition == .tooShort || !judgeable {
        return .releasedBeforeUsableAudio
      }
      // Long enough to judge but no usable frame ever appeared.
      return .zeroOrNearZeroSamples
    }

    // Capture is operational and delivered usable audio.
    if disposition == .committed {
      return .committed
    }
    if disposition == .tooShort {
      return .tooShortAudible
    }
    // silentRejected with usable audio (e.g. a loud transient the VAD rejected as
    // non-speech) is still a rejected turn, not a committed one. Keep it observable
    // remotely — returning .committed would mark it local-only and hide exactly the
    // silent incident this model exists to surface. first_chunks_energy_bucket +
    // turn_disposition separate it from a true zero-sample turn in a query.
    return .zeroOrNearZeroSamples
  }

  // MARK: - Helpers

  private func finalizeFirstChunksEnergy(
    hadCallbacks: Bool,
    isNearZero: Bool,
    judgeable: Bool
  ) -> FirstChunksEnergyBucket {
    if !hadCallbacks { return .none }
    if firstChunksEnergy == .audible { return .audible }
    // Callbacks arrived but no usable frame: collapse to the zero/near-zero
    // energy class so the leading-buffer silence is observable.
    return (isNearZero && judgeable) ? .zero : (firstChunksEnergy == .none ? .zero : firstChunksEnergy)
  }

  private func milliseconds(since start: Date?, to event: Date?) -> Int? {
    guard let start, let event else { return nil }
    return max(0, Int(event.timeIntervalSince(start) * 1000))
  }

  /// Peak amplitude (0–32767) of a 16 kHz mono Int16 PCM buffer. Bounded scan.
  static func peakAmplitude(pcm16k data: Data) -> Int {
    let n = data.count / 2
    guard n > 0 else { return 0 }
    var peak = 0
    data.withUnsafeBytes { raw in
      let s = raw.bindMemory(to: Int16.self)
      for i in 0..<n {
        let v = Int(s[i])
        let absolute = v == Int16.min ? Int(Int16.max) : Swift.abs(v)
        if absolute > peak { peak = absolute }
      }
    }
    return peak
  }
}
