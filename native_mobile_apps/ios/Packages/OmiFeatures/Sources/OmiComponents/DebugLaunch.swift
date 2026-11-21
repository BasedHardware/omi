import Foundation

/// Launch arguments a feature screen reads itself, so a screenshot can show a state without
/// tapping (`-omiConversationPage transcript`, `-omiMemoryGraph YES`, …). Inert outside Debug.
public enum DebugLaunch {
    public static func string(_ key: String) -> String? {
        #if DEBUG
            UserDefaults.standard.string(forKey: key)
        #else
            nil
        #endif
    }

    public static func flag(_ key: String) -> Bool {
        string(key).map { ["YES", "1", "true"].contains($0) } ?? false
    }
}
