import AppKit
import CoreAudio
import Foundation

/// Compares HAL metadata only. The private system-audio aggregate is ours and
/// may disappear asynchronously after stopTranscription returns.
@MainActor
struct ArmedChangeSignalGate {
  struct InputSnapshot: Equatable {
    let deviceIDs: Set<AudioDeviceID>
    let defaultInputID: AudioDeviceID?

    static func currentInputs(
      _ devices: [AudioCaptureService.InputDevice], defaultInputID: AudioDeviceID?
    ) -> Self {
      let inputs = devices.filter { !$0.uid.hasPrefix("omi.systemaudio.") }
      let inputIDs = Set(inputs.map(\.id))
      return Self(
        deviceIDs: inputIDs,
        defaultInputID: defaultInputID.flatMap { inputIDs.contains($0) ? $0 : nil })
    }
  }
  struct DisplaySnapshot: Equatable {
    let asleepByID: [CGDirectDisplayID: Bool]
  }
  enum Decision: Equatable { case changed, unchanged, settling }

  static let settleInterval: TimeInterval = 2
  var inputSnapshot: @MainActor () -> InputSnapshot?
  var displaySnapshot: @MainActor () -> DisplaySnapshot?
  var now: @MainActor () -> Date
  private var baselineInput: InputSnapshot?
  private var baselineDisplay: DisplaySnapshot?
  private var settleUntil: Date?

  init(
    inputSnapshot: @escaping @MainActor () -> InputSnapshot? = Self.currentInput,
    displaySnapshot: @escaping @MainActor () -> DisplaySnapshot? = Self.currentDisplay,
    now: @escaping @MainActor () -> Date = Date.init
  ) {
    self.inputSnapshot = inputSnapshot
    self.displaySnapshot = displaySnapshot
    self.now = now
  }

  mutating func begin() {
    baselineInput = inputSnapshot()
    baselineDisplay = displaySnapshot()
    settleUntil = now().addingTimeInterval(Self.settleInterval)
  }

  mutating func evaluate(_ signal: ArmedCaptureRecoveryPolicy.Signal) -> Decision {
    if let settleUntil, now() < settleUntil { return .settling }
    switch signal {
    case .inputChanged:
      guard let current = inputSnapshot(), let previous = baselineInput else { return .unchanged }
      guard current != previous else { return .unchanged }
      baselineInput = current
      return .changed
    case .displayChanged:
      guard let current = displaySnapshot(), let previous = baselineDisplay else { return .unchanged }
      guard current != previous else { return .unchanged }
      baselineDisplay = current
      return .changed
    default: return .unchanged
    }
  }

  private static func currentInput() -> InputSnapshot? {
    // The private aggregate has an Omi-owned UID; exclude it even if the
    // background HAL teardown has not finished when waiting starts. Resolve
    // the default through the same filtered list so its removal cannot look
    // like a real user input change either.
    InputSnapshot.currentInputs(
      AudioCaptureService.availableInputDevices(),
      defaultInputID: AudioCaptureService.currentDefaultInputDeviceID())
  }

  private static func currentDisplay() -> DisplaySnapshot? {
    var displays = [CGDirectDisplayID](repeating: 0, count: 16)
    var count: UInt32 = 0
    guard CGGetOnlineDisplayList(UInt32(displays.count), &displays, &count) == .success else { return nil }
    var states: [CGDirectDisplayID: Bool] = [:]
    for id in displays.prefix(Int(count)) { states[id] = CGDisplayIsAsleep(id) != 0 }
    return DisplaySnapshot(asleepByID: states)
  }
}

/// The cloud mixer runs off the main actor. A probe cannot send any mixed
/// system audio to paid STT until the microphone itself proves live.
final class CaptureProbeAudioGate: @unchecked Sendable {
  private let lock = NSLock()
  private var open = true

  var isOpen: Bool { lock.withLock { open } }
  func setOpen(_ value: Bool) { lock.withLock { open = value } }

  func forward(_ audio: Data, to sink: (Data) -> Void) {
    guard isOpen else { return }
    sink(audio)
  }
}

/// Owns only a waiting timer and change listeners. AppState owns capture teardown
/// and the ordinary short probe. In waiting, there is no CoreAudio IO or STT.
@MainActor
final class ArmedMicrophoneRecoveryCoordinator {
  private(set) var policy = ArmedCaptureRecoveryPolicy()
  private var timer: Task<Void, Never>?
  private var milestoneTasks: [Task<Void, Never>] = []
  private var observers: [(NotificationCenter, NSObjectProtocol)] = []
  private var deviceListener: AudioObjectPropertyListenerBlock?
  private var defaultListener: AudioObjectPropertyListenerBlock?
  private var settleRecheck: Task<Void, Never>?
  private var changeGate: ArmedChangeSignalGate
  private weak var appState: AppState?
  private(set) var trigger = "initial"
  private(set) var episodeID = UUID().uuidString.lowercased()
  private var episodeLaunchContext = "other"
  private var episodeUpdateAttemptID: String?
  private var lastInputIsBuiltIn: Bool?
  private var lifecycleEventPolicy = ArmedLifecycleEventPolicy()
  let outboundAudioGate = CaptureProbeAudioGate()

  init(changeGate: ArmedChangeSignalGate = ArmedChangeSignalGate()) {
    self.changeGate = changeGate
  }

  var isWaitingOrProbing: Bool { policy.state != .idle }
  var isProbing: Bool { policy.state == .probing }
  var episodeContext: CaptureLaunchContext.Kind {
    CaptureLaunchContext.Kind(rawValue: episodeLaunchContext) ?? .other
  }

  func enter(
    appState: AppState, launchContext: String? = nil, updateAttemptID: String? = nil,
    inputIsBuiltIn: Bool? = nil
  ) {
    // Enter only after stopTranscription's local tail flush has finished.
    guard
      ArmedCaptureRecoveryPolicy.canEnterWaiting(
        captureActive: appState.isTranscribing || appState.audioCaptureService != nil
          || appState.systemAudioCaptureService != nil,
        sttActive: appState.transcriptionService != nil || appState.localMicService != nil
          || appState.localSystemService != nil)
    else {
      log("Transcription: refused armed-waiting entry while capture resources are still open")
      return
    }
    self.appState = appState
    lastInputIsBuiltIn = inputIsBuiltIn
    let wasIdle = policy.state == .idle
    let action = policy.enter(now: Date())
    if wasIdle && !policy.continuedEpisode {
      cancelMilestones()
      episodeID = UUID().uuidString.lowercased()
      trigger = "initial"
      episodeLaunchContext = launchContext ?? CaptureLaunchContext.kindForStart().rawValue
      episodeUpdateAttemptID =
        updateAttemptID
        ?? (episodeLaunchContext == CaptureLaunchContext.Kind.updateRelaunch.rawValue
          ? CaptureLaunchContext.updateAttemptID : nil)
      lifecycleEventPolicy.beginEpisode()
      scheduleMilestones()
    }
    appState.isWaitingForMicrophone = true
    outboundAudioGate.setOpen(false)
    changeGate.begin()
    installObservers()
    schedule(action)
    emitLifecycle(phase: "entered", trigger: trigger, duration: "0_10s")
  }

  func signal(_ signal: ArmedCaptureRecoveryPolicy.Signal) {
    guard policy.state == .waiting else { return }
    if signal == .inputChanged { lastInputIsBuiltIn = nil }
    let presence = CapturePresence.current()
    let inputIsBuiltIn =
      presence.lidClosed == true
      ? lastInputIsBuiltIn ?? CaptureInputPresence.builtInForNextProbe() : nil
    let action = policy.signal(signal, now: Date(), presence: presence, inputIsBuiltIn: inputIsBuiltIn)
    if case .retrySkipped(let reason, _) = action {
      emitLifecycle(
        phase: "retry_skipped", trigger: signal.rawValue,
        duration: CaptureLaunchContext.timeBucket(policy.enteredAt.map { Date().timeIntervalSince($0) }),
        presenceReason: reason.rawValue, presenceReasonValue: reason)
      schedule(action)
      return
    }
    guard action == .probe else { return }
    settleRecheck?.cancel()
    settleRecheck = nil
    lifecycleEventPolicy.presenceReturned()
    trigger = signal.rawValue
    timer?.cancel()
    timer = nil
    outboundAudioGate.setOpen(false)
    emitLifecycle(
      phase: "retry", trigger: trigger,
      duration: CaptureLaunchContext.timeBucket(policy.enteredAt.map { Date().timeIntervalSince($0) }))
    guard policy.state == .probing, let appState else { return }
    guard AssistantSettings.shared.audioRecordingMode != .off else {
      cancel()
      return
    }
    appState.startTranscription(userInitiated: false, armedRetry: true)
    if !appState.isTranscribing && isProbing {
      appState.recordSilentMicDiagnostic(
        detection: nil, phase: "armed_retry", result: "start_abandoned")
      cancel()
    }
  }

  func recovered() {
    guard let duration = policy.succeeded(now: Date()) else { return }
    outboundAudioGate.setOpen(true)
    appState?.recordSilentMicDiagnostic(detection: nil, phase: "armed_retry", result: "live_signal")
    appState?.isWaitingForMicrophone = false
    emitLifecycle(
      phase: "recovered", trigger: trigger,
      duration: CaptureLaunchContext.timeBucket(duration))
    removeObservers()
    timer?.cancel()
    timer = nil
  }

  func cancel() {
    policy.reset()
    outboundAudioGate.setOpen(true)
    appState?.isWaitingForMicrophone = false
    removeObservers()
    timer?.cancel()
    timer = nil
    settleRecheck?.cancel()
    settleRecheck = nil
    cancelMilestones()
  }

  private func schedule(_ action: ArmedCaptureRecoveryPolicy.Action) {
    let deadline: Date
    switch action {
    case .releaseAndWait(let until), .retrySkipped(_, let until): deadline = until
    default: return
    }
    timer?.cancel()
    timer = Task { @MainActor [weak self] in
      let remaining = max(0, deadline.timeIntervalSinceNow)
      try? await Task.sleep(for: .seconds(remaining))
      guard !Task.isCancelled else { return }
      self?.signal(.backoff)
    }
  }

  private func scheduleMilestones() {
    for (seconds, phase) in [(3_600.0, "unrecovered_1h"), (86_400.0, "unrecovered_24h")] {
      milestoneTasks.append(
        Task { @MainActor [weak self] in
          try? await Task.sleep(for: .seconds(seconds))
          guard !Task.isCancelled, let self, self.policy.state != .idle else { return }
          self.emitLifecycle(
            phase: phase, trigger: self.trigger,
            duration: CaptureLaunchContext.timeBucket(seconds))
        })
    }
  }

  private func cancelMilestones() {
    for task in milestoneTasks { task.cancel() }
    milestoneTasks.removeAll()
  }

  private func observe(_ name: Notification.Name, center: NotificationCenter, signal: ArmedCaptureRecoveryPolicy.Signal)
  {
    let observer = center.addObserver(forName: name, object: nil, queue: .main) { [weak self] _ in
      Task { @MainActor in
        if signal == .displayChanged { self?.handleObservedChange(signal) } else { self?.signal(signal) }
      }
    }
    observers.append((center, observer))
  }

  private func installObservers() {
    guard observers.isEmpty else { return }
    observe(.screenDidUnlock, center: .default, signal: .unlock)
    observe(NSWorkspace.didWakeNotification, center: NSWorkspace.shared.notificationCenter, signal: .systemWake)
    observe(NSWorkspace.screensDidWakeNotification, center: NSWorkspace.shared.notificationCenter, signal: .screenWake)
    observe(
      NSWorkspace.sessionDidBecomeActiveNotification, center: NSWorkspace.shared.notificationCenter,
      signal: .sessionActive)
    observe(NSApplication.didBecomeActiveNotification, center: .default, signal: .appActive)
    observe(NSApplication.didChangeScreenParametersNotification, center: .default, signal: .displayChanged)

    let device: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
      Task { @MainActor in self?.handleObservedChange(.inputChanged) }
    }
    var devicesAddress = Self.address(kAudioHardwarePropertyDevices)
    if AudioObjectAddPropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &devicesAddress, .main, device)
      == noErr
    {
      deviceListener = device
    }
    let defaultInput: AudioObjectPropertyListenerBlock = { [weak self] _, _ in
      Task { @MainActor in self?.handleObservedChange(.inputChanged) }
    }
    var defaultAddress = Self.address(kAudioHardwarePropertyDefaultInputDevice)
    if AudioObjectAddPropertyListenerBlock(
      AudioObjectID(kAudioObjectSystemObject), &defaultAddress, .main, defaultInput) == noErr
    {
      defaultListener = defaultInput
    }
  }

  private func removeObservers() {
    settleRecheck?.cancel()
    settleRecheck = nil
    for (center, observer) in observers { center.removeObserver(observer) }
    observers.removeAll()
    if let deviceListener {
      var address = Self.address(kAudioHardwarePropertyDevices)
      AudioObjectRemovePropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address, .main, deviceListener)
      self.deviceListener = nil
    }
    if let defaultListener {
      var address = Self.address(kAudioHardwarePropertyDefaultInputDevice)
      AudioObjectRemovePropertyListenerBlock(AudioObjectID(kAudioObjectSystemObject), &address, .main, defaultListener)
      self.defaultListener = nil
    }
  }

  private func handleObservedChange(_ signal: ArmedCaptureRecoveryPolicy.Signal) {
    guard policy.state == .waiting else { return }
    switch changeGate.evaluate(signal) {
    case .changed: self.signal(signal)
    case .unchanged:
      emitLifecycle(
        phase: "suppressed_signal", trigger: signal.rawValue,
        duration: CaptureLaunchContext.timeBucket(policy.enteredAt.map { Date().timeIntervalSince($0) }))
    case .settling:
      emitLifecycle(
        phase: "suppressed_signal", trigger: signal.rawValue,
        duration: CaptureLaunchContext.timeBucket(policy.enteredAt.map { Date().timeIntervalSince($0) }))
      guard settleRecheck == nil else { return }
      settleRecheck = Task { @MainActor [weak self] in
        try? await Task.sleep(for: .seconds(ArmedChangeSignalGate.settleInterval))
        guard !Task.isCancelled else { return }
        self?.settleRecheck = nil
        self?.handleObservedChange(.inputChanged)
        self?.handleObservedChange(.displayChanged)
      }
    }
  }

  private nonisolated static func address(_ selector: AudioObjectPropertySelector) -> AudioObjectPropertyAddress {
    AudioObjectPropertyAddress(
      mSelector: selector, mScope: kAudioObjectPropertyScopeGlobal,
      mElement: kAudioObjectPropertyElementMain)
  }

  private func emitLifecycle(
    phase: String, trigger: String, duration: String, presenceReason: String? = nil,
    presenceReasonValue: ArmedCaptureRecoveryPolicy.PresenceReason? = nil
  ) {
    let now = Date()
    guard
      lifecycleEventPolicy.shouldEmit(
        phase: phase, presenceReason: presenceReasonValue, now: now)
    else { return }
    let properties = SilentMicDiagnosticTelemetry.armedProperties(
      attemptID: episodeID, phase: phase, trigger: trigger,
      launchContext: episodeLaunchContext,
      updateAttemptID: episodeUpdateAttemptID, duration: duration, presenceReason: presenceReason,
      flapCount: policy.flapCount, continuedEpisode: policy.continuedEpisode)
    PostHogManager.shared.track(SilentMicDiagnosticTelemetry.armedEventName, properties: properties)
  }
}
