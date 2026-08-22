import XCTest

@testable import ContextApp

/// **"Run setup again" has to be the first run, and it has to be nothing more than the first run.**
///
/// The two halves are separate failures and both are here. If it clears too little, the press appears
/// to do nothing — the terminal flag survives and `ContextAppDelegate.landing` still answers
/// `.activity`, or the flag goes and a stale resume point drops the user onto card four with no
/// intro. If it clears too much, a row whose copy promises a walkthrough has quietly signed the user
/// out, forgotten their storage strategy, or re-asked for a permission macOS had already granted.
final class OnboardingResetTests: XCTestCase {

    /// A scratch domain per test, exactly as `OnboardingResumeTests` and `CinematicTests` build one:
    /// the machine running the suite is the machine the app runs on, and a test that reached
    /// `UserDefaults.standard` here would put the developer's own install back into onboarding.
    /// The suite name comes back too: the blast-radius test below diffs the *persistent domain*
    /// rather than `dictionaryRepresentation()`, which would also carry every global default on the
    /// machine and make the assertion a test of the host rather than of the reset.
    private func scratch() throws -> (UserDefaults, String, () -> Void) {
        let suite = "com.omi.context-for-claude.OnboardingResetTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        return (defaults, suite, { UserDefaults.standard.removePersistentDomain(forName: suite) })
    }

    /// An install that has been all the way through, and then abandoned a walkthrough: every one of
    /// the three records populated, which is the state with the most for a reset to miss.
    private func settledInstall(in defaults: UserDefaults) {
        defaults.set(true, forKey: CinematicGate.onboardedKey)
        OnboardingResume(defaults: defaults).record(.permissions)
        TutorialResume(defaults: defaults).record(.timeline)
    }

    // MARK: - All three, and only three

    func testTheResetSpendsAllThreeRecords() throws {
        let (defaults, _, cleanup) = try scratch()
        defer { cleanup() }
        settledInstall(in: defaults)

        OnboardingReset(defaults: defaults).clear()

        XCTAssertFalse(
            defaults.bool(forKey: CinematicGate.onboardedKey),
            "the terminal flag is what `landing` reads first; left set, the reset shows nothing at all")
        XCTAssertNil(
            defaults.object(forKey: CinematicGate.onboardedKey),
            "a first run is the absence of the key, not a false stored in it")
        XCTAssertNil(
            OnboardingResume(defaults: defaults).step,
            "a surviving resume point drops the user onto the card they left off on, with no intro")
        XCTAssertNil(
            TutorialResume(defaults: defaults).step,
            "a surviving tutorial beat outranks the Activity panel at the next launch (`landing`)")
    }

    /// **The blast radius, asserted as a set rather than as a promise in a comment.**
    ///
    /// Every `context.*` key the app writes is planted here and the whole domain is diffed across the
    /// reset. This is the test that fails if someone later "helpfully" adds a sign-out, a permission
    /// re-probe or a settings wipe to the reset — none of which the row's copy claims, and each of
    /// which is a support ticket from a user who wanted to see the intro again.
    func testTheResetTouchesNothingElseInDefaults() throws {
        let (defaults, suite, cleanup) = try scratch()
        defer { cleanup() }
        settledInstall(in: defaults)

        // Real keys, from `grep -Eho '"context\.[A-Za-z.]+"' Sources`. Values are arbitrary; what is
        // asserted is that each key comes back out with the value it went in with.
        let untouched: [String: Any] = [
            "context.settings.appearance": "dark",
            "context.settings.captureQuality": "high",
            "context.settings.claudeTarget": "desktop",
            "context.settings.pausesOnInactivity": true,
            "context.settings.screenCapture": true,
            "context.settings.showsDockIcon": false,
            "context.settings.storageLimitBytes": 42_000_000_000,
            "context.settings.storageStrategy": "keep",
            "context.settings.timelineControls": true,
            "context.sound.musicEnabled": false,
            // The capture side: a probe cache and the sync cursors. Clearing any of these would
            // re-prompt for a grant the user already gave, or re-upload what has already gone.
            "context.permission.systemAudio.granted": true,
            "context.permission.systemAudio.probedAt": 1_700_000_000.0,
            "context.permission.screen.pendingRelaunch": false,
            "context.screenSync.installId": "an-install",
            "context.screenSync.lastId": 918,
            "context.activity": "something",
            "context.db": "/somewhere/context.db",
            "context.search.refocus": true,
            "context.revival.recentAt": [1_700_000_000.0],
            "context.update.relaunchFromVersion": "1.0",
        ]
        for (key, value) in untouched { defaults.set(value, forKey: key) }

        let before = UserDefaults.standard.persistentDomain(forName: suite) ?? [:]
        OnboardingReset(defaults: defaults).clear()
        let after = UserDefaults.standard.persistentDomain(forName: suite) ?? [:]

        let removed = Set(before.keys).subtracting(after.keys)
        XCTAssertEqual(
            removed,
            [CinematicGate.onboardedKey, OnboardingResume.key, TutorialResume.key],
            "the reset is these three keys and nothing else")
        for key in untouched.keys {
            XCTAssertEqual(
                String(describing: after[key]), String(describing: before[key]),
                "\(key) survived the reset unchanged")
        }
    }

    /// Idempotent, because the row can be pressed twice and because a fresh install is the state it
    /// produces — clearing a record that was never there must not be a different code path.
    func testResettingAnInstallThatWasNeverSetUpIsANoOp() throws {
        let (defaults, _, cleanup) = try scratch()
        defer { cleanup() }

        OnboardingReset(defaults: defaults).clear()
        OnboardingReset(defaults: defaults).clear()

        XCTAssertFalse(defaults.bool(forKey: CinematicGate.onboardedKey))
        XCTAssertNil(OnboardingResume(defaults: defaults).step)
        XCTAssertNil(TutorialResume(defaults: defaults).step)
    }

    // MARK: - The intro, and the one case that must not have it

    /// **The point of the feature**, in the user's words: *"It should also go through the initial
    /// cinematic walkthrough and everything."*
    ///
    /// `CinematicGate.shouldPlay` is `!onboarded && OnboardingResume.step == nil`, so both halves have
    /// to be spent for the eight seconds to come back. A reset that cleared only the flag would land
    /// the user straight on a card.
    func testTheCinematicPlaysAgainAfterAReset() throws {
        let (defaults, _, cleanup) = try scratch()
        defer { cleanup() }
        settledInstall(in: defaults)

        XCTAssertFalse(
            CinematicGate(defaults: defaults).shouldPlay,
            "an install that has been through setup does not get the intro")

        OnboardingReset(defaults: defaults).clear()

        XCTAssertTrue(
            CinematicGate(defaults: defaults).shouldPlay,
            "the reset is a first run, and a first run opens with the eight-second intro")
    }

    /// **The opposite case, and the bug the gate exists for.** A process that came back from the
    /// screen-recording restart is *resuming*, not resetting: `context.onboarded` is false there too,
    /// and replaying the intro over a user who was four cards in is exactly what was reported. The two
    /// paths differ by one record, so they are asserted against each other rather than apart.
    func testAResumedRunStillDoesNotReplayTheIntro() throws {
        let (defaults, _, cleanup) = try scratch()
        defer { cleanup() }

        OnboardingResume(defaults: defaults).record(.permissions)
        XCTAssertFalse(
            defaults.bool(forKey: CinematicGate.onboardedKey),
            "a resumed run has the same terminal flag a reset leaves behind")
        XCTAssertFalse(
            CinematicGate(defaults: defaults).shouldPlay,
            "the resume point is the whole difference, and it is what keeps the intro off")

        OnboardingReset(defaults: defaults).clear()
        XCTAssertTrue(
            CinematicGate(defaults: defaults).shouldPlay,
            "and pressing the row from the same state is the deliberate case that does want it")
    }

    // MARK: - Where the reset lands

    /// The reset spends the records so that the *launch* decision answers `.onboarding`. Asserted
    /// through `ContextAppDelegate.landing` — the pure function `OnboardingReset.restart()` reaches
    /// through `surfaceSomethingForTheUser()` — because "the records are gone" and "the app now shows
    /// setup" are two claims, and only the second one is the feature.
    func testAResetInstallLandsOnOnboarding() throws {
        let (defaults, _, cleanup) = try scratch()
        defer { cleanup() }
        settledInstall(in: defaults)

        XCTAssertEqual(
            ContextAppDelegate.landing(
                onboarded: defaults.bool(forKey: CinematicGate.onboardedKey),
                onboardingInProgress: OnboardingResume(defaults: defaults).step != nil,
                tutorialResume: TutorialResume(defaults: defaults).step),
            .onboarding,
            "an unfinished run already lands here; this is the state before the reset")

        OnboardingReset(defaults: defaults).clear()

        XCTAssertEqual(
            ContextAppDelegate.landing(
                onboarded: defaults.bool(forKey: CinematicGate.onboardedKey),
                onboardingInProgress: OnboardingResume(defaults: defaults).step != nil,
                tutorialResume: TutorialResume(defaults: defaults).step),
            .onboarding,
            "and after it the launch path answers the same thing a first launch does")
    }

    // MARK: - What the user is told

    /// The subtitle and the dialog are the only account the user gets of a press that takes the screen
    /// for several minutes, so the claims in them are asserted rather than trusted.
    @MainActor
    func testTheRowSaysWhatWillHappenAndWhatWillNot() {
        let subtitle = SettingsGeneralPane.resetSubtitle
        XCTAssertTrue(subtitle.contains("Nothing is deleted"), subtitle)
        XCTAssertTrue(subtitle.contains("permissions"), subtitle)
        XCTAssertTrue(subtitle.contains("sign-in"), subtitle)

        // The window the press came from closes immediately, so the dialog says so first.
        let message = SettingsGeneralPane.resetConfirmationMessage
        XCTAssertTrue(message.hasPrefix("Settings closes"), message)
        XCTAssertTrue(message.contains("Nothing is deleted"), message)
        XCTAssertTrue(
            SettingsGeneralPane.resetConfirmationTitle.hasSuffix("?"),
            "the confirmation asks; it does not announce")
    }
}
