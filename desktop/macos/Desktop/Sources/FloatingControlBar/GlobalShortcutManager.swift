import Carbon.HIToolbox.Events
import Cocoa

// MARK: - Global Shortcut Manager

/// Manages global keyboard shortcuts using Carbon APIs for the floating control bar.
class GlobalShortcutManager: @unchecked Sendable {
  static let shared = GlobalShortcutManager()

  static let askAINotification = Notification.Name("com.omi.desktop.askAI")

  private var hotKeyRefs: [HotKeyID: HotKeyReference] = [:]
  private var isRegistrationSuspended = false
  /// Session event tap that intercepts ⌘O before the frontmost app's menu can
  /// swallow it (⌘O is File ▸ Open everywhere, so a Carbon global hotkey registers
  /// but never fires). See `installCommandOEventTap()`.
  private var commandOEventTap: CFMachPort?
  private var commandORunLoopSource: CFRunLoopSource?
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
    case commandO = 3
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
    registerCommandO()
    installCommandOEventTap()
  }

  // MARK: - ⌘O session event tap

  /// ⌘O is a universal menu key-equivalent (File ▸ Open), so the frontmost app's
  /// menu swallows the key before Omi's Carbon global hotkey ever sees it — every
  /// OTHER Omi hotkey fires, only ⌘O doesn't. Intercept it at the session
  /// event-tap level, which sees the key before any app dispatches it, and consume
  /// it so ⌘O reliably summons Omi and nothing else "Opens". Needs Accessibility;
  /// when it isn't granted we silently keep the (best-effort) Carbon hotkey.
  private func installCommandOEventTap() {
    removeCommandOEventTap()
    guard AXIsProcessTrusted() else {
      logger("GlobalShortcutManager: ⌘O event tap needs Accessibility — keeping Carbon fallback")
      return
    }
    let mask =
      (1 << CGEventType.keyDown.rawValue)
      | (1 << CGEventType.tapDisabledByTimeout.rawValue)
      | (1 << CGEventType.tapDisabledByUserInput.rawValue)
    let callback: CGEventTapCallBack = { _, type, event, _ in
      let manager = GlobalShortcutManager.shared
      // The system disables a tap if a callback is slow or on fast user input;
      // re-enable so ⌘O keeps working for the rest of the session.
      if type == .tapDisabledByTimeout || type == .tapDisabledByUserInput {
        if let tap = manager.commandOEventTap { CGEvent.tapEnable(tap: tap, enable: true) }
        return Unmanaged.passUnretained(event)
      }
      if type == .keyDown {
        let keyCode = event.getIntegerValueField(.keyboardEventKeycode)
        let f = event.flags
        // Match ⌘O exactly — command down, none of the other chord modifiers — so
        // ⌘⇧O / ⌃⌘O etc. still pass through to the focused app untouched.
        let isCommandOnly =
          f.contains(.maskCommand) && !f.contains(.maskControl)
          && !f.contains(.maskAlternate) && !f.contains(.maskShift)
        if keyCode == Int64(kVK_ANSI_O), isCommandOnly {
          manager.triggerCommandOSummon()
          return nil  // consume — the frontmost app never sees ⌘O
        }
      }
      return Unmanaged.passUnretained(event)
    }
    guard
      let tap = CGEvent.tapCreate(
        tap: .cgSessionEventTap, place: .headInsertEventTap, options: .defaultTap,
        eventsOfInterest: CGEventMask(mask), callback: callback, userInfo: nil)
    else {
      logger("GlobalShortcutManager: failed to create ⌘O event tap")
      return
    }
    let source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, tap, 0)
    CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
    CGEvent.tapEnable(tap: tap, enable: true)
    commandOEventTap = tap
    commandORunLoopSource = source
    logger("GlobalShortcutManager: Installed ⌘O event tap")
  }

  private func removeCommandOEventTap() {
    if let source = commandORunLoopSource {
      CFRunLoopRemoveSource(CFRunLoopGetMain(), source, .commonModes)
      commandORunLoopSource = nil
    }
    if let tap = commandOEventTap {
      CGEvent.tapEnable(tap: tap, enable: false)
      commandOEventTap = nil
    }
  }

  /// Bridges the ⌘O event tap's C callback to the summon action (fronts Omi +
  /// opens chat). Runs on the main run loop; `openOmiFromShortcut` hops to main.
  func triggerCommandOSummon() {
    openOmiFromShortcut()
  }

  /// Registers ⌘O as a dedicated global Carbon hotkey that summons Omi (fronts
  /// the app + opens chat). A Carbon hotkey fires system-wide without the
  /// Accessibility/Input-Monitoring permission an NSEvent monitor needs, and it
  /// consumes the key so it reliably reaches Omi. This is separate from the
  /// user-configurable Ask-Omi shortcut (⌃⌥O by default) — ⌘O always works.
  private func registerCommandO() {
    if let ref = hotKeyRefs.removeValue(forKey: .commandO) {
      _ = unregisterHotKey(ref)
    }
    var hotKeyRef: EventHotKeyRef?
    let hotKeyID = EventHotKeyID(signature: FourCharCode(0x4F4D_4921), id: HotKeyID.commandO.rawValue)  // "OMI!"
    let status = RegisterEventHotKey(
      UInt32(kVK_ANSI_O), UInt32(cmdKey), hotKeyID,
      GetApplicationEventTarget(), 0, &hotKeyRef
    )
    if status == noErr, let hotKeyRef {
      hotKeyRefs[.commandO] = .carbon(hotKeyRef)
      logger("GlobalShortcutManager: Registered ⌘O Omi summon hotkey")
    } else {
      logger("GlobalShortcutManager: Failed to register ⌘O hotkey, error: \(status)")
    }
  }

  func setRegistrationSuspended(_ suspended: Bool) {
    isRegistrationSuspended = suspended
    if suspended {
      unregisterShortcuts()
    } else {
      registerShortcuts()
    }
  }

  func registerAskOmi() {
    guard !isRegistrationSuspended else { return }
    // Unregister previous Ask Omi hotkey if any
    if let ref = hotKeyRefs.removeValue(forKey: .askOmi) {
      _ = unregisterHotKey(ref)
    }
    let (askOmiEnabled, askOmiShortcut) = MainActor.assumeIsolated {
      (ShortcutSettings.shared.askOmiEnabled, ShortcutSettings.shared.askOmiShortcut)
    }
    guard askOmiEnabled else {
      logger("GlobalShortcutManager: Ask Omi shortcut is disabled")
      return
    }
    guard askOmiShortcut.supportsGlobalHotKey, let keyCode = askOmiShortcut.keyCode else {
      logger("GlobalShortcutManager: Ask Omi shortcut is not a registerable hotkey")
      return
    }
    let outcome = registerHotKey(keyCode: Int(keyCode), modifiers: askOmiShortcut.carbonModifiers, id: .askOmi)
    // Gate the success log on the registration outcome. Previously this logged
    // "Registered" unconditionally — even when Carbon had rejected the combo
    // (e.g. another app owns it) — which made the silent failure actively misleading.
    if outcome == .registered {
      logger("GlobalShortcutManager: Registered Ask Omi shortcut: \(askOmiShortcut.displayLabel)")
    }
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
    case .askOmi, .commandO:
      openOmiFromShortcut()
    }

    return noErr
  }

  private func openOmiFromShortcut() {
    NSLog("GlobalShortcutManager: Open Omi shortcut detected")
    DispatchQueue.main.async {
      // Typing moved to the main app: the shortcut opens Omi itself
      // instead of the floating bar's typed input panel — and lands straight in
      // the chat surface (the one continuous thread), not the resting hero.
      (NSApp.delegate as? AppDelegate)?.openMainAppWindow()
      NotificationCenter.default.post(name: .navigateToChat, object: nil)
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
    removeCommandOEventTap()
  }
}
