import XCTest

@testable import Omi_Computer

final class OnboardingDataSourceRowStatusTests: XCTestCase {
  func testUsesMetricsWhenNoScanStateIsProvided() {
    XCTAssertEqual(
      OnboardingDataSourceRowStatus.resolve(
        metrics: "0 emails - 0 memories",
        scanFinished: nil,
        scanFailed: false
      ),
      OnboardingDataSourceRowStatus(text: "0 emails - 0 memories", isError: false)
    )
  }

  func testShowsScanningWhileSourceReadIsStillInFlight() {
    XCTAssertEqual(
      OnboardingDataSourceRowStatus.resolve(
        metrics: "0 emails - 0 memories",
        scanFinished: false,
        scanFailed: false
      ),
      OnboardingDataSourceRowStatus(text: "Scanning...", isError: false)
    )
  }

  func testFailureOverridesStaleMetrics() {
    XCTAssertEqual(
      OnboardingDataSourceRowStatus.resolve(
        metrics: "114 emails - 114 memories",
        scanFinished: true,
        scanFailed: true
      ),
      OnboardingDataSourceRowStatus(
        text: "Couldn't read - check access",
        isError: true
      )
    )
  }
}
