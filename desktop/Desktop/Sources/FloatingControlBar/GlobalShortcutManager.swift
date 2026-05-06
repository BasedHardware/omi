import Carbon.HIToolbox.Events
import Cocoa

// MARK: - Global Shortcut Manager

/// Manages global keyboard shortcuts using Carbon APIs for the floating control bar.
class GlobalShortcutManager {
    static let shared = GlobalShortcutManager()

    static let askAINotification = Notification.Name("com.omi.desktop.askAI")

    private var hotKeyRefs: [HotKeyID: EventHotKeyRef] = [:]
    private var isRegistrationSuspended = false

    private enum HotKeyID: UInt32 {
        case askOmi = 2
        case toggleListening = 3
    }

    private var shortcutObserver: NSObjectProtocol?
    private var toggleListeningShortcutObserver: NSObjectProtocol?

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
        toggleListeningShortcutObserver = NotificationCenter.default.addObserver(
            forName: ShortcutSettings.toggleListeningShortcutChanged,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            self?.registerToggleListening()
        }
    }

    func registerShortcuts() {
        unregisterShortcuts()
        guard !isRegistrationSuspended else { return }
        // Register Ask Omi shortcut from user settings
        registerAskOmi()
        registerToggleListening()
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
        registerHotKey(keyCode: Int(keyCode), modifiers: askOmiShortcut.carbonModifiers, id: .askOmi)
        NSLog("GlobalShortcutManager: Registered Ask Omi shortcut: \(askOmiShortcut.displayLabel)")
    }

    private func registerToggleListening() {
        guard !isRegistrationSuspended else { return }
        if let ref = hotKeyRefs.removeValue(forKey: .toggleListening) {
            UnregisterEventHotKey(ref)
        }
        let (enabled, shortcut) = MainActor.assumeIsolated {
            (ShortcutSettings.shared.toggleListeningEnabled, ShortcutSettings.shared.toggleListeningShortcut)
        }
        guard enabled else {
            NSLog("GlobalShortcutManager: Toggle Listening shortcut is disabled")
            return
        }
        guard shortcut.supportsGlobalHotKey, let keyCode = shortcut.keyCode else {
            NSLog("GlobalShortcutManager: Toggle Listening shortcut is not a registerable hotkey")
            return
        }
        registerHotKey(keyCode: Int(keyCode), modifiers: shortcut.carbonModifiers, id: .toggleListening)
        NSLog("GlobalShortcutManager: Registered Toggle Listening shortcut: \(shortcut.displayLabel)")
    }

    private func registerHotKey(keyCode: Int, modifiers: Int, id: HotKeyID) {
        var hotKeyRef: EventHotKeyRef?
        let hotKeyID = EventHotKeyID(signature: FourCharCode(0x4F4D4921), id: id.rawValue) // "OMI!"

        let status = RegisterEventHotKey(
            UInt32(keyCode), UInt32(modifiers), hotKeyID,
            GetApplicationEventTarget(), 0, &hotKeyRef
        )

        if status == noErr, let ref = hotKeyRef {
            hotKeyRefs[id] = ref
        } else {
            NSLog("GlobalShortcutManager: Failed to register hotkey (keycode \(keyCode)), error: \(status)")
        }
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
            NSLog("GlobalShortcutManager: Ask Omi shortcut detected")
            DispatchQueue.main.async {
                FloatingControlBarManager.shared.toggleAIInput()
            }
        case .toggleListening:
            NSLog("GlobalShortcutManager: Toggle Listening shortcut detected")
            DispatchQueue.main.async {
                NotificationCenter.default.post(name: .toggleListeningShortcutPressed, object: nil)
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
