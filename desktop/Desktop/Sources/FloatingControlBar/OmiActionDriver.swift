import AppKit

@MainActor
protocol OmiActionDriver: AnyObject {
    func click(at point: CGPoint, targetApp: NSRunningApplication?) async throws
    func type(text: String, targetApp: NSRunningApplication?) async throws
    func pressShortcut(_ keys: String, targetApp: NSRunningApplication?) async throws
    func scroll(direction: String, amount: Int, targetApp: NSRunningApplication?) async throws
    func openApp(named: String) async throws
}

enum OmiActionDriverError: LocalizedError {
    case elementNotFound(label: String)
    case appNotFound(name: String)
    case unparseableShortcut(String)
    case axPermissionDenied

    var errorDescription: String? {
        switch self {
        case .elementNotFound(let label):
            return "UI element not found: \(label)"
        case .appNotFound(let name):
            return "Application not found: \(name)"
        case .unparseableShortcut(let shortcut):
            return "Could not parse shortcut: \(shortcut)"
        case .axPermissionDenied:
            return "Accessibility permission denied. Grant access in System Settings > Privacy & Security > Accessibility."
        }
    }
}
