import XCTest
@testable import Omi_Computer

final class ConversationReconciliationPolicyTests: XCTestCase {
  func testServerStatusAndSummaryWinOverStaleCache() {
    let local = makeConversation(
      id: "c1",
      title: "Cache title",
      overview: "old summary",
      status: .processing
    )
    let server = makeConversation(
      id: "c1",
      title: "Server title",
      overview: "fresh summary",
      status: .completed
    )

    let result = ConversationReconciliationPolicy.mergeList(server: [server], current: [local])

    XCTAssertEqual(result.conversations.map(\.id), ["c1"])
    XCTAssertEqual(result.conversations[0].status, .completed)
    XCTAssertEqual(result.conversations[0].structured.overview, "fresh summary")
    XCTAssertEqual(result.conversations[0].structured.title, "Server title")
    XCTAssertTrue(result.pendingMutations.isEmpty)
  }

  func testStaleLocalTitleDoesNotMaskServerWithoutPendingMutation() {
    let local = makeConversation(id: "c1", title: "Local stale")
    let server = makeConversation(id: "c1", title: "Server fresh")

    let result = ConversationReconciliationPolicy.mergeList(server: [server], current: [local])

    XCTAssertEqual(result.conversations[0].structured.title, "Server fresh")
  }

  func testPendingTitleMutationTemporarilyWinsUntilServerMatches() {
    let local = makeConversation(id: "c1", title: "Optimistic local")
    let serverLagging = makeConversation(id: "c1", title: "Server old")
    var mutation = ConversationPendingMutation()
    mutation.setTitle("Optimistic local")

    let lagging = ConversationReconciliationPolicy.mergeList(
      server: [serverLagging],
      current: [local],
      pendingMutations: ["c1": mutation]
    )

    XCTAssertEqual(lagging.conversations[0].structured.title, "Optimistic local")
    XCTAssertEqual(lagging.pendingMutations["c1"]?.title, "Optimistic local")

    let serverCaughtUp = makeConversation(id: "c1", title: "Optimistic local")
    let caughtUp = ConversationReconciliationPolicy.mergeList(
      server: [serverCaughtUp],
      current: lagging.conversations,
      pendingMutations: lagging.pendingMutations
    )

    XCTAssertEqual(caughtUp.conversations[0].structured.title, "Optimistic local")
    XCTAssertNil(caughtUp.pendingMutations["c1"])
  }

  func testExpiredPendingMutationDoesNotMaskNewerServerValue() {
    let baseTime = Date(timeIntervalSince1970: 10_000)
    let local = makeConversation(id: "c1", title: "Optimistic local")
    let serverSuperseded = makeConversation(id: "c1", title: "Server from another client")
    var mutation = ConversationPendingMutation()
    mutation.setTitle("Optimistic local")
    mutation.titleRecordedAt = baseTime

    let result = ConversationReconciliationPolicy.mergeList(
      server: [serverSuperseded],
      current: [local],
      pendingMutations: ["c1": mutation],
      now: baseTime.addingTimeInterval(121),
      pendingMutationTTL: 120
    )

    XCTAssertEqual(result.conversations[0].structured.title, "Server from another client")
    XCTAssertNil(result.pendingMutations["c1"])
  }

  func testExpiredPendingMutationForMissingServerRowIsDropped() {
    let baseTime = Date(timeIntervalSince1970: 10_000)
    let server = makeConversation(id: "server-row")
    var expired = ConversationPendingMutation()
    expired.setTitle("Never returned again")
    expired.titleRecordedAt = baseTime

    let result = ConversationReconciliationPolicy.mergeList(
      server: [server],
      current: [server],
      pendingMutations: ["missing-row": expired],
      now: baseTime.addingTimeInterval(121),
      pendingMutationTTL: 120
    )

    XCTAssertEqual(result.conversations.map(\.id), ["server-row"])
    XCTAssertTrue(result.pendingMutations.isEmpty)
  }

  func testPendingStarAndFolderMutationsTemporarilyWinAndThenClear() {
    let local = makeConversation(id: "c1", starred: true, folderId: "local-folder")
    let serverLagging = makeConversation(id: "c1", starred: false, folderId: "server-folder")
    var mutation = ConversationPendingMutation()
    mutation.setStarred(true)
    mutation.setFolderId("local-folder")

    let lagging = ConversationReconciliationPolicy.mergeList(
      server: [serverLagging],
      current: [local],
      pendingMutations: ["c1": mutation]
    )

    XCTAssertTrue(lagging.conversations[0].starred)
    XCTAssertEqual(lagging.conversations[0].folderId, "local-folder")
    XCTAssertEqual(lagging.pendingMutations["c1"]?.starred, true)

    let serverCaughtUp = makeConversation(id: "c1", starred: true, folderId: "local-folder")
    let caughtUp = ConversationReconciliationPolicy.mergeList(
      server: [serverCaughtUp],
      current: lagging.conversations,
      pendingMutations: lagging.pendingMutations
    )

    XCTAssertTrue(caughtUp.conversations[0].starred)
    XCTAssertEqual(caughtUp.conversations[0].folderId, "local-folder")
    XCTAssertNil(caughtUp.pendingMutations["c1"])
  }

  // MARK: - Per-field TTL independence (review feedback)

  /// A later star change must NOT refresh the TTL of an older title overlay.
  func testLaterStarMutationDoesNotRefreshOlderTitleOverlayTTL() {
    let baseTime = Date(timeIntervalSince1970: 10_000)
    let server = makeConversation(id: "c1", title: "Server title", starred: false)

    var mutation = ConversationPendingMutation()
    mutation.setTitle("Optimistic title")
    mutation.titleRecordedAt = baseTime  // title recorded at T+0

    // 60 seconds later, user also stars the conversation — title is 60s old
    mutation.setStarred(true)
    // setStarred stamps starredRecordedAt, but does NOT touch titleRecordedAt

    // At T+121, title is expired (121 > 120) but star is only 61s old (not expired)
    let result = ConversationReconciliationPolicy.mergeList(
      server: [server],
      current: [server],
      pendingMutations: ["c1": mutation],
      now: baseTime.addingTimeInterval(121),
      pendingMutationTTL: 120
    )

    // Title overlay should have expired — server title wins
    XCTAssertEqual(result.conversations[0].structured.title, "Server title")
    // Star overlay is still within TTL — pending star still wins
    XCTAssertTrue(result.conversations[0].starred)
    XCTAssertEqual(result.pendingMutations["c1"]?.starred, true)
    XCTAssertNil(result.pendingMutations["c1"]?.title)
  }

  /// Each field expires independently; when all fields are expired the
  /// whole mutation entry is removed even if the conversation is in the server list.
  func testAllFieldsExpiredRemovesMutationEvenWhenConversationPresent() {
    let baseTime = Date(timeIntervalSince1970: 10_000)
    let server = makeConversation(id: "c1", title: "Server title", starred: false)

    var mutation = ConversationPendingMutation()
    mutation.setTitle("Old title")
    mutation.titleRecordedAt = baseTime
    mutation.setStarred(true)
    mutation.starredRecordedAt = baseTime

    let result = ConversationReconciliationPolicy.mergeList(
      server: [server],
      current: [server],
      pendingMutations: ["c1": mutation],
      now: baseTime.addingTimeInterval(121),
      pendingMutationTTL: 120
    )

    XCTAssertTrue(result.pendingMutations.isEmpty)
    XCTAssertEqual(result.conversations[0].structured.title, "Server title")
    XCTAssertFalse(result.conversations[0].starred)
  }

  func testServerOrderIsPreservedAndSyncedCacheRowsMissingFromServerAreDropped() {
    let localOnlySynced = makeConversation(id: "stale", createdAt: Date(timeIntervalSince1970: 999))
    let serverOlder = makeConversation(id: "older", createdAt: Date(timeIntervalSince1970: 100))
    let serverNewer = makeConversation(id: "newer", createdAt: Date(timeIntervalSince1970: 200))

    let result = ConversationReconciliationPolicy.mergeList(
      server: [serverOlder, serverNewer],
      current: [localOnlySynced, serverNewer, serverOlder]
    )

    XCTAssertEqual(result.conversations.map(\.id), ["older", "newer"])
  }

  func testLocalInProgressRowsSurviveUntilBackendCreatesServerConversation() {
    let localRecording = makeConversation(id: "local-live", status: .inProgress)
    let server = makeConversation(id: "server-conversation")

    let result = ConversationReconciliationPolicy.mergeList(
      server: [server],
      current: [localRecording]
    )

    XCTAssertEqual(result.conversations.map(\.id), ["server-conversation", "local-live"])
  }

  private func makeConversation(
    id: String,
    title: String = "Title",
    overview: String = "Overview",
    status: ConversationStatus = .completed,
    starred: Bool = false,
    folderId: String? = nil,
    createdAt: Date = Date(timeIntervalSince1970: 1_000)
  ) -> ServerConversation {
    ServerConversation(
      id: id,
      createdAt: createdAt,
      startedAt: createdAt,
      finishedAt: createdAt.addingTimeInterval(60),
      structured: Structured(
        title: title,
        overview: overview,
        emoji: "💬",
        category: "other",
        actionItems: [],
        events: []
      ),
      transcriptSegments: [],
      transcriptSegmentsIncluded: true,
      geolocation: nil,
      photos: [],
      appsResults: [],
      source: .desktop,
      language: "en",
      status: status,
      discarded: false,
      deleted: false,
      isLocked: false,
      starred: starred,
      folderId: folderId,
      inputDeviceName: nil,
      deferred: false
    )
  }
}
