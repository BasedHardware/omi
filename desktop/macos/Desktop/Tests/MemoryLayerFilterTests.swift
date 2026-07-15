import XCTest
@testable import Omi_Computer

final class MemoryLayerFilterTests: XCTestCase {
    func testDefaultFilterIsDefaultAccessOnly() {
        XCTAssertEqual(MemoryLayerFilter.defaultAccess.allowedLayers, [.shortTerm, .longTerm])
        XCTAssertFalse(MemoryLayerFilter.defaultAccess.allowedLayers.contains(.archive))
    }

    func testExplicitArchiveFilterOnlyAllowsArchive() {
        XCTAssertEqual(MemoryLayerFilter.archive.allowedLayers, [.archive])
    }

    func testRecordRoundTripsLayerThroughServerMemory() {
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

        XCTAssertEqual(record.tier, MemoryLayer.longTerm.rawValue)
        XCTAssertEqual(roundTripped?.tier, .longTerm)
    }

    func testDefaultLayerScopeExcludesArchive() {
        XCTAssertEqual(MemoryLayerScope.defaultAccess.tiers, [.shortTerm, .longTerm])
        XCTAssertFalse(MemoryLayerScope.defaultAccess.includesArchive)
    }

    func testArchiveScopeRequiresAcknowledgement() {
        XCTAssertEqual(MemoryLayerScope.archiveOnly.tiers, [.archive])
        XCTAssertTrue(MemoryLayerScope.archiveOnly.requiresArchiveAcknowledgement)
    }

    func testUnknownPersistedTierIsExcludedNotPromotedToLongTerm() {
        let record = MemoryRecord(
            backendId: "mem-unknown",
            backendSynced: true,
            content: "Legacy record",
            category: "system",
            tier: "unexpected_future_tier"
        )

        XCTAssertNil(record.toServerMemory())
    }

    func testHidingLifecycleExposureClearsStaleExplicitTierForLegacyDisplay() {
        let memory = ServerMemory(
            id: "mem-stale-tier",
            content: "Cached stale tier",
            category: .system,
            tier: .shortTerm,
            tierIsExplicit: true,
            createdAt: Date(timeIntervalSince1970: 1),
            updatedAt: Date(timeIntervalSince1970: 2),
            conversationId: nil,
            reviewed: false,
            userReview: nil,
            visibility: "private",
            manuallyAdded: false,
            scoring: nil,
            source: nil,
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

        let hidden = memory.hidingLifecycleExposure()

        XCTAssertEqual(hidden.tier, .longTerm)
        XCTAssertFalse(hidden.tierIsExplicit)
    }

    func testLifecycleDisplayScopesAreMutuallyExclusive() throws {
        let source = try memoriesPageSource()

        XCTAssertTrue(source.contains("recordReadScope(for: token)"))
        XCTAssertTrue(source.contains("values.filter { $0.tierIsExplicit == lifecycleExposed }"))
        XCTAssertFalse(source.contains("lifecycleExposed ? values : values.map { $0.hidingLifecycleExposure() }"))
    }

    func testMemoriesPageCommitsPageCapabilitiesThroughSingleFreshnessHelper() throws {
        let source = try memoriesPageSource()

        XCTAssertTrue(source.contains("private func commitMemoryPageCapabilities("))
        XCTAssertTrue(source.contains("private struct MemoryPageFetchResult"))
        XCTAssertEqual(
            source.components(separatedBy: "canonicalLifecycleExposed = page.canonicalLifecycleExposed").count - 1,
            1,
            "Page capability metadata should only be assigned inside commitMemoryPageCapabilities()."
        )
        XCTAssertEqual(
            source.components(separatedBy: "deviceScopeSupported = false").count - 1,
            0,
            "Device-scope fallback metadata should be returned to commitMemoryPageCapabilities(), not assigned in fetch retry code."
        )
        XCTAssertTrue(source.contains("guard commitMemoryPageCapabilities(page, for: token) else"))
        XCTAssertTrue(source.contains("let fetchResult = try await fetchMemoriesPageDeviceScopeAware("))
        XCTAssertTrue(source.contains("let page = fetchResult.page"))
        XCTAssertTrue(source.contains("deviceScopeSupportedOverride: fetchResult.deviceScopeSupportedOverride"))
        XCTAssertTrue(source.contains("reason: \"capability_mismatch\""))
    }

    func testLegacyDeviceScopeFallbackDoesNotLocallyHideUnprovenancedMemories() throws {
        let source = try memoriesPageSource()

        XCTAssertTrue(
            source.contains("if filterThisDeviceOnly && deviceScopeSupported {"),
            "The local device matcher must run only when the backend can provide device provenance."
        )
    }

    func testMemoriesPageProjectsCacheReadsBeforeDisplay() throws {
        let source = try memoriesPageSource()

        XCTAssertTrue(source.contains("private func displayCacheMemories("))
        XCTAssertFalse(source.contains("memories.append(contentsOf: moreFromCache)"))
        XCTAssertFalse(source.contains("memories = displayMemories(cachedMemories, for: token)"))
        XCTAssertFalse(source.contains("memories = displayMemories(mergedMemories, for: token)"))
        XCTAssertTrue(source.contains("memories.append(contentsOf: visibleMemories)"))
        XCTAssertTrue(source.contains("memories = displayCacheMemories(cachedMemories, for: token)"))
        XCTAssertTrue(source.contains("memories = displayCacheMemories(mergedMemories, for: token)"))
    }

    func testMemoriesPageDoesNotRenderUnclassifiedCacheBeforeLifecycleCapability() throws {
        let source = try memoriesPageSource()

        XCTAssertTrue(source.contains("memoriesCanonicalLifecycleExposure_v1_"))
        XCTAssertTrue(source.contains("let hasRememberedLifecycleExposure = restoreCanonicalLifecycleExposure()"))
        XCTAssertTrue(source.contains("if hasRememberedLifecycleExposure {"))
        XCTAssertTrue(source.contains("Deferring unclassified cache until lifecycle capability is confirmed"))
    }

    func testLayerFilterControlsRenderOnlyAfterCanonicalLifecycleExposure() throws {
        let source = try memoriesPageSource()

        XCTAssertTrue(source.contains("if viewModel.canonicalLifecycleExposed {\n        // Layer filter dropdown"))
        XCTAssertTrue(source.contains("ForEach(MemoryLayerFilter.allCases)"))
        XCTAssertLessThan(
            try XCTUnwrap(source.range(of: "if viewModel.canonicalLifecycleExposed {\n        // Layer filter dropdown")?.lowerBound),
            try XCTUnwrap(source.range(of: "ForEach(MemoryLayerFilter.allCases)")?.lowerBound)
        )
    }

    private func memoriesPageSource() throws -> String {
        let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
        let packageDirectory = testsDirectory.deletingLastPathComponent()
        let sourceURL = packageDirectory
            .appendingPathComponent("Sources")
            .appendingPathComponent("MainWindow")
            .appendingPathComponent("Pages")
            .appendingPathComponent("MemoriesPage.swift")
        return try String(contentsOf: sourceURL, encoding: .utf8)
    }
}

/// Reversible alias during WS-G client rename (Wave 36).
typealias MemoryTierFilterTests = MemoryLayerFilterTests
