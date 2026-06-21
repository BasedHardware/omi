import XCTest
@testable import Omi_Computer

final class MemoryTierFilterTests: XCTestCase {
    func testDefaultFilterIsDefaultAccessOnly() {
        XCTAssertEqual(MemoryTierFilter.defaultAccess.allowedTiers, [.shortTerm, .longTerm])
        XCTAssertFalse(MemoryTierFilter.defaultAccess.allowedTiers.contains(.archive))
    }

    func testExplicitArchiveFilterOnlyAllowsArchive() {
        XCTAssertEqual(MemoryTierFilter.archive.allowedTiers, [.archive])
    }

    func testRecordRoundTripsTierThroughServerMemory() {
        let memory = ServerMemory(
            id: "mem-1",
            content: "A stable preference",
            category: .manual,
            tier: .longTerm,
            createdAt: Date(timeIntervalSince1970: 1),
            updatedAt: Date(timeIntervalSince1970: 2),
            conversationId: nil,
            reviewed: false,
            userReview: nil,
            visibility: "private",
            manuallyAdded: true,
            scoring: nil,
            source: "desktop",
            confidence: nil,
            sourceApp: nil,
            contextSummary: nil,
            isRead: false,
            isDismissed: false,
            tags: [],
            reasoning: nil,
            currentActivity: nil,
            inputDeviceName: nil,
            windowTitle: nil,
            headline: nil
        )

        let record = MemoryRecord.from(memory)
        let roundTripped = record.toServerMemory()

        XCTAssertEqual(record.tier, MemoryTier.longTerm.rawValue)
        XCTAssertEqual(roundTripped?.tier, .longTerm)
    }

    func testUnknownPersistedTierFallsBackToLongTerm() {
        let record = MemoryRecord(
            backendId: "mem-unknown",
            backendSynced: true,
            content: "Legacy record",
            category: "system",
            tier: "unexpected_future_tier"
        )

        XCTAssertEqual(record.toServerMemory()?.tier, .longTerm)
    }
}
