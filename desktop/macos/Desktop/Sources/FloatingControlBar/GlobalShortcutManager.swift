import Carbon.HIToolbox.Events
import Cocoa

// MARK: - Global Shortcut Manager

/// Manages global keyboard shortcuts using Carbon APIs for the floating control bar.
class GlobalShortcutManager: @unchecked Sendable {
  static let shared = GlobalShortcutManager()

  static let askAINotification = Notification.Name("com.omi.desktop.askAI")

  private var hotKeyRefs: [HotKeyID: EventHotKeyRef] = [:]
  private var isRegistrationSuspended = false

  private enum HotKeyID: UInt32 {
    case askOmi = 2
  }

  private var shortcutObserver: NSObjectProtocol?

  private init() {
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

    // Re-register Ask Omi shortcut when user changes it in settings
    shortcutObserver = NotificationCenter.default.addObserver(
      forName: ShortcutSettings.askOmiShortcutChanged,
      object: nil,
      queue: .main
    ) { [weak self] _ in
      self?.registerAskOmi()
    }
  }

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

  private func registerAskOmi() {
    guard !isRegistrationSuspended else { return }
    // Unregister previous Ask Omi hotkey if any
    if let ref = hotKeyRefs.removeValue(forKey: .askOmi) {
      UnregisterEventHotKey(ref)
    }
    let (askOmiEnabled, askOmiShortcut) = MainActor.assumeIsolated {
      (ShortcutSettings.shared.askOmiEnabled, ShortcutSettings.shared.askOmiShortcut)
    }
    guard askOmiEnabled else {
      NSLog("GlobalShortcutManager: Ask Omi shortcut is disabled")
      return
    }
    guard askOmiShortcut.supportsGlobalHotKey, let keyCode = askOmiShortcut.keyCode else {
      NSLog("GlobalShortcutManager: Ask Omi shortcut is not a registerable hotkey")
      return
    }
    let outcome = registerHotKey(keyCode: Int(keyCode), modifiers: askOmiShortcut.carbonModifiers, id: .askOmi)
    // Gate the success log on the registration outcome. Previously this logged
    // "Registered" unconditionally — even when Carbon had rejected the combo
    // (e.g. another app owns it) — which made the silent failure actively misleading.
    if outcome == .registered {
      NSLog("GlobalShortcutManager: Registered Ask Omi shortcut: \(askOmiShortcut.displayLabel)")
    }
  }

  /// Outcome of a Carbon `RegisterEventHotKey` attempt, classified for telemetry.
  enum HotKeyRegistrationOutcome: Equatable {
    case registered
    case alreadyInUse
    case otherFailure
  }

  /// Pure classifier over the `OSStatus` returned by `RegisterEventHotKey`.
  ///
  /// Extracted from `registerHotKey` so the registration-failure decision is
  /// unit-testable without driving the real Carbon call, which cannot be made to
  /// return a conflict status hermetically. `eventHotKeyExistsErr` (-9878,
  /// CarbonEvents.h) means another app — or a macOS System Settings > Keyboard >
  /// Shortcuts entry, even a disabled one — already owns this (keyCode, modifiers)
  /// pair in the global Carbon hotkey namespace; the shortcut is dead on that machine.
  static func classifyRegistration(_ status: OSStatus) -> HotKeyRegistrationOutcome {
    if status == noErr { return .registered }
    if Int(status) == eventHotKeyExistsErr { return .alreadyInUse }
    return .otherFailure
  }

  private func registerHotKey(keyCode: Int, modifiers: Int, id: HotKeyID) -> HotKeyRegistrationOutcome {
    var hotKeyRef: EventHotKeyRef?
    let hotKeyID = EventHotKeyID(signature: FourCharCode(0x4F4D_4921), id: id.rawValue)  // "OMI!"

    let status = RegisterEventHotKey(
      UInt32(keyCode), UInt32(modifiers), hotKeyID,
      GetApplicationEventTarget(), 0, &hotKeyRef
    )

    let outcome = Self.classifyRegistration(status)
    if outcome == .registered, let ref = hotKeyRef {
      hotKeyRefs[id] = ref
    } else {
      // The shortcut will not fire on this machine. Keep the local NSLog for
      // debugging and surface the failure to ops/Sentry via the incident path
      // (NOT recordFallback — this is a hard-terminal failure with no mode switch).
      // User-visible conflict surfacing in shortcut settings is tracked separately.
      NSLog("GlobalShortcutManager: Failed to register hotkey (keycode \(keyCode)), error: \(status)")
      DesktopDiagnosticsManager.shared.recordHotkeyRegistrationFailed(
        osStatus: Int(status),
        keycode: keyCode,
        modifiers: modifiers,
        isConflict: outcome == .alreadyInUse)
    }
    return outcome
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
      UnregisterEventHotKey(ref)
    }
    hotKeyRefs.removeAll()
  }
}
