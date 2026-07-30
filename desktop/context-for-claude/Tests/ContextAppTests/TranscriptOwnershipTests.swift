import XCTest

@testable import ContextApp

final class TranscriptOwnershipTests: XCTestCase {
    func testLocalParakeetIsNotFed() {
        XCTAssertFalse(
            TranscriptOwnership.shouldFeedLocal(),
            "backend /v4/listen owns speech; local Parakeet must not receive audio")
    }
}
