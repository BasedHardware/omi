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

    // MARK: - Why Accessibility is asked first

    /// Ordering is what buys precise guidance on the other three panes.
    ///
    /// `PermissionChoreography` finds the real row by walking System Settings' accessibility tree,
    /// and `AXUIElementCopyAttributeValue` against another process is hard-gated on this app being
    /// AX-trusted. With Accessibility last, every earlier pane could only draw a boundary around the
    /// whole window — reported for Screen Recording as *"the blue dotted line highlight the entire
    /// settings window, not specifically the screen and system audio recording one"*.
    @MainActor
    func testAccessibilityIsAskedFirstBecauseEveryOtherPointDependsOnIt() {
        let invitations = PermissionInvitations()

        XCTAssertEqual(
            invitations.listed.first, .accessibility,
            "AX trust is the precondition for locating any row in System Settings")
        XCTAssertEqual(
            Set(invitations.listed), Set(Capability.allCases),
            "reordering must not drop a capability off the card")
    }

    /// Ordering changed; the exit predicate did not. Accessibility stays *listed but not required* —
    /// macOS has no dialog for it, so gating the card on it would strand anyone unwilling to leave
    /// the flow on a step with no button that could finish it.
    @MainActor
    func testMovingAccessibilityFirstDidNotMakeItMandatory() {
        let invitations = PermissionInvitations()

        XCTAssertFalse(
            invitations.required.contains(.accessibility),
            "capture degrades to OCR-only without it: a worse product, and a working one")
        XCTAssertEqual(Set(invitations.required), [.microphone, .systemAudio, .screen])
    }
}
