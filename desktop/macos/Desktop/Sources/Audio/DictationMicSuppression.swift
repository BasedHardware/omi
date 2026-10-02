import Foundation

/// Lets the detached CoreAudio probe hand its sample back to the main-actor monitor without
/// sending `self` across the isolation boundary (same shape as `WeakMeetingDetector`).
private final class WeakDictationMicSuppressionMonitor: @unchecked Sendable {
  weak var value: DictationMicSuppressionMonitor?

  init(_ value: DictationMicSuppressionMonitor) {
    self.value = value
  }
}

/// Ambient capture ignores the microphone while a dictation app holds it.
///
/// A dictation tool (Wispr Flow, superwhisper, macOS Dictation, …) opens the microphone for
/// exactly as long as the user holds its hotkey. Ambient capture hears the same speech, so every
/// dictation became a conversation — and a dictation longer than the backend discard gate's
/// 100-word early exit was never even considered for discard. The transcript cannot tell a
/// dictation from a monologue; the microphone's *co-consumer* can. CoreAudio reports which
/// processes are running input (`ConferencingApps.bundleIDsRunningInput`), so while a catalogued
/// dictation app holds the mic and no call surface does, the mic contribution to ambient capture
/// is replaced with the same length of PCM16 silence for exactly that window.
///
/// Deliberately a catalog, not "any non-call process": a generic rule fires on in-person
/// recorders (Voice Memos, Granola's in-person mode) and could only be made safe by retracting
/// speech after the window closes. Deliberately "call wins": dictating during a Zoom or Meet call
/// keeps everything, because the call app is also running input.
enum DictationMicSuppressionPolicy {
  enum Verdict: Equatable {
    /// Mute the mic contribution; `bundleID` is the dictation app holding the microphone.
    case suppress(bundleID: String)
    case pass(Reason)

    enum Reason: String, Equatable {
      case disabled
      case noDictationApp = "no_dictation_app"
      case callSurfaceHoldsMic = "call_surface_holds_mic"
    }
  }

  /// Exact bundle IDs (lowercased) of known dictation apps.
  static let dictationAppBundleIDs: Set<String> = [
    "com.superduper.superwhisper",  // superwhisper
    "com.goodsnooze.macwhisper",  // MacWhisper
    "com.electron.wispr-flow",  // Wispr Flow (Electron)
    "com.apple.dictationim",  // macOS Dictation input method
  ]

  /// Lowercased substrings that mark a bundle ID as a dictation tool when its exact ID is not
  /// catalogued — vendors rename Electron bundles and Apple's dictation helper varies by release.
  /// Matched against bundle IDs only, never against window titles or process names.
  static let dictationAppBundleIDTokens: [String] = [
    "wispr", "superwhisper", "macwhisper", "voiceink", "aquavoice", "dictation",
  ]

  static func isDictationApp(bundleID: String) -> Bool {
    let lower = bundleID.lowercased()
    if dictationAppBundleIDs.contains(lower) { return true }
    return dictationAppBundleIDTokens.contains { lower.contains($0) }
  }

  /// Decide from one sample of the processes currently running microphone input.
  ///
  /// - Parameters:
  ///   - runningInputBundleIDs: every process running mic input, as CoreAudio reports them.
  ///   - enabled: the user's "ignore dictation apps" setting.
  ///   - isCallSurface: whether a bundle ID is a native call app or a browser (a call in progress
  ///     outranks a dictation app so nothing said on a call is ever muted).
  static func verdict(
    runningInputBundleIDs: [String],
    enabled: Bool,
    isCallSurface: (String) -> Bool = ConferencingApps.isCallSurface(bundleID:)
  ) -> Verdict {
    guard enabled else { return .pass(.disabled) }
    let ids = runningInputBundleIDs.map { $0.lowercased() }
    guard let dictation = ids.first(where: isDictationApp(bundleID:)) else {
      return .pass(.noDictationApp)
    }
    if ids.contains(where: isCallSurface) { return .pass(.callSurfaceHoldsMic) }
    return .suppress(bundleID: dictation)
  }
}

/// The one bit shared between the monitor (main actor) and the microphone chunk callback
/// (CoreAudio's IO thread). Reads are lock-protected rather than atomic so the gate has no
/// dependency beyond Foundation; a chunk arrives every few tens of milliseconds, so the cost is nil.
final class DictationMicSuppressionGate: @unchecked Sendable {
  private let lock = NSLock()
  private var suppressed = false

  var isSuppressing: Bool {
    lock.lock()
    defer { lock.unlock() }
    return suppressed
  }

  func set(_ value: Bool) {
    lock.lock()
    defer { lock.unlock() }
    suppressed = value
  }

  /// The chunk ambient capture should consume: the input unchanged, or the same number of bytes
  /// of PCM16 silence. Length is preserved so the mixer's liveness tracking and the local
  /// transcriber's cadence see an uninterrupted stream; the silent-mic watchdog is unaffected
  /// because it measures the raw HAL buffers before this callback runs.
  func gated(_ chunk: Data) -> Data {
    isSuppressing ? Data(count: chunk.count) : chunk
  }
}

/// Polls the set of processes running microphone input while ambient capture is live and keeps
/// `gate` in step with `DictationMicSuppressionPolicy`. Exists only for the lifetime of a mic
/// capture session, like `MeetingDetector`, so there is no cost while not recording.
///
/// The probe runs off the main actor (the CoreAudio process scan can block right after wake) and
/// its result is applied back on the main actor through `apply(runningInputBundleIDs:)`, which is
/// also the deterministic entry point tests drive directly.
@MainActor
final class DictationMicSuppressionMonitor {
  struct ClosedWindow: Equatable {
    let bundleID: String
    let duration: TimeInterval
  }

  let gate: DictationMicSuppressionGate

  private let pollInterval: TimeInterval
  private let probe: @Sendable () -> [String]
  private let isEnabled: () -> Bool
  private let now: () -> Date
  private let onWindowClosed: (ClosedWindow) -> Void

  private var timer: Timer?
  private var probeTask: Task<Void, Never>?
  private var probeGeneration: UInt64 = 0
  private var started = false
  private var openWindowBundleID: String?
  private var openWindowStart: Date?

  /// - Parameters:
  ///   - pollInterval: how often to re-probe. A dictation hotkey hold is short, so this bounds how
  ///     many words leak before muting engages and how long muting lingers after release.
  ///   - probe: processes running mic input (injectable for tests). Default: CoreAudio on
  ///     macOS 14.4+, nothing on older releases (the feature is then inert).
  ///   - isEnabled: the user's setting, read on every sample so a toggle takes effect mid-session.
  ///   - now: clock (injectable for tests).
  ///   - onWindowClosed: called on the main actor once per completed suppression window.
  init(
    pollInterval: TimeInterval = 0.25,
    probe: @escaping @Sendable () -> [String] = {
      if #available(macOS 14.4, *) { return ConferencingApps.bundleIDsRunningInput() }
      return []
    },
    isEnabled: @escaping () -> Bool,
    now: @escaping () -> Date = { Date() },
    gate: DictationMicSuppressionGate = DictationMicSuppressionGate(),
    onWindowClosed: @escaping (ClosedWindow) -> Void
  ) {
    self.pollInterval = pollInterval
    self.probe = probe
    self.isEnabled = isEnabled
    self.now = now
    self.gate = gate
    self.onWindowClosed = onWindowClosed
  }

  var isSuppressing: Bool { gate.isSuppressing }

  func start() {
    guard !started else { return }
    started = true
    probeGeneration &+= 1
    timer = Timer.scheduledTimer(withTimeInterval: pollInterval, repeats: true) { [weak self] _ in
      Task { @MainActor in self?.tick() }
    }
    tick()
    log("DictationMicSuppression: started (poll=\(pollInterval)s)")
  }

  /// Stop polling. An open window is closed and reported so its duration is never lost, and the
  /// gate is released so a capture that outlives the monitor is never left muted.
  func stop() {
    guard started else { return }
    started = false
    probeGeneration &+= 1
    probeTask?.cancel()
    probeTask = nil
    timer?.invalidate()
    timer = nil
    closeWindowIfOpen()
    gate.set(false)
    log("DictationMicSuppression: stopped")
  }

  private func tick() {
    let probe = probe
    probeGeneration &+= 1
    let generation = probeGeneration
    let weakSelf = WeakDictationMicSuppressionMonitor(self)
    probeTask?.cancel()
    probeTask = Task.detached(priority: .utility) {
      let sample = probe()
      await MainActor.run {
        guard let monitor = weakSelf.value,
          monitor.started,
          monitor.probeGeneration == generation
        else { return }
        monitor.apply(runningInputBundleIDs: sample)
      }
    }
  }

  /// Apply one sample. Public to the module so tests can drive the state machine without a clock
  /// or CoreAudio.
  func apply(runningInputBundleIDs: [String]) {
    let verdict = DictationMicSuppressionPolicy.verdict(
      runningInputBundleIDs: runningInputBundleIDs, enabled: isEnabled())
    switch verdict {
    case .suppress(let bundleID):
      if openWindowBundleID == nil {
        openWindowBundleID = bundleID
        openWindowStart = now()
        log("DictationMicSuppression: \(bundleID) holds the microphone — muting ambient mic contribution")
      }
      gate.set(true)
    case .pass:
      closeWindowIfOpen()
      gate.set(false)
    }
  }

  private func closeWindowIfOpen() {
    guard let bundleID = openWindowBundleID, let start = openWindowStart else { return }
    let duration = max(0, now().timeIntervalSince(start))
    openWindowBundleID = nil
    openWindowStart = nil
    log(
      "DictationMicSuppression: \(bundleID) released the microphone after "
        + String(format: "%.1f", duration) + "s")
    onWindowClosed(ClosedWindow(bundleID: bundleID, duration: duration))
  }
}
