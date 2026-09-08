import Carbon.HIToolbox.Events
import Cocoa

// MARK: - Global Shortcut Manager

/// Manages global keyboard shortcuts using Carbon APIs for the floating control bar.
class GlobalShortcutManager: @unchecked Sendable {
  static let shared = GlobalShortcutManager()

  static let askAINotification = Notification.Name("com.omi.desktop.askAI")

  private var hotKeyRefs: [HotKeyID: HotKeyReference] = [:]
  private var isRegistrationSuspended = false
  #if DEBUG
    private var askOmiRegistrationTrace: [HotKeyRegistrationOutcome] = []
  #endif
  typealias HotKeyRegistrar = (Int, Int) -> HotKeyRegistrationAttempt
  typealias HotKeyFailureRecorder = (Int, Int, Int, HotKeyRegistrationOutcome) -> Void
  typealias HotKeyLogger = (String) -> Void

  #if DEBUG
    /// A test-owned stand-in for Carbon's opaque `EventHotKeyRef`.
    struct TestHotKeyReference: Hashable {
      let value: String

      init(_ value: String) {
        self.value = value
      }
    }

    typealias TestHotKeyUnregisterer = (TestHotKeyReference) -> OSStatus
  #endif

  fileprivate enum HotKeyReference {
    case carbon(EventHotKeyRef)
    #if DEBUG
      case testing(TestHotKeyReference)
    #endif
  }

  /// The Carbon result pair that determines whether a hotkey is live. The real
  /// registrar supplies its returned ref; DEBUG tests use an owned token that
  /// travels through the same retention and unregister lifecycle.
  struct HotKeyRegistrationAttempt {
    let status: OSStatus
    fileprivate let reference: HotKeyReference?

    init(status: OSStatus, hotKeyRef: EventHotKeyRef?) {
      self.status = status
      reference = hotKeyRef.map(HotKeyReference.carbon)
    }

    #if DEBUG
      static func testing(status: OSStatus, reference: TestHotKeyReference?) -> Self {
        Self(status: status, reference: reference.map(HotKeyReference.testing))
      }

      private init(status: OSStatus, reference: HotKeyReference?) {
        self.status = status
        self.reference = reference
      }
    #endif

    var hasReference: Bool {
      reference != nil
    }
  }

  private let registrar: HotKeyRegistrar
  #if DEBUG
    private let testUnregisterer: TestHotKeyUnregisterer?
  #endif
  private let failureRecorder: HotKeyFailureRecorder
  private let logger: HotKeyLogger

  private enum HotKeyID: UInt32 {
    case askOmi = 2
    case summonOmi = 3
  }

  private var shortcutObserver: NSObjectProtocol?

  private init() {
    registrar = Self.registerWithCarbon
    #if DEBUG
      testUnregisterer = nil
    #endif
    failureRecorder = Self.recordRegistrationFailure
    logger = { message in NSLog("%@", message) }

    var eventType = EventTypeSpec(
      eventClass: OSType(kEventClassKeyboard),
      eventKind: OSType(kEventHotKeyPressed)
    )
    InstallEventHandler(
      GetApplicationEventTarget(),
      { (_, event, _) -> OSStatus in
        return GlobalShortcutManager.shared.handleHotKeyEvent(event!)
      },
      1, &eventType, nil, nil
    )

    observeSettings()
  }

  #if DEBUG
    init(
      registrar: @escaping HotKeyRegistrar,
      testUnregisterer: TestHotKeyUnregisterer? = nil,
      failureRecorder: HotKeyFailureRecorder? = nil,
      logger: @escaping HotKeyLogger,
      observesSettings: Bool
    ) {
      self.registrar = registrar
      self.testUnregisterer = testUnregisterer
      self.failureRecorder = failureRecorder ?? Self.recordRegistrationFailure
      self.logger = logger
      if observesSettings {
        observeSettings()
      }
    }
  #endif

  private func observeSettings() {
    // Re-register Ask Omi shortcut when user changes it in settings.
    shortcutObserver = NotificationCenter.default.addObserver(
      forName: ShortcutSettings.askOmiShortcutChanged,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      self?.registerAskOmi()
    }
  }

  #if DEBUG
    func stopObservingSettingsForTests() {
      if let shortcutObserver {
        NotificationCenter.default.removeObserver(shortcutObserver)
        self.shortcutObserver = nil
      }
    }
  #endif

  func registerShortcuts() {
    unregisterShortcuts()
    guard !isRegistrationSuspended else { return }
    // Register Ask Omi shortcut from user settings
    registerAskOmi()
    registerSummonHotkey()
  }

  /// Registers ⌃⌘O as a dedicated global Carbon hotkey that summons Omi (fronts the
  /// app + opens chat), independent of the user-configurable Ask-Omi shortcut. A
  /// Carbon hotkey fires system-wide without any extra permission.
  ///
  /// ⌃⌘O is chosen because it collides with nothing. Note what the collision *is*: a Carbon hotkey
  /// is not swallowed by the frontmost app's menu, it preempts it. Measured — a probe holding a
  /// Carbon ⌘O fired while another app was frontmost, and that app's own key-down monitor never
  /// received the event. So a chord registered here is taken away from every other app on the Mac
  /// for as long as Omi runs, which is exactly why ⌘O (File ▸ Open everywhere) is a poor default and
  /// why any Option-based combo is worse still (Option held = push-to-talk).
  private func registerSummonHotkey() {
    // The Ask-Omi shortcut is registered first and may be this same chord — onboarding offers ⌃⌘O.
    // Both ids run `openOmiFromShortcut`, so the second registration would add nothing and fail with
    // `eventHotKeyExistsErr`, reporting a hard hotkey-registration incident for a chord that is
    // working perfectly.
    if let ref = hotKeyRefs.removeValue(forKey: .summonOmi) {
      _ = unregisterHotKey(ref)
    }
    var hotKeyRef: EventHotKeyRef?
    let hotKeyID = EventHotKeyID(signature: FourCharCode(0x4F4D_4921), id: HotKeyID.summonOmi.rawValue)  // "OMI!"
    let status = RegisterEventHotKey(
      UInt32(kVK_ANSI_O), UInt32(controlKey | cmdKey), hotKeyID,
      GetApplicationEventTarget(), 0, &hotKeyRef
    )
    if status == noErr, let hotKeyRef {
      hotKeyRefs[.summonOmi] = .carbon(hotKeyRef)
      logger("GlobalShortcutManager: Registered ⌃⌘O Omi summon hotkey")
    } else {
      logger("GlobalShortcutManager: Failed to register ⌃⌘O hotkey, error: \(status)")
    }
  }

  /// The chord `registerSummonHotkey` holds unconditionally, expressed once so the Ask-Omi path can
  /// recognise it rather than restating ⌃⌘O in a second place that could drift.
  @MainActor
  static var summonShortcut: ShortcutSettings.KeyboardShortcut { ShortcutSettings.askOmiControlCommandOShortcut }

  func setRegistrationSuspended(_ suspended: Bool) {
    isRegistrationSuspended = suspended
    if suspended {
      unregisterShortcuts()
    } else {
      registerShortcuts()
    }
  }

  @discardableResult
  func registerAskOmi() -> HotKeyRegistrationOutcome? {
    guard !isRegistrationSuspended else { return nil }
    // Unregister previous Ask Omi hotkey if any
    if let ref = hotKeyRefs.removeValue(forKey: .askOmi) {
      _ = unregisterHotKey(ref)
    }
    let (askOmiEnabled, askOmiShortcut, isSummonChord) = MainActor.assumeIsolated {
      (
        ShortcutSettings.shared.askOmiEnabled, ShortcutSettings.shared.askOmiShortcut,
        ShortcutSettings.shared.askOmiShortcut == Self.summonShortcut
      )
    }
    guard askOmiEnabled else {
      logger("GlobalShortcutManager: Ask Omi shortcut is disabled")
      return nil
    }
    guard askOmiShortcut.supportsGlobalHotKey, let keyCode = askOmiShortcut.keyCode else {
      logger("GlobalShortcutManager: Ask Omi shortcut is not a registerable hotkey")
      return .otherFailure
    }
    // Onboarding now offers ⌃⌘O — the chord `registerSummonHotkey` already holds unconditionally,
    // routed to the same `openOmiFromShortcut`. Registering it twice cannot add behaviour, and the
    // second attempt fails with `eventHotKeyExistsErr`, which `registerHotKey` reports as a hard
    // hotkey-registration incident for a chord that is working perfectly.
    guard !isSummonChord else {
      logger("GlobalShortcutManager: Ask Omi shortcut is the summon hotkey; already registered")
      return .registered
    }
    let outcome = registerHotKey(keyCode: Int(keyCode), modifiers: askOmiShortcut.carbonModifiers, id: .askOmi)
    // Gate the success log on the registration outcome. Previously this logged
    // "Registered" unconditionally — even when Carbon had rejected the combo
    // (e.g. another app owns it) — which made the silent failure actively misleading.
    if outcome == .registered {
      logger("GlobalShortcutManager: Registered Ask Omi shortcut: \(askOmiShortcut.displayLabel)")
    }
    return outcome
  }

  /// Probe the selected Ask Omi chord while onboarding's local event monitor is armed. The monitor
  /// intentionally suspends Carbon registration so it can observe the test press; this narrow probe
  /// temporarily re-enables registration and then removes the probe before the stage advances. A
  /// conflict therefore keeps onboarding active instead of claiming a shortcut that will not work
  /// after the user finishes setup.
  func validateAskOmiShortcutForOnboarding() -> HotKeyRegistrationOutcome {
    let wasSuspended = isRegistrationSuspended
    if wasSuspended {
      isRegistrationSuspended = false
      unregisterShortcuts()
    }
    let outcome = registerAskOmi() ?? .otherFailure
    if wasSuspended {
      unregisterShortcuts()
      isRegistrationSuspended = true
    }
    return outcome
  }

  /// Outcome of a Carbon `RegisterEventHotKey` attempt, classified for telemetry.
  enum HotKeyRegistrationOutcome: Equatable {
    case registered
    case alreadyInUse
    case otherFailure
  }

  private func registerHotKey(keyCode: Int, modifiers: Int, id: HotKeyID) -> HotKeyRegistrationOutcome {
    let attempt = registrar(keyCode, modifiers)
    let outcome = registrationOutcome(for: attempt)
    #if DEBUG
      if id == .askOmi {
        askOmiRegistrationTrace.append(outcome)
      }
    #endif
    if outcome == .registered {
      if let ref = attempt.reference {
        hotKeyRefs[id] = ref
      }
    } else {
      // The shortcut will not fire on this machine. Keep the local NSLog for
      // debugging and surface the failure to ops/Sentry via the incident path
      // (NOT recordFallback — this is a hard-terminal failure with no mode switch).
      // User-visible conflict surfacing in shortcut settings is tracked separately.
      logger("GlobalShortcutManager: Failed to register hotkey (keycode \(keyCode)), error: \(attempt.status)")
      failureRecorder(Int(attempt.status), keyCode, modifiers, outcome)
    }
    return outcome
  }

  private static func registerWithCarbon(keyCode: Int, modifiers: Int) -> HotKeyRegistrationAttempt {
    var hotKeyRef: EventHotKeyRef?
    let hotKeyID = EventHotKeyID(signature: FourCharCode(0x4F4D_4921), id: HotKeyID.askOmi.rawValue)  // "OMI!"
    let status = RegisterEventHotKey(
      UInt32(keyCode), UInt32(modifiers), hotKeyID,
      GetApplicationEventTarget(), 0, &hotKeyRef
    )
    return HotKeyRegistrationAttempt(status: status, hotKeyRef: hotKeyRef)
  }

  private static func recordRegistrationFailure(
    osStatus: Int,
    keyCode: Int,
    modifiers: Int,
    outcome: HotKeyRegistrationOutcome
  ) {
    DesktopDiagnosticsManager.shared.recordHotkeyRegistrationFailed(
      osStatus: osStatus,
      keycode: keyCode,
      modifiers: modifiers,
      isConflict: outcome == .alreadyInUse)
  }

  private func registrationOutcome(for attempt: HotKeyRegistrationAttempt) -> HotKeyRegistrationOutcome {
    if attempt.status == noErr, attempt.hasReference { return .registered }
    if Int(attempt.status) == eventHotKeyExistsErr { return .alreadyInUse }
    return .otherFailure
  }

  private func unregisterHotKey(_ reference: HotKeyReference) -> OSStatus {
    switch reference {
    case .carbon(let reference):
      return UnregisterEventHotKey(reference)
    #if DEBUG
      case .testing(let reference):
        return testUnregisterer?(reference) ?? noErr
    #endif
    }
  }

  #if DEBUG
    func retainedTestHotKeyReferences() -> [TestHotKeyReference] {
      hotKeyRefs.values.compactMap { reference in
        guard case .testing(let reference) = reference else { return nil }
        return reference
      }
    }

    func resetAskOmiRegistrationTraceForAutomation() {
      askOmiRegistrationTrace.removeAll()
    }

    func askOmiRegistrationTraceForAutomation() -> [HotKeyRegistrationOutcome] {
      askOmiRegistrationTrace
    }
  #endif

  private func handleHotKeyEvent(_ event: EventRef) -> OSStatus {
    var hotKeyID = EventHotKeyID()
    let status = GetEventParameter(
      event,
      OSType(kEventParamDirectObject),
      OSType(typeEventHotKeyID),
      nil,
      MemoryLayout<EventHotKeyID>.size,
      nil,
      &hotKeyID
    )

    guard status == noErr, let id = HotKeyID(rawValue: hotKeyID.id) else {
      return status
    }

    switch id {
    case .askOmi, .summonOmi:
      openOmiFromShortcut()
    }

    return noErr
  }

  private func openOmiFromShortcut() {
    NSLog("GlobalShortcutManager: Open Omi shortcut detected")
    DispatchQueue.main.async {
      // Typing moved to the main app: when hidden, the shortcut opens Omi itself
      // instead of the floating bar's typed input panel — and lands straight in
      // the chat surface (the one continuous thread), not the resting hero. When
      // the shell is already visible, the same shortcut dismisses it instead.
      guard let appDelegate = AppDelegate.summonWindowTarget() else { return }
      if appDelegate.toggleMainAppWindow() == .summon {
        NotificationCenter.default.post(name: .navigateToChat, object: nil)
      }
    }
  }

  #if DEBUG
    /// Drives the same dispatched Open Omi action as a registered Carbon event.
    func triggerOpenOmiShortcutForAutomation() {
      openOmiFromShortcut()
    }
  #endif

  func unregisterShortcuts() {
    for (_, ref) in hotKeyRefs {
      _ = unregisterHotKey(ref)
    }
    hotKeyRefs.removeAll()
  }
}
