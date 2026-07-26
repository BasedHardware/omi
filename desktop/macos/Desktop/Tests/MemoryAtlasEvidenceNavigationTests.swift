import XCTest

@testable import Omi_Computer

/// A cited memory in the Brain Map inspector is readable in place, but it is
/// still a memory: editable, deletable, with provenance of its own. Clicking one
/// opens it on the Memories page instead of leaving the graph as the only place
/// that memory exists.
@MainActor
final class MemoryAtlasEvidenceNavigationTests: XCTestCase {
  private var userDir: URL!
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot!

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "atlas-evidence-nav")
    userDir = fixture.userDir
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
  }

  override func tearDown() async throws {
    RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
  }

  /// The graph cites memories from the whole cache; the Memories page shows a
  /// tier-filtered, device-scoped slice. Resolving only against the visible page
  /// would make most citations un-openable.
  func testOpeningACitedMemoryResolvesItFromTheCacheNotTheVisiblePage() async throws {
    let viewModel = MemoriesViewModel()
    try await MemoryStorage.shared.syncServerMemories([
      makeMemory(id: "cited-1", content: "the cited memory")
    ])
    viewModel.memories = []

    let opened = await viewModel.openMemory(id: "cited-1")

    XCTAssertTrue(opened)
    XCTAssertEqual(viewModel.selectedMemory?.content, "the cited memory")
  }

  func testOpeningAMemoryThatIsNotOnThisDeviceReportsFailure() async {
    let viewModel = MemoriesViewModel()

    let opened = await viewModel.openMemory(id: "never-synced")

    XCTAssertFalse(opened, "A caller that also switches surfaces must be able to stay put")
    XCTAssertNil(viewModel.selectedMemory)
  }

  func testStaticCheckerEvidenceRowsAreClickable() throws {
    // STATIC CHECKER. The row is a SwiftUI button inside an inspector that only
    // exists in a rendered window; the rule it encodes is that reading evidence
    // and acting on it are different gestures.
    let source = try atlasSource()
    guard let row = source.range(of: "private func evidenceRow(") else {
      return XCTFail("The inspector must render evidence through one row builder")
    }
    let body = String(source[row.lowerBound...].prefix(2600))

    XCTAssertTrue(
      body.contains("onOpenMemory(item)"),
      "A cited memory must be openable, not just readable")
    XCTAssertTrue(
      body.contains("accessibilityIdentifier(\"memory_atlas_evidence_row\")"),
      "The evidence row needs an identifier for cursor-free verification")
  }

  func testStaticCheckerTheHubOnlyLeavesTheGraphOnceTheMemoryIsOpen() throws {
    // STATIC CHECKER. The navigation is a binding write inside a SwiftUI view.
    // Switching destinations first would strand the user on the Memories page
    // with an empty panel whenever a citation is not on this device.
    let source = try homeSource()
    guard let handler = source.range(of: "onOpenMemory: { memoryId in") else {
      return XCTFail("The hub must route cited memories through one handler")
    }
    let body = String(source[handler.lowerBound...].prefix(400))

    guard
      let guardProbe = body.range(of: "guard await memoriesViewModel.openMemory(id: memoryId)"),
      let navigateProbe = body.range(of: "destinationRawValue = MemoryHubDestination.memories")
    else {
      return XCTFail("The hub must open the memory and then switch destinations")
    }
    XCTAssertLessThan(guardProbe.lowerBound, navigateProbe.lowerBound)
  }

  private func atlasSource() throws -> String {
    try read("Sources/MainWindow/Pages/MemoryGraph/CanonicalMemoryAtlasView.swift")
  }

  private func homeSource() throws -> String {
    try read("Sources/MainWindow/DesktopHomeView.swift")
  }

  private func read(_ relativePath: String) throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent(relativePath)
    return try String(contentsOf: url, encoding: .utf8)
  }

  private func makeMemory(id: String, content: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: content,
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
