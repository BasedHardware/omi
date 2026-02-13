import Foundation

/// Persistent settings for keyboard shortcuts.
@MainActor
class ShortcutSettings: ObservableObject {
    static let shared = ShortcutSettings()

    /// Available modifier keys for push-to-talk.
    enum PTTKey: String, CaseIterable {
        case option = "Option (⌥)"
        case rightCommand = "Right Command (⌘)"
        case fn = "Fn / Globe"

        var symbol: String {
            switch self {
            case .option: return "\u{2325}"
            case .rightCommand: return "\u{2318}"
            case .fn: return "\u{1F310}"
            }
        }
    }

    @Published var pttKey: PTTKey {
        didSet { UserDefaults.standard.set(pttKey.rawValue, forKey: "shortcut_pttKey") }
    }

    @Published var doubleTapForLock: Bool {
        didSet { UserDefaults.standard.set(doubleTapForLock, forKey: "shortcut_doubleTapForLock") }
    }

    private init() {
        if let saved = UserDefaults.standard.string(forKey: "shortcut_pttKey"),
           let key = PTTKey(rawValue: saved) {
            self.pttKey = key
        } else {
            self.pttKey = .option
        }
        self.doubleTapForLock = UserDefaults.standard.object(forKey: "shortcut_doubleTapForLock") as? Bool ?? true
    }
}
