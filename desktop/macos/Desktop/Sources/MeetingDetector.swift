import AppKit
import Foundation

private final class WeakMeetingDetector: @unchecked Sendable {
  weak var value: MeetingDetector?

  init(_ value: MeetingDetector) {
    self.value = value
  }
}

/// Detects whether a conferencing call ("meeting") is currently active by scanning on-screen
/// windows for known call apps (see `ConferencingApps`).
///
/// Used to gate system-audio capture in "Only during meetings" mode and to rotate logical
/// conversations at call boundaries while Always mode keeps the microphone live. It exists only
/// while microphone transcription is active, so there is zero overhead otherwise.
///
/// Transitions **on** as soon as a call is detected, but transitions **off** only after a grace
/// period of sustained "no meeting" (hysteresis) to avoid flapping when a call window briefly
/// disappears (focus changes, screen-share popups, etc.).
@MainActor
final class MeetingDetector {

  /// Current meeting state. Updated on the main actor by `applyDetected(_:)`.
  private(set) var isMeetingActive: Bool = false
  /// True after at least one async probe has reported. Until then, `isMeetingActive == false`
  /// means "unknown", not "no meeting".
  private(set) var hasObservedState: Bool = false
  /// Set when a different call replaced the one in progress without an off edge. The owner
  /// clears it when it starts rotating and restores it if the rotation could not run. Reset
  /// whenever the meeting ends.
  private(set) var hasPendingCallChange = false

  private let pollInterval: TimeInterval
  private let offGracePeriod: TimeInterval
  private let isMeetingNow: @Sendable () -> Bool
  private let callIdentities: @Sendable () -> Set<String>
  private var callTracker: MeetingCallIdentityTracker
  private let now: () -> Date
  private let onInitialStateObserved: () -> Void
  private let onCallChanged: () -> Void
  private let onChange: (Bool) -> Void

  private var timer: Timer?
  private var workspaceObservers: [NSObjectProtocol] = []
  /// When the call first goes undetected, the time at which we will actually flip to inactive.
  /// `nil` whenever a meeting is detected or no pending-off is in progress.
  private var pendingOffDeadline: Date?
  private var started = false
  private var probeGeneration: UInt64 = 0
  private var probeTask: Task<Void, Never>?

  /// - Parameters:
  ///   - pollInterval: how often to re-probe (browser tab-title changes only surface via the poll).
  ///   - offGracePeriod: sustained "no meeting" time required before flipping off.
  ///   - isMeetingNow: conferencing-call probe (injectable for tests). Default: a native or browser
  ///     app using the mic (macOS 14.4+), or a browser call window (window-title fallback).
  ///   - callIdentities: which calls are on, probed only while a call is detected. Default: none,
  ///     so a detector without it never reports a call change.
  ///   - callConfirmationPeriod: how long a new call must stay visible before it counts.
  ///   - now: clock (injectable for tests).
  ///   - onInitialStateObserved: called on the main actor once the first async probe completes.
  ///   - onCallChanged: called on the main actor when a different call replaces the current one.
  ///   - onChange: called on the main actor whenever `isMeetingActive` flips.
  init(
    pollInterval: TimeInterval = 4.0,
    offGracePeriod: TimeInterval = 8.0,
    isMeetingNow: @escaping @Sendable () -> Bool = {
      if #available(macOS 14.4, *), ConferencingApps.callAppIsUsingMicrophone() { return true }
      return ConferencingApps.browserCallWindowPresent()
    },
    callIdentities: @escaping @Sendable () -> Set<String> = { [] },
    callConfirmationPeriod: TimeInterval = 8.0,
    now: @escaping () -> Date = { Date() },
    onInitialStateObserved: @escaping () -> Void = {},
    onCallChanged: @escaping () -> Void = {},
    onChange: @escaping (Bool) -> Void
  ) {
    self.pollInterval = pollInterval
    self.offGracePeriod = offGracePeriod
    self.isMeetingNow = isMeetingNow
    self.callIdentities = callIdentities
    self.callTracker = MeetingCallIdentityTracker(confirmationPeriod: callConfirmationPeriod)
    self.now = now
    self.onInitialStateObserved = onInitialStateObserved
    self.onCallChanged = onCallChanged
    self.onChange = onChange
  }

  /// Begin observing app launch/terminate/activation and polling. Emits the initial state
  /// synchronously so callers can read `isMeetingActive` immediately after `start()`.
  func start() {
    guard !started else { return }
    started = true
    probeGeneration &+= 1

    let nc = NSWorkspace.shared.notificationCenter
    for name in [
      NSWorkspace.didActivateApplicationNotification,
      NSWorkspace.didLaunchApplicationNotification,
      NSWorkspace.didTerminateApplicationNotification,
    ] {
      let observer = nc.addObserver(forName: name, object: nil, queue: .main) {
        [weak self] _ in
        Task { @MainActor in self?.tick() }
      }
      workspaceObservers.append(observer)
    }

    timer = Timer.scheduledTimer(withTimeInterval: pollInterval, repeats: true) {
      [weak self] _ in
      Task { @MainActor in self?.tick() }
    }

    // Establish the initial state. The probe runs off the main actor and is applied
    // asynchronously (and surfaced via onChange), so the caller's gate converges shortly after.
    tick()
    log("MeetingDetector: started (poll=\(pollInterval)s, offGrace=\(offGracePeriod)s)")
  }

  /// Stop all observation. Resets pending-off state; `isMeetingActive` is left as-is.
  func stop() {
    guard started else { return }
    started = false
    probeGeneration &+= 1
    probeTask?.cancel()
    probeTask = nil

    timer?.invalidate()
    timer = nil

    let nc = NSWorkspace.shared.notificationCenter
    for observer in workspaceObservers {
      nc.removeObserver(observer)
    }
    workspaceObservers.removeAll()
    pendingOffDeadline = nil
    log("MeetingDetector: stopped")
  }

  /// Probe for an active call off the main actor — the CoreAudio process scan / CGWindowList query
  /// can block (notably right after wake) — then apply the result back on the main actor.
  private func tick() {
    let probe = isMeetingNow
    let identities = callIdentities
    probeGeneration &+= 1
    let generation = probeGeneration
    let weakSelf = WeakMeetingDetector(self)
    probeTask?.cancel()
    probeTask = Task.detached(priority: .utility) {
      let detected = probe()
      let callIDs = detected ? identities() : []
      await MainActor.run {
        guard let detector = weakSelf.value,
          detector.started,
          detector.probeGeneration == generation
        else { return }
        detector.applyDetected(detected, callIDs: callIDs)
      }
    }
  }

  /// Apply a boolean detection result, honoring the off-hysteresis. Exposed for tests; normally
  /// driven by the poll timer and workspace notifications via `tick()`.
  func applyDetected(_ detected: Bool, callIDs: Set<String> = []) {
    let hadObservedState = hasObservedState
    hasObservedState = true

    if detected {
      // Meeting present: cancel any pending-off and ensure we're active.
      pendingOffDeadline = nil
      setActive(true)
      if callTracker.observe(callIDs, at: now()) {
        log("MeetingDetector: call CHANGED (now \(callIDs.sorted().joined(separator: ",")))")
        hasPendingCallChange = true
        onCallChanged()
      }
    } else if isMeetingActive {
      // Meeting undetected while active: arm or honor the off grace period.
      callTracker.noteMicrophoneGap(at: now())
      if let deadline = pendingOffDeadline {
        if now() >= deadline {
          pendingOffDeadline = nil
          setActive(false)
        }
      } else {
        pendingOffDeadline = now().addingTimeInterval(offGracePeriod)
      }
    } else {
      // Already inactive and still no meeting.
      pendingOffDeadline = nil
    }

    if !hadObservedState {
      onInitialStateObserved()
    }
  }

  private func setActive(_ active: Bool) {
    guard active != isMeetingActive else { return }
    isMeetingActive = active
    if !active {
      callTracker.reset()
      hasPendingCallChange = false
    }
    log("MeetingDetector: meeting \(active ? "STARTED" : "ENDED")")
    onChange(active)
  }

  func clearPendingCallChange() { hasPendingCallChange = false }
  func restorePendingCallChange() { hasPendingCallChange = true }

  #if DEBUG
    var currentProbeTaskForTesting: Task<Void, Never>? {
      probeTask
    }

    @discardableResult
    func triggerProbeForTesting() -> Task<Void, Never>? {
      tick()
      return probeTask
    }
  #endif
}

/// Tells one call from the next while the detector stays "in a meeting".
///
/// Leaving one Google Meet and joining another within the off grace period (the next Meet's
/// green room takes the microphone within seconds) never produces an off edge, so both calls
/// used to land in one conversation. Identities (`ConferencingApps.currentCallIdentities()`)
/// separate them. A call counts as new when an identity not seen earlier in this meeting stays
/// visible for `confirmationPeriod` **and replaces** the call in progress: that call's
/// identities are gone, or the microphone dropped shortly before the new identity appeared
/// (leaving A with its tab still open). A new identity merely appearing alongside the current
/// call (the next meeting's green room opened early, a huddle started mid-Meet) does not rotate.
/// Identities seen before never count again within the meeting, so switching tabs away from a
/// Meet and back does not rotate. No identities at all (no Screen Recording permission, a web
/// call that is not Meet) degrades to the old behaviour: one conversation until the off edge.
struct MeetingCallIdentityTracker {
  let confirmationPeriod: TimeInterval
  /// A microphone gap this long before a new identity first appears still counts as the
  /// previous call ending.
  let gapLeadWindow: TimeInterval = 30
  private var seen: Set<String> = []
  /// Identities of the call in progress.
  private var current: Set<String> = []
  private var candidate: (id: String, since: Date)?
  private var lastGapAt: Date?

  init(confirmationPeriod: TimeInterval) {
    self.confirmationPeriod = confirmationPeriod
  }

  mutating func reset() {
    seen = []
    current = []
    candidate = nil
    lastGapAt = nil
  }

  /// The detector saw no call on a probe while the meeting stayed active (inside the off grace).
  mutating func noteMicrophoneGap(at now: Date) {
    lastGapAt = now
  }

  /// Record one probe's identities; true when a new call has just been confirmed.
  mutating func observe(_ identities: Set<String>, at now: Date) -> Bool {
    guard !seen.isEmpty else {
      // The meeting's first identities name the call in progress, not a new one.
      seen = identities
      current = identities
      return false
    }
    let unseen = identities.subtracting(seen)
    guard let next = unseen.min() else {
      candidate = nil
      return false
    }
    if candidate?.id != next {
      candidate = (next, now)
    }
    guard let since = candidate?.since, now.timeIntervalSince(since) >= confirmationPeriod else { return false }
    let currentGone = current.isDisjoint(with: identities)
    let gapAroundAppearance = lastGapAt.map { $0 >= since.addingTimeInterval(-gapLeadWindow) } ?? false
    // Keep the candidate: the current call may still end (its window closes, its mic drops).
    guard currentGone || gapAroundAppearance else { return false }
    seen.formUnion(identities)
    current = unseen
    candidate = nil
    lastGapAt = nil
    return true
  }
}
