import ContextCore
import XCTest

@testable import ContextApp

/// **The permission this app asked for over and over while the switch was already on.**
///
/// Reported with two screenshots taken at the same moment: a system alert reading *"Context for
/// Claude would like to record this computer's screen and audio. Grant access to this application in
/// Privacy & Security settings."*, and System Settings ▸ Privacy & Security ▸ Screen & System Audio
/// Recording with `Context for Claude` in the list and its switch **on**. The alert came back every
/// few seconds.
///
/// Measured in this install's own log, over the launch that produced the report:
///
/// ```
/// 13:36:07 [screen] Shareable content unavailable: The user declined TCCs for application, window,
///                   display capture
/// 17:48:10 [engine] Screen capture has produced nothing for 3 minutes — macOS is refusing this
///                   app's screen requests.
/// 17:48:39 [engine] Rebuilding the screen watcher after a stall: …
/// 17:51:41 [engine] Screen capture has produced nothing for 3 minutes …
/// 17:52:10 [engine] Rebuilding the screen watcher after a stall: …
/// ```
///
/// Those two lines cannot both happen unless `Permissions.screenBlock()` returned `nil` — the
/// blocked branch of `ScreenWatcher.tickOutcome()` calls `noteServed()`, so a screen the app knows is
/// blocked can never arm the stall clock. So: `CGPreflightScreenCaptureAccess()` was `true`,
/// ScreenCaptureKit answered `userDeclined`, and the app's own reading of that pair was "nothing is
/// in your way". `nil` is not a status — it is a licence to ask the WindowServer again in three
/// seconds, and every one of those asks is the TCC request macOS answers with that alert.
///
/// Why the state was unreachable rather than merely mishandled: `.needsRelaunch` was derived from
/// `screenGrantedAtLaunch` alone, so it could only ever describe a grant that arrived *after* launch.
/// This app had just been re-released as a notarized Developer ID build, which invalidates the TCC
/// records keyed to the old signature — the user re-granted, relaunched, and the preflight was
/// therefore `true` **at launch**, which is exactly the input that says "nothing is waiting on a
/// relaunch". The predicate written for "TCC says yes and this process cannot use it" was switched
/// off by the only situation that produces it.
///
/// The seam is the refusal, injected. Nothing here touches TCC, a window server or a display: the
/// tests drive `Permissions`' real decision functions tick by tick and count how many times the
/// capture path is allowed to ask.
final class ScreenStaleGrantTests: XCTestCase {

    // MARK: - The driver

    /// One launch of the real gate, played one tick at a time.
    ///
    /// `attempts` counts requests that reach ScreenCaptureKit — which is what the user experiences as
    /// prompts, because macOS answers each refused one with the alert. Everything it consults is the
    /// production rule; the only thing this stands in for is the OS.
    private struct Launch {
        /// What `CGPreflightScreenCaptureAccess()` says. `true` throughout these tests: the switch is
        /// on, which is the half of the report that makes it a bug rather than a missing permission.
        var preflightGranted = true
        /// Whether the preflight already read `true` when this process connected to the window server.
        var grantedAtLaunch = true
        /// Whether this install has ever captured, which is what separates `.grantLost` from
        /// `.notGranted`.
        var hasEverCaptured = true

        /// The injected OS: whether ScreenCaptureKit answers `userDeclined` to a request.
        var osDeclines = false

        /// Requests that actually reached ScreenCaptureKit.
        private(set) var attempts = 0
        /// The refusal `Permissions.noteScreenCaptureDeclined()` records, process-scoped.
        private(set) var captureDeclined = false
        private(set) var lastBlock: Permissions.ScreenBlock?

        /// `ScreenWatcher.tickOutcome()`'s gate, then the request it guards.
        mutating func tick() {
            let needsRelaunch =
                preflightGranted
                && Permissions.screenGrantIsStale(
                    grantedAtLaunch: grantedAtLaunch, captureDeclined: captureDeclined)
            lastBlock = Permissions.screenBlock(
                granted: preflightGranted,
                hasEverCaptured: hasEverCaptured,
                needsRelaunch: needsRelaunch,
                recordIsUnusable: preflightGranted
                    && Permissions.screenGrantStaleness(
                        grantedAtLaunch: grantedAtLaunch, captureDeclined: captureDeclined)
                        == .recordUnusable)
            guard lastBlock == nil else { return }

            attempts += 1
            if osDeclines { captureDeclined = true }
        }

        mutating func run(ticks: Int) {
            for _ in 0..<ticks { tick() }
        }
    }

    // MARK: - The regression

    func testARefusedProcessAsksOnceAndThenStopsAsking() {
        var launch = Launch()
        launch.osDeclines = true

        // An hour at the watcher's three-second cadence.
        launch.run(ticks: 1_200)

        XCTAssertEqual(
            launch.attempts, 1,
            "a process ScreenCaptureKit has refused must ask exactly once; before the fix this was "
                + "one request every tick, and macOS answers each refused request with the "
                + "\"would like to record this computer's screen and audio\" alert")
    }

    /// **The refusal that survives the relaunch the app asked for.**
    ///
    /// `grantedAtLaunch` defaults to `true` here, which is the whole content of this case: the
    /// process started already holding the grant. There is nothing for a reopen to change — the
    /// successor starts holding the same grant and is refused for the same reason — so telling the
    /// user to reopen is a loop, and they went round it. Live, in two consecutive processes:
    ///
    /// ```text
    /// 11:39:56  Context for Claude[9394]  ScreenCaptureKit refused this process …
    /// 11:42:13  Context for Claude[9660]  ScreenCaptureKit refused this process …
    /// ```
    ///
    /// Reported as *"Granting screen permissions doesn't work. I've already granted permissions."*
    func testARefusalThatOutlivedTheRelaunchIsNotAnotherRelaunchNudge() {
        var launch = Launch()
        launch.osDeclines = true
        launch.run(ticks: 2)

        XCTAssertEqual(
            launch.lastBlock, .recordUnusable,
            "the reopen has already happened and the refusal is still here, so the record is the "
                + "thing that is wrong — a second relaunch nudge is the dead end the user reported")
    }

    /// The inverse, and the case that must keep working: a grant that landed *after* this process
    /// connected to the window server genuinely is fixed by reopening, and must still say so.
    ///
    /// Without this, the fix above would be a rename — every refusal would tell every user to run a
    /// Terminal command, including the ordinary ones two seconds from being fine.
    func testAGrantThatArrivedMidRunStillJustAsksToBeReopened() {
        var launch = Launch()
        launch.grantedAtLaunch = false
        launch.osDeclines = true
        launch.run(ticks: 2)

        XCTAssertEqual(
            launch.lastBlock, .needsRelaunch,
            "this process was simply early; the next one gets the grant and nothing is wrong with "
                + "the record")
    }

    /// The half that makes the count above meaningful: the gate must not have simply switched screen
    /// capture off. A healthy process keeps capturing on every tick.
    func testAWorkingProcessIsNeverStoodDown() {
        var launch = Launch()
        launch.osDeclines = false
        launch.run(ticks: 1_200)

        XCTAssertEqual(launch.attempts, 1_200, "nothing refused this process, so nothing may stop it")
        XCTAssertNil(launch.lastBlock, "a capturing screen has no block to report")
    }

    // MARK: - The inputs, separately

    /// The exact shape of the shipped defect, as a unit: granted before launch, refused by the OS,
    /// and the predicate saying there is nothing to do.
    func testAGrantThatWasAlreadyOnAtLaunchCanStillBeStale() {
        XCTAssertTrue(
            Permissions.screenGrantIsStale(grantedAtLaunch: true, captureDeclined: true),
            "a re-signed bundle is granted *before* it launches, so launch ordering cannot detect "
                + "it — the OS's own refusal is the only evidence there is")
    }

    func testAGrantThatArrivedAfterLaunchStillNeedsARelaunch() {
        // The case the predicate was originally written for, unchanged.
        XCTAssertTrue(
            Permissions.screenGrantIsStale(grantedAtLaunch: false, captureDeclined: false))
    }

    func testAGrantHeldSinceLaunchAndNeverRefusedIsNotStale() {
        // The ordinary healthy launch. Claiming staleness here would nag every working install to
        // restart itself forever.
        XCTAssertFalse(
            Permissions.screenGrantIsStale(grantedAtLaunch: true, captureDeclined: false))
    }

    // MARK: - The other two thirds of the trichotomy

    /// `.needsRelaunch` must not swallow the two cases that are genuinely about the user, or this
    /// becomes an app that answers "restart me" to a permission nobody ever granted.
    func testAnUngrantedScreenIsStillTheUsersOwnChoice() {
        XCTAssertEqual(
            Permissions.screenBlock(
                granted: false, hasEverCaptured: false, needsRelaunch: false, recordIsUnusable: false),
            .notGranted)
    }

    func testAGrantThisInstallUsedAndLostIsStillARegression() {
        XCTAssertEqual(
            Permissions.screenBlock(
                granted: false, hasEverCaptured: true, needsRelaunch: false, recordIsUnusable: false),
            .grantLost)
        XCTAssertTrue(
            Permissions.screenBlock(
                granted: false, hasEverCaptured: true, needsRelaunch: false, recordIsUnusable: false)?
                .isRegression == true,
            "a promise that stopped being kept has to be logged as one")
    }

    // MARK: - Telling the two stale states apart

    /// The reported state, as a unit. This is the one the boolean could not express.
    func testAGrantHeldSinceLaunchAndStillRefusedIsAnUnusableRecord() {
        XCTAssertEqual(
            Permissions.screenGrantStaleness(grantedAtLaunch: true, captureDeclined: true),
            .recordUnusable,
            """
            The process started holding the grant and macOS refused it anyway. Window-server \
            capture rights are settled at connection time, so the successor starts from exactly \
            here — there is no reopening out of this.
            """)
    }

    /// The state the original predicate was written for, still named the way it was.
    func testAGrantThatArrivedAfterLaunchIsWaitingOnARelaunch() {
        XCTAssertEqual(
            Permissions.screenGrantStaleness(grantedAtLaunch: false, captureDeclined: false),
            .waitingOnRelaunch)
        XCTAssertEqual(
            Permissions.screenGrantStaleness(grantedAtLaunch: false, captureDeclined: true),
            .waitingOnRelaunch,
            """
            A refusal in a process that was early is still just a process that was early. Only a \
            refusal that could not have been about timing accuses the record.
            """)
    }

    func testAHealthyLaunchIsNeitherStaleState() {
        XCTAssertEqual(
            Permissions.screenGrantStaleness(grantedAtLaunch: true, captureDeclined: false), .none)
    }

    /// **The guidance is the fix.** The state exists so the user is told the one thing that works,
    /// and the app has already spent two rounds telling them things that do not.
    func testTheUnusableRecordIsExplainedWithTheCommandThatActuallyFixesIt() {
        let reason = Permissions.ScreenBlock.recordUnusable.reason

        XCTAssertTrue(
            reason.contains(Permissions.screenRecordResetCommand),
            """
            Deleting the record is the only remedy — System Settings updates the row's allowed flag \
            without rewriting the stored code requirement — so the sentence has to name the exact \
            command rather than gesture at it.
            """)
        // Not a second literal: the command names whichever bundle is *running*, and a sentence
        // pinned to the shipping id would tell a dev build's user to reset the installed app's
        // grant instead of their own. The rule itself is proved in `BuildIdentityTests`.
        XCTAssertTrue(
            reason.contains("tccutil reset ScreenCapture \(ContextPaths.bundleIdentifier)"), reason)
        XCTAssertFalse(
            reason.lowercased().contains("reopen me"),
            "reopening is the advice this state exists to stop repeating")
        XCTAssertTrue(
            Permissions.ScreenBlock.recordUnusable.isRegression,
            """
            Logged at a level that survives: this is a state the user cannot leave without being \
            told a command, so the line explaining it has to still be readable tomorrow.
            """)
    }

    /// The two remedies must not be confusable in the copy either — a user reading the relaunch
    /// sentence must not be handed a Terminal command, and vice versa.
    func testTheRelaunchSentenceStillOffersARelaunchAndNothingElse() {
        let reason = Permissions.ScreenBlock.needsRelaunch.reason

        XCTAssertTrue(reason.contains("reopened"))
        XCTAssertFalse(
            reason.contains("tccutil"),
            "a process that is merely early must not be sent to delete a perfectly good record")
    }

    func testAWorkingScreenReportsNoBlockAtAll() {
        XCTAssertNil(
            Permissions.screenBlock(
                granted: true, hasEverCaptured: true, needsRelaunch: false, recordIsUnusable: false))
    }
}
