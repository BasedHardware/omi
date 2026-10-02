import XCTest

@testable import Omi_Computer

final class MemoryLayerFilterTests: XCTestCase {
  func testDefaultFilterIsDefaultAccessOnly() {
    XCTAssertEqual(MemoryLayerFilter.defaultAccess.allowedLayers, [.shortTerm, .longTerm])
    XCTAssertFalse(MemoryLayerFilter.defaultAccess.allowedLayers.contains(.archive))
  }

  func testUsefulNowKeepsUnknownAndDropsServerDatedHistory() {
    let unknown = makeMemory(id: "unknown", tierIsExplicit: true)
    let history = ServerMemory(
      id: "history",
      content: "Old decision",
      category: .system,
      tier: .longTerm,
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
      headline: nil,
      currencyBand: "history",
      currencyMetadataIsExplicit: true
    )

    let useful = MemoryPageProjection.visibleMemories(
      cachedMemories: [], serverMemories: [unknown, history],
      source: .authoritativeServer, lifecycleExposed: true,
      temporalFilter: .usefulNow)
    let all = MemoryPageProjection.visibleMemories(
      cachedMemories: [], serverMemories: [unknown, history],
      source: .authoritativeServer, lifecycleExposed: true,
      temporalFilter: .all)

    XCTAssertEqual(useful.map(\.id), ["unknown"])
    XCTAssertEqual(Set(all.map(\.id)), Set(["unknown", "history"]))
  }

  func testHistoryKeepsSuppressedRowsForReEnable() {
    let suppressed = ServerMemory(
      id: "suppressed",
      content: "A true but currently suppressed memory",
      category: .system,
      tier: .longTerm,
      tierIsExplicit: true,
      createdAt: Date(timeIntervalSince1970: 1),
      updatedAt: Date(timeIntervalSince1970: 2),
      conversationId: nil,
      reviewed: true,
      userReview: true,
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
      headline: nil,
      ledgerMetadata: [
        MemoryLedgerMetadata.argumentsJSONKey:
          "{\"memory_use\":{\"last_action\":\"suppress\",\"suppressed\":true}}"
      ],
      currencyBand: "current",
      currencyMetadataIsExplicit: true
    )
    let history = MemoryPageProjection.visibleMemories(
      cachedMemories: [], serverMemories: [suppressed],
      source: .authoritativeServer, lifecycleExposed: true,
      temporalFilter: .history)

    XCTAssertEqual(history.map(\.id), ["suppressed"])
  }

  func testHistoryKeepsServerRetainedRowsEvenWhenCurrencyBandLooksCurrent() {
    let invalid = makeMemory(
      id: "invalid",
      tierIsExplicit: true,
      ledgerMetadata: ["invalid_at": "2026-06-21T10:00:00Z"],
      currencyBand: "current")
    let superseded = makeMemory(
      id: "superseded",
      tierIsExplicit: true,
      ledgerMetadata: ["superseded_by": "memory-newer"],
      currencyBand: "current")
    let suppressed = makeMemory(
      id: "suppressed-current",
      tierIsExplicit: true,
      ledgerMetadata: [
        MemoryLedgerMetadata.argumentsJSONKey:
          "{\"memory_use\":{\"last_action\":\"suppress\",\"suppressed\":true}}"
      ],
      currencyBand: "current")
    let values = [invalid, superseded, suppressed]

    XCTAssertTrue(invalid.isHistory)
    XCTAssertTrue(superseded.isHistory)
    XCTAssertTrue(suppressed.isHistory)
    XCTAssertFalse(invalid.isUsefulNow)
    XCTAssertFalse(superseded.isUsefulNow)
    XCTAssertFalse(suppressed.isUsefulNow)

    let useful = MemoryPageProjection.visibleMemories(
      cachedMemories: [], serverMemories: values,
      source: .authoritativeServer, lifecycleExposed: true,
      temporalFilter: .usefulNow)
    let history = MemoryPageProjection.visibleMemories(
      cachedMemories: [], serverMemories: values,
      source: .authoritativeServer, lifecycleExposed: true,
      temporalFilter: .history)

    XCTAssertTrue(useful.isEmpty)
    XCTAssertEqual(Set(history.map(\.id)), Set(values.map(\.id)))
  }

  func testUseControlsHideInactiveHistoryButRemainForActiveDatedAndSuppressedRows() {
    let activeDated = makeMemory(
      id: "active-dated",
      tierIsExplicit: true,
      currencyBand: "history")
    let suppressed = makeMemory(
      id: "suppressed",
      tierIsExplicit: true,
      ledgerMetadata: [
        MemoryLedgerMetadata.argumentsJSONKey:
          "{\"memory_use\":{\"last_action\":\"suppress\",\"suppressed\":true}}"
      ],
      currencyBand: "current")
    let invalid = makeMemory(
      id: "invalid",
      tierIsExplicit: true,
      ledgerMetadata: ["invalid_at": "2026-06-21T10:00:00Z"],
      currencyBand: "current")
    let superseded = makeMemory(
      id: "superseded",
      tierIsExplicit: true,
      ledgerMetadata: ["superseded_by": "memory-newer"],
      currencyBand: "current")
    let inactive = makeMemory(
      id: "inactive",
      tierIsExplicit: true,
      ledgerMetadata: ["status": "inactive"],
      currencyBand: "current")

    XCTAssertTrue(activeDated.isUseControlEligible)
    XCTAssertTrue(suppressed.isUseControlEligible)
    XCTAssertFalse(invalid.isUseControlEligible)
    XCTAssertFalse(superseded.isUseControlEligible)
    XCTAssertFalse(inactive.isUseControlEligible)
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
    XCTAssertTrue(source.contains("guard\n        commitMemoryPageCapabilities("))
    XCTAssertTrue(source.contains("let fetchResult = try await fetchMemoriesPageDeviceScopeAware("))
    XCTAssertTrue(source.contains("let page = fetchResult.page"))
    XCTAssertTrue(source.contains("deviceScopeSupportedOverride: fetchResult.deviceScopeSupportedOverride"))
    XCTAssertTrue(source.contains("reason: \"capability_mismatch\""))
  }

  func testLegacyDeviceScopeFallbackDoesNotLocallyHideUnprovenancedMemories() throws {
    let source = try memoriesPageSource()

    // omi-test-quality: source-inspection -- static contract: the page must reach device scoping only
    // through the one shared guardrail, so a second reader of the view model cannot obey a copy of the
    // rule that lives inside this page's private recompute. The *behaviour* — an account the backend
    // cannot scope keeps its unprovenanced rows instead of emptying the list — is covered by
    // MemoryVisibilityGuardrailTests.testDeviceScopeIsNotAppliedLocallyWhenTheBackendCannotSupportIt,
    // which exercises the policy rather than asserting on this file's text.
    XCTAssertTrue(
      source.contains("MemoryPageProjection.guardrailed("),
      "The page must apply device scope through the shared guardrail, not a private copy."
    )
    XCTAssertFalse(
      source.contains("if filterThisDeviceOnly && deviceScopeSupported {"),
      "The in-page copy of the device-scope branch must not come back; it is what leaked archive to Home."
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

  func testMemoryUseControlsAndWritesRequireBeliefCapability() throws {
    let source = try memoriesPageSource()

    // omi-test-quality: source-inspection -- use feedback is beta-gated both at the UI surface and mutation boundary, including stale closures
    XCTAssertTrue(
      source.contains("showUseControls: viewModel.beliefCapabilityEnabled == true && memory.isUseControlEligible"))
    XCTAssertTrue(source.contains("if showUseControls {"))
    XCTAssertTrue(source.contains("guard beliefCapabilityEnabled == true, memory.isUseControlEligible else { return }"))
    XCTAssertTrue(source.contains("memory.isUseControlEligible"))
    XCTAssertTrue(source.contains("await waitForMemoryLoadLifecycleToSettle()"))
    XCTAssertTrue(source.contains("let projectionBeforeRefresh = authoritativeProjectionGeneration"))
    XCTAssertTrue(source.contains("authoritativeProjectionGeneration > projectionBeforeRefresh"))
    XCTAssertTrue(source.contains("if confirmed {"))
    XCTAssertTrue(source.contains("pendingMemoryUseFeedbackIDs.removeAll()"))
  }

  func testInitialMemoryHandshakeRestartsExplicitTemporalViewBeforeRetainingCursor() throws {
    let source = try memoriesPageSource()

    // omi-test-quality: source-inspection -- a capability-discovering first page cannot donate its released-view cursor to temporal pagination
    XCTAssertTrue(source.contains("let initialRequestedView: APIClient.MemoryTemporalView?"))
    XCTAssertTrue(source.contains("if page.beliefEnabled == true && initialRequestedView == nil"))
    XCTAssertTrue(source.contains("offset: 0"))
    XCTAssertTrue(source.contains("viewOverride: selectedMemoryTemporalView"))
    XCTAssertTrue(source.contains("before retaining its cursor"))
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

  private func makeMemory(
    id: String,
    tierIsExplicit: Bool,
    ledgerMetadata: [String: String] = [:],
    currencyBand: String? = nil
  ) -> ServerMemory {
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
      headline: nil,
      ledgerMetadata: ledgerMetadata,
      currencyBand: currencyBand
    )
  }
}

/// Reversible alias during WS-G client rename (Wave 36).
typealias MemoryTierFilterTests = MemoryLayerFilterTests
