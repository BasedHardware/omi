import XCTest

@testable import Omi_Computer

final class RewindCaptureIntentPolicyTests: XCTestCase {
  func testMonitoringStopPreservesEnabledCaptureIntentForRecovery() {
    let state = RewindCaptureState.afterMonitoringChange(captureEnabled: true, monitoring: false)

    XCTAssertFalse(state.isMonitoring)
    XCTAssertTrue(state.captureEnabled)
  }

  func testMonitoringStartDoesNotEnableCaptureWithoutUserIntent() {
    let state = RewindCaptureState.afterMonitoringChange(captureEnabled: false, monitoring: true)

    XCTAssertTrue(state.isMonitoring)
    XCTAssertFalse(state.captureEnabled)
  }
}
