import XCTest

@testable import Omi_Computer

/// The Memory hub's Brain Map destination is the surface users actually reach
/// from the Memory menu. It previously rendered `MemoryGraphPage`
/// unconditionally, so canonical-cohort users kept the legacy graph there even
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
    let source = try desktopHomeViewSource()

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
    let source = try desktopHomeViewSource()
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

  private func desktopHomeViewSource() throws -> String {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let packageDirectory = testsDirectory.deletingLastPathComponent()
    let sourceURL =
      packageDirectory
      .appendingPathComponent("Sources")
      .appendingPathComponent("MainWindow")
      .appendingPathComponent("DesktopHomeView.swift")
    // omi-test-quality: source-inspection -- static contract: SwiftUI exposes no seam to observe which branch of a @ViewBuilder switch rendered, so the hub's gate wiring is asserted statically; the decision itself is covered behaviorally above.
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
