import XCTest

@testable import Omi_Computer

final class NegativeFeedbackRemediationFeatureTests: XCTestCase {
  func testRemediationRunsForEveryoneUnlessTheKillSwitchIsSet() {
    XCTAssertTrue(NegativeFeedbackRemediationFeature.isEnabled(killSwitchEnabled: false))
    XCTAssertFalse(NegativeFeedbackRemediationFeature.isEnabled(killSwitchEnabled: true))
  }
}
