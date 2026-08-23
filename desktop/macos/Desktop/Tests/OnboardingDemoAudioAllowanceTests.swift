import XCTest

@testable import Omi_Computer

/// The onboarding demo video loops and its SwiftUI view is rebuilt on every
/// onboarding step. A budget that lived on one `AVPlayer`'s item time therefore
/// restarted the music on each rebuild, which is the bug these tests pin.
@MainActor
final class OnboardingDemoAudioAllowanceTests: XCTestCase {
  // XCTest's lifecycle hooks are nonisolated, so the main-actor session state is
  // reset at the top of each test body instead of in setUp/tearDown.

  func testFirstPlayerGetsTheFullAllowance() {
    OnboardingDemoAudioAllowance.resetForTesting()
    let start = Date()
    XCTAssertEqual(
      OnboardingDemoAudioAllowance.remaining(now: start),
      OnboardingDemoAudioAllowance.allowance,
      accuracy: 0.001)
  }

  /// The regression: a player created for a later onboarding step must inherit
  /// the session deadline, not restart the 10 seconds.
  func testLaterPlayerInheritsTheSameDeadline() {
    OnboardingDemoAudioAllowance.resetForTesting()
    let start = Date()
    _ = OnboardingDemoAudioAllowance.remaining(now: start)

    let rebuilt = OnboardingDemoAudioAllowance.remaining(now: start.addingTimeInterval(4))

    XCTAssertEqual(rebuilt, OnboardingDemoAudioAllowance.allowance - 4, accuracy: 0.001)
  }

  func testPlayerCreatedAfterTheDeadlineStartsMuted() {
    OnboardingDemoAudioAllowance.resetForTesting()
    let start = Date()
    _ = OnboardingDemoAudioAllowance.remaining(now: start)

    let afterDeadline = OnboardingDemoAudioAllowance.remaining(
      now: start.addingTimeInterval(OnboardingDemoAudioAllowance.allowance + 1))

    XCTAssertLessThanOrEqual(afterDeadline, 0)
  }

  /// Sound is capped at ten seconds, so the budget never grows no matter how
  /// many times the view is rebuilt.
  func testAllowanceNeverExtends() {
    OnboardingDemoAudioAllowance.resetForTesting()
    let start = Date()
    var previous = OnboardingDemoAudioAllowance.remaining(now: start)
    for step in 1...5 {
      let next = OnboardingDemoAudioAllowance.remaining(now: start.addingTimeInterval(Double(step)))
      XCTAssertLessThan(next, previous)
      previous = next
    }
  }
}
