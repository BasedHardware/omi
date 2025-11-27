import Cocoa
import Carbon.HIToolbox.Events

// Using Carbon APIs for robust global shortcut handling.
class GlobalShortcutManager {
    
    static let toggleFloatingButtonNotification = Notification.Name("com.omi.toggleFloatingButton")
    static let askAINotification = Notification.Name("com.omi.askAI")
    
    static let shared = GlobalShortcutManager()
    
    private var hotKeyRefs: [EventHotKeyRef?] = []
    
    private enum HotKeyID: UInt32 {
        case askAI = 1
        case askAIKeypad = 2
        case toggleButton = 3
    }
    
    private init() {
        // Install the event handler when the manager is initialized.
        var eventType = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: OSType(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { (handler, event, userData) -> OSStatus in
            // This closure captures `self`, so we need to handle potential cycles if this object could be deallocated
            // while the handler is still installed. Since this is a singleton, it's not an issue.
            return GlobalShortcutManager.shared.handleHotKeyEvent(event!)
        }, 1, &eventType, nil, nil)
    }
    
    func registerShortcuts() {
        // Unregister any existing shortcuts before registering new ones.
        unregisterShortcuts()
        
        registerHotKey(keyCode: kVK_Return, modifiers: cmdKey, id: .askAI) // CMD+Enter
        registerHotKey(keyCode: kVK_ANSI_KeypadEnter, modifiers: cmdKey, id: .askAIKeypad) // CMD+Keypad Enter
        registerHotKey(keyCode: 42, modifiers: cmdKey, id: .toggleButton) // kVK_Backslash
    }
    
    private func registerHotKey(keyCode: Int, modifiers: Int, id: HotKeyID) {
        var hotKeyRef: EventHotKeyRef?
        let hotKeyID = EventHotKeyID(signature: FourCharCode("OMI".utf16.first!), id: id.rawValue)
        
        let status = RegisterEventHotKey(UInt32(keyCode), UInt32(modifiers), hotKeyID, GetApplicationEventTarget(), 0, &hotKeyRef)
        
        if status == noErr {
            if let ref = hotKeyRef {
                hotKeyRefs.append(ref)
            }
        } else {
            print("Failed to register shortcut for keycode \(keyCode), error: \(status). This might be due to a conflict with another application.")
        }
    }
    
    private func handleHotKeyEvent(_ event: EventRef) -> OSStatus {
        var hotKeyID = EventHotKeyID()
        let status = GetEventParameter(event,
                                       OSType(kEventParamDirectObject),
                                       OSType(typeEventHotKeyID),
                                       nil,
                                       MemoryLayout<EventHotKeyID>.size,
                                       nil,
                                       &hotKeyID)
        
        if status != noErr {
            return status
        }
        
        guard let id = HotKeyID(rawValue: hotKeyID.id) else {
            return noErr
        }
        
        switch id {
        case .askAI, .askAIKeypad:
            print("CMD+Enter shortcut detected. Triggering Ask AI...")
            NotificationCenter.default.post(name: GlobalShortcutManager.askAINotification, object: nil)
        case .toggleButton:
            print("CMD+\\ shortcut detected. Toggling floating button...")
            NotificationCenter.default.post(name: GlobalShortcutManager.toggleFloatingButtonNotification, object: nil)
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
