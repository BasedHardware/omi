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

    func testLocalModelStartsOnlyWhenCloudBufferCannotCoverTheGap() {
        XCTAssertFalse(
            TranscriptOwnership.shouldStartLocalFallback(
                when: .connecting, isSignedIn: true))
        XCTAssertFalse(
            TranscriptOwnership.shouldStartLocalFallback(
                when: .idle, isSignedIn: true))
        XCTAssertTrue(
            TranscriptOwnership.shouldStartLocalFallback(
                when: .idle, isSignedIn: false))
        XCTAssertTrue(
            TranscriptOwnership.shouldStartLocalFallback(
                when: .failed("network unavailable"), isSignedIn: true))
        XCTAssertTrue(
            TranscriptOwnership.shouldStartLocalFallback(
                when: .paywalled, isSignedIn: true))
        XCTAssertTrue(
            TranscriptOwnership.shouldStartLocalFallback(
                when: .airgapped, isSignedIn: true))
    }
}
