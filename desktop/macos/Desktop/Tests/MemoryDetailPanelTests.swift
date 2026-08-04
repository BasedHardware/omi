import XCTest

@testable import Omi_Computer

/// The memory detail surface became a persistent side panel instead of a modal
/// sheet. A modal hid two defects that a panel puts on screen: stale content
/// after a save, and edit state carried between memories.
@MainActor
final class MemoryDetailPanelTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memory-detail-panel")
    userDir = fixture.userDir
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
  }

  override func tearDown() async throws {
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
    }
    await RewindStorageTestIsolation.tearDown(userDir: userDir)
  }

  /// `ServerMemory.content` is immutable and `selectedMemory` holds a value
  /// copy, so a successful edit used to leave the open panel rendering the text
  /// the user had just replaced — indistinguishable from Save doing nothing.
  func testSavedEditIsReflectedInTheOpenPanel() async {
    let viewModel = MemoriesViewModel()
    let stale = makeMemory(id: "m1", content: "before the edit")
    let saved = makeMemory(id: "m1", content: "after the edit")

    viewModel.selectedMemory = stale
    viewModel.memories = [saved]

    await viewModel.refreshSelectedMemory()

    XCTAssertEqual(viewModel.selectedMemory?.content, "after the edit")
  }

  func testRefreshFallsBackToTheCacheWhenTheReloadedPageOmitsTheMemory() async throws {
    let viewModel = MemoriesViewModel()
    let cached = makeMemory(id: "cached-1", content: "cached content")
    try await MemoryStorage.shared.syncServerMemories([cached])

    viewModel.selectedMemory = makeMemory(id: "cached-1", content: "stale content")
    // The reloaded page is tier-filtered and device-scoped; the open memory can
    // legitimately fall outside it while still existing.
    viewModel.memories = []

    await viewModel.refreshSelectedMemory()

    XCTAssertEqual(viewModel.selectedMemory?.content, "cached content")
  }

  func testRefreshDoesNothingWithNoOpenMemory() async {
    let viewModel = MemoriesViewModel()
    viewModel.selectedMemory = nil
    viewModel.memories = [makeMemory(id: "m1", content: "irrelevant")]

    await viewModel.refreshSelectedMemory()

    XCTAssertNil(viewModel.selectedMemory)
  }

  func testStaticCheckerPanelIsRebuiltPerMemory() throws {
    // STATIC CHECKER. SwiftUI's reuse of a same-position view is not
    // observable without a rendered hierarchy. Without an identity the panel
    // carries one memory's unsaved draft into the next memory's editor.
    let source = try memoriesPageSource()
    guard let call = source.range(of: "private func memoryDetailPanel(") else {
      return XCTFail("The Memories page must build its detail panel in one place")
    }
    let body = String(source[call.lowerBound...].prefix(1200))

    XCTAssertTrue(
      body.contains(".id(memory.id)"),
      "The detail panel must be identified by memory, or edit state leaks between selections")
  }

  /// Public is not cosmetic: it is the only gate that feeds a memory into the
  /// user's shareable persona. It must not sit under the cursor as a switch.
  func testStaticCheckerPublishingIsADeliberateConfirmedAction() throws {
    // STATIC CHECKER. Menu and confirmation presentation is SwiftUI chrome
    // that needs a window to exercise.
    let source = try memoriesPageSource()
    guard let start = source.range(of: "struct MemoryDetailPanel: View {") else {
      return XCTFail("The Memories detail surface must be a panel")
    }
    let panel = String(source[start.lowerBound...].prefix(12000))

    XCTAssertFalse(
      panel.contains("isOn: Binding(\n            get: { memory.isPublic }"),
      "Publishing must not be a one-tap switch in the panel header")
    XCTAssertTrue(
      panel.contains("isPresented: $isConfirmingPublic"),
      "Making a memory public must be confirmed")
    XCTAssertTrue(
      panel.contains("Button(\"Make public…\")"),
      "Publishing belongs in the secondary actions menu")
  }

  private func memoriesPageSource() throws -> String {
    let url = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/MainWindow/Pages/MemoriesPage.swift")
    // omi-test-quality: source-inspection -- static contract: whether the memory detail surface is a panel or a sheet is a SwiftUI view-tree fact with no runtime accessor; the behaviour it guards is covered separately by the view-model tests.
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
