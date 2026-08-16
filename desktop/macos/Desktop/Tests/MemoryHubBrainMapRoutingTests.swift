import XCTest

@testable import Omi_Computer

/// The Memory hub's Brain Map destination is the surface users actually reach
/// from the Memory menu. It previously rendered `MemoryGraphPage`
/// unconditionally, so assertion-backed users kept the legacy graph there even
/// though the atlas had already shipped behind `MemoryGraphPresentationMode`.
final class MemoryHubBrainMapRoutingTests: XCTestCase {

  // MARK: - Behavioral coverage of the routing decision

  func testBrainMapDestinationResolvesAtlasOnlyForCanonicalCohort() {
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(canonicalLifecycleExposed: true),
      .canonicalAtlas,
      "Canonical-cohort users must get the atlas on the Brain Map destination."
    )
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(canonicalLifecycleExposed: false),
      .legacyBrainMap,
      "Users outside the canonical lifecycle must keep the legacy graph."
    )
  }

  func testUnknownCohortMountsNeitherSurfaceInsteadOfGuessingLegacy() {
    // Regression: the gate read a Bool, so "not canonical" and "not known yet"
    // were the same answer, and the Brain Map mounted the legacy graph for the
    // frames before the first authoritative memory response. That mount is not
    // inert — it latches the shared view model's in-flight guard, so the atlas
    // that replaced it found prepareCanonicalAtlas() already "in progress" and
    // rendered permanently empty, and its empty-graph bootstrap fired a
    // DELETE-then-rebuild against a healthy 26-entity graph.
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(
        canonicalLifecycleExposed: false,
        capabilityEstablished: false
      ),
      .undetermined
    )
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(
        canonicalLifecycleExposed: true,
        capabilityEstablished: false
      ),
      .undetermined,
      "An unestablished capability is unknown regardless of the stale Bool it carries."
    )
    // Once established, both cohorts resolve to a real surface as before.
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(
        canonicalLifecycleExposed: true, capabilityEstablished: true),
      .canonicalAtlas
    )
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(
        canonicalLifecycleExposed: false, capabilityEstablished: true),
      .legacyBrainMap
    )
    // Local QA still short-circuits: it has no server capability to wait for.
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(
        canonicalLifecycleExposed: false,
        forceCanonicalAtlasForLocalQA: true,
        capabilityEstablished: false
      ),
      .canonicalAtlas
    )
  }

  func testStaticCheckerEmptyGraphBootstrapRequiresAnAuthoritativeLoad() throws {
    // STATIC CHECKER. The rebuild bootstrap is DELETE-then-regenerate against
    // live account data, and `isEmpty` starts true, so gating it on emptiness
    // alone made a cancelled fetch indistinguishable from an empty graph.
    let source = try memoryGraphPageSource()
    let prepare = source.components(separatedBy: "func prepareGraph() async {")
    let body = String((prepare.count > 1 ? prepare[1] : "").prefix(1200))

    XCTAssertTrue(
      body.contains("didLoadAuthoritatively && isEmpty && !hasRunEmptyBootstrap"),
      "The bootstrap must require a load that actually succeeded")
    XCTAssertFalse(
      body.contains("if isEmpty && !hasRunEmptyBootstrap"),
      "Gating the destructive rebuild on isEmpty alone treats a failed fetch as an empty graph")
  }

  private func memoryGraphPageSource() throws -> String {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let packageDirectory = testsDirectory.deletingLastPathComponent()
    let sourceURL =
      packageDirectory
      .appendingPathComponent("Sources")
      .appendingPathComponent("MainWindow")
      .appendingPathComponent("Pages")
      .appendingPathComponent("MemoryGraph")
      .appendingPathComponent("MemoryGraphPage.swift")
    // omi-test-quality: source-inspection -- static contract: rebuildGraph issues a live DELETE-then-regenerate against the signed-in account, so the guard protecting it cannot be exercised behaviorally without a network seam; the gate decision it depends on is covered behaviorally above.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }

  func testLocalQAOverrideDoesNotLeakIntoProductionBundles() {
    // The override is the QA affordance for the hub tab as well; it must stay
    // gated on a non-production build so a production cohort is never widened
    // by an environment variable.
    XCTAssertEqual(
      MemoryGraphPresentationMode.resolve(
        canonicalLifecycleExposed: false,
        forceCanonicalAtlasForLocalQA: true
      ),
      .canonicalAtlas
    )
    if !AppBuild.isNonProduction {
      XCTAssertFalse(
        MemoryGraphPresentationMode.localQAOverrideEnabled,
        "Production bundles must remain gate-driven regardless of environment."
      )
    }
  }

  // MARK: - Static checker (not behavioral coverage)

  /// STATIC CHECKER, not a behavioral test: SwiftUI offers no seam to observe
  /// which view a `@ViewBuilder` switch produced without rendering the hub and
  /// its full `ViewModelContainer`. This asserts on source text instead, so it
  /// proves wiring shape only — the tests above cover the decision itself.
  func testStaticCheckerBrainMapDestinationRoutesThroughPresentationGate() throws {
    let source = try memoryHubPageSource()

    XCTAssertTrue(
      source.contains("private var brainMapPresentationMode: MemoryGraphPresentationMode"),
      "The hub must resolve the Brain Map surface through MemoryGraphPresentationMode."
    )
    XCTAssertTrue(
      source.contains("case .canonicalAtlas:") && source.contains("CanonicalMemoryAtlasTabView("),
      "The canonical branch must present the atlas tab view."
    )
    XCTAssertTrue(
      source.contains("case .legacyBrainMap:"),
      "The legacy branch must remain reachable for users outside the cohort."
    )
    XCTAssertEqual(
      source.components(separatedBy: "MemoryGraphPage(viewModel:").count - 1,
      1,
      "The legacy graph should be constructed once, inside the gated branch."
    )
    XCTAssertTrue(
      source.contains("await memoriesViewModel.loadMemoriesIfNeeded()"),
      """
      The Brain Map destination must establish the lifecycle capability itself; \
      otherwise opening straight into a persisted Brain Map destination resolves \
      the legacy graph for a canonical user who never visited Memories.
      """
    )
  }

  func testEvidenceResolvesOnlyLoadedMemoriesAndPreservesListOrder() {
    let memories = [
      makeMemory(id: "m3", content: "third"),
      makeMemory(id: "m1", content: "first"),
      makeMemory(id: "m2", content: "second"),
    ]

    // "m9" is cited by the graph but not in the loaded page. It must be absent
    // rather than fabricated, so the panel can report the gap.
    let resolved = MemoryAtlasEvidence.resolve(["m1", "m9", "m3"], in: memories)

    XCTAssertEqual(resolved.map(\.id), ["m3", "m1"])
    XCTAssertEqual(resolved.map(\.content), ["third", "first"])
    XCTAssertTrue(MemoryAtlasEvidence.resolve([], in: memories).isEmpty)
  }

  func testStaticCheckerBrainMapReadsEvidenceInPlaceInsteadOfSwitchingDestination() throws {
    // STATIC CHECKER. Selecting an entity used to switch the hub to Memories,
    // discarding the camera, the time cursor, and the selection. The inspector
    // reads the same evidence without leaving the map, so no destination write
    // may survive on the Brain Map's evidence path.
    let source = try memoryHubPageSource()
    let atlasCall =
      source.components(separatedBy: "CanonicalMemoryAtlasTabView(").last ?? ""
    let atlasBlock = String(atlasCall.prefix(600))

    XCTAssertTrue(atlasBlock.contains("evidenceProvider:"))
    XCTAssertFalse(
      atlasBlock.contains("destinationRawValue = MemoryHubDestination.memories.rawValue"),
      "Reading evidence must not navigate away from the Brain Map")
    XCTAssertFalse(
      atlasBlock.contains("memoriesViewModel.selectedMemory ="),
      "Reading evidence must not reach into the Memories page's selection")
  }

  func testStaticCheckerEvidenceIsResolvedFromTheCacheNotTheVisiblePage() throws {
    // STATIC CHECKER. Which collection the provider reads is a wiring decision
    // in a SwiftUI view builder; the cache lookup it must use is covered
    // behaviorally in MemoryCitationResolutionTests.
    //
    // `memoriesViewModel.memories` is one page of a tier-filtered,
    // device-scoped browse. Resolving citations against it reported evidence as
    // missing while it sat in the local cache.
    let source = try memoryHubPageSource()
    let atlasBlock = String(
      (source.components(separatedBy: "CanonicalMemoryAtlasTabView(").last ?? "").prefix(1000))

    XCTAssertTrue(
      atlasBlock.contains("memoriesViewModel.memories(withIDs:"),
      "Citations must resolve against the local cache")
    XCTAssertFalse(
      atlasBlock.contains("in: memoriesViewModel.memories)"),
      "Citations must not resolve against the paginated visible page")
  }

  func testStaticCheckerMemoryDetailPanelDoesNotCarrySheetSizing() throws {
    // STATIC CHECKER. Clipping is a layout outcome that needs a rendered
    // window to observe. The defect was structural: a modal sheet pinned to
    // 450×600 was reused as a side panel, so its content laid out wider than
    // the column and was clipped mid-word while its background stopped short
    // of the window bottom.
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/MemoriesPage.swift")
    // omi-test-quality: source-inspection -- static contract: the panel's placement in the SwiftUI hierarchy is not observable at runtime; this asserts the structural choice while the routing behaviour itself is exercised through the view model.
    let source = try String(contentsOf: url, encoding: .utf8)

    guard let start = source.range(of: "struct MemoryDetailPanel: View {") else {
      return XCTFail("The Memories detail surface must be a panel, not a sheet")
    }
    let panel = String(source[start.lowerBound...].prefix(12000))

    XCTAssertFalse(
      panel.contains(".frame(width: 450)"),
      "The panel must size to the column it is given, not to a sheet width")
    XCTAssertFalse(
      panel.contains(".frame(maxHeight: 600)"),
      "The panel must fill the window height, not stop at a sheet height")
    XCTAssertFalse(
      source.contains("MemoryDetailSheet"),
      "The modal sheet has no remaining caller; leaving it behind is a second source of truth")
  }

  private func makeMemory(id: String, content: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: content,
      category: .system,
      tier: .shortTerm,
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

  private func memoryHubPageSource() throws -> String {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let packageDirectory = testsDirectory.deletingLastPathComponent()
    let sourceURL =
      packageDirectory
      .appendingPathComponent("Sources")
      .appendingPathComponent("MainWindow")
      .appendingPathComponent("MemoryHubPage.swift")
    // omi-test-quality: source-inspection -- static contract: SwiftUI exposes no seam to observe which branch of a @ViewBuilder switch rendered, so the hub's gate wiring is asserted statically; the decision itself is covered behaviorally above.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
