import XCTest

@testable import Omi_Computer

private final class MemoryEditMockURLProtocol: URLProtocol, @unchecked Sendable {
  private static let lock = NSLock()
  private nonisolated(unsafe) static var _responseHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

  static func setResponseHandler(_ handler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)) {
    lock.lock()
    _responseHandler = handler
    lock.unlock()
  }

  static func reset() {
    lock.lock()
    _responseHandler = nil
    lock.unlock()
  }

  override class func canInit(with request: URLRequest) -> Bool { true }
  override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

  override func startLoading() {
    Self.lock.lock()
    let handler = Self._responseHandler
    Self.lock.unlock()

    if let handler {
      do {
        let (response, data) = try handler(request)
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: data)
        client?.urlProtocolDidFinishLoading(self)
      } catch {
        client?.urlProtocol(self, didFailWithError: error)
      }
    } else {
      guard let url = request.url,
        let response = HTTPURLResponse(
          url: url, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"])
      else {
        client?.urlProtocol(self, didFailWithError: URLError(.badServerResponse))
        return
      }
      client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
      client?.urlProtocol(self, didLoad: Data("{\"status\":\"ok\"}".utf8))
      client?.urlProtocolDidFinishLoading(self)
    }
  }

  override func stopLoading() {}
}

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
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: fixture.testUserId)
  }

  override func tearDown() async throws {
    await APIClient.shared.resetTestSession()
    MemoryEditMockURLProtocol.reset()
    if let authSnapshot {
      RewindStorageTestIsolation.restoreAuthSnapshot(authSnapshot)
      RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
      RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: authSnapshot.userId)
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

  func testFailedSaveRetainsDraftAndTheCurrentEditor() async {
    let viewModel = MemoriesViewModel(editMemoryRequest: { _, _, _ in
      throw URLError(.cannotConnectToHost)
    })
    let original = makeMemory(id: "failed-edit", content: "original")
    viewModel.selectedMemory = original
    viewModel.editingMemory = original
    viewModel.editText = "draft to keep"

    let saved = await viewModel.saveEditedMemory(original)

    XCTAssertFalse(saved)
    XCTAssertEqual(viewModel.editText, "draft to keep")
    XCTAssertEqual(viewModel.editingMemory?.id, original.id)
    XCTAssertNotNil(viewModel.editError)
    XCTAssertFalse(viewModel.isSavingMemoryEdit)
  }

  func testCanonicalReplacementAndSupersededCacheRowCommitTogether() async throws {
    let original = makeMemory(id: "old-correction", content: "before")
    let replacement = makeMemory(id: "new-correction", content: "after")
    try await MemoryStorage.shared.syncServerMemories([original])
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())

    try await MemoryStorage.shared.applyEditedMemory(
      originalID: original.id, content: replacement.content, replacement: replacement,
      authorization: LocalMutationAuthorization { RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) })

    let visible = try await MemoryStorage.shared.getLocalMemories(limit: 100)
    XCTAssertFalse(visible.contains { $0.id == original.id })
    XCTAssertEqual(visible.filter { $0.id == replacement.id }.count, 1)
  }

  func testRevokedEditReceiptDoesNotMutateCache() async throws {
    let original = makeMemory(id: "stale-correction", content: "before")
    try await MemoryStorage.shared.syncServerMemories([original])
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    RuntimeOwnerAuthorizationAuthority.shared.beginTransition()
    RuntimeOwnerAuthorizationAuthority.shared.endTransition(ownerID: snapshot.ownerID)

    do {
      try await MemoryStorage.shared.applyEditedMemory(
        originalID: original.id, content: "must not apply", replacement: nil,
        authorization: LocalMutationAuthorization { RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) })
      XCTFail("The prior authenticated session must be revoked even for the same UID")
    } catch LocalMutationAuthorizationError.revoked {
      // Expected at the production persistence boundary.
    }
    let cached = try await MemoryStorage.shared.getMemoryByBackendId(original.id)
    XCTAssertEqual(cached?.content, "before")
  }

  func testFailureRetiringOriginalRollsBackTheReplacement() async throws {
    let original = makeMemory(id: "rollback-original", content: "before")
    let replacement = makeMemory(id: "rollback-replacement", content: "after")
    try await MemoryStorage.shared.syncServerMemories([original])
    let db = try await MemoryStorage.shared.ensureInitialized()
    try await db.write { database in
      try database.execute(
        sql: """
          CREATE TRIGGER reject_edit_retirement BEFORE UPDATE OF deleted ON memories
          WHEN NEW.backendId = 'rollback-original' AND NEW.deleted = 1
          BEGIN SELECT RAISE(ABORT, 'injected edit-retirement failure'); END;
          """)
    }
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    do {
      try await MemoryStorage.shared.applyEditedMemory(
        originalID: original.id, content: replacement.content, replacement: replacement,
        authorization: LocalMutationAuthorization { RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) })
      XCTFail("Injected SQLite failure should fail the edit commit")
    } catch {}

    let visible = try await MemoryStorage.shared.getLocalMemories(limit: 100)
    XCTAssertTrue(visible.contains { $0.id == original.id })
    XCTAssertFalse(visible.contains { $0.id == replacement.id }, "A failed transaction must not leave two projections")
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

  func testSavedEditSelectsReplacementMemoryWhenBackendReturnsNewCanonicalId() async {
    let viewModel = MemoriesViewModel()
    let original = makeMemory(id: "m1-original", content: "before correction")
    let replacement = makeMemory(id: "m1-replacement", content: "after canonical correction")

    viewModel.selectedMemory = original
    viewModel.memories = [replacement]

    await viewModel.refreshSelectedMemory(preferredId: replacement.id)

    XCTAssertEqual(viewModel.selectedMemory?.id, "m1-replacement")
    XCTAssertEqual(viewModel.selectedMemory?.content, "after canonical correction")
  }

  func testSaveEditedMemoryAppliesCanonicalReplacementFromMockedAPIClient() async throws {
    let configuration = URLSessionConfiguration.ephemeral
    configuration.protocolClasses = [MemoryEditMockURLProtocol.self]
    let mockSession = URLSession(configuration: configuration)
    await APIClient.shared.setTestSession(mockSession)
    await APIClient.shared.setTestAuthHeader("Bearer test-token")

    MemoryEditMockURLProtocol.setResponseHandler { request in
      let url = try XCTUnwrap(request.url)
      let response = try XCTUnwrap(
        HTTPURLResponse(
          url: url,
          statusCode: 200,
          httpVersion: nil,
          headerFields: ["Content-Type": "application/json"]
        ))
      let body: String
      if request.httpMethod == "PATCH" && (request.url?.path.contains("/v3/memories/") ?? false) {
        body = """
          {
            "status": "ok",
            "memory": {
              "id": "m1-replacement",
              "content": "canonical replacement from mocked backend",
              "category": "system",
              "created_at": "2026-06-21T10:00:00Z",
              "updated_at": "2026-06-21T10:00:00Z"
            }
          }
          """
      } else {
        body = "{\"status\": \"ok\"}"
      }
      return (response, Data(body.utf8))
    }

    let viewModel = MemoriesViewModel()
    let original = makeMemory(id: "m1-orig", content: "before correction")
    viewModel.selectedMemory = original
    viewModel.memories = [original]
    viewModel.editText = "user correction text"

    let saved = await viewModel.saveEditedMemory(original)
    XCTAssertTrue(saved)
    XCTAssertNil(viewModel.editError)
    XCTAssertEqual(viewModel.selectedMemory?.id, "m1-replacement")
    XCTAssertEqual(viewModel.selectedMemory?.content, "canonical replacement from mocked backend")
  }

  func testStaticCheckerSaveKeepsEditorOpenWhenSaveFails() throws {
    let source = try memoriesPageSource()
    guard let start = source.range(of: "struct MemoryDetailPanel: View {") else {
      return XCTFail("The Memories detail surface must be a panel")
    }
    let panel = String(source[start.lowerBound...].prefix(12000))

    XCTAssertTrue(
      panel.contains("let saved = await viewModel.saveEditedMemory(memory)"),
      "MemoryDetailPanel must check whether saveEditedMemory succeeded before closing the editor")
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
      panel.contains("Button(\"Make Public…\")"),
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
