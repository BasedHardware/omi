import XCTest

@testable import Omi_Computer

/// The intro is 8.6s of full-screen cinematic. These assert the two situations that
/// must never see it — a resume, and an involuntary re-auth — because both read as the
/// app having lost the user's place, and the one that must: an explicit Reset
/// Onboarding.
final class SBOnboardingIntroGateTests: XCTestCase {
  private let promiseRaw = SBOnboardingModel.Step.promise.rawValue

  private func gatePlays(_ defaults: UserDefaults) -> Bool {
    SBOnboardingIntroGate.shouldPlay(resumeStepRaw: 0, promiseStepRaw: promiseRaw, defaults: defaults)
  }

  func testFirstRunPlaysTheIntro() {
    XCTAssertTrue(
      SBOnboardingIntroGate.shouldPlay(resumeStepRaw: 0, promiseStepRaw: promiseRaw, alreadyPlayed: false))
  }

  /// Granting Screen Recording restarts the process by design, and the permission step
  /// persists a resume point. Replaying the intro on the way back to step 9 would look
  /// like the app forgot everything the user just did.
  func testAResumeNeverReplaysTheIntro() {
    let resumed = SBOnboardingModel.Step.screen.rawValue
    XCTAssertGreaterThan(resumed, promiseRaw, "precondition: a permission step outranks .promise")
    XCTAssertFalse(
      SBOnboardingIntroGate.shouldPlay(resumeStepRaw: resumed, promiseStepRaw: promiseRaw, alreadyPlayed: false))
  }

  /// Re-entering onboarding does not by itself earn a replay — only an explicit reset
  /// clears the flag, and that is asserted below.
  func testAnAlreadyPlayedInstallDoesNotReplayOnItsOwn() {
    XCTAssertFalse(
      SBOnboardingIntroGate.shouldPlay(resumeStepRaw: 0, promiseStepRaw: promiseRaw, alreadyPlayed: true))
  }

  /// A resume that lands back on the first step is still a first step, not a resume.
  func testAResumePointEqualToPromiseStillPlays() {
    XCTAssertTrue(
      SBOnboardingIntroGate.shouldPlay(
        resumeStepRaw: promiseRaw, promiseStepRaw: promiseRaw, alreadyPlayed: false))
  }

  /// `markPlayed` is called *before* playback starts, so a quit mid-intro must already
  /// have disarmed it. This pins that the flag round-trips through the defaults the
  /// production call site reads.
  func testMarkPlayedDisarmsTheGateThroughDefaults() throws {
    let suiteName = "SBOnboardingIntroGateTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    XCTAssertTrue(
      SBOnboardingIntroGate.shouldPlay(resumeStepRaw: 0, promiseStepRaw: promiseRaw, defaults: defaults))

    SBOnboardingIntroGate.markPlayed(defaults: defaults)

    XCTAssertFalse(
      SBOnboardingIntroGate.shouldPlay(resumeStepRaw: 0, promiseStepRaw: promiseRaw, defaults: defaults))

    SBOnboardingIntroGate.reset(defaults: defaults)
    XCTAssertTrue(
      SBOnboardingIntroGate.shouldPlay(resumeStepRaw: 0, promiseStepRaw: promiseRaw, defaults: defaults))
  }

  /// Settings → Restart and Reset Onboarding is a person deliberately asking to see
  /// first run again, so the cinematic replays. Driven through the real clearing calls
  /// `resetOnboardingAndRestart` makes, in its order: the shared account-scoped clear,
  /// then the doomed pre-restart onboarding session marking the intro played on appear,
  /// and only then the re-arm. That last write is the whole contract — moving it up
  /// beside `clearPersistedState()` puts the transient session's `markPlayed()` last
  /// and the reset silently does nothing.
  func testResetOnboardingReplaysTheIntroEvenAfterThePreRestartSessionMarksItPlayed() throws {
    let suiteName = "SBOnboardingIntroGateTests.reset.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    SBOnboardingIntroGate.markPlayed(defaults: defaults)
    XCTAssertFalse(gatePlays(defaults), "precondition: an install that has already seen the intro")

    OnboardingFlow.clearPersistedState(in: defaults)
    SBOnboardingIntroGate.markPlayed(defaults: defaults)
    OnboardingFlow.armIntroReplayForOnboardingReset(in: defaults)

    XCTAssertTrue(gatePlays(defaults), "Reset Onboarding must replay the cinematic on the next launch")
  }

  /// A session expiring is not a request for cinema. Sign-out clears the rest of
  /// onboarding through the shared list and leaves the intro flag standing, so someone
  /// signing back in gets their app rather than 8.6 seconds of it.
  func testAReAuthClearsOnboardingWithoutReplayingTheIntro() throws {
    let suiteName = "SBOnboardingIntroGateTests.reauth.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suiteName))
    defer { defaults.removePersistentDomain(forName: suiteName) }

    SBOnboardingIntroGate.markPlayed(defaults: defaults)
    defaults.set(SBOnboardingModel.Step.screen.rawValue, forKey: SBOnboardingModel.resumeStepKey)

    OnboardingFlow.clearPersistedState(in: defaults)

    XCTAssertNil(
      defaults.object(forKey: SBOnboardingModel.resumeStepKey),
      "precondition: the shared clear really did drop account-scoped onboarding state")
    XCTAssertFalse(gatePlays(defaults), "a re-auth must not force the intro on the way back in")
  }
}
