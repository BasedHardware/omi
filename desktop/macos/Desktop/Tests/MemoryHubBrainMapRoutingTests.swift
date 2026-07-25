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
