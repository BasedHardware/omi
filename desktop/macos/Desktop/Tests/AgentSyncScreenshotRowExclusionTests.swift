import GRDB
import XCTest

@testable import Omi_Computer

/// Closes the remaining screen-data egress in the non-screen sync path.
///
/// `memories`, `action_items`, and `staged_tasks` can hold rows whose
/// `source == "screenshot"` — frame-derived extractions with screen-derived
/// content, context summaries, app/window metadata. They live in non-screen
/// tables, so the table allowlist alone does not stop them leaving the Mac;
/// these tests prove they are dropped from every payload while the cursor
/// still advances past them.
@MainActor
final class AgentSyncScreenshotRowExclusionTests: XCTestCase {
  private var testUserId: String!
  private var userDir: URL!
  private var ownerFixture: RuntimeOwnerAuthorityTestFixture?
  private let probe = AgentSyncPayloadProbe()

  override func setUp() async throws {
    try await super.setUp()
    ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture?.establish(authOwnerID: "agent-sync-exclusion-owner")
    UserDefaults.standard.removeObject(forKey: "agentSync_cursors.agent-sync-exclusion-owner")
    testUserId = "agent-sync-exclusion-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()

    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDir =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    RewindDatabase.currentUserId = nil
    if let userDir { try? FileManager.default.removeItem(at: userDir) }
    await ownerFixture?.restore()
    ownerFixture = nil
    try await super.tearDown()
  }

  private func makeService() -> AgentSyncService {
    let probe = self.probe
    return AgentSyncService(
      networkHooks: AgentSyncService.NetworkHooks(
        fetchIDToken: { "test-firebase-token" },
        dataForRequest: { request in try await probe.respond(to: request) },
        reuploadDatabase: { _, _ in false },
        now: Date.init,
        tableSyncEnabled: true))
  }

  private func seedMemory(content: String, source: String?) async throws {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("Rewind database should be initialized")
    }
    let now = Date(timeIntervalSince1970: 1_700_000_000)
    try await dbQueue.write { db in
      try db.execute(
        sql: """
            INSERT INTO memories (content, category, source, sourceApp, contextSummary, createdAt, updatedAt)
            VALUES (?, 'system', ?, 'SecretApp', 'screen-derived summary', ?, ?)
          """,
        arguments: [content, source, now, now])
    }
  }

  func testScreenshotSourcedMemoriesNeverReachTheSyncPayload() async throws {
    try await seedMemory(content: "screen-derived memory", source: "screenshot")
    try await seedMemory(content: "conversation-derived memory", source: "desktop")

    let originalPhase = AuthState.shared.sessionPhase
    AuthState.shared.transition(to: .authenticated)
    defer { AuthState.shared.transition(to: originalPhase) }

    let service = makeService()
    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")
    await service.syncOnceForTesting()

    let contents = await probe.recordedMemoryContents()
    XCTAssertEqual(
      contents, ["conversation-derived memory"],
      "the screenshot-sourced extraction must never leave the Mac")
    await service.stop(flushPendingChanges: false)
  }

  func testFullyFilteredPageAdvancesTheCursorInsteadOfLoopingForever() async throws {
    try await seedMemory(content: "only a screen-derived memory", source: "screenshot")

    let originalPhase = AuthState.shared.sessionPhase
    AuthState.shared.transition(to: .authenticated)
    defer { AuthState.shared.transition(to: originalPhase) }

    let service = makeService()
    await service.startForTesting(vmIP: "127.0.0.1", authToken: "test-token")
    await service.syncOnceForTesting()
    await service.syncOnceForTesting()

    let pushes = await probe.pushedMemoryBatchCount()
    XCTAssertEqual(
      pushes, 0,
      "a page that is entirely screenshot-sourced has nothing to push")

    // The page must still have been consumed: a newly added non-screen row is
    // picked up on the next tick rather than the scan being stuck re-reading
    // the filtered page forever.
    try await seedMemory(content: "later conversation memory", source: "phone")
    await service.syncOnceForTesting()
    let laterContents = await probe.recordedMemoryContents()
    XCTAssertEqual(laterContents, ["later conversation memory"])
    await service.stop(flushPendingChanges: false)
  }
}

/// Records `/sync` payloads so tests can assert exactly which memory rows
/// would have left the Mac, as plain `String`s (payload dictionaries are not
/// Sendable under Swift 6 strict checking). Health always reports a ready
/// database and every push 200s.
private actor AgentSyncPayloadProbe {
  private var pushedBatches = 0
  private var memoryContents: [String] = []

  func respond(to request: URLRequest) throws -> (Data, URLResponse) {
    let url = try XCTUnwrap(request.url)
    let response =
      HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)
      ?? URLResponse(url: url, mimeType: nil, expectedContentLength: 0, textEncodingName: nil)
    switch url.path {
    case "/auth":
      return (Data(), response)
    case "/sync":
      let payload = try XCTUnwrap(request.httpBody)
      let json = try XCTUnwrap(try JSONSerialization.jsonObject(with: payload) as? [String: Any])
      if json["table"] as? String == "memories" {
        pushedBatches += 1
        let rows = try XCTUnwrap(json["rows"] as? [[String: Any]])
        memoryContents.append(contentsOf: rows.compactMap { $0["content"] as? String })
      }
      return (Data(), response)
    default:
      return (
        try JSONSerialization.data(withJSONObject: ["databaseReady": true]),
        response
      )
    }
  }

  func recordedMemoryContents() -> [String] { memoryContents }
  func pushedMemoryBatchCount() -> Int { pushedBatches }
}

/// Ambiguous VM readiness must not preserve cursors bound to a previous VM:
/// a replacement VM plus a transient health failure would otherwise send only
/// rows newer than the dead VM's cursors, permanently losing unchanged data.
@MainActor
final class AgentSyncAmbiguousReadinessTests: XCTestCase {
  func testAnUnreachableHealthResponseResetsPersistedCursors() async {
    await assertCursorsResetWhenHealthResponds(.error)
  }

  func testANonSuccessHealthResponseResetsPersistedCursors() async {
    await assertCursorsResetWhenHealthResponds(.status(503))
  }

  func testAMalformedHealthBodyResetsPersistedCursors() async {
    await assertCursorsResetWhenHealthResponds(.malformed)
  }

  private enum HealthBehavior: Sendable {
    case error
    case status(Int)
    case malformed
  }

  @MainActor
  private func assertCursorsResetWhenHealthResponds(_ behavior: HealthBehavior) async {
    let ownerFixture = RuntimeOwnerAuthorityTestFixture()
    await ownerFixture.establish(authOwnerID: "agent-sync-ambiguous-owner")
    defer { Task { await ownerFixture.restore() } }
    let cursorKey = "agentSync_cursors.agent-sync-ambiguous-owner"
    let seeded = #"{"memories":{"lastId":42,"lastUpdatedAt":"2026-01-01T00:00:00"}}"#.data(using: .utf8)
    UserDefaults.standard.set(seeded, forKey: cursorKey)
    defer { UserDefaults.standard.removeObject(forKey: cursorKey) }

    let service = AgentSyncService(
      networkHooks: AgentSyncService.NetworkHooks(
        fetchIDToken: { "test-firebase-token" },
        dataForRequest: { request in
          guard let url = request.url,
            let response = HTTPURLResponse(
              url: url, statusCode: 200, httpVersion: nil, headerFields: nil)
          else { throw URLError(.badURL) }
          switch behavior {
          case .error:
            throw URLError(.timedOut)
          case .status(let status):
            return (Data(), HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil)!)
          case .malformed:
            return (Data("not-json".utf8), response)
          }
        },
        reuploadDatabase: { _, _ in false },
        now: Date.init,
        tableSyncEnabled: true))

    await service.start(vmIP: "replacement-vm", authToken: "vm-token")
    await service.stop(flushPendingChanges: false)

    XCTAssertNil(
      UserDefaults.standard.data(forKey: cursorKey),
      "readiness that cannot be confirmed must conservatively reset cursors: resending is cheap, losing rows is not")
  }
}
