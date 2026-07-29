import Foundation

/// Copy for the local Claude connector step. A written MCP entry means this Mac is configured to
/// launch our server; it does not prove that a Claude account, session, or conversation is active.
enum ClaudeSurface: CaseIterable {
    case claudeCode
    case claudeDesktop

    var name: String {
        switch self {
        case .claudeCode: return "Claude Code"
        case .claudeDesktop: return "Claude Desktop"
        }
    }
}

struct OnboardingConnectorCopy {
    let title: String
    let detail: String
    let action: String

    init(surfaces: Set<ClaudeSurface>) {
        let configured = ClaudeSurface.allCases.filter { surfaces.contains($0) }.map(\.name)
        guard !configured.isEmpty else {
            title = "Bring Claude in"
            detail = "Set up a local connector so Claude can ask about this Mac when you use it."
            action = "Set up Claude"
            return
        }

        let names = Self.list(configured)
        title = "\(names) \(configured.count == 1 ? "is" : "are") ready"
        detail = "The local connector is configured for \(names)."
        action = "Continue"
    }

    private static func list(_ names: [String]) -> String {
        guard names.count > 1 else { return names.first ?? "Claude" }
        return names.dropLast().joined(separator: ", ") + " and " + (names.last ?? "Claude")
    }
}
