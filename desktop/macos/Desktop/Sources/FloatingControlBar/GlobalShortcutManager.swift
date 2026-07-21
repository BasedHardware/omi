import Carbon.HIToolbox.Events
import Cocoa

// MARK: - Global Shortcut Manager

/// Manages global keyboard shortcuts using Carbon APIs for the floating control bar.
class GlobalShortcutManager: @unchecked Sendable {
  static let shared = GlobalShortcutManager()

  static let askAINotification = Notification.Name("com.omi.desktop.askAI")

  private var hotKeyRefs: [HotKeyID: EventHotKeyRef] = [:]
  private var isRegistrationSuspended = false
  typealias HotKeyRegistrar = (Int, Int) -> HotKeyRegistrationAttempt
  typealias HotKeyFailureRecorder = (Int, Int, Int, HotKeyRegistrationOutcome) -> Void
  typealias HotKeyLogger = (String) -> Void

  /// The Carbon result pair that determines whether a hotkey is live. The real
  /// registrar supplies its returned ref; DEBUG tests can model the presence of
  /// that opaque ref without manufacturing a Core Foundation object.
  struct HotKeyRegistrationAttempt {
    let status: OSStatus
    let hotKeyRef: EventHotKeyRef?

    #if DEBUG
      private let testReferenceWasReturned: Bool?
    #endif

    init(status: OSStatus, hotKeyRef: EventHotKeyRef?) {
      self.status = status
      self.hotKeyRef = hotKeyRef
      #if DEBUG
        self.testReferenceWasReturned = nil
      #endif
    }

    #if DEBUG
      static func testing(status: OSStatus, referenceWasReturned: Bool) -> Self {
        Self(status: status, hotKeyRef: nil, testReferenceWasReturned: referenceWasReturned)
      }

      private init(status: OSStatus, hotKeyRef: EventHotKeyRef?, testReferenceWasReturned: Bool) {
        self.status = status
        self.hotKeyRef = hotKeyRef
        self.testReferenceWasReturned = testReferenceWasReturned
      }
    #endif

    var hasReference: Bool {
      #if DEBUG
        return testReferenceWasReturned ?? (hotKeyRef != nil)
      #else
        return hotKeyRef != nil
      #endif
    }
  }

  private let registrar: HotKeyRegistrar
  private let unregisterer: (EventHotKeyRef) -> OSStatus
  private let failureRecorder: HotKeyFailureRecorder
  private let logger: HotKeyLogger

  private enum HotKeyID: UInt32 {
    case askOmi = 2
  }

  private var shortcutObserver: NSObjectProtocol?

  private init() {
    registrar = Self.registerWithCarbon
    unregisterer = UnregisterEventHotKey
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

  init(
    registrar: @escaping HotKeyRegistrar,
    unregisterer: @escaping (EventHotKeyRef) -> OSStatus,
    failureRecorder: HotKeyFailureRecorder? = nil,
    logger: @escaping HotKeyLogger,
    observesSettings: Bool
  ) {
    self.registrar = registrar
    self.unregisterer = unregisterer
    self.failureRecorder = failureRecorder ?? Self.recordRegistrationFailure
    self.logger = logger
    if observesSettings {
      observeSettings()
    }
  }

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
      _ = unregisterer(ref)
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
    if outcome == .registered {
      if let ref = attempt.hotKeyRef {
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
    case .askOmi:
      NSLog("GlobalShortcutManager: Open Omi shortcut detected")
      DispatchQueue.main.async {
        // Typing moved to the main app: the shortcut opens Omi itself
        // instead of the floating bar's typed input panel.
        (NSApp.delegate as? AppDelegate)?.openMainAppWindow()
      }
    }

    return noErr
  }

  func unregisterShortcuts() {
    for (_, ref) in hotKeyRefs {
      _ = unregisterer(ref)
    }
    hotKeyRefs.removeAll()
  }
}
