import XCTest
@testable import Omi_Computer

final class TranscriptionSessionRecordTests: XCTestCase {
    func testBackendIdentityExistsWhenBackendIdIsPresent() {
        let record = TranscriptionSessionRecord(
            source: "desktop",
            backendId: "conversation-a",
            backendSynced: false
        )

        XCTAssertTrue(record.hasSyncedBackendIdentity)
    }

    func testBackendIdentityExistsWhenBackendSyncedIsTrue() {
        let record = TranscriptionSessionRecord(
            source: "desktop",
            backendId: nil,
            backendSynced: true
        )

        XCTAssertTrue(record.hasSyncedBackendIdentity)
    }

    func testCompletionAcceptsEmptyBackendIdentity() {
        let record = TranscriptionSessionRecord(
            source: "desktop",
            backendId: nil,
            backendSynced: false
        )

        XCTAssertTrue(record.canAcceptCompletion(backendId: "conversation-a"))
    }

    func testCompletionAcceptsSameBackendId() {
        let record = TranscriptionSessionRecord(
            source: "desktop",
            backendId: "conversation-a",
            backendSynced: true
        )

        XCTAssertTrue(record.canAcceptCompletion(backendId: "conversation-a"))
    }

    func testCompletionRejectsConflictingBackendId() {
        let record = TranscriptionSessionRecord(
            source: "desktop",
            backendId: "conversation-a",
            backendSynced: true
        )

        XCTAssertFalse(record.canAcceptCompletion(backendId: "conversation-b"))
    }
}
