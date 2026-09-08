import XCTest

@testable import ContextApp

/// **macOS's own "Quit & Reopen" quits this app and never reopens it.**
///
/// Reported verbatim, three times: *"Also quit and reopen does not reopen automatically. THIS NEEDS
/// TO WORK."* That is not our button. Switching a TCC service on for a running app puts up macOS's
/// alert — `QUIT_APP` in `SecurityPrivacyExtension.appex`, rendered "Quit & Reopen" — and pressing
/// it sends a Quit Apple Event and then does nothing else at all.
///
/// Measured on macOS 26.5.2 (25F84) from the live trace of the first incident, `log show` around
/// the press:
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
    @MainActor
    func testASystemQuitMidOnboardingComesBack() {
        XCTAssertTrue(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: true,
                aGrantJustArrived: false,
                revivalsAlreadySpent: 0),
            """
            This is "Quit & Reopen" pressed on macOS's own alert: the user answered a permission, \
            macOS ended the process to make the answer take effect, and macOS issued no launch. \
            Nothing else will reopen an LSUIElement app, so this has to.
            """)
    }

    /// **The regression.** The first fix shipped with a third clause — "a Screen Recording grant is
    /// waiting on a relaunch" — and the user lost their app again, because the "Quit & Reopen" they
    /// actually pressed was macOS's **Accessibility** alert. From the live trace of that failure:
    ///
    /// ```text
    /// 14:07:49.825  SecurityPrivacyExtension  kTCCServiceAccessibility  com.omi.context-for-claude  full
    /// 14:07:49.828  SecurityPrivacyExtension  kTCCServiceScreenCapture  com.omi.context-for-claude  none
    /// 14:07:51.267  SecurityPrivacyExtension  AESendMessage(aevt,quit target='kpid'[pid=13102 …
    /// 14:07:51.280  Context for Claude        [AppKit:Application] Handling Quit AppleEvent
    /// 14:07:51.325  launchservicesd           QUITTING: pid=13102
    /// ```
    ///
    /// Screen Recording was `none` — never granted, `context.permission.screen.pendingRelaunch = 0`
    /// in the user's defaults afterwards — so the clause was false and no helper was spawned. The
    /// next launch of the bundle is twenty-five seconds later, which is the user reopening it by
    /// hand.
    ///
    /// The permissions card lists four capabilities and macOS raises that alert for more than one of
    /// them, so the predicate must not name a permission at all.
    @MainActor
    func testAnAccessibilityQuitAndReopenComesBackToo() {
        XCTAssertTrue(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: true,
                aGrantJustArrived: false,
                revivalsAlreadySpent: 0),
            """
            Accessibility was just granted and Screen Recording never was. The app is still \
            mid-onboarding and macOS still ended it, so it still has to come back — the reason \
            macOS chose to quit us is not something this decision may depend on.
            """)
    }

    // MARK: - The half that must say no

    /// The failure that would be worse than the bug.
    @MainActor
    func testAQuitTheUserPressedIsNotUndone() {
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: true,
                onboardingInProgress: true,
                aGrantJustArrived: false,
                revivalsAlreadySpent: 0),
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
                aGrantJustArrived: false,
                revivalsAlreadySpent: 0),
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
                aGrantJustArrived: false,
                revivalsAlreadySpent: 0),
            "a Mac that is shutting down is not asking for the app back")
    }

    /// With no run waiting and no grant behind it, an app that reappears after being quit is the app
    /// refusing to leave.
    ///
    /// **This is what bounds both clauses, and the second one needed it more than the first.**
    /// "Somebody other than the user ended us" would have covered the reported bug in one line and
    /// must not be used: measured in this app's own log, an ordinary Sparkle update is an external
    /// quit too — the updater launches at 13:35:18 and the app is terminated at 13:35:21, with
    /// `requestedLocally=false` — and reviving that would race the relaunch Sparkle is already
    /// performing. `killall` and an Activity Monitor quit land here identically.
    @MainActor
    func testAnExternalQuitWithNothingBehindItIsLeftAlone() {
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: false,
                aGrantJustArrived: false,
                revivalsAlreadySpent: 0))
    }

    // MARK: - The third report: a permission granted after setup

    /// **The reported bug**, in the user's words: *"The app crashes upon giving permissions."*
    ///
    /// There is no crash. No `.ips` report exists for this bundle in either DiagnosticReports
    /// directory, and the exit is clean. What happens is that the user opens Privacy & Security to
    /// turn a stale switch off and on — the remedy `Permissions.staleGrantReason` tells them to use
    /// — and macOS recycles the process so the new grant can take effect:
    ///
    /// ```text
    /// 11:40:09  tccd                accessing={SecurityPrivacyExtension, pid=9049}
    /// 11:40:11  Context for Claude  [AppKit:Application] Handling Quit AppleEvent
    /// 11:40:11  Context for Claude  Termination — requestedLocally=false onboardingInProgress=false
    ///                               tutorialBeat=none revivalsSpent=0/3 → staying quit
    /// 11:40:11  launchservicesd     QUITTING: pid=9394
    /// ```
    ///
    /// Setup was finished, so `onboardingInProgress` was false and the whole predicate fell at the
    /// second clause. From the user's chair the app vanished at the exact moment they told it to
    /// start recording, and capture stopped silently while they believed it had just been switched
    /// on — which is worse than useless for a capture app.
    @MainActor
    func testAPermissionGrantedAfterSetupBringsTheAppBack() {
        XCTAssertTrue(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: false,
                aGrantJustArrived: true,
                revivalsAlreadySpent: 0),
            """
            A grant this process could not use has just become one it can, and macOS ended the \
            process precisely so a successor could pick it up. Nothing else is going to launch that \
            successor.
            """)
    }

    /// The half that must still say no, on the new clause as much as the old one. A grant landing
    /// two minutes before the user presses ⌘Q does not make ⌘Q something to undo.
    @MainActor
    func testAUserQuitOutranksAGrantThatJustArrived() {
        TerminationOrigin.userAskedToQuit()

        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: TerminationOrigin.wasRequestedLocally,
                onboardingInProgress: false,
                aGrantJustArrived: true,
                revivalsAlreadySpent: 0),
            """
            The grant clause is a reason to come back from a termination nobody here asked for. It \
            is never a reason to come back from one the user did.
            """)
    }

    /// …and the same for a Mac that is closing the session. Granting a permission and then choosing
    /// Restart is an entirely ordinary sequence, and the app must go quietly.
    @MainActor
    func testAPowerOffOutranksAGrantThatJustArrived() {
        TerminationOrigin.systemIsPoweringOff()

        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: TerminationOrigin.wasRequestedLocally,
                onboardingInProgress: false,
                aGrantJustArrived: true,
                revivalsAlreadySpent: 0),
            "reopening into a session that is closing is the app arguing with the shutdown")
    }

    /// The ceiling binds the new clause too. Four capabilities on one card is four consecutive
    /// grants, so this is a path a real user can walk rather than a hypothetical.
    @MainActor
    func testTheBudgetStillStopsAGrantDrivenChain() {
        XCTAssertFalse(
            ContextAppDelegate.shouldReviveAfterTermination(
                requestedLocally: false,
                onboardingInProgress: false,
                aGrantJustArrived: true,
                revivalsAlreadySpent: RevivalBudget.allowance),
            """
            An app that respawns forever is worse than an app that needs reopening, and the \
            allowance has to bound every route into the revival rather than only the first one.
            """)
    }

    // MARK: - It cannot loop

    /// **The fork-bomb proof.**
    ///
    /// A process that revives itself on a condition it can satisfy again is a fork bomb, and this one
    /// would be an unkillable menu-bar app respawning forever. The old predicate terminated by
    /// accident of a neighbouring subsystem: the successor launched *with* the Screen Recording
    /// grant, which cleared `screenPendingRelaunch`, which made the third argument false. That
    /// argument is gone, so the ceiling is now the predicate's own.
    ///
    /// The loop below drives the real predicate with the worst case for looping — every generation
    /// ends by being terminated by macOS mid-onboarding, so the user is never given a chance to
    /// press Quit and nothing else ever turns false. If a future change removed the ceiling this
    /// runs to its bound and fails rather than hanging.
    @MainActor
    func testTheChainOfRevivalsTerminates() {
        var spent = 0
        var revivals = 0

        for _ in 0..<50 {
            guard
                ContextAppDelegate.shouldReviveAfterTermination(
                    requestedLocally: false,
                    onboardingInProgress: true,
                    aGrantJustArrived: false,
                    revivalsAlreadySpent: spent)
            else { break }

            revivals += 1
            // The successor inherits the spend, which is the whole point of persisting it.
            spent += 1
        }

        XCTAssertEqual(
            revivals, RevivalBudget.allowance,
            """
            The chain has to end, and it has to end at the stated allowance rather than wherever an \
            unrelated permission flag happens to fall over.
            """)
    }

    /// The same proof for the clause that has no unfinished run under it.
    ///
    /// The worst case for looping is sharper here than it is for onboarding, because the successor
    /// launches *holding* the grant — so if the ledger behind `aGrantJustArrived` were ever
    /// persisted, every generation would read its predecessor's arrival and the chain would only be
    /// stopped by the budget. This drives the predicate as though that had happened.
    @MainActor
    func testAGrantDrivenChainTerminatesToo() {
        var spent = 0
        var revivals = 0

        for _ in 0..<50 {
            guard
                ContextAppDelegate.shouldReviveAfterTermination(
                    requestedLocally: false,
                    onboardingInProgress: false,
                    aGrantJustArrived: true,
                    revivalsAlreadySpent: spent)
            else { break }

            revivals += 1
            spent += 1
        }

        XCTAssertEqual(revivals, RevivalBudget.allowance, "the ceiling is the predicate's own, on both routes in")
    }

    // MARK: - What counts as a grant arriving

    /// A first sighting is the baseline this process starts from, not a change to act on.
    ///
    /// Without this every launch of a Mac that is granted everything would look like four grants
    /// landing at once, and the first external quit of the session would reopen the app.
    func testTheFirstSightingOfACapabilityIsNotAnArrival() {
        let ledger = GrantLedger()

        ledger.observe(.screen, granted: true, now: 100)

        XCTAssertNil(
            ledger.secondsSinceGrantArrived(now: 100),
            "there is nothing before the first reading for it to differ from")
    }

    /// The reported episode, through the ledger: ungranted at launch, granted a moment before the
    /// quit.
    func testAnUngrantedCapabilityBecomingGrantedIsAnArrival() {
        let ledger = GrantLedger()

        ledger.observe(.accessibility, granted: false, now: 100)
        ledger.observe(.accessibility, granted: true, now: 160)

        XCTAssertEqual(ledger.secondsSinceGrantArrived(now: 162), 2)
    }

    /// **A permission taken away is not a permission given.**
    ///
    /// macOS raises the same "Quit & Reopen" alert when a switch goes off, so this is a live path
    /// rather than a hypothetical — and an app that reopens itself after the user revokes its
    /// access is the app arguing with them about the one thing they are most entitled to decide.
    func testARevokedGrantIsNotAnArrival() {
        let ledger = GrantLedger()

        ledger.observe(.microphone, granted: true, now: 100)
        ledger.observe(.microphone, granted: false, now: 160)

        XCTAssertNil(ledger.secondsSinceGrantArrived(now: 161))
    }

    /// **The stamp is the transition, not the readings that follow it.**
    ///
    /// The engine re-reads every capability every thirty seconds. If each of those readings renewed
    /// the stamp, a grant made once at breakfast would keep the app inside the arrival window for
    /// the rest of the day — and every external quit in it, an update included, would be undone.
    func testAGrantThatHasBeenInPlaceForHoursIsNotAnArrival() {
        let ledger = GrantLedger()

        ledger.observe(.screen, granted: false, now: 0)
        ledger.observe(.screen, granted: true, now: 60)
        // Six hours of the ordinary poll, all of it agreeing with what it already saw.
        for tick in stride(from: 90.0, through: 21_600, by: 30) {
            ledger.observe(.screen, granted: true, now: tick)
        }

        XCTAssertEqual(
            ledger.secondsSinceGrantArrived(now: 21_600), 21_540,
            "the arrival stays where it happened; a poll is not an event")
        XCTAssertFalse(
            Permissions.grantArrivedRecently(
                secondsSince: ledger.secondsSinceGrantArrived(now: 21_600),
                within: Permissions.grantArrivalSeconds))
    }

    /// The window itself, asserted without a TCC record moving.
    func testTheArrivalWindowBoundsTheDecisionInBothDirections() {
        let window = Permissions.grantArrivalSeconds

        XCTAssertFalse(
            Permissions.grantArrivedRecently(secondsSince: nil, within: window),
            "nothing has arrived, so nothing is a reason to reopen")
        XCTAssertTrue(
            Permissions.grantArrivedRecently(secondsSince: 2, within: window),
            "two seconds is the measured gap between the switch and the Quit Apple Event")
        XCTAssertFalse(
            Permissions.grantArrivedRecently(secondsSince: window + 1, within: window),
            "outside the window this is an ordinary external quit and the app stays quit")
        XCTAssertFalse(
            Permissions.grantArrivedRecently(secondsSince: -1, within: window),
            """
            A clock that moved backwards leaves a stamp in the future. It has to read as "nothing \
            arrived" rather than as a licence to reopen — staying quit is the safe direction for \
            every clause of this decision.
            """)
    }

    /// End to end on the live seam: a process in which nobody has granted anything has nothing to
    /// come back for, whatever this Mac happens to be allowed to do.
    ///
    /// The one assertion here that is machine-independent, and it is the one worth having: the
    /// first reading of each capability is a baseline, so no arrangement of TCC records on the
    /// machine running the suite can make this answer true.
    func testALiveProcessWithNoGrantChangeReportsNoArrival() {
        XCTAssertFalse(
            Permissions.aGrantJustArrived(),
            """
            Nothing was granted during this test process, so the delegate must not be told a grant \
            arrived — a predicate that answered from the current grant state rather than from a \
            change would reopen the app after any external quit at all.
            """)
    }

    /// The successor only inherits the ceiling if the spend actually reaches it, so the budget's
    /// own arithmetic is asserted rather than assumed.
    @MainActor
    func testTheBudgetForgetsRevivalsOlderThanItsWindow() {
        let now: Double = 1_000_000
        let stamps = [
            now - RevivalBudget.window - 1,  // yesterday's onboarding, or last week's
            now - RevivalBudget.window + 1,  // just inside
            now - 5,
        ]

        XCTAssertEqual(
            RevivalBudget.inWindow(stamps, now: now).count, 2,
            """
            A revival that happened outside the window is not evidence of a loop — it is a user who \
            came back to setup later, and holding it against them would leave the app dead for the \
            same reason the bug did.
            """)
    }

    /// A clock that moved backwards must not be able to hide a revival from the ceiling.
    @MainActor
    func testAStampFromTheFutureStillCountsAgainstTheBudget() {
        let now: Double = 1_000_000

        XCTAssertEqual(
            RevivalBudget.inWindow([now + 30], now: now).count, 1,
            """
            Ignoring stamps ahead of the clock would make a ceiling that silently stops being one \
            the moment time moves. Counting them errs towards staying quit, which is the safe \
            direction for every clause of this decision.
            """)
    }

    /// End to end on the real storage: a spend has to be visible to the process that reads it next,
    /// because the reader is a different process every time.
    @MainActor
    func testASpentRevivalIsVisibleToTheNextProcess() throws {
        let suite = "context.revival.test.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }

        let now: Double = 2_000_000
        XCTAssertEqual(RevivalBudget(defaults: defaults).recent(now: now).count, 0)

        RevivalBudget(defaults: defaults).record(now: now)

        // A *fresh* value reading the same storage, which is what the successor process is.
        XCTAssertEqual(
            RevivalBudget(defaults: defaults).recent(now: now + 1).count, 1,
            "a budget the successor cannot see is not a ceiling at all")
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

    // MARK: - Leaving a trace

    /// **Static checker, not behavioural coverage.**
    ///
    /// The decision has to be readable from `log show` after the fact, which means two things at
    /// once and both of them failed last time. It has to log **whichever way it goes** — the first
    /// version only logged the yes branch, so the failure produced silence — and it has to log at a
    /// level unified logging keeps on disk. `ContextLog.info` is `OS_LOG_TYPE_INFO`, which lives in
    /// a memory ring buffer: measured on this Mac, the oldest readable `INFO` line was four minutes
    /// old while `DEFAULT` lines from thirty-four minutes back were still there.
    ///
    /// Emitting the line means ending a process, so the guard is on the source and labelled as such.
    func testTheRevivalDecisionLeavesAPersistedTrace() throws {
        let source = try appDelegateSource()
        let decision = try XCTUnwrap(
            source.range(of: "shouldReviveAfterTermination("),
            "expected the delegate to still ask the predicate")
        let tail = String(source[decision.upperBound...])

        let logged = try XCTUnwrap(
            tail.range(of: "ContextLog.milestone("),
            """
            The decision must be logged at a level that persists. ContextLog.info is thrown away \
            within minutes, which is why the second failure had no trace to read at all.
            """)
        let bail = try XCTUnwrap(
            tail.range(of: "guard revive else { return }"),
            "expected the delegate to still stop when the answer is no")

        XCTAssertTrue(
            logged.lowerBound < bail.lowerBound,
            """
            Logged *before* the early return, so a decision not to revive is as readable as a \
            decision to revive. Only the yes branch was recorded last time, and the failure the \
            user reported was a no.
            """)

        for input in [
            "requestedLocally=", "onboardingInProgress=", "grantJustArrived=", "revivalsSpent=",
        ] {
            XCTAssertTrue(
                tail.contains(input),
                "the line has to carry \(input) or it cannot say why the answer was what it was")
        }
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
