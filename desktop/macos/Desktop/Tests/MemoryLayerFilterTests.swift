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

    // omi-test-quality: source-inspection -- static contract: MemoriesPage read-scope and projection paths must stay mutually exclusive without resurrecting the legacy local lifecycle-hide branch
    XCTAssertTrue(source.contains("recordReadScope(for: token)"))
    XCTAssertTrue(source.contains("MemoryPageProjection.visibleMemories("))
    XCTAssertFalse(source.contains("lifecycleExposed ? values : values.map { $0.hidingLifecycleExposure() }"))
  }

  func testMemoriesPageCommitsPageCapabilitiesThroughSingleFreshnessHelper() throws {
    let source = try memoriesPageSource()

    // omi-test-quality: source-inspection -- static contract: page capability metadata must be committed only through commitMemoryPageCapabilities so fetch retries cannot assign stale device-scope flags
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

    // omi-test-quality: source-inspection -- static contract: local device filtering must not run unless the backend advertises device provenance, avoiding silent hiding of unprovenanced memories
    XCTAssertTrue(
      source.contains("if filterThisDeviceOnly && deviceScopeSupported {"),
      "The local device matcher must run only when the backend can provide device provenance."
    )
  }

  func testMemoriesPageUsesTheServerPageAfterASuccessfulFetch() throws {
    let source = try memoriesPageSource()

    // omi-test-quality: source-inspection -- static contract: authoritative server pages must drive display projection and forbid resurrecting legacy cache-merge or append paths after fetch
    XCTAssertTrue(source.contains("private func displayCacheMemories("))
    XCTAssertFalse(source.contains("memories.append(contentsOf: moreFromCache)"))
    XCTAssertFalse(source.contains("memories = displayMemories(cachedMemories, for: token)"))
    XCTAssertFalse(source.contains("memories = displayMemories(mergedMemories, for: token)"))
    XCTAssertTrue(source.contains("memories = displayCacheMemories(cachedMemories, for: token)"))
    XCTAssertTrue(source.contains("source: .authoritativeServer"))
    XCTAssertTrue(source.contains("hasAuthoritativeServerProjection"))
  }

  func testEmptyAuthoritativeServerPageDoesNotDisplayNewerCachedMemory() {
    let cached = makeMemory(id: "local_42", tierIsExplicit: true)

    let visible = MemoryPageProjection.visibleMemories(
      cachedMemories: [cached],
      serverMemories: [],
      source: .authoritativeServer,
      lifecycleExposed: true
    )

    XCTAssertTrue(
      visible.isEmpty,
      "An empty successful v3 page is an empty account projection, not a reason to resurrect cache rows"
    )

    let offlineFallback = MemoryPageProjection.visibleMemories(
      cachedMemories: [cached],
      serverMemories: [],
      source: .cache,
      lifecycleExposed: true
    )
    XCTAssertEqual(offlineFallback.map(\.id), ["local_42"])
  }

  func testMemoriesPageDoesNotRenderUnclassifiedCacheBeforeLifecycleCapability() throws {
    let source = try memoriesPageSource()

    // omi-test-quality: source-inspection -- static contract: unclassified cache rows must stay deferred until canonical lifecycle exposure is remembered or confirmed by fetch
    XCTAssertTrue(source.contains("memoriesCanonicalLifecycleExposure_v1_"))
    XCTAssertTrue(source.contains("let hasRememberedLifecycleExposure = restoreCanonicalLifecycleExposure()"))
    XCTAssertTrue(source.contains("let canRenderCacheBeforeAuthoritativeFetch ="))
    XCTAssertTrue(source.contains("if canRenderCacheBeforeAuthoritativeFetch {"))
    XCTAssertTrue(source.contains("Deferring unclassified cache until lifecycle capability is confirmed"))
  }

  func testLayerFilterControlsRenderOnlyAfterCanonicalLifecycleExposure() throws {
    let source = try memoriesPageSource()

    // omi-test-quality: source-inspection -- static contract: layer-filter controls must render only after canonical lifecycle exposure is known, preventing stale tier UI before capability fetch
    let headerStart = try XCTUnwrap(source.range(of: "private var header: some View"))
    let headerSource = source[headerStart.lowerBound...]
    let lifecycleGate = try XCTUnwrap(
      headerSource.range(of: "if viewModel.canonicalLifecycleExposed {")?.lowerBound)
    let layerOptions = try XCTUnwrap(
      headerSource.range(of: "ForEach(MemoryLayerFilter.allCases)")?.lowerBound)

    XCTAssertLessThan(lifecycleGate, layerOptions)
  }

  private func memoriesPageSource() throws -> String {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let packageDirectory = testsDirectory.deletingLastPathComponent()
    let sourceURL =
      packageDirectory
      .appendingPathComponent("Sources")
      .appendingPathComponent("MainWindow")
      .appendingPathComponent("Pages")
      .appendingPathComponent("MemoriesPage.swift")
    // omi-test-quality: source-inspection -- static contract: MemoriesPage layer-filter and projection wiring cannot be exercised without a booted SwiftUI view
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  private func makeMemory(id: String, tierIsExplicit: Bool) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "A cached memory",
      category: .system,
      tier: .longTerm,
      tierIsExplicit: tierIsExplicit,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
      reviewed: false,
      userReview: nil,
      visibility: "private",
      manuallyAdded: false,
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
  }
}

/// Reversible alias during WS-G client rename (Wave 36).
typealias MemoryTierFilterTests = MemoryLayerFilterTests
