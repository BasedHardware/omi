import XCTest

@testable import Omi_Computer

final class ShellWindowLaunchRecoveryPolicyTests: XCTestCase {
  func testFirstProbeRequestsTheMainScene() {
    XCTAssertEqual(ShellWindowLaunchRecoveryPolicy.decision(for: 0), .requestWindow)
  }

  func testIntermediateProbesWaitForSwiftUIToMountTheScene() {
    XCTAssertEqual(ShellWindowLaunchRecoveryPolicy.decision(for: 1), .retry)
    XCTAssertEqual(ShellWindowLaunchRecoveryPolicy.decision(for: 4), .retry)
  }

  func testSlowMountsReceivePeriodicSceneRequests() {
    XCTAssertEqual(ShellWindowLaunchRecoveryPolicy.decision(for: 5), .requestWindow)
    XCTAssertEqual(ShellWindowLaunchRecoveryPolicy.decision(for: 10), .requestWindow)
    XCTAssertEqual(ShellWindowLaunchRecoveryPolicy.decision(for: 20), .requestWindow)
  }

  func testRecoveryStopsAfterItsBoundedWindow() {
    XCTAssertEqual(
      ShellWindowLaunchRecoveryPolicy.decision(for: ShellWindowLaunchRecoveryPolicy.maxAttempt + 1),
      .stop)
    XCTAssertEqual(ShellWindowLaunchRecoveryPolicy.decision(for: -1), .stop)
  }
}
