import Carbon.HIToolbox.Events
import Cocoa

// MARK: - Global Shortcut Manager

/// Manages global keyboard shortcuts using Carbon APIs for the floating control bar.
class GlobalShortcutManager {
    static let shared = GlobalShortcutManager()

    static let toggleFloatingBarNotification = Notification.Name("com.omi.desktop.toggleFloatingBar")
    static let askAINotification = Notification.Name("com.omi.desktop.askAI")

    private var hotKeyRefs: [EventHotKeyRef?] = []

    private enum HotKeyID: UInt32 {
        case toggleBar = 1
    }

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
    }

    func registerShortcuts() {
        unregisterShortcuts()
        // Register Cmd+\ for toggle bar (keycode 42 = backslash)
        registerHotKey(keyCode: 42, modifiers: Int(cmdKey), id: .toggleBar)
    }

    private func registerHotKey(keyCode: Int, modifiers: Int, id: HotKeyID) {
        var hotKeyRef: EventHotKeyRef?
        let hotKeyID = EventHotKeyID(signature: FourCharCode(0x4F4D4921), id: id.rawValue) // "OMI!"

        let status = RegisterEventHotKey(
            UInt32(keyCode), UInt32(modifiers), hotKeyID,
            GetApplicationEventTarget(), 0, &hotKeyRef
        )

        if status == noErr, let ref = hotKeyRef {
            hotKeyRefs.append(ref)
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
        case .toggleBar:
            NSLog("GlobalShortcutManager: Cmd+\\ detected, toggling floating bar")
            NotificationCenter.default.post(name: GlobalShortcutManager.toggleFloatingBarNotification, object: nil)
        }

        return noErr
    }

    func unregisterShortcuts() {
        for ref in hotKeyRefs {
            if let validRef = ref {
                UnregisterEventHotKey(validRef)
            }
        }
        hotKeyRefs.removeAll()
    }
}
