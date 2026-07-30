import XCTest

@testable import ContextApp

final class FreemiumLimitGateTests: XCTestCase {
    func testLatchesWhenRemainingIsZeroOrNegative() {
        XCTAssertTrue(FreemiumLimitGate.shouldLatchPaywall(remainingSeconds: 0))
        XCTAssertTrue(FreemiumLimitGate.shouldLatchPaywall(remainingSeconds: -1))
    }

    func testDoesNotLatchWhileSecondsRemain() {
        XCTAssertFalse(FreemiumLimitGate.shouldLatchPaywall(remainingSeconds: 1))
        XCTAssertFalse(FreemiumLimitGate.shouldLatchPaywall(remainingSeconds: 60))
    }

    func testDoesNotLatchWhenRemainingSecondsAbsent() {
        XCTAssertNil(FreemiumLimitGate.remainingSeconds(in: [:]))
        XCTAssertFalse(FreemiumLimitGate.shouldLatchPaywall(remainingSeconds: nil))
    }

    func testParsesRemainingSecondsFromPayloadShapes() {
        XCTAssertEqual(FreemiumLimitGate.remainingSeconds(in: ["remaining_seconds": 0]), 0)
        XCTAssertEqual(FreemiumLimitGate.remainingSeconds(in: ["remaining_seconds": 12]), 12)
        XCTAssertEqual(FreemiumLimitGate.remainingSeconds(in: ["remaining_seconds": 3.9]), 3)
        XCTAssertNil(FreemiumLimitGate.remainingSeconds(in: [:]))
    }
}
