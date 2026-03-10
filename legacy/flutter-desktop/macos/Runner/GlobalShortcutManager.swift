import Cocoa
import Carbon.HIToolbox.Events

// MARK: - Shortcut Validator
struct ShortcutValidator {
    static func isValid(keyCode: Int, modifiers: UInt32) -> Bool {
        // Require at least Command modifier for global shortcuts
        let hasCommand = (modifiers & UInt32(cmdKey)) != 0
        guard hasCommand else { return false }
        
        // Disallow certain reserved key codes
        let reservedKeyCodes: Set<Int> = [
            Int(kVK_Escape),
            Int(kVK_Tab),
            Int(kVK_Delete),
            Int(kVK_ForwardDelete)
        ]
        
        if reservedKeyCodes.contains(keyCode) {
            return false
        }
        
        return true
    }
}

// MARK: - Shortcut Formatter
struct ShortcutFormatter {
    static func format(keyCode: Int, modifiers: UInt32) -> String {
        var parts: [String] = []
        
        // Add modifiers in standard macOS order
        if (modifiers & UInt32(controlKey)) != 0 {
            parts.append("⌃")
        }
        if (modifiers & UInt32(optionKey)) != 0 {
            parts.append("⌥")
        }
        if (modifiers & UInt32(shiftKey)) != 0 {
            parts.append("⇧")
        }
        if (modifiers & UInt32(cmdKey)) != 0 {
            parts.append("⌘")
        }
        
        // Add key name
        parts.append(keyName(for: keyCode))
        
        return parts.joined()
    }
    
    private static func keyName(for keyCode: Int) -> String {
        switch keyCode {
        case Int(kVK_Return): return "↩︎"
        case Int(kVK_ANSI_KeypadEnter): return "⌤"
        case 42: return "\\"
        case Int(kVK_Space): return "Space"
        case Int(kVK_Escape): return "⎋"
        case Int(kVK_Delete): return "⌫"
        case Int(kVK_ForwardDelete): return "⌦"
        case Int(kVK_Tab): return "⇥"
        case Int(kVK_LeftArrow): return "←"
        case Int(kVK_RightArrow): return "→"
        case Int(kVK_UpArrow): return "↑"
        case Int(kVK_DownArrow): return "↓"
        case Int(kVK_Home): return "↖"
        case Int(kVK_End): return "↘"
        case Int(kVK_PageUp): return "⇞"
        case Int(kVK_PageDown): return "⇟"
        
        // Number keys (not contiguous, must handle individually)
        case Int(kVK_ANSI_0): return "0"
        case Int(kVK_ANSI_1): return "1"
        case Int(kVK_ANSI_2): return "2"
        case Int(kVK_ANSI_3): return "3"
        case Int(kVK_ANSI_4): return "4"
        case Int(kVK_ANSI_5): return "5"
        case Int(kVK_ANSI_6): return "6"
        case Int(kVK_ANSI_7): return "7"
        case Int(kVK_ANSI_8): return "8"
        case Int(kVK_ANSI_9): return "9"
        
        // Letter keys (in QWERTY layout order, not alphabetical)
        case Int(kVK_ANSI_A): return "A"
        case Int(kVK_ANSI_B): return "B"
        case Int(kVK_ANSI_C): return "C"
        case Int(kVK_ANSI_D): return "D"
        case Int(kVK_ANSI_E): return "E"
        case Int(kVK_ANSI_F): return "F"
        case Int(kVK_ANSI_G): return "G"
        case Int(kVK_ANSI_H): return "H"
        case Int(kVK_ANSI_I): return "I"
        case Int(kVK_ANSI_J): return "J"
        case Int(kVK_ANSI_K): return "K"
        case Int(kVK_ANSI_L): return "L"
        case Int(kVK_ANSI_M): return "M"
        case Int(kVK_ANSI_N): return "N"
        case Int(kVK_ANSI_O): return "O"
        case Int(kVK_ANSI_P): return "P"
        case Int(kVK_ANSI_Q): return "Q"
        case Int(kVK_ANSI_R): return "R"
        case Int(kVK_ANSI_S): return "S"
        case Int(kVK_ANSI_T): return "T"
        case Int(kVK_ANSI_U): return "U"
        case Int(kVK_ANSI_V): return "V"
        case Int(kVK_ANSI_W): return "W"
        case Int(kVK_ANSI_X): return "X"
        case Int(kVK_ANSI_Y): return "Y"
        case Int(kVK_ANSI_Z): return "Z"
        
        // F keys (these ARE contiguous)
        case Int(kVK_F1)...Int(kVK_F12):
            return "F\(keyCode - Int(kVK_F1) + 1)"
        
        default:
            return "Key\(keyCode)"
        }
    }
}

// MARK: - NSEvent Extension
extension NSEvent.ModifierFlags {
    var carbonModifiers: UInt32 {
        var carbon: UInt32 = 0
        if contains(.command) { carbon |= UInt32(cmdKey) }
        if contains(.shift) { carbon |= UInt32(shiftKey) }
        if contains(.option) { carbon |= UInt32(optionKey) }
        if contains(.control) { carbon |= UInt32(controlKey) }
        return carbon
    }
}

// MARK: - Global Shortcut Manager
// Using Carbon APIs for robust global shortcut handling.
class GlobalShortcutManager {
    
    static let toggleFloatingButtonNotification = Notification.Name("com.omi.toggleFloatingButton")
    static let askAINotification = Notification.Name("com.omi.askAI")
    static let shortcutDidChangeNotification = Notification.Name("com.omi.shortcutDidChange")
    
    static let shared = GlobalShortcutManager()
    
    private var hotKeyRefs: [EventHotKeyRef?] = []
    
    private enum HotKeyID: UInt32 {
        case toggleButton = 1
    }
    
    // UserDefaults keys
    private static let askAIKeyCodeKey = "askAIKeyCode"
    private static let askAIModifiersKey = "askAIModifiers"
    private static let toggleControlBarKeyCodeKey = "toggleControlBarKeyCode"
    private static let toggleControlBarModifiersKey = "toggleControlBarModifiers"
    
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
        
        // Register toggle button shortcut (global)
        let (toggleKeyCode, toggleModifiers) = getToggleControlBarShortcut()
        registerHotKey(keyCode: toggleKeyCode, modifiers: Int(toggleModifiers), id: .toggleButton)
        
        // Note: Ask AI shortcut is now handled by the menu bar item (app-scoped)
        // This allows other apps to use the same shortcut when Omi is not active
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
    
    // MARK: - Customizable Shortcuts
    
    /// Get the current Ask AI shortcut
    func getAskAIShortcut() -> (keyCode: Int, modifiers: UInt32) {
        let keyCode = UserDefaults.standard.integer(forKey: GlobalShortcutManager.askAIKeyCodeKey)
        let modifiers = UserDefaults.standard.integer(forKey: GlobalShortcutManager.askAIModifiersKey)
        
        // Return defaults if not set
        if keyCode == 0 {
            return (Int(kVK_Return), UInt32(cmdKey))
        }
        
        return (keyCode, UInt32(modifiers))
    }
    
    /// Get the formatted display string for Ask AI shortcut
    func getAskAIShortcutString() -> String {
        let (keyCode, modifiers) = getAskAIShortcut()
        return ShortcutFormatter.format(keyCode: keyCode, modifiers: modifiers)
    }
    
    /// Update the Ask AI shortcut
    func setAskAIShortcut(keyCode: Int, modifiers: UInt32) {
        UserDefaults.standard.set(keyCode, forKey: GlobalShortcutManager.askAIKeyCodeKey)
        UserDefaults.standard.set(Int(modifiers), forKey: GlobalShortcutManager.askAIModifiersKey)
        
        // Re-register shortcuts with new values
        registerShortcuts()
        
        // Notify observers that shortcut changed
        NotificationCenter.default.post(name: GlobalShortcutManager.shortcutDidChangeNotification, object: nil)
    }
    
    /// Reset Ask AI shortcut to default
    func resetAskAIShortcut() {
        UserDefaults.standard.removeObject(forKey: GlobalShortcutManager.askAIKeyCodeKey)
        UserDefaults.standard.removeObject(forKey: GlobalShortcutManager.askAIModifiersKey)
        registerShortcuts()
        
        // Notify observers that shortcut changed
        NotificationCenter.default.post(name: GlobalShortcutManager.shortcutDidChangeNotification, object: nil)
    }
    
    // MARK: - Toggle Control Bar Shortcut
    
    /// Get the current Toggle Control Bar shortcut
    func getToggleControlBarShortcut() -> (keyCode: Int, modifiers: UInt32) {
        let keyCode = UserDefaults.standard.integer(forKey: GlobalShortcutManager.toggleControlBarKeyCodeKey)
        let modifiers = UserDefaults.standard.integer(forKey: GlobalShortcutManager.toggleControlBarModifiersKey)
        
        // Return defaults if not set (Cmd+\)
        if keyCode == 0 {
            return (42, UInt32(cmdKey)) // kVK_Backslash = 42
        }
        
        return (keyCode, UInt32(modifiers))
    }
    
    /// Get the formatted display string for Toggle Control Bar shortcut
    func getToggleControlBarShortcutString() -> String {
        let (keyCode, modifiers) = getToggleControlBarShortcut()
        return ShortcutFormatter.format(keyCode: keyCode, modifiers: modifiers)
    }
    
    /// Update the Toggle Control Bar shortcut
    func setToggleControlBarShortcut(keyCode: Int, modifiers: UInt32) {
        UserDefaults.standard.set(keyCode, forKey: GlobalShortcutManager.toggleControlBarKeyCodeKey)
        UserDefaults.standard.set(Int(modifiers), forKey: GlobalShortcutManager.toggleControlBarModifiersKey)
        
        // Re-register shortcuts with new values
        registerShortcuts()
        
        // Notify observers that shortcut changed
        NotificationCenter.default.post(name: GlobalShortcutManager.shortcutDidChangeNotification, object: nil)
    }
    
    /// Reset Toggle Control Bar shortcut to default
    func resetToggleControlBarShortcut() {
        UserDefaults.standard.removeObject(forKey: GlobalShortcutManager.toggleControlBarKeyCodeKey)
        UserDefaults.standard.removeObject(forKey: GlobalShortcutManager.toggleControlBarModifiersKey)
        registerShortcuts()
        
        // Notify observers that shortcut changed
        NotificationCenter.default.post(name: GlobalShortcutManager.shortcutDidChangeNotification, object: nil)
    }
}
