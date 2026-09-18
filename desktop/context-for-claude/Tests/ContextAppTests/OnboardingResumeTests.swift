import XCTest

@testable import ContextApp

/// **A relaunch in the middle of onboarding is a normal event, not a crash.**
///
/// Screen Recording only applies to a process that already held it when it connected to the window
/// server, so the flow restarts the app on purpose — the card's own "Restart to finish", and macOS's
/// own "Quit & Reopen" on the system dialog. Everything here is about the process that comes back.
///
/// Reported verbatim: *"when I open the app again, myself manually, it goes to the initial cinematic
/// intro and everything, and I have to go through everything again. Though the permissions that have
/// already been granted shows granted, but I have to see it again, which should not happen."*
final class OnboardingResumeTests: XCTestCase {

    /// A scratch domain per test. The machine running the tests is also the machine the app runs on,
    /// so touching `UserDefaults.standard` here would rewrite the developer's own onboarding state —
    /// the same reason `CinematicTests` builds its own suite.
    private func scratch() throws -> (UserDefaults, () -> Void) {
        let suite = "com.omi.context-for-claude.OnboardingResumeTests.\(UUID().uuidString)"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        return (defaults, { UserDefaults.standard.removePersistentDomain(forName: suite) })
    }

    // MARK: - The record itself

    func testAFreshInstallHasNothingToResume() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        XCTAssertNil(
            OnboardingResume(defaults: defaults).step,
            "nothing has been recorded, so there is no card to reopen on")
    }

    func testTheCardItRecordsIsTheCardItAnswers() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let resume = OnboardingResume(defaults: defaults)
        for step in OnboardingStep.allCases {
            resume.record(step)
            XCTAssertEqual(resume.step, step, "\(step) has to survive the process that recorded it")
        }
    }

    func testFinishingTheRunSpendsTheResumePoint() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let resume = OnboardingResume(defaults: defaults)
        resume.record(.permissions)
        resume.clear()

        XCTAssertNil(
            resume.step,
            "a resume point left behind after the flow ends reopens the card over a user who is done")
    }

    /// The downgrade case: a newer build recorded a card this one does not have.
    ///
    /// Starting over is a bad morning. Starting on the *wrong* card is a bug nobody can read, so an
    /// unrecognised token answers "no resume point" rather than guessing at the nearest one.
    func testAnUnreadableTokenIsNotAGuess() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        defaults.set("a-card-from-a-later-build", forKey: OnboardingResume.key)
        XCTAssertNil(OnboardingResume(defaults: defaults).step)
    }

    /// The persisted form is a **stable token**, never `OnboardingStep.rawValue`.
    ///
    /// Those raw values are positional — `OnboardingStep.next(after:)` compares them to decide
    /// ordering — so inserting a card renumbers every card after it. A persisted integer would then
    /// resume a mid-upgrade user onto somebody else's screen: silently, once, on a build nobody could
    /// reproduce. This asserts the written value is not the number.
    func testWhatLandsOnDiskIsATokenAndNotAnOrdinal() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        OnboardingResume(defaults: defaults).record(.permissions)

        let written = try XCTUnwrap(defaults.string(forKey: OnboardingResume.key))
        XCTAssertEqual(written, "permissions")
        XCTAssertNil(
            Int(written),
            "a number here is an ordinal, and ordinals move when a card is inserted")
    }

    // MARK: - What the resumed process does with it

    /// The defect itself, at the seam it happened on.
    ///
    /// `context.onboarded` is still false in the resumed process — the run it is resuming never
    /// finished — so the flag alone said "fresh install" and the eight-second cinematic played over a
    /// user who was already past sign-in.
    func testTheCinematicDoesNotReplayOverARunInProgress() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        XCTAssertTrue(
            CinematicGate(defaults: defaults).shouldPlay,
            "a genuine first run still gets the intro")

        OnboardingResume(defaults: defaults).record(.permissions)

        XCTAssertFalse(
            CinematicGate(defaults: defaults).shouldPlay,
            "a resumed run is not a first run, whatever context.onboarded still says")
        XCTAssertFalse(
            defaults.bool(forKey: CinematicGate.onboardedKey),
            "and the flag really is still false — that is what made the old gate wrong")
    }

    func testTheIntroComesBackOnceTheResumePointIsSpent() throws {
        let (defaults, cleanup) = try scratch()
        defer { cleanup() }

        let resume = OnboardingResume(defaults: defaults)
        resume.record(.tutorial)
        resume.clear()

        XCTAssertTrue(
            CinematicGate(defaults: defaults).shouldPlay,
            "clearing the resume point must not permanently suppress the intro; only finishing does")
    }

    // MARK: - Why the screen is asked for first

    /// **The ordering is a cycle with exactly one way out, and this is the guard on which way.**
    ///
    /// `PermissionChoreography` has two locators and each needs the other's grant.
    /// `SettingsRowLocator` walks System Settings' accessibility tree, and
    /// `AXUIElementCopyAttributeValue` against another process is hard-gated on this app being
    /// AX-trusted — so pointing at the **screen** row needs Accessibility already granted.
    /// `SettingsRowSighting` reads the row out of a screenshot of the pane, which is gated on Screen
    /// Recording — so pointing at the **Accessibility** row needs the screen already granted. One of
    /// the two has to go first with no overlay of its own; there is no third arrangement.
    ///
    /// This asserted `.accessibility` for one release, on the reasoning that AX trust buys precise
    /// guidance for the three panes after it. That reasoning was right about what it measured and
    /// wrong about what it left out: Accessibility is the one capability that is **never required**,
    /// so putting it first made an optional grant the precondition for all three required ones — skip
    /// it and microphone, system audio and screen all fell back to a boundary round the whole window.
    /// Reported from exactly that state: *"the blue dotted line highlight the entire settings window,
    /// not specifically the screen and system audio recording one"*, and *"it does not give me an
    /// option to drop something in this or highlighting only the area where the accessibility stuff is
    /// there, highlights the entire settings window."*
    ///
    /// Screen-first breaks the coupling: once the pixels are readable every other pane is pointable
    /// whether or not Accessibility is ever given — including Accessibility's own row, which under the
    /// old order could never be pointed at by anything at all.
    @MainActor
    func testTheScreenIsAskedForFirstBecauseTheOtherLocatorNeedsItsPixels() {
        let invitations = PermissionInvitations()

        XCTAssertEqual(
            invitations.listed.first, .screen,
            "the Accessibility row can only be located from a screenshot, and a screenshot needs the "
                + "screen grant first")
        guard let screen = invitations.listed.firstIndex(of: .screen),
            let accessibility = invitations.listed.firstIndex(of: .accessibility)
        else { return XCTFail("both capabilities must be listed") }
        XCTAssertLessThan(screen, accessibility)
        XCTAssertEqual(
            Set(invitations.listed), Set(Capability.allCases),
            "reordering must not drop a capability off the card")
    }

    /// Ordering changed; the exit predicate did not. Accessibility stays *listed but not required* —
    /// macOS has no dialog for it, so gating the card on it would strand anyone unwilling to leave
    /// the flow on a step with no button that could finish it. It is also the whole reason the order
    /// above is what it is: an optional grant is the one people abandon when they cannot find the row.
    @MainActor
    func testReorderingDidNotMakeAnythingNewlyMandatory() {
        let invitations = PermissionInvitations()

        XCTAssertFalse(
            invitations.required.contains(.accessibility),
            "capture degrades to OCR-only without it: a worse product, and a working one")
        XCTAssertEqual(Set(invitations.required), [.microphone, .systemAudio, .screen])
    }
}
