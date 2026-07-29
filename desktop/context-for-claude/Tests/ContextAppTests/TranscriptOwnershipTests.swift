import XCTest

@testable import ContextApp

final class TranscriptOwnershipTests: XCTestCase {
    func testLocalTranscriberIsTheFallbackWhileCloudIsNotLive() {
        for state in [
            ListenSocket.State.idle,
            .connecting,
            .failed("network unavailable"),
            .paywalled,
        ] {
            XCTAssertTrue(
                TranscriptOwnership.shouldFeedLocalFallback(when: state),
                "local capture must remain available while cloud is \(state)")
        }
    }

    func testLiveCloudOwnsNewTranscriptChunks() {
        XCTAssertFalse(TranscriptOwnership.shouldFeedLocalFallback(when: .live))
    }
}
