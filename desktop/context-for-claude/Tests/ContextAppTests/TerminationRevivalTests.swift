import XCTest

@testable import ContextApp

/// **macOS's own "Quit & Reopen" quits this app and never reopens it.**
///
/// Reported verbatim: *"when I clicked quit and reopen in system settings after granting this
/// permission the app did not reopen itself."* That is not our button. Switching on Screen &
/// System Audio Recording for a running app puts up macOS's alert — `QUIT_APP` in
/// `SecurityPrivacyExtension.appex`, rendered "Quit & Reopen" — and pressing it sends a Quit Apple
/// Event and then does nothing else at all.
///
/// Measured on macOS 26.5.2 (25F84) from the live trace of the real incident, `log show` around the
/// press:
///
/// ```text
/// 11:30:32.358  SecurityPrivacyExtension  (AppKit) trackMouse send action on mouseUp
/// 11:30:32.374  Context for Claude        [AppKit:Application] Handling Quit AppleEvent
/// 11:30:32.374  Context for Claude        Asking app delegate whether applicationShouldTerminate:
/// 11:30:32.374  Context for Claude        App termination approved
/// 11:30:32.388  Context for Claude        Termination complete. Exiting without sudden termination.
/// 11:30:32.415  launchd  [gui/501/application.com.omi.context-for-claude…] exited due to exit(0)
/// ```
///
/// …and then **not one further log line naming this bundle for the next five minutes**. No
/// LaunchServices open request, no runningboard launch job, no failed launch. The reopen half was
/// never attempted. The only thing AppKit does towards it is `_setShouldRestoreStateOnNextLaunch: 1`
/// — state restoration for whenever *something* launches the app next — and this app is
/// `LSUIElement`, so there is no Dock icon and no ⌘-Tab entry for the user to launch it from.
///
/// Two facts follow, and both are load-bearing for the fix:
///
/// 1. The termination is graceful, so `applicationWillTerminate` runs. (Confirmed independently in
///    the same trace: the app's CoreAudio input tore down at 11:30:32.285, which is
///    `Engine.shared.pause()` inside that callback.) There is a moment to act in.
/// 2. Nobody else is going to bring the app back, so it has to bring itself back.
///
/// Everything here is about the one decision that moment turns on, and the half of it that matters
/// most is the half that must answer **no**: an app that resurrects itself after the user presses
/// Quit is an app that cannot be quit, which is a far worse product than one that needs reopening.
final class TerminationRevivalTests: XCTestCase {

    /// The flag is process-wide, which is right for the app and wrong for a suite that runs its
    /// cases in one process. Nothing here may inherit a previous case's answer.
    @MainActor
    override func setUp() {
        super.setUp()
        TerminationOrigin.resetForTesting()
    }

    @MainActor
    override func tearDown() {
        TerminationOrigin.resetForTesting()
        super.tearDown()
    }

    // MARK: - The bug

    /// The reported failure, as the predicate sees it.
    func testASystemQuitMidOnboardingWithAPendingScreenGrantComesBack() {
        XCTAssertTrue(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: true,
                screenGrantPendingRelaunch: true),
            """
            This is "Quit & Reopen" pressed on macOS's own alert: the user granted Screen Recording, \
            macOS ended the process to make the grant take effect, and macOS issued no launch. \
            Nothing else will reopen an LSUIElement app, so this has to.
            """)
    }

    // MARK: - The half that must say no

    /// The failure that would be worse than the bug.
    func testAQuitTheUserPressedIsNotUndone() {
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: true,
                onboardingInProgress: true,
                screenGrantPendingRelaunch: true),
            """
            Every other condition for reviving holds, and it still must not: the user pressed Quit \
            in the menu bar. An app that comes back from its own Quit cannot be quit at all — there \
            is no Dock icon to force-quit from either.
            """)
    }

    /// The menu bar's Quit reaches the predicate through `TerminationOrigin`, so the flag has to be
    /// the thing that actually turns the answer over — not just a boolean nobody reads.
    @MainActor
    func testTheMenuBarQuitFlagIsWhatTurnsTheAnswerOver() {
        XCTAssertFalse(TerminationOrigin.wasRequestedLocally, "a fresh process asked for nothing")

        TerminationOrigin.userAskedToQuit()

        XCTAssertTrue(TerminationOrigin.wasRequestedLocally)
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: TerminationOrigin.wasRequestedLocally,
                onboardingInProgress: true,
                screenGrantPendingRelaunch: true),
            "the same inputs that revive an unasked-for termination must not revive this one")
    }

    /// Log-out, restart and shut-down quit every app exactly the way macOS quits us for a TCC
    /// change — a Quit Apple Event — so `applicationWillTerminate` cannot tell them apart on its
    /// own. `NSWorkspace.willPowerOffNotification` is the only notice, and reopening into a session
    /// that is closing would be the app arguing with the shutdown.
    @MainActor
    func testAPowerOffIsNotATerminationToUndo() {
        TerminationOrigin.systemIsPoweringOff()

        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: TerminationOrigin.wasRequestedLocally,
                onboardingInProgress: true,
                screenGrantPendingRelaunch: true),
            "a Mac that is shutting down is not asking for the app back")
    }

    /// Outside onboarding there is nothing to come back to, and an app that reappears after being
    /// quit is the app refusing to leave.
    func testAFinishedUserIsLeftAlone() {
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: false,
                screenGrantPendingRelaunch: true))
    }

    /// And with no grant waiting on a relaunch there is no reason macOS would have ended us for
    /// this, so a termination arriving here belongs to something else.
    func testNoPendingScreenGrantIsNoReasonToComeBack() {
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: true,
                screenGrantPendingRelaunch: false))
    }

    // MARK: - It cannot loop

    /// **The fork-bomb proof.**
    ///
    /// A process that revives itself on a condition it can satisfy again is a fork bomb, and this one
    /// would be an unkillable menu-bar app respawning forever. It terminates because the successor's
    /// third input is false by construction: the replacement launches *with* the Screen Recording
    /// grant, so `Permissions.screenGrantedAtLaunch` is true, which clears
    /// `context.permission.screen.pendingRelaunch`, which is what `screenNeedsRelaunch` returns.
    ///
    /// The generation rule below is that fact, and the loop drives the real predicate. If a future
    /// change made the predicate depend on something the successor *can* re-satisfy, this runs
    /// forever and the ceiling turns it into a failure rather than a hung suite.
    func testARevivedProcessCannotReviveAgain() {
        /// One process's answers. A generation only ever ends by being terminated by macOS, which is
        /// the worst case for looping — the user is never given a chance to press Quit.
        struct Generation {
            var onboardingInProgress: Bool
            var screenGrantPendingRelaunch: Bool
        }

        // Generation 0: launched before the grant existed, mid-onboarding, user has just granted
        // Screen Recording in System Settings and pressed "Quit & Reopen".
        var generation = Generation(onboardingInProgress: true, screenGrantPendingRelaunch: true)
        var revivals = 0

        for _ in 0..<50 {
            guard
                ContextAppDelegate.shouldReviveAfterTermination(
                    requestedLocally: false,
                    onboardingInProgress: generation.onboardingInProgress,
                    screenGrantPendingRelaunch: generation.screenGrantPendingRelaunch)
            else { break }

            revivals += 1
            // The successor. Onboarding is deliberately still in progress — the resume point is the
            // whole reason the app comes back — so the *only* thing that stops the chain is the
            // grant no longer pending, which is what a process that launched with it reports.
            generation = Generation(onboardingInProgress: true, screenGrantPendingRelaunch: false)
        }

        XCTAssertEqual(
            revivals, 1,
            """
            Exactly one revival per grant. More than one is a fork bomb; zero is the bug. The chain \
            ends because a process that started with the grant reports screenNeedsRelaunch == false.
            """)
    }

    // MARK: - One relauncher, not two

    /// **Static checker, not behavioural coverage.**
    ///
    /// Both revival paths — the card's "Restart to finish" and this delegate — must go through
    /// `Permissions.spawnRelaunchHelper()`. A second copy of that shell script is the defect this
    /// guards: the script encodes the ordering fix (wait for *this* pid to leave the process table,
    /// *then* `open`, so LaunchServices has no live instance to coalesce the launch back onto), and
    /// a copy would drift out of it silently. Running both paths for real means ending the test
    /// process, so the check is on the source text and labelled as such.
    func testBothRevivalPathsShareOneRelauncher() throws {
        let source = try appDelegateSource()

        XCTAssertTrue(
            source.contains("Permissions.spawnRelaunchHelper()"),
            "the terminate path must reuse the shared helper")
        XCTAssertFalse(
            source.contains("/bin/sh"),
            """
            The detached relauncher belongs to Permissions.spawnRelaunchHelper() and nowhere else. \
            A second copy of the script here would drift out of the ordering fix it encodes.
            """)

        let permissions = try permissionsSource()
        XCTAssertEqual(
            permissions.components(separatedBy: "/bin/sh").count - 1, 1,
            "exactly one spawn of the relauncher exists in the product")
    }

    /// **Static checker, not behavioural coverage.**
    ///
    /// `NSApp.terminate` runs `applicationWillTerminate` synchronously, so a flag set *after* it is
    /// a flag set too late — the delegate would already have decided to revive. The ordering is the
    /// whole correctness of the user-quit case and it cannot be observed from a unit test without
    /// ending the test process, so it is checked in the source.
    func testTheMenuBarMarksTheQuitBeforeItAsksForIt() throws {
        let source = try statusViewSource()

        let mark = try XCTUnwrap(
            source.range(of: "TerminationOrigin.userAskedToQuit()"),
            "the menu bar's Quit must say the quit was the user's")
        let terminate = try XCTUnwrap(
            source.range(of: "NSApp.terminate"),
            "expected the menu bar to still be the thing that quits")

        XCTAssertTrue(
            mark.lowerBound < terminate.lowerBound,
            """
            userAskedToQuit() has to run before NSApp.terminate, which invokes \
            applicationWillTerminate synchronously. Marked afterwards, the user's own Quit reads as \
            a termination the app did not ask for and the app comes straight back.
            """)
    }

    // MARK: Helpers

    private func appDelegateSource() throws -> String {
        try strippedSource(at: "ContextApp.swift")
    }

    private func permissionsSource() throws -> String {
        try strippedSource(at: "Permissions.swift")
    }

    private func statusViewSource() throws -> String {
        try strippedSource(at: "MenuBar/StatusView.swift")
    }

    /// Comments stripped, so prose about `/bin/sh` or about the ordering does not stand in for the
    /// code doing it.
    private func strippedSource(at relativePath: String) throws -> String {
        let url = InkSourceSweep.uiSourceRoot.appendingPathComponent(relativePath)
        return InkSourceSweep.strippingComments(from: try String(contentsOf: url, encoding: .utf8))
    }
}
