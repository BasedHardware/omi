import AppKit
import Foundation

/// One agent surface the Agents pane lists, and whether it is genuinely on this Mac.
///
/// Detection is real by construction: the only two things that count as evidence are an application
/// bundle LaunchServices can resolve by identifier, or an executable file on disk at a path the tool
/// actually installs to. There is no hardcoded `Installed` pill anywhere — `I13` in
/// `docs/requirements-checklist.md` calls that out because a green dot that is always green is worse
/// than no list at all.
enum AgentSurface: String, CaseIterable, Identifiable, Sendable {
    case claude
    case codex
    case cursor

    var id: String { rawValue }

    var title: String {
        switch self {
        case .claude: "Claude"
        case .codex: "Codex"
        case .cursor: "Cursor"
        }
    }

    /// Bundle identifiers to ask LaunchServices about. More than one where a vendor ships both a
    /// stable and a preview build under different identifiers.
    var bundleIdentifiers: [String] {
        switch self {
        case .claude: ["com.anthropic.claudefordesktop", "com.anthropic.claude"]
        case .codex: ["com.openai.codex", "com.openai.chat"]
        case .cursor: ["com.todesktop.230313mzl4w4u92", "com.cursor.Cursor"]
        }
    }

    /// CLI binaries, relative to `$HOME` or absolute. A coding agent is often *only* a CLI, so an
    /// app-bundle-only check would report Codex missing on a machine that has it.
    var executableCandidates: [String] {
        switch self {
        case .claude: ["~/.claude/local/claude", "/opt/homebrew/bin/claude", "/usr/local/bin/claude"]
        case .codex: ["/opt/homebrew/bin/codex", "/usr/local/bin/codex", "~/.codex/bin/codex"]
        case .cursor: ["/opt/homebrew/bin/cursor", "/usr/local/bin/cursor"]
        }
    }

    /// Directories the tool creates on first run. Weaker evidence than a binary, and used the same
    /// way `ClaudeRegistrar.Surface.isInstalled` already uses it: proof the user has run the thing.
    var stateDirectories: [String] {
        switch self {
        case .claude: ["~/.claude"]
        case .codex: ["~/.codex"]
        case .cursor: ["~/.cursor"]
        }
    }
}

/// What was found, and by which kind of evidence — so the pane can say *how* it knows.
enum AgentPresence: Equatable, Sendable {
    case application(URL)
    case executable(String)
    case configured(String)
    case absent

    var isInstalled: Bool { self != .absent }

    /// The pill's label. `Installed` only where an app or a binary was actually located.
    var label: String {
        switch self {
        case .application, .executable: "Installed"
        case .configured: "Configured"
        case .absent: "Not installed"
        }
    }

    /// A `~`-relative path or app name, never an absolute path carrying the user's name.
    var detail: String? {
        switch self {
        case .application(let url): url.lastPathComponent
        case .executable(let path): AgentDetector.abbreviate(path)
        case .configured(let path): AgentDetector.abbreviate(path)
        case .absent: nil
        }
    }
}

/// The probe, with the filesystem behind an injectable seam so the mapping from evidence to state can
/// be tested without depending on what happens to be installed on the machine running the suite.
struct AgentDetector: Sendable {

    /// Resolves an application URL for a bundle identifier, or nil.
    var applicationForBundleID: @Sendable (String) -> URL?
    /// True when the path is an executable file. **Always receives an absolute path** — `presence`
    /// expands the `~` before asking, so an implementation of this seam never has to.
    var isExecutableFile: @Sendable (String) -> Bool
    /// True when the path is a directory. Also always absolute.
    var isDirectory: @Sendable (String) -> Bool

    static let live = AgentDetector(
        applicationForBundleID: { identifier in
            MainActor.assumeIsolated { NSWorkspace.shared.urlForApplication(withBundleIdentifier: identifier) }
        },
        isExecutableFile: { FileManager.default.isExecutableFile(atPath: $0) },
        isDirectory: { path in
            var isDirectory: ObjCBool = false
            let exists = FileManager.default.fileExists(atPath: path, isDirectory: &isDirectory)
            return exists && isDirectory.boolValue
        })

    /// Strongest evidence wins, so a machine with both the app and the CLI reports the app.
    ///
    /// Paths are expanded before the probe and stored expanded; `AgentPresence.detail` abbreviates them
    /// back to `~`-relative for display, which is what keeps the user's name out of the window.
    func presence(of surface: AgentSurface) -> AgentPresence {
        for identifier in surface.bundleIdentifiers {
            if let url = applicationForBundleID(identifier) { return .application(url) }
        }
        for path in surface.executableCandidates.map(Self.expand) where isExecutableFile(path) {
            return .executable(path)
        }
        for path in surface.stateDirectories.map(Self.expand) where isDirectory(path) {
            return .configured(path)
        }
        return .absent
    }

    func survey() -> [(surface: AgentSurface, presence: AgentPresence)] {
        AgentSurface.allCases.map { ($0, presence(of: $0)) }
    }

    static func expand(_ path: String) -> String {
        (path as NSString).expandingTildeInPath
    }

    /// The inverse, for display. Keeps the user's name out of the window and out of any log line.
    static func abbreviate(_ path: String) -> String {
        (path as NSString).abbreviatingWithTildeInPath
    }
}
