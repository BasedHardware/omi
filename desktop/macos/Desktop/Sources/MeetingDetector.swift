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
/// Capture opens provisionally on first evidence; conversation boundaries wait for sustained
/// confirmation. Capture closes after sustained "no meeting"; confirmation survives a bounded resume window. The notice
/// additionally waits out short meetings and a successful conversation rotation.
///
/// Polls every 1s while a native call app or browser holds the microphone, and every 4s
/// otherwise. The off grace stays a fixed 8s, so the faster poll does not shorten it.
@MainActor
final class MeetingDetector {

  /// Current meeting state. Updated on the main actor by `applyDetected(_:)`.
  private(set) var isMeetingActive: Bool = false
  /// Confirmed level for conversation boundaries, independent of provisional capture gating.
  private(set) var isMeetingConfirmed = false
  private var pendingOnSince: Date?
  private var confirmedSince: Date?
  private var noticeRequested = false
  private var noticePresented = false
  private let confirmationPeriod: TimeInterval
  private let noticeDelay: TimeInterval
  private let onConfirmedChange: (Bool) -> Void
  private let onNoteTakingNoticeReady: () -> Void
  private let onConfirmedEvidence: (MeetingDetectionEvidence) -> Void
  private var latestEvidence: MeetingDetectionEvidence?
  private var confirmedApps: Set<String> = []
  private var lastNativeOutputAt: [String: Date] = [:]
  private var confirmedCallIDs: Set<String> = []
  private var confirmedCalendarIDs: Set<String> = []
  private(set) var resumeOffAt: Date?
  private(set) var lastMeetingEndedAt: Date?
  private(set) var lastPositiveEvidenceDescription = "none"
  private let resumeWindow: TimeInterval
  private let calendarEventIDs: @Sendable () async -> Set<String>
  private var latestCalendarEventIDs: Set<String> = []
  private var calendarTask: Task<Void, Never>?
  private var calendarProbeStartedAt: Date?
  private var calendarProbeGeneration: UInt64 = 0
  /// True after at least one async probe has reported. Until then, `isMeetingActive == false`
  /// means "unknown", not "no meeting".
  private(set) var hasObservedState: Bool = false
  /// Set when a different call replaced the one in progress without an off edge. The owner
  /// clears it when it starts rotating and restores it if the rotation could not run. Reset
  /// whenever the meeting ends.
  private(set) var hasPendingCallChange = false
  /// Idle interval until a call surface holds the mic, then the 1s interval.
  private(set) var pollInterval: TimeInterval

  private let idlePollInterval: TimeInterval
  private let activePollInterval: TimeInterval
  private let offGracePeriod: TimeInterval
  private let mode: AssistantSettings.AudioRecordingMode
  private let processInputAPIAvailable: Bool
  private let snapshot: @Sendable () -> CallAudioSnapshot
  private var callTracker: MeetingCallIdentityTracker
  private var audioLedger: CallAppAudioDailyLedger
  private let now: () -> Date
  private let onInitialStateObserved: () -> Void
  private let onCallChanged: () -> Void
  private let onChange: (Bool) -> Void
  private let onAudioSummaries: ([CallAppAudioSummary]) -> Void

  private var timer: Timer?
  private var workspaceObservers: [NSObjectProtocol] = []
  /// When the call first goes undetected, the time at which we will actually flip to inactive.
  /// `nil` whenever a meeting is detected or no pending-off is in progress.
  private var pendingOffDeadline: Date?
  private var started = false
  private var probeGeneration: UInt64 = 0
  private var probeTask: Task<Void, Never>?

  /// - Parameters:
  ///   - pollInterval: how often to re-probe while no call surface holds the mic.
  ///   - activePollInterval: how often to re-probe while a native call app or browser holds the mic.
  ///   - offGracePeriod: sustained "no meeting" time required before flipping off.
  ///   - mode: recording mode whose detection semantics this detector must match.
  ///   - processInputAPIAvailable: macOS 14.4+ per-process input API. Tests pin it; production
  ///     follows the running OS.
  ///   - snapshot: one off-main audio snapshot per tick (injectable for tests).
  ///   - callConfirmationPeriod: how long a new call must stay visible before it counts.
  ///   - now: clock (injectable for tests).
  ///   - onInitialStateObserved: called on the main actor once the first async probe completes.
  ///   - onCallChanged: called on the main actor when a different call replaces the current one.
  ///   - onChange: called on the main actor whenever `isMeetingActive` flips.
  ///   - onAudioSummaries: daily call-audio aggregates to emit. Default sends them through PostHog.
  init(
    pollInterval: TimeInterval = 4.0,
    activePollInterval: TimeInterval = 1.0,
    offGracePeriod: TimeInterval = 8.0,
    mode: AssistantSettings.AudioRecordingMode = .onlyMeetings,
    processInputAPIAvailable: Bool? = nil,
    snapshot: (@Sendable () -> CallAudioSnapshot)? = nil,
    callConfirmationPeriod: TimeInterval = 8.0,
    confirmationPeriod: TimeInterval = MeetingDetectionTiming.confirmationPeriod,
    noticeDelay: TimeInterval = MeetingDetectionTiming.noticeDelay,
    resumeWindow: TimeInterval = MeetingDetectionTiming.resumeWindow,
    calendarEventIDs: @escaping @Sendable () async -> Set<String> = { [] },
    now: @escaping () -> Date = { Date() },
    audioLedgerDefaults: UserDefaults = .standard,
    calendar: Calendar = .current,
    onInitialStateObserved: @escaping () -> Void = {},
    onCallChanged: @escaping () -> Void = {},
    onChange: @escaping (Bool) -> Void,
    onConfirmedChange: @escaping (Bool) -> Void = { _ in },
    onNoteTakingNoticeReady: @escaping () -> Void = {},
    onConfirmedEvidence: @escaping (MeetingDetectionEvidence) -> Void = {
      PostHogManager.shared.track(MeetingDetectionEvidence.eventName, properties: $0.properties)
      if !$0.titlesReadable, $0.processInputAPIAvailable,
        $0.bundleIDs.contains(where: { MeetingCallObservation.browserFamily($0) != nil })
      {
        DesktopDiagnosticsManager.shared.recordFallback(
          area: "screen_capture", from: "browser_title_corroboration", to: "browser_microphone",
          reason: "capability_mismatch", outcome: .recovered)
      }
    },
    onAudioSummaries: @escaping ([CallAppAudioSummary]) -> Void = { summaries in
      for summary in summaries {
        PostHogManager.shared.callAppAudioSummary(summary)
      }
    }
  ) {
    let apiAvailable: Bool
    if let processInputAPIAvailable {
      apiAvailable = processInputAPIAvailable
    } else if #available(macOS 14.4, *) {
      apiAvailable = true
    } else {
      apiAvailable = false
    }
    let titles = CallAudioBrowserTitlePolicy.capture(mode: mode, processInputAPIAvailable: apiAvailable)
    self.idlePollInterval = pollInterval
    self.activePollInterval = activePollInterval
    self.pollInterval = pollInterval
    self.offGracePeriod = offGracePeriod
    self.mode = mode
    self.processInputAPIAvailable = apiAvailable
    self.snapshot = snapshot ?? { ConferencingApps.captureCallAudioSnapshot(browserTitles: titles) }
    self.callTracker = MeetingCallIdentityTracker(confirmationPeriod: callConfirmationPeriod)
    self.audioLedger = CallAppAudioDailyLedger(defaults: audioLedgerDefaults, calendar: calendar)
    self.now = now
    self.onInitialStateObserved = onInitialStateObserved
    self.onCallChanged = onCallChanged
    self.onChange = onChange
    self.confirmationPeriod = confirmationPeriod
    self.noticeDelay = noticeDelay
    self.resumeWindow = resumeWindow
    self.calendarEventIDs = calendarEventIDs
    self.onConfirmedChange = onConfirmedChange
    self.onNoteTakingNoticeReady = onNoteTakingNoticeReady
    self.onConfirmedEvidence = onConfirmedEvidence
    self.onAudioSummaries = onAudioSummaries
  }

  /// Begin observing app changes and polling. The first off-main probe asynchronously
  /// establishes readiness and provisional capture state.
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

    scheduleTimer()
    emitAudioSummaries(audioLedger.begin(at: now()))

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
    calendarTask?.cancel()
    calendarTask = nil
    calendarProbeStartedAt = nil
    calendarProbeGeneration &+= 1
    latestCalendarEventIDs = []
    lastNativeOutputAt = [:]

    timer?.invalidate()
    timer = nil

    let nc = NSWorkspace.shared.notificationCenter
    for observer in workspaceObservers {
      nc.removeObserver(observer)
    }
    workspaceObservers.removeAll()
    pendingOffDeadline = nil
    pendingOnSince = nil
    noticeRequested = false
    log("MeetingDetector: stopped")
  }

  /// One snapshot off the main actor — the CoreAudio process scan / CGWindowList query can
  /// block (notably right after wake) — then derive detection and identities on the main actor.
  private func tick() {
    let probe = snapshot
    probeGeneration &+= 1
    let generation = probeGeneration
    refreshCalendarEvents()
    let weakSelf = WeakMeetingDetector(self)
    probeTask?.cancel()
    probeTask = Task.detached(priority: .utility) {
      let shot = probe()
      await MainActor.run {
        guard let detector = weakSelf.value,
          detector.started,
          detector.probeGeneration == generation
        else { return }
        detector.applySnapshot(shot, calendarEventIDs: detector.latestCalendarEventIDs)
      }
    }
  }

  private func refreshCalendarEvents() {
    // Do not use a task group: it would await an EventKit call that ignores cancellation.
    // The regular audio poll retires the request and fences out any late result, even
    // across stop/start. Clear cached IDs so stale calendar evidence cannot resume a call.
    if let since = calendarProbeStartedAt,
      now().timeIntervalSince(since) >= MeetingDetectionTiming.calendarProbeTimeout
    {
      calendarTask?.cancel()
      calendarTask = nil
      calendarProbeStartedAt = nil
      latestCalendarEventIDs = []
      log("MeetingDetector: calendar probe timed out; retrying")
    }
    guard calendarTask == nil else { return }
    calendarProbeGeneration &+= 1
    let generation = calendarProbeGeneration
    calendarProbeStartedAt = now()
    let events = calendarEventIDs
    calendarTask = Task { [weak self] in
      let ids = await events()
      guard !Task.isCancelled, let self, self.started, self.calendarProbeGeneration == generation else { return }
      self.latestCalendarEventIDs = ids
      self.calendarProbeStartedAt = nil
      self.calendarTask = nil
    }
  }

  private func scheduleTimer() {
    timer?.invalidate()
    timer = Timer.scheduledTimer(withTimeInterval: pollInterval, repeats: true) { [weak self] _ in
      Task { @MainActor in self?.tick() }
    }
  }

  private func emitAudioSummaries(_ summaries: [CallAppAudioSummary]) {
    guard !summaries.isEmpty else { return }
    onAudioSummaries(summaries)
  }

  /// Apply one probe. Updates the mic-session ledger and the poll cadence, then the meeting
  /// state. Exposed for tests; the timer and workspace notifications drive it via `tick()`.
  func applySnapshot(_ snapshot: CallAudioSnapshot, calendarEventIDs: Set<String> = []) {
    let timestamp = now()
    emitAudioSummaries(audioLedger.ingest(snapshot, at: timestamp))
    let desired = MeetingCallObservation.pollInterval(
      snapshot: snapshot, idle: idlePollInterval, active: activePollInterval)
    if desired != pollInterval {
      pollInterval = desired
      if started { scheduleTimer() }
    }
    let maySustain = resumeOffAt.map { timestamp.timeIntervalSince($0) < resumeWindow } ?? isMeetingConfirmed
    for process in snapshot.processes where process.isRunningOutput {
      if let app = ConferencingApps.nativeCallAppID(bundleID: process.bundleID) {
        lastNativeOutputAt[app] = timestamp
      }
    }
    let sustainingApps: Set<String> =
      maySustain
      ? confirmedApps.filter { app in
        lastNativeOutputAt[app].map {
          timestamp.timeIntervalSince($0) < MeetingDetectionTiming.inputOnlySustainPeriod
        } ?? false
      } : []
    let detected = MeetingCallObservation.isDetected(
      snapshot: snapshot, mode: mode, processInputAPIAvailable: processInputAPIAvailable,
      sustainingApps: sustainingApps)
    let callIDs =
      detected
      ? MeetingCallObservation.identities(
        snapshot: snapshot,
        processInputAPIAvailable: processInputAPIAvailable,
        sustainingApps: sustainingApps,
        nativeIdentity: { self.audioLedger.nativeCallIdentity(bundleID: $0) })
      : []
    latestEvidence = MeetingDetectionEvidence(
      snapshot: snapshot, mode: mode, processInputAPIAvailable: processInputAPIAvailable)
    if detected {
      let apps = MeetingCallObservation.nativeApps(snapshot: snapshot, sustainingApps: sustainingApps)
      let flags = apps.sorted().map { app in
        let processes = snapshot.processes.filter { ConferencingApps.nativeCallAppID(bundleID: $0.bundleID) == app }
        return
          "\(app)(input=\(processes.contains(where: \.isRunningInput)),output=\(processes.contains(where: \.isRunningOutput)))"
      }
      lastPositiveEvidenceDescription =
        "at=\(timestamp.timeIntervalSince1970) apps=[\(flags.joined(separator: ","))] browserTitle=\(latestEvidence?.titleMatched == true)"
    }
    applyDetected(detected, callIDs: callIDs, calendarEventIDs: calendarEventIDs)
  }

  /// Apply a boolean detection result, honoring the off-hysteresis. Exposed for tests; normally
  /// driven by the poll timer and workspace notifications via `tick()`.
  func applyDetected(_ detected: Bool, callIDs: Set<String> = [], calendarEventIDs: Set<String> = []) {
    let hadObservedState = hasObservedState
    hasObservedState = true

    if let offAt = resumeOffAt {
      let expired = now().timeIntervalSince(offAt) >= resumeWindow
      let matches =
        !confirmedCallIDs.isDisjoint(with: callIDs)
        || !confirmedCalendarIDs.isDisjoint(with: calendarEventIDs)
      if expired || (detected && !matches) {
        endConfirmedMeeting(at: offAt)
      } else if detected {
        // The call survived the capture gap. Re-adopt identities (including a new
        // audio-helper generation) without publishing another conversation boundary.
        resumeOffAt = nil
        adoptConfirmedCall(callIDs, calendarEventIDs: calendarEventIDs)
        callTracker.reset()
        _ = callTracker.observe(callIDs, at: now())
        log("MeetingDetector: meeting RESUMED")
      }
    }

    if detected {
      // Meeting present: cancel any pending-off and ensure we're active.
      pendingOffDeadline = nil
      setActive(true)
      if !isMeetingConfirmed {
        if pendingOnSince == nil { pendingOnSince = now() }
        if let since = pendingOnSince, now().timeIntervalSince(since) >= confirmationPeriod {
          isMeetingConfirmed = true
          lastMeetingEndedAt = nil
          adoptConfirmedCall(callIDs, calendarEventIDs: calendarEventIDs)
          confirmedSince = now()
          noticePresented = false
          pendingOnSince = nil
          if let latestEvidence { onConfirmedEvidence(latestEvidence) }
          onConfirmedChange(true)
        }
      }
      if isMeetingConfirmed, confirmedCallIDs.isEmpty, !callIDs.isEmpty {
        adoptConfirmedCall(callIDs, calendarEventIDs: calendarEventIDs)
      }
      if isMeetingConfirmed, confirmedCalendarIDs.isEmpty { confirmedCalendarIDs = calendarEventIDs }
      if isMeetingConfirmed, callTracker.observe(callIDs, at: now()) {
        adoptConfirmedCall(callIDs, calendarEventIDs: calendarEventIDs)
        log("MeetingDetector: call CHANGED (now \(callIDs.sorted().joined(separator: ",")))")
        hasPendingCallChange = true
        confirmedSince = now()
        noticeRequested = false
        noticePresented = false
        onCallChanged()
      }
      deliverNoteTakingNoticeIfReady()
    } else if isMeetingActive {
      pendingOnSince = nil
      // Meeting undetected while active: arm or honor the off grace period.
      if isMeetingConfirmed { callTracker.noteMicrophoneGap(at: now()) }
      if let deadline = pendingOffDeadline {
        if now() >= deadline {
          pendingOffDeadline = nil
          if isMeetingConfirmed { resumeOffAt = now() }
          setActive(false)
        }
      } else {
        pendingOffDeadline = now().addingTimeInterval(offGracePeriod)
      }
    } else {
      // Already inactive and still no meeting.
      pendingOffDeadline = nil
      pendingOnSince = nil
    }

    if !hadObservedState {
      onInitialStateObserved()
    }
  }

  private func setActive(_ active: Bool) {
    guard active != isMeetingActive else { return }
    isMeetingActive = active
    if !active {
      pendingOnSince = nil
      // A committed notice remains owed while this confirmed session can resume.
      // Already delivered notices stay disarmed, and inactive capture cannot present one.
      if !isMeetingConfirmed {
        confirmedSince = nil
        noticeRequested = false
        noticePresented = false
      }
      callTracker.reset()
      hasPendingCallChange = false
    }
    log(
      "MeetingDetector: meeting \(active ? "STARTED" : "ENDED")\(active ? "" : " lastPositive=\(lastPositiveEvidenceDescription) resumePending=\(resumeOffAt != nil)")"
    )
    onChange(active)
  }

  private func adoptConfirmedCall(_ callIDs: Set<String>, calendarEventIDs: Set<String>) {
    confirmedCallIDs = callIDs
    confirmedCalendarIDs = calendarEventIDs
    confirmedApps = Set(
      callIDs.compactMap { id in
        guard id.hasPrefix("app:"), let bundle = id.dropFirst(4).split(separator: "#").first else { return nil }
        return String(bundle)
      })
  }

  private func endConfirmedMeeting(at offAt: Date) {
    resumeOffAt = nil
    lastMeetingEndedAt = offAt
    isMeetingConfirmed = false
    confirmedSince = nil
    noticeRequested = false
    noticePresented = false
    confirmedApps = []
    confirmedCallIDs = []
    confirmedCalendarIDs = []
    callTracker.reset()
    hasPendingCallChange = false
    onConfirmedChange(false)
  }

  /// Called only after a successful rotation. A late commit can owe a notice during
  /// a resume hold, but retired meetings cannot arm one and inactive capture cannot show it.
  func requestNoteTakingNotice() {
    guard isMeetingConfirmed, !noticePresented, isMeetingActive || resumeOffAt != nil else { return }
    noticeRequested = true
    deliverNoteTakingNoticeIfReady()
  }

  private func deliverNoteTakingNoticeIfReady() {
    guard noticeRequested, !noticePresented, isMeetingConfirmed, isMeetingActive, pendingOffDeadline == nil,
      let since = confirmedSince, now().timeIntervalSince(since) >= noticeDelay
    else { return }
    noticeRequested = false
    noticePresented = true
    onNoteTakingNoticeReady()
  }

  func clearPendingCallChange() { hasPendingCallChange = false }
  func restorePendingCallChange() { hasPendingCallChange = true }

  #if DEBUG
    var currentCalendarTaskForTesting: Task<Void, Never>? { calendarTask }
    var calendarEventIDsForTesting: Set<String> { latestCalendarEventIDs }

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
/// used to land in one conversation. Identities from one `CallAudioSnapshot` separate them:
/// `meet:<code>` for a Google Meet window, `app:<bundle>` for a native call app, and
/// `app:<bundle>#<n>` when `CallAppReleasePolicy` says a mic release ends that app's call.
/// A call counts as new when an identity not seen earlier in this meeting stays
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
