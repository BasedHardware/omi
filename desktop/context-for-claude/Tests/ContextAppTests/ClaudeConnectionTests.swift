import XCTest

@testable import ContextApp

/// **The claim this app made for three days while it was false.**
///
/// A pre-release developer build wrote its own build directory into Claude Desktop's
/// `claude_desktop_config.json`. The directory was deleted; the entry stayed. Every launch from
/// 2026-08-16 to 2026-08-19, Claude Desktop tried to spawn a binary that was not there and logged
/// `Failed to spawn process: No such file or directory`, and for all three days the menu bar and the
/// Agents pane both read **Connected to Claude Code and Claude Desktop** — because the only question
/// either of them asked was whether an entry existed in a file.
///
/// `ClaudeServerLiveness` could already answer the question that matters, and had been able to since
/// it was written. It was reachable only from the tutorial, which runs once. So the tests here are
/// about the wiring, not about the probe: given the probe's answer, no surface may report a
/// connection Claude cannot use, and every surface must name the one thing that fixes it.
///
/// The probe itself is deliberately not exercised live. It walks the real process table for a real
/// Claude Desktop, so a test that asserted on its output would pass or fail on whether the machine
/// running the suite happened to have Claude open — which is why `ClaudeConnection`'s init takes the
/// state as a parameter and every case below is arranged, not observed.
final class ClaudeConnectionTests: XCTestCase {

    // MARK: - The fact

    /// A restart is claimed **only on evidence**, and `.notServingClaudeDesktop` is the only state
    /// that is evidence. `.unknown` means Claude Desktop is not running or the process list could
    /// not be read, and telling a user to restart an app on that basis would send them to quit
    /// something that is working — or something that is not even open.
    func testOnlyDemonstrableAbsenceAsksForARestart() {
        XCTAssertTrue(
            ClaudeConnection(claudeCode: true, claudeDesktop: true, liveness: .notServingClaudeDesktop)
                .desktopNeedsRestart)
        XCTAssertFalse(
            ClaudeConnection(claudeCode: true, claudeDesktop: true, liveness: .servingClaudeDesktop)
                .desktopNeedsRestart)
        XCTAssertFalse(
            ClaudeConnection(claudeCode: true, claudeDesktop: true, liveness: .unknown)
                .desktopNeedsRestart)
    }

    /// Nothing registered for Claude Desktop means there is nothing for a restart to pick up. The
    /// remedy for that state is connecting, and offering a restart instead would send the user to
    /// quit an app that was never going to gain an entry by relaunching.
    func testAnUnregisteredDesktopIsNeverAskedToRestart() {
        for liveness: ClaudeServerLiveness.State in [
            .notServingClaudeDesktop, .servingClaudeDesktop, .unknown,
        ] {
            XCTAssertFalse(
                ClaudeConnection(claudeCode: true, claudeDesktop: false, liveness: liveness)
                    .desktopNeedsRestart,
                "an unregistered Claude Desktop was asked to restart on \(liveness)")
        }
    }

    /// `desktopIsReachable` is the fact the summaries are allowed to call connected: registered
    /// *and* actually serving. It is what separates "Claude can read this Mac" from "a file on this
    /// Mac says it can".
    func testReachabilityIsRegistrationAndLivenessTogether() {
        XCTAssertTrue(
            ClaudeConnection(claudeCode: false, claudeDesktop: true, liveness: .servingClaudeDesktop)
                .desktopIsReachable)
        XCTAssertFalse(
            ClaudeConnection(claudeCode: false, claudeDesktop: true, liveness: .notServingClaudeDesktop)
                .desktopIsReachable)
        XCTAssertFalse(
            ClaudeConnection(claudeCode: false, claudeDesktop: false, liveness: .servingClaudeDesktop)
                .desktopIsReachable)
    }

    // MARK: - The menu bar

    /// **The regression, at the surface that displayed it.** Registered, not serving: the line may
    /// not name Claude Desktop as connected, and it has to say what to do instead.
    func testTheMenuBarLineDoesNotCallADeadDesktopConnected() {
        let line = ClaudeConnectorLine(
            connection: ClaudeConnection(
                claudeCode: true, claudeDesktop: true, liveness: .notServingClaudeDesktop),
            note: nil,
            isConnecting: false)

        XCTAssertEqual(line.summary, "Connected to Claude Code")
        XCTAssertFalse(
            line.summary.contains("Claude Desktop"),
            "the line still reports a Claude Desktop that cannot answer as connected")
        XCTAssertEqual(line.note, "Quit and reopen Claude Desktop to finish connecting it.")
    }

    /// The state that is *only* a stale Claude Desktop still reads as unsettled, so it draws in the
    /// contrast `StatusView` reserves for a line with something to do about it.
    func testADesktopOnlyConnectionThatCannotAnswerIsNotReportedAsConnected() {
        let line = ClaudeConnectorLine(
            connection: ClaudeConnection(
                claudeCode: false, claudeDesktop: true, liveness: .notServingClaudeDesktop),
            note: nil,
            isConnecting: false)

        XCTAssertEqual(line.summary, "Not connected to Claude")
        XCTAssertFalse(line.isConnected)
    }

    /// **No button that cannot help.** `Connect` rewrites the two config files, which in this state
    /// are already correct — pressing it would change nothing the user can see and leave them with
    /// the same dead connector. The registration is on disk, so the press is withheld and the note
    /// carries the remedy.
    func testTheConnectPressIsNotOfferedWhenItWouldRewriteACorrectConfig() {
        let stale = ClaudeConnectorLine(
            connection: ClaudeConnection(
                claudeCode: false, claudeDesktop: true, liveness: .notServingClaudeDesktop),
            note: nil,
            isConnecting: false)
        XCTAssertNil(stale.action, "offered a press that rewrites a config that is already correct")

        // …and it is still offered when nothing is registered, which is the state it is for.
        let nothing = ClaudeConnectorLine(
            connection: ClaudeConnection(claudeCode: false, claudeDesktop: false, liveness: .unknown),
            note: nil,
            isConnecting: false)
        XCTAssertEqual(nothing.action, "Connect")
    }

    /// The note slot is shared, and the sentence about the press the user just made is the fresher
    /// fact. A standing condition they can act on at any time must not push it out.
    func testAFreshRegistrationMessageOutranksTheStandingRemedy() {
        let line = ClaudeConnectorLine(
            connection: ClaudeConnection(
                claudeCode: true, claudeDesktop: true, liveness: .notServingClaudeDesktop),
            note: "Connected to Claude Code and Claude Desktop.",
            isConnecting: false)

        XCTAssertEqual(line.note, "Connected to Claude Code and Claude Desktop.")
    }

    /// Every state that is *not* the new one is byte-for-byte what it was before liveness existed.
    /// The point of the change is one new state, not new wording for the four that were right.
    func testTheSettledStatesAreUnchanged() {
        let expected: [(Bool, Bool, String)] = [
            (true, true, "Connected to Claude Code and Claude Desktop"),
            (true, false, "Connected to Claude Code"),
            (false, true, "Connected to Claude Desktop"),
            (false, false, "Not connected to Claude"),
        ]
        for (code, desktop, summary) in expected {
            for liveness: ClaudeServerLiveness.State in [.unknown, .servingClaudeDesktop] {
                let line = ClaudeConnectorLine(
                    connection: ClaudeConnection(
                        claudeCode: code, claudeDesktop: desktop, liveness: liveness),
                    note: nil,
                    isConnecting: false)
                XCTAssertEqual(line.summary, summary, "code=\(code) desktop=\(desktop) live=\(liveness)")
                XCTAssertNil(line.note, "a settled state grew a note")
            }
        }
    }

    // MARK: - The settings pane

    /// The same regression at the other surface. The pane says what is connected *and* what is
    /// pending, because both are facts the user needs — one of them to know it worked, the other to
    /// know it has not finished.
    func testTheSettingsSubtitleReportsThePendingRestart() {
        let subtitle = SettingsAgentsPane.connectionSubtitle(
            ClaudeConnection(claudeCode: true, claudeDesktop: true, liveness: .notServingClaudeDesktop))

        XCTAssertEqual(
            subtitle,
            "Connected to Claude Code. Quit and reopen Claude Desktop to finish connecting it.")
    }

    /// A working connection gains no nagging sentence, and the probe having said nothing yet is
    /// still reported as not knowing rather than as a failure.
    func testTheSettingsSubtitleStaysQuietWhenThereIsNothingToFix() {
        XCTAssertEqual(
            SettingsAgentsPane.connectionSubtitle(
                ClaudeConnection(
                    claudeCode: true, claudeDesktop: true, liveness: .servingClaudeDesktop)),
            "Connected to Claude Code and Claude Desktop.")
        XCTAssertEqual(
            SettingsAgentsPane.connectionSubtitle(nil), "Checking whether Claude is connected…")
    }
}
