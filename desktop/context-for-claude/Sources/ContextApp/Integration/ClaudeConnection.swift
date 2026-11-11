import AppKit
import ContextCore
import Darwin
import Foundation

/// The Claude connection **as the user experiences it**: what is registered on disk, and whether the
/// Claude Desktop running right now can actually reach us.
///
/// ## Why the disk answer alone is a lie
///
/// `ClaudeRegistrar.status()` reads two config files. That is the whole of what every user-facing
/// surface knew, so both of them said `Connected to Claude Code and Claude Desktop` whenever the
/// entry was on disk — including for the three days this Mac spent with a Claude Desktop whose
/// server had failed to spawn at every launch. The config was perfect. The connector was dead. The
/// app said "Connected", the menu bar said "Connected", and the only place the truth existed was a
/// line in `~/Library/Logs/Claude/mcp-server-context-for-claude.log` that nothing points a user at.
///
/// `ClaudeServerLiveness` has been able to answer this since it was written — it looks for a live
/// server descending from a running Claude Desktop — but it was reachable only from the tutorial,
/// which runs once. This type is what puts that evidence in front of the two surfaces a user
/// actually consults, so a registration that Claude has not picked up can no longer read as success.
///
/// ## What it does not do
///
/// It does not quit anybody's Claude. `ClaudeHandoff` may offer that, with consent, because it is
/// about to hand Claude a question and the answer would be wrong without it; a status line has no
/// such errand and no right to take a conversation away to tidy up its own wording. So the remedy
/// here is a sentence, and the press stays the user's.
struct ClaudeConnection: Equatable {
    /// Registered on disk, pointing at this build's binary.
    let claudeCode: Bool
    let claudeDesktop: Bool

    /// Registered for Claude Desktop, and Claude Desktop is demonstrably not serving us.
    ///
    /// **Only ever true on evidence.** `.unknown` — Claude Desktop is not running, or the process
    /// list could not be read — leaves this false, because a surface that nags on absence of
    /// evidence would tell users to restart an app that is working, or one that is not even open.
    let desktopNeedsRestart: Bool

    /// The sentence naming the remedy, or nil when there is nothing to remedy. Shared so the menu
    /// bar and the settings pane cannot drift into describing the same state two different ways.
    var restartNotice: String? {
        desktopNeedsRestart ? "Quit and reopen Claude Desktop to finish connecting it." : nil
    }

    /// Whether Claude can reach this Mac through Claude Desktop *now*, as opposed to after a restart.
    /// This, not `claudeDesktop`, is what a summary line may call connected.
    var desktopIsReachable: Bool { claudeDesktop && !desktopNeedsRestart }

    /// Pure, so the whole decision is testable without a Claude on the machine.
    init(claudeCode: Bool, claudeDesktop: Bool, liveness: ClaudeServerLiveness.State) {
        self.claudeCode = claudeCode
        self.claudeDesktop = claudeDesktop
        self.desktopNeedsRestart = claudeDesktop && liveness == .notServingClaudeDesktop
    }

    /// Reads both config files and the process list. Off the main actor at every call site: the
    /// config half JSON-decodes `~/.claude.json`, and the liveness half sweeps every PID on the Mac.
    static func current() -> ClaudeConnection {
        let registration = ClaudeRegistrar.status()
        return ClaudeConnection(
            claudeCode: registration.claudeCode,
            claudeDesktop: registration.claudeDesktop,
            liveness: ClaudeServerLiveness.state(claudeDesktopPIDs: ClaudeDesktopProcesses.pids))
    }
}

// MARK: - The running Claude Desktops

/// Claude Desktop, as processes.
///
/// Separate from `ClaudeRegistrar` because that file is deliberately free of AppKit — its comment on
/// `ClaudeServerLiveness.state` says so, and the PIDs are a parameter for exactly that reason. This
/// is the one place that reads them, so the three callers that used to build the same
/// `runningApplications(withBundleIdentifier:)` call by hand now share it and cannot disagree about
/// which bundle identifier Claude Desktop has.
enum ClaudeDesktopProcesses {
    static let bundleIdentifier = "com.anthropic.claudefordesktop"

    /// Empty when Claude Desktop is not running, which `ClaudeServerLiveness` reads as `.unknown`
    /// rather than as an absence — there is nothing for a server to be serving.
    static var pids: Set<pid_t> {
        Set(
            NSRunningApplication.runningApplications(withBundleIdentifier: bundleIdentifier)
                .map(\.processIdentifier))
    }
}
