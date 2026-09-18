import AppKit
import Foundation

/// Path display for the Settings panes.
///
/// **This file used to be an agent survey** — `AgentSurface`, `AgentPresence` and a probe that asked
/// LaunchServices and the filesystem whether Claude, Codex and Cursor were on this Mac — feeding a
/// "Detected on this Mac" section in the Agents pane. That section is gone (see
/// `SettingsAgentsPane`): it was read-only, nothing else consulted it, and a list a user cannot act
/// on is not a setting. What survived is the pair of path helpers, because they are the reason no
/// window and no log line in this app ever prints the user's name.
enum AgentPaths {
    static func expand(_ path: String) -> String {
        (path as NSString).expandingTildeInPath
    }

    /// The inverse, for display. Keeps the user's name out of the window and out of any log line.
    static func abbreviate(_ path: String) -> String {
        (path as NSString).abbreviatingWithTildeInPath
    }
}
