import XCTest

@testable import Omi_Computer

/// The intro is 8.6s of full-screen cinematic. These assert the two situations that
/// must never see it — a resume, and a second run — because both read as the app
/// having lost the user's place.
final class SBOnboardingIntroGateTests: XCTestCase {
  private let promiseRaw = SBOnboardingModel.Step.promise.rawValue

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

  func testASecondRunNeverReplaysTheIntro() {
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
}
