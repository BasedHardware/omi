import Carbon
import Cocoa

/// Persistent settings for keyboard shortcuts.
@MainActor
class ShortcutSettings: ObservableObject {
    static let shared = ShortcutSettings()

    /// Notification posted when the Ask Omi shortcut changes so hotkeys can be re-registered.
    nonisolated static let askOmiShortcutChanged = Notification.Name("ShortcutSettings.askOmiShortcutChanged")

    struct KeyboardShortcut: Codable, Hashable {
        var keyCode: UInt16?
        var keyDisplay: String?
        var modifiersRawValue: UInt
        var modifierOnly: Bool
        var requiresRightCommand: Bool

        private static let supportedModifierMask: NSEvent.ModifierFlags = [.command, .shift, .option, .control, .function]

        init(keyCode: UInt16, keyDisplay: String, modifiers: NSEvent.ModifierFlags = []) {
            self.keyCode = keyCode
            self.keyDisplay = keyDisplay
            self.modifiersRawValue = Self.normalizedModifiers(modifiers).rawValue
            self.modifierOnly = false
            self.requiresRightCommand = false
        }

        init(modifierOnly modifiers: NSEvent.ModifierFlags, requiresRightCommand: Bool = false) {
            let normalized = Self.normalizedModifiers(modifiers)
            self.keyCode = nil
            self.keyDisplay = nil
            self.modifiersRawValue = normalized.rawValue
            self.modifierOnly = true
            self.requiresRightCommand = requiresRightCommand && normalized == [.command]
        }

        var modifiers: NSEvent.ModifierFlags {
            Self.normalizedModifiers(NSEvent.ModifierFlags(rawValue: modifiersRawValue))
        }

        var supportsGlobalHotKey: Bool {
            !modifierOnly && keyCode != nil
        }

        var displayTokens: [String] {
            let modifierTokens = Self.modifierTokens(for: modifiers)
            if modifierOnly {
                return modifierTokens
            }
            if let keyDisplay {
                return modifierTokens + [keyDisplay]
            }
            return modifierTokens
        }

        var displayLabel: String {
            if modifierOnly {
                if requiresRightCommand {
                    return "Right Cmd"
                }
                switch modifiers {
                case [.option]:
                    return "Option"
                case [.function]:
                    return "Fn"
                case [.command]:
                    return "Command"
                case [.control]:
                    return "Control"
                case [.shift]:
                    return "Shift"
                default:
                    return displayTokens.joined(separator: " ")
                }
            }
            return displayTokens.joined(separator: " ")
        }

        var promptLabel: String {
            if modifierOnly {
                if requiresRightCommand {
                    return "right cmd"
                }
                switch modifiers {
                case [.option]:
                    return "option"
                case [.function]:
                    return "fn"
                case [.command]:
                    return "command"
                case [.control]:
                    return "control"
                case [.shift]:
                    return "shift"
                default:
                    return displayLabel.lowercased()
                }
            }
            return displayLabel.lowercased()
        }

        var carbonModifiers: Int {
            var value = 0
            if modifiers.contains(.command) {
                value |= Int(cmdKey)
            }
            if modifiers.contains(.shift) {
                value |= Int(shiftKey)
            }
            if modifiers.contains(.option) {
                value |= Int(optionKey)
            }
            if modifiers.contains(.control) {
                value |= Int(controlKey)
            }
            if modifiers.contains(.function) {
                value |= Int(kEventKeyModifierFnMask)
            }
            return value
        }

        func matchesKeyDown(_ event: NSEvent) -> Bool {
            guard !modifierOnly, event.type == .keyDown, let keyCode else { return false }
            return keyCode == event.keyCode && Self.normalizedModifiers(event.modifierFlags) == modifiers
        }

        func matchesKeyUp(_ event: NSEvent) -> Bool {
            guard !modifierOnly, event.type == .keyUp, let keyCode else { return false }
            return keyCode == event.keyCode && Self.normalizedModifiers(event.modifierFlags) == modifiers
        }

        func matchesFlagsChanged(_ event: NSEvent) -> Bool {
            guard modifierOnly, event.type == .flagsChanged else { return false }
            let activeModifiers = Self.normalizedModifiers(event.modifierFlags)
            guard activeModifiers == modifiers else { return false }
            if requiresRightCommand {
                return event.keyCode == 54
            }
            return true
        }

        static func fromRecordingEvent(_ event: NSEvent, allowModifierOnly: Bool) -> KeyboardShortcut? {
            switch event.type {
            case .keyDown:
                return KeyboardShortcut(
                    keyCode: event.keyCode,
                    keyDisplay: keyDisplay(for: event.keyCode, characters: event.charactersIgnoringModifiers),
                    modifiers: normalizedModifiers(event.modifierFlags)
                )
            case .flagsChanged:
                guard allowModifierOnly else { return nil }
                let modifiers = normalizedModifiers(event.modifierFlags)
                guard !modifiers.isEmpty else { return nil }
                return KeyboardShortcut(
                    modifierOnly: modifiers,
                    requiresRightCommand: modifiers == [.command] && event.keyCode == 54
                )
            default:
                return nil
            }
        }

        static func normalizedModifiers(_ flags: NSEvent.ModifierFlags) -> NSEvent.ModifierFlags {
            flags.intersection(supportedModifierMask)
        }

        static func modifierTokens(for flags: NSEvent.ModifierFlags) -> [String] {
            var tokens: [String] = []
            if flags.contains(.control) {
                tokens.append("⌃")
            }
            if flags.contains(.option) {
                tokens.append("⌥")
            }
            if flags.contains(.shift) {
                tokens.append("⇧")
            }
            if flags.contains(.command) {
                tokens.append("⌘")
            }
            if flags.contains(.function) {
                tokens.append("fn")
            }
            return tokens
        }

        static func keyDisplay(for keyCode: UInt16, characters: String?) -> String {
            switch keyCode {
            case 36:
                return "↩"
            case 48:
                return "Tab"
            case 49:
                return "Space"
            case 51:
                return "⌫"
            case 53:
                return "Esc"
            case 71:
                return "⌧"
            case 76:
                return "Enter"
            case 96:
                return "F5"
            case 97:
                return "F6"
            case 98:
                return "F7"
            case 99:
                return "F3"
            case 100:
                return "F8"
            case 101:
                return "F9"
            case 103:
                return "F11"
            case 105:
                return "F13"
            case 106:
                return "F16"
            case 107:
                return "F14"
            case 109:
                return "F10"
            case 111:
                return "F12"
            case 113:
                return "F15"
            case 114:
                return "Help"
            case 115:
                return "Home"
            case 116:
                return "PgUp"
            case 117:
                return "⌦"
            case 118:
                return "F4"
            case 119:
                return "End"
            case 120:
                return "F2"
            case 121:
                return "PgDn"
            case 122:
                return "F1"
            case 123:
                return "←"
            case 124:
                return "→"
            case 125:
                return "↓"
            case 126:
                return "↑"
            default:
                if let characters {
                    let trimmed = characters.trimmingCharacters(in: .whitespacesAndNewlines)
                    if !trimmed.isEmpty {
                        return trimmed.uppercased()
                    }
                }
                return "Key \(keyCode)"
            }
        }
    }

    static let askOmiPresets: [KeyboardShortcut] = [
        KeyboardShortcut(keyCode: 36, keyDisplay: "↩", modifiers: .command),
        KeyboardShortcut(keyCode: 36, keyDisplay: "↩", modifiers: [.command, .shift]),
        KeyboardShortcut(keyCode: 38, keyDisplay: "J", modifiers: .command),
        KeyboardShortcut(keyCode: 31, keyDisplay: "O", modifiers: .command),
    ]

    static let pttPresets: [KeyboardShortcut] = [
        KeyboardShortcut(modifierOnly: .option),
        KeyboardShortcut(modifierOnly: .command, requiresRightCommand: true),
        KeyboardShortcut(modifierOnly: .function),
    ]

    @Published var pttShortcut: KeyboardShortcut {
        didSet {
            persistShortcut(pttShortcut, forKey: Self.pttShortcutDefaultsKey)
        }
    }

    @Published var askOmiShortcut: KeyboardShortcut {
        didSet {
            persistShortcut(askOmiShortcut, forKey: Self.askOmiShortcutDefaultsKey)
            NotificationCenter.default.post(name: Self.askOmiShortcutChanged, object: nil)
        }
    }

    @Published var askOmiEnabled: Bool {
        didSet {
            UserDefaults.standard.set(askOmiEnabled, forKey: "shortcut_askOmiEnabled")
            NotificationCenter.default.post(name: Self.askOmiShortcutChanged, object: nil)
        }
    }

    @Published var pttEnabled: Bool {
        didSet { UserDefaults.standard.set(pttEnabled, forKey: "shortcut_pttEnabled") }
    }

    @Published var doubleTapForLock: Bool {
        didSet { UserDefaults.standard.set(doubleTapForLock, forKey: "shortcut_doubleTapForLock") }
    }

    /// When true, the floating bar uses a solid dark background instead of semi-transparent blur.
    @Published var solidBackground: Bool {
        didSet { UserDefaults.standard.set(solidBackground, forKey: "shortcut_solidBackground") }
    }

    /// When true, push-to-talk plays start/end sounds.
    @Published var pttSoundsEnabled: Bool {
        didSet { UserDefaults.standard.set(pttSoundsEnabled, forKey: "shortcut_pttSoundsEnabled") }
    }

    /// Selected AI model for Ask Omi.
    @Published var selectedModel: String {
        didSet { UserDefaults.standard.set(selectedModel, forKey: "shortcut_selectedModel") }
    }

    /// Available models for Ask Omi.
    static let availableModels: [(id: String, label: String)] = [
        ("claude-sonnet-4-6", "Sonnet"),
        ("claude-opus-4-6", "Opus"),
    ]

    /// Push-to-talk transcription mode.
    enum PTTTranscriptionMode: String, CaseIterable {
        case live = "Live"
        case batch = "Batch"

        var description: String {
            switch self {
            case .live: return "Real-time transcription as you speak"
            case .batch: return "Transcribe after recording for better accuracy"
            }
        }
    }

    @Published var pttTranscriptionMode: PTTTranscriptionMode {
        didSet { UserDefaults.standard.set(pttTranscriptionMode.rawValue, forKey: "shortcut_pttTranscriptionMode") }
    }

    /// When true, the floating bar can be repositioned by dragging. Off by default.
    @Published var draggableBarEnabled: Bool {
        didSet { UserDefaults.standard.set(draggableBarEnabled, forKey: "shortcut_draggableBarEnabled") }
    }

    /// When true, floating-bar replies are spoken aloud.
    @Published var floatingBarVoiceAnswersEnabled: Bool {
        didSet {
            UserDefaults.standard.set(floatingBarVoiceAnswersEnabled, forKey: "shortcut_floatingBarVoiceAnswersEnabled")
            if !floatingBarVoiceAnswersEnabled {
                FloatingBarVoicePlaybackService.shared.stop()
            }
        }
    }

    var askOmiUsesCustomShortcut: Bool {
        !Self.askOmiPresets.contains(askOmiShortcut)
    }

    var pttUsesCustomShortcut: Bool {
        !Self.pttPresets.contains(pttShortcut)
    }

    private static let askOmiShortcutDefaultsKey = "shortcut_askOmiKey"
    private static let pttShortcutDefaultsKey = "shortcut_pttKey"

    private init() {
        self.pttShortcut = Self.loadShortcut(
            forKey: Self.pttShortcutDefaultsKey,
            legacyMapper: Self.legacyPTTShortcut
        ) ?? Self.pttPresets[0]

        self.askOmiShortcut = Self.loadShortcut(
            forKey: Self.askOmiShortcutDefaultsKey,
            legacyMapper: Self.legacyAskOmiShortcut
        ) ?? Self.askOmiPresets[0]

        self.askOmiEnabled = UserDefaults.standard.object(forKey: "shortcut_askOmiEnabled") as? Bool ?? true
        self.pttEnabled = UserDefaults.standard.object(forKey: "shortcut_pttEnabled") as? Bool ?? true
        self.doubleTapForLock = UserDefaults.standard.object(forKey: "shortcut_doubleTapForLock") as? Bool ?? true
        self.solidBackground = UserDefaults.standard.object(forKey: "shortcut_solidBackground") as? Bool ?? true
        self.pttSoundsEnabled = UserDefaults.standard.object(forKey: "shortcut_pttSoundsEnabled") as? Bool ?? true
        self.selectedModel = UserDefaults.standard.string(forKey: "shortcut_selectedModel") ?? "claude-sonnet-4-6"
        if let saved = UserDefaults.standard.string(forKey: "shortcut_pttTranscriptionMode"),
           let mode = PTTTranscriptionMode(rawValue: saved) {
            self.pttTranscriptionMode = mode
        } else {
            self.pttTranscriptionMode = .live
        }
        self.draggableBarEnabled = UserDefaults.standard.object(forKey: "shortcut_draggableBarEnabled") as? Bool ?? false
        self.floatingBarVoiceAnswersEnabled = UserDefaults.standard.object(forKey: "shortcut_floatingBarVoiceAnswersEnabled") as? Bool ?? false
    }

    private func persistShortcut(_ shortcut: KeyboardShortcut, forKey key: String) {
        let encoder = JSONEncoder()
        guard let data = try? encoder.encode(shortcut) else { return }
        UserDefaults.standard.set(data, forKey: key)
    }

    private static func loadShortcut(
        forKey key: String,
        legacyMapper: (String) -> KeyboardShortcut?
    ) -> KeyboardShortcut? {
        let defaults = UserDefaults.standard
        if let data = defaults.data(forKey: key),
           let decoded = try? JSONDecoder().decode(KeyboardShortcut.self, from: data) {
            return decoded
        }
        if let legacyValue = defaults.string(forKey: key),
           let migrated = legacyMapper(legacyValue) {
            return migrated
        }
        return nil
    }

    private static func legacyAskOmiShortcut(_ value: String) -> KeyboardShortcut? {
        switch value {
        case "⌘ Enter":
            return askOmiPresets[0]
        case "⌘⇧ Enter":
            return askOmiPresets[1]
        case "⌘J":
            return askOmiPresets[2]
        case "⌘O":
            return askOmiPresets[3]
        default:
            return nil
        }
    }

    private static func legacyPTTShortcut(_ value: String) -> KeyboardShortcut? {
        switch value {
        case "Option (⌥)":
            return pttPresets[0]
        case "Right Command (⌘)":
            return pttPresets[1]
        case "Fn / Globe":
            return pttPresets[2]
        default:
            return nil
        }
    }
}
