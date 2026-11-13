import OmiTheme
import SwiftUI
import XCTest

@testable import Omi_Computer

/// A truncated list page (`X-Omi-List-Truncated: true`) is an unfinished read:
/// the server stopped before its read budget, so absence from it proves
/// nothing. The Memories page used to present such a page as a complete, empty
/// account ("No Memories Yet"), and a truncated conversation-cascade refresh
/// pruned local rows the server never reached (#24722). These tests pin the
/// honest state: an empty truncated page keeps the rows on screen and flags the
/// list, a truncated page with rows is shown but flagged, a complete page clears
/// the flag, and a truncated cascade refresh never prunes.
@MainActor
final class MemoriesTruncatedReadStateTests: XCTestCase {
  private var userDir: URL?
  private var authSnapshot: RewindStorageTestIsolation.AuthSnapshot?

  /// The browse surface reads 100-row pages; the background full sync and the
  /// cascade refresh read 500-row batches. The stub tells them apart by limit
  /// so a test can script the visible list without the background reads
  /// consuming its pages.
  private let backgroundBatchSize = 500

  override func setUp() async throws {
    authSnapshot = RewindStorageTestIsolation.captureAuthSnapshot()
    let fixture = try await RewindStorageTestIsolation.setUp(userIdPrefix: "memories-truncated-read")
    userDir = fixture.userDir
    RewindStorageTestIsolation.signInForTests(userId: fixture.testUserId)
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: fixture.testUserId)
  }

  override func tearDown() async throws {
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
      RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: authSnapshot.userId)
    }
    if let userDir {
      await RewindStorageTestIsolation.tearDown(userDir: userDir)
    }
  }

  // MARK: - Visible list

  func testEmptyTruncatedFirstReadIsUnfinishedNotEmpty() async throws {
    let viewModel = makeViewModel(browsePages: [page([], truncated: true)])

    await viewModel.loadMemories()

    XCTAssertTrue(viewModel.memories.isEmpty)
    XCTAssertTrue(viewModel.listReadTruncated, "an empty truncated page is an unfinished read")
    XCTAssertNil(viewModel.errorMessage, "an unfinished read is not a failed one")
    XCTAssertFalse(viewModel.hasMoreMemories, "a truncated page carries no resumable cursor")
    XCTAssertFalse(viewModel.isLoading)
  }

  func testEmptyTruncatedRefreshKeepsTheRowsOnScreen() async throws {
    let kept = makeMemory(id: "kept-1")
    let alsoKept = makeMemory(id: "kept-2")
    let viewModel = makeViewModel(browsePages: [page([kept, alsoKept]), page([], truncated: true)])
    await viewModel.loadMemories()
    XCTAssertEqual(viewModel.memories.map(\.id), ["kept-1", "kept-2"])
    XCTAssertFalse(viewModel.listReadTruncated)

    viewModel.isActive = true
    await viewModel.refreshMemoriesIfNeeded()

    XCTAssertEqual(
      viewModel.memories.map(\.id), ["kept-1", "kept-2"],
      "a refresh the server could not finish must not blank what was already shown")
    XCTAssertTrue(viewModel.listReadTruncated)
    XCTAssertFalse(viewModel.hasMoreMemories)
  }

  func testTruncatedPageWithRowsIsShownButFlagged() async throws {
    let partial = makeMemory(id: "partial-1")
    let viewModel = makeViewModel(browsePages: [page([partial], truncated: true)])

    await viewModel.loadMemories()

    XCTAssertEqual(viewModel.memories.map(\.id), ["partial-1"])
    XCTAssertTrue(viewModel.listReadTruncated, "rows that did arrive are shown, but not as the whole history")
    XCTAssertFalse(viewModel.hasMoreMemories)
  }

  func testCompleteReadClearsTheUnfinishedFlag() async throws {
    let complete = makeMemory(id: "complete-1")
    let viewModel = makeViewModel(browsePages: [page([], truncated: true), page([complete])])
    await viewModel.loadMemories()
    XCTAssertTrue(viewModel.listReadTruncated)

    await viewModel.loadMemories()

    XCTAssertEqual(viewModel.memories.map(\.id), ["complete-1"])
    XCTAssertFalse(viewModel.listReadTruncated, "a complete page is authoritative again")
  }

  func testSessionResetClearsTheUnfinishedFlag() async throws {
    let viewModel = makeViewModel(browsePages: [page([], truncated: true)])
    await viewModel.loadMemories()
    XCTAssertTrue(viewModel.listReadTruncated)

    viewModel.resetSessionState()

    XCTAssertFalse(viewModel.listReadTruncated, "the next owner starts without the previous owner's read state")
  }

  // MARK: - Conversation cascade refresh

  func testTruncatedCascadeRefreshDoesNotPruneLocalRows() async throws {
    let reached = makeMemory(id: "reached")
    let unreached = makeMemory(id: "unreached")
    try await MemoryStorage.shared.syncServerMemories([reached, unreached])
    // The cascade and the fallback load both see a truncated page that holds
    // only the first row; the second row is absent because the server stopped,
    // not because it was deleted.
    let viewModel = makeViewModel(
      browsePages: [page([reached, unreached]), page([reached], truncated: true)],
      backgroundPage: page([reached], truncated: true))
    await viewModel.loadMemories()
    XCTAssertEqual(viewModel.memories.map(\.id), ["reached", "unreached"])

    await viewModel.handleConversationDeleted("some-other-conversation")

    let survivor = try await MemoryStorage.shared.getMemoryByBackendId("unreached")
    XCTAssertNotNil(survivor, "a row the truncated pull never reached must still be cached")
    XCTAssertNotEqual(survivor?.deleted, true, "a truncated cascade pull is no evidence of deletion")
    XCTAssertEqual(viewModel.memories.map(\.id), ["reached"], "the rows that did arrive are shown")
    XCTAssertTrue(viewModel.listReadTruncated, "and the list says it is unfinished")
  }

  // MARK: - Page states

  /// Renders the two unfinished-read states so a reviewer can see them without
  /// forcing the server to stop early. Set `OMI_MEMORIES_RENDER_DIR` to write
  /// the PNGs that back the PR's UI evidence.
  func testRendersUnfinishedReadStates() throws {
    let frames: [(String, AnyView)] = [
      ("001-desktop-macos-memories-unfinished-read", AnyView(MemoriesUnfinishedReadState(retry: {}))),
      (
        "002-desktop-macos-memories-unfinished-footer",
        AnyView(
          VStack(spacing: OmiSpacing.md) {
            Text("Memories").font(.title)
            Spacer()
            MemoriesUnfinishedReadFooter(retry: {})
          })
      ),
    ]
    for (name, content) in frames {
      let view =
        content
        .padding(24)
        .frame(width: 640, height: 360)
        .background(Color(nsColor: .windowBackgroundColor))
        .environment(\.colorScheme, .dark)
      let renderer = ImageRenderer(content: view)
      renderer.scale = 2
      let image = try XCTUnwrap(renderer.cgImage, "\(name) must render offscreen")
      let png = try XCTUnwrap(
        NSBitmapImageRep(cgImage: image).representation(using: .png, properties: [:]))
      if let dir = ProcessInfo.processInfo.environment["OMI_MEMORIES_RENDER_DIR"] {
        try png.write(to: URL(fileURLWithPath: dir).appendingPathComponent("\(name).png"))
      }
    }
  }

  // MARK: - Helpers

  private func page(_ memories: [ServerMemory], truncated: Bool = false) -> APIClient.MemoryListPage {
    APIClient.MemoryListPage(
      memories: memories,
      nextCursor: nil,
      canonicalLifecycleExposed: false,
      deviceScopeSupported: true,
      defaultMemoryDeleteSupported: true,
      truncated: truncated
    )
  }

  /// A view model whose browse reads come from `browsePages` in order (the
  /// last page repeats) and whose 500-row background reads all return
  /// `backgroundPage`. The reconcile read fails, which the reconcile treats as
  /// "retry next launch", so no background path touches the rows under test.
  private func makeViewModel(
    browsePages: [APIClient.MemoryListPage],
    backgroundPage: APIClient.MemoryListPage? = nil
  ) -> MemoriesViewModel {
    let viewModel = MemoriesViewModel(deleteMemoryRequest: { _ in })
    var queue = browsePages
    let background = backgroundPage ?? page([])
    viewModel.memoriesPageFetch = { [backgroundBatchSize] limit, _, _, _, _, _ in
      if limit == backgroundBatchSize { return background }
      return queue.count > 1 ? queue.removeFirst() : queue[0]
    }
    viewModel.reconcilePageFetch = { _, _, _ in throw CancellationError() }
    return viewModel
  }

  private func makeMemory(id: String) -> ServerMemory {
    ServerMemory(
      id: id,
      content: "Memory \(id)",
      category: .system,
      tier: .longTerm,
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
