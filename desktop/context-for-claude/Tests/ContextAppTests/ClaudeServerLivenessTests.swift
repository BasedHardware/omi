import Darwin
import XCTest

@testable import ContextApp

/// **Who a running server belongs to.**
///
/// `ClaudeServerLiveness` exists to contradict the config files when they claim a connection Claude
/// cannot use. It can only do that if it attributes servers correctly, and the version that shipped
/// did not: it asked whether a Claude Desktop PID appeared *anywhere* above a server, and Claude
/// Code now runs inside Claude Desktop, so every Claude Code session in the desktop app put one.
///
/// The tree below is not invented. It is the ancestry read off the Mac whose Claude Desktop
/// connector had been failing to spawn since 2026-08-16 — where the old walk answered
/// `servingClaudeDesktop` on the strength of fifteen Claude Code servers, which is the one answer
/// that would have kept the status surfaces lying after they were wired to this probe.
///
/// Everything here drives the two process-table reads as closures. The real tree needs a running
/// Claude Desktop with a running Claude Code inside it and a server under each, which no test may
/// arrange and none should wait for.
final class ClaudeServerLivenessTests: XCTestCase {

    /// PIDs and paths from `ps` on 2026-08-19, unchanged.
    private enum Real {
        static let server: pid_t = 5160
        static let claudeCode: pid_t = 5065
        static let disclaimer: pid_t = 5064
        static let claudeDesktop: pid_t = 1233
        static let launchd: pid_t = 1

        static let parents: [pid_t: pid_t] = [
            server: claudeCode, claudeCode: disclaimer, disclaimer: claudeDesktop,
            claudeDesktop: launchd,
        ]
        static let paths: [pid_t: String] = [
            server: "/Applications/Context for Claude.app/Contents/MacOS/context-for-claude-mcp",
            claudeCode:
                "/Users/architlal/Library/Application Support/Claude/claude-code/2.1.229/claude.app/Contents/MacOS/claude",
            disclaimer: "/Applications/Claude.app/Contents/Helpers/disclaimer",
            claudeDesktop: "/Applications/Claude.app/Contents/MacOS/Claude",
            launchd: "/sbin/launchd",
        ]
    }

    private func owner(
        of pid: pid_t,
        desktops: Set<pid_t>,
        parents: [pid_t: pid_t] = Real.parents,
        paths: [pid_t: String] = Real.paths
    ) -> ClaudeServerLiveness.Owner {
        ClaudeServerLiveness.owner(
            of: pid,
            claudeDesktopPIDs: desktops,
            parent: { parents[$0] },
            executablePath: { paths[$0] })
    }

    /// **The regression.** Claude Code's server, on a chain that reaches Claude Desktop three hops
    /// up, belongs to Claude Code.
    func testAClaudeCodeServerInsideTheDesktopAppIsNotTheDesktopApps() {
        XCTAssertEqual(owner(of: Real.server, desktops: [Real.claudeDesktop]), .claudeCode)
    }

    /// Claude Desktop's own server — spawned by the app rather than through Claude Code — is still
    /// attributed to it. The fix must not silence the probe altogether.
    func testAServerSpawnedByClaudeDesktopIsStillItsOwn() {
        let server: pid_t = 900
        XCTAssertEqual(
            owner(
                of: server,
                desktops: [Real.claudeDesktop],
                parents: [server: Real.disclaimer, Real.disclaimer: Real.claudeDesktop],
                paths: [Real.disclaimer: "/Applications/Claude.app/Contents/Helpers/disclaimer"]),
            .claudeDesktop)
    }

    /// A server under a Claude Code that Claude Desktop never launched — a terminal CLI — reaches
    /// launchd having met nobody. It was never a false positive, and it does not become a false
    /// negative either.
    func testAServerUnderNoClaudeAtAllIsAttributedToNeither() {
        let server: pid_t = 700
        let shell: pid_t = 600
        XCTAssertEqual(
            owner(
                of: server,
                desktops: [Real.claudeDesktop],
                parents: [server: shell, shell: Real.launchd],
                paths: [shell: "/bin/zsh", Real.launchd: "/sbin/launchd"]),
            .none)
    }

    /// An unreadable parent is "I could not tell", which is neither owner and is never acted on.
    func testAnUnreadableChainIsUnknownRatherThanAnAnswer() {
        XCTAssertEqual(
            owner(of: Real.server, desktops: [Real.claudeDesktop], parents: [:], paths: [:]),
            .unknown)
    }

    /// A cycle in the parent chain — corrupted, or a PID reused mid-walk — terminates instead of
    /// spinning, and terminates as "could not tell" rather than as an answer.
    func testACyclicChainTerminates() {
        let a: pid_t = 10
        let b: pid_t = 11
        XCTAssertEqual(
            owner(
                of: a, desktops: [Real.claudeDesktop], parents: [a: b, b: a], paths: [:]),
            .unknown)
    }

    /// With no Claude Desktop running there is nothing for a server to be serving, so the question
    /// is moot rather than answered — and a moot question must never read as a fault.
    func testNoRunningClaudeDesktopIsUnknownNotAbsence() {
        XCTAssertEqual(ClaudeServerLiveness.state(claudeDesktopPIDs: []), .unknown)
    }
}
