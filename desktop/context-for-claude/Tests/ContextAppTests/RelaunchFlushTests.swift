import XCTest

@testable import ContextApp

/// **"Restart to finish" is the button this app puts in front of a user the moment they grant
/// Screen Recording, and it used to end the process with `exit(0)`.**
///
/// `exit(0)` does not run `applicationWillTerminate`. That callback is the app's only flush — it
/// closes the open capture session and writes the final heartbeat, and its own note says what
/// happens without it: *"the last session stays open forever and `status()` reports a recording
/// that stopped hours ago."* So every restart from this button left one behind, and did it on the
/// one path through this app that produced no `Termination —` line at all, which is why three
/// rounds of debugging the disappearing app could not see it.
///
/// **This was not the cause of the reported disappearance, and that is worth writing down rather
/// than implying.** Over twelve hours of this install's unified log there is not one
/// `Relaunch helper … will reopen` milestone and not one `Relaunch helper failed to spawn` error,
/// so `Permissions.relaunchApp()` was never reached — the terminations the user saw were a Quit
/// Apple Event and a Sparkle update. The defect here is real, it is on the path a user takes
/// immediately after granting a permission, and it is not what they hit.
///
/// The seam is `prepareRelaunch(spawnHelper:)`. The two lines after it — mark the origin, ask
/// AppKit to terminate — cannot be run without ending this process, so the property they carry is
/// asserted where it is observable: through `TerminationOrigin`, and through one labelled source
/// check for the `exit(0)` that must not come back.
final class RelaunchFlushTests: XCTestCase {

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

    // MARK: - A restart that cannot happen must not take the app with it

    /// The failure that would be worst of all: the user presses a button labelled "Restart to
    /// finish" and is left with nothing to finish it in.
    func testAHelperThatNeverCameUpDoesNotLicenseEndingTheProcess() {
        XCTAssertFalse(
            Permissions.prepareRelaunch(spawnHelper: { false }),
            """
            Nothing is going to reopen this bundle, so ending it would leave the user with no app. \
            Staying up costs them a click; exiting costs them the product.
            """)
    }

    /// …and the ordinary case still goes through, or the button does nothing at all.
    func testAHelperThatIsUpLicensesEndingTheProcess() {
        XCTAssertTrue(Permissions.prepareRelaunch(spawnHelper: { true }))
    }

    /// The helper is spawned **before** anything ends the process, not after. Reversed, a restart
    /// whose spawn fails has already killed the app by the time it finds out.
    func testTheHelperIsAskedForBeforeTheDecisionToEndIsTaken() {
        var spawnedFirst = false
        let licensed = Permissions.prepareRelaunch(spawnHelper: {
            spawnedFirst = true
            return true
        })

        XCTAssertTrue(spawnedFirst, "the replacement has to be arranged while there is still a process to arrange it")
        XCTAssertTrue(licensed)
    }

    // MARK: - A restart is not a termination to undo

    /// **The restart must not spawn a second helper on top of its own.**
    ///
    /// `relaunchApp` now ends the process through `NSApp.terminate`, which runs the delegate — and
    /// the delegate's whole job at that moment is to reopen a run macOS ended. A restart pressed
    /// seconds after a grant landed is *exactly* the shape it revives: a termination nobody here
    /// asked for, with a grant that just arrived. Marking the origin is what stops the app arranging
    /// a second relaunch and spending a revival from the budget for it.
    @MainActor
    func testARestartArrangedHereIsNotRevivedAgainByTheDelegate() {
        XCTAssertFalse(TerminationOrigin.wasRequestedLocally, "a fresh process asked for nothing")

        TerminationOrigin.relaunchWasArrangedHere()

        XCTAssertTrue(TerminationOrigin.wasRequestedLocally)
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: TerminationOrigin.wasRequestedLocally,
                onboardingInProgress: true,
                aGrantJustArrived: true,
                revivalsAlreadySpent: 0),
            """
            Every other input says revive — a grant just landed, a run is waiting, the budget is \
            untouched — and it still must not, because the successor is already spoken for.
            """)
    }

    // MARK: - The flush

    /// **Static checker, not behavioural coverage.**
    ///
    /// What guarantees the flush is that the process ends through AppKit rather than through
    /// `exit`: `NSApp.terminate` runs `applicationWillTerminate`, which is where `Engine.pause()`
    /// lives, and `exit(0)` runs neither. Proving that by observation means ending this process, so
    /// the guard is on the source and labelled as such.
    func testTheRestartEndsTheProcessThroughAppKitRatherThanExit() throws {
        let source = try permissionsSource()
        let relaunch = try XCTUnwrap(
            source.range(of: "static func relaunchApp()"),
            "expected the restart to still be here")
        let body = String(source[relaunch.upperBound...].prefix(600))

        XCTAssertTrue(
            body.contains("NSApp.terminate"),
            """
            The flush has one owner — applicationWillTerminate — and terminate is what runs it. A \
            second copy of the teardown here would be the same defect as a second copy of the \
            relauncher script.
            """)
        XCTAssertFalse(
            body.contains("exit("),
            """
            exit(0) skips applicationWillTerminate, so the open capture session is never closed and \
            status() goes on reporting a recording that stopped hours ago. It also skips the \
            Termination milestone, which is why this path left no trace in the log.
            """)
    }

    private func permissionsSource() throws -> String {
        let url = InkSourceSweep.uiSourceRoot.appendingPathComponent("Permissions.swift")
        return InkSourceSweep.strippingComments(from: try String(contentsOf: url, encoding: .utf8))
    }
}
