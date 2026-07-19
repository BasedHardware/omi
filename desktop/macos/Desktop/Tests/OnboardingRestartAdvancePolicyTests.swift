import XCTest

@testable import Omi_Computer

/// Regression coverage for the Full Disk Access "Reopen Omi" restart loop.
///
/// The restart-carrying permission step used to re-show the reopen prompt on
/// every relaunch: the permission reads granted after the restart, the step is
/// still the persisted current step, and the prompt's primary button restarted
/// the app again — an infinite loop escapable only via the cancel-role
/// "Later" button. A step whose permission was already granted when it
/// appeared must advance directly.
final class OnboardingRestartAdvancePolicyTests: XCTestCase {
  func testNonRestartStepAlwaysAdvances() {
    XCTAssertEqual(
      OnboardingRestartAdvancePolicy.action(requiresRestart: false, grantedWhenStepAppeared: false),
      .advance)
    XCTAssertEqual(
      OnboardingRestartAdvancePolicy.action(requiresRestart: false, grantedWhenStepAppeared: true),
      .advance)
  }

  func testRestartStepPromptsForGrantDuringThisRun() {
    XCTAssertEqual(
      OnboardingRestartAdvancePolicy.action(requiresRestart: true, grantedWhenStepAppeared: false),
      .promptRestart)
  }

  func testRestartStepAdvancesWhenGrantPrecededAppearance() {
    // Post-restart relaunch: the permission was granted before the step
    // appeared, so the restart it needed already happened. Prompting again
    // would loop the user through endless restarts.
    XCTAssertEqual(
      OnboardingRestartAdvancePolicy.action(requiresRestart: true, grantedWhenStepAppeared: true),
      .advance)
  }
}
