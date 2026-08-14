import Foundation
import XCTest

@testable import Omi_Computer

private final class Box<T>: @unchecked Sendable {
  var value: T
  init(_ v: T) { self.value = v }
}

final class MemoryTaskInterruptionLedger: TaskInterruptionLedgerPersisting {
  var ledger = TaskInterruptionLedger()
  func load() -> TaskInterruptionLedger { ledger }
  func save(_ ledger: TaskInterruptionLedger) { self.ledger = ledger }
}

private actor SuspendedPromotionInsert {
  private var started = false
  private var released = false
  private(set) var committed = 0

  func insert(authorization: LocalMutationAuthorization) async throws {
    started = true
    while !released { await Task.yield() }
    try authorization.require()
    committed += 1
  }

  func waitUntilStarted() async {
    while !started { await Task.yield() }
  }

  func release() { released = true }
}

private actor PromotionCallRecorder {
  private var promoteCalls = 0

  func record() { promoteCalls += 1 }

  func callCount() -> Int { promoteCalls }
}

private actor SuspendedContextClient: TaskContextualResurfacingClient {
  enum PausePoint: Equatable { case control, snapshot }

  private let pausePoint: PausePoint
  private var started = false
  private var released = false
  private var snapshotCount = 0
  private var evaluationCount = 0

  init(pausePoint: PausePoint) { self.pausePoint = pausePoint }

  func getCandidateWorkflowControl(
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.TaskWorkflowControl {
    if pausePoint == .control { await pause() }
    return OmiAPI.TaskWorkflowControl(accountGeneration: 1, workflowMode: .read)
  }

  func replaceTaskContextSnapshot(
    _ snapshot: OmiAPI.NormalizedContextSnapshot,
    accountGeneration: Int,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.SnapshotReceipt {
    snapshotCount += 1
    if pausePoint == .snapshot { await pause() }
    return OmiAPI.SnapshotReceipt(
      expiresAt: snapshot.expiresAt,
      replaced: true,
      snapshotId: snapshot.snapshotId
    )
  }

  func evaluateWhatMattersNow(
    _ request: OmiAPI.EvaluationRequest,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.WhatMattersNowProjection {
    evaluationCount += 1
    return OmiAPI.WhatMattersNowProjection(
      evaluationId: "evaluation",
      expiresAt: "2030-01-01T00:00:00Z",
      generatedAt: "2029-12-31T23:00:00Z",
      materialVersion: "material",
      outputVersion: "output",
      recommendations: [],
      schemaVersion: 1
    )
  }

  private func pause() async {
    started = true
    while !released { await Task.yield() }
  }

  func waitUntilStarted() async {
    while !started { await Task.yield() }
  }

  func release() { released = true }

  func counts() -> (snapshots: Int, evaluations: Int) {
    (snapshotCount, evaluationCount)
  }
}

private func transitionContextTestOwner(to ownerID: String?) async {
  do {
    _ = try await RuntimeOwnerIdentity.performEffectiveOwnerTransition(
      plannedNextOwner: { _, _ in ownerID },
      quiesceVoice: { _, _ in },
      retargetLocalStorage: { _, _ in },
      ownerDidChange: {
        await MainActor.run {
          NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
        }
      },
      { defaults in
        defaults.removeObject(forKey: .automationOwnerOverride)
        if let ownerID {
          defaults.set(ownerID, forKey: .authUserId)
        } else {
          defaults.removeObject(forKey: .authUserId)
        }
      })
  } catch {
    XCTFail("owner transition failed: \(error)")
  }
}

final class TaskInterruptionLedgerOwnerIsolationTests: XCTestCase {
  func testDefaultOwnerTracksAuthenticationChanges() {
    let suite = "TaskInterruptionLedgerOwnerIsolationTests.\(UUID().uuidString)"
    guard let defaults = UserDefaults(suiteName: suite) else {
      XCTFail("Failed to create isolated defaults suite")
      return
    }
    defer { defaults.removePersistentDomain(forName: suite) }
    let persistence = TaskInterruptionLedgerDefaults(defaults: defaults)
    defaults.set("owner-a", forKey: .authUserId)
    persistence.save(TaskInterruptionLedger(sentAt: [Date(timeIntervalSince1970: 42)]))
    defaults.set("owner-b", forKey: .authUserId)
    XCTAssertTrue(persistence.load().sentAt.isEmpty)
    defaults.set("owner-a", forKey: .authUserId)
    XCTAssertEqual(persistence.load().sentAt.count, 1)
  }

  func testLegacyQuietHoursTraceDecodesWithoutResettingLedger() throws {
    let suite = "TaskInterruptionLedgerOwnerIsolationTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let persistence = TaskInterruptionLedgerDefaults(defaults: defaults, ownerID: "owner-a")
    let payload: [String: Any] = [
      "sentAt": [42.0],
      "dedupeExpirations": ["dedupe-key": 4_200.0],
      "lastTrace": [
        "schemaVersion": 1,
        "decisionID": "decision",
        "recommendationID": "recommendation",
        "interventionID": "intervention",
        "dedupeHash": "sha256:legacy",
        "cohort": "dogfood",
        "reason": "quiet_hours",
        "evaluatedAt": 123.0,
      ],
    ]
    defaults.set(
      try JSONSerialization.data(withJSONObject: payload),
      forKey: .taskInterruptionLedger(ownerID: "owner-a")
    )

    let loaded = persistence.load()
    XCTAssertEqual(loaded.sentAt, [Date(timeIntervalSinceReferenceDate: 42)])
    XCTAssertEqual(loaded.dedupeExpirations["dedupe-key"], Date(timeIntervalSinceReferenceDate: 4_200))
    XCTAssertEqual(loaded.lastTrace?.reason, .legacyQuietHours)

    persistence.save(loaded)
    let saved = try XCTUnwrap(
      defaults.data(forKey: .taskInterruptionLedger(ownerID: "owner-a"))
    )
    let savedJSON = try XCTUnwrap(String(data: saved, encoding: .utf8))
    XCTAssertFalse(savedJSON.contains("\"quiet_hours\""))
    XCTAssertTrue(savedJSON.contains("\"legacy_quiet_hours\""))
  }
}

final class FakeTaskContextualResurfacingClient: TaskContextualResurfacingClient, @unchecked Sendable {
  var workflowMode: OmiAPI.TaskWorkflowMode = .read
  var controlRequests = 0
  var onControl: (() -> Void)?
  var onSnapshot: (() -> Void)?
  var snapshots: [OmiAPI.NormalizedContextSnapshot] = []
  var evaluations: [OmiAPI.EvaluationRequest] = []
  var recommendations: [OmiAPI.Recommendation] = []

  func getCandidateWorkflowControl(
    expectedOwnerId: String,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.TaskWorkflowControl {
    XCTAssertFalse(expectedOwnerId.isEmpty)
    XCTAssertNotNil(authorizationSnapshot)
    controlRequests += 1
    onControl?()
    return OmiAPI.TaskWorkflowControl(accountGeneration: 1, workflowMode: workflowMode)
  }

  func replaceTaskContextSnapshot(
    _ snapshot: OmiAPI.NormalizedContextSnapshot,
    accountGeneration: Int,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.SnapshotReceipt {
    XCTAssertEqual(accountGeneration, 1)
    XCTAssertFalse(expectedOwnerId?.isEmpty ?? true)
    XCTAssertNotNil(authorizationSnapshot)
    snapshots.append(snapshot)
    onSnapshot?()
    return OmiAPI.SnapshotReceipt(
      expiresAt: snapshot.expiresAt,
      replaced: true,
      snapshotId: snapshot.snapshotId
    )
  }

  func evaluateWhatMattersNow(
    _ request: OmiAPI.EvaluationRequest,
    expectedOwnerId: String?,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot?
  ) async throws -> OmiAPI.WhatMattersNowProjection {
    XCTAssertFalse(expectedOwnerId?.isEmpty ?? true)
    XCTAssertNotNil(authorizationSnapshot)
    evaluations.append(request)
    return OmiAPI.WhatMattersNowProjection(
      evaluationId: "evaluation-1",
      expiresAt: "2030-01-01T00:00:00Z",
      generatedAt: "2029-12-31T23:00:00Z",
      materialVersion: "material-1",
      outputVersion: "output-1",
      recommendations: recommendations,
      schemaVersion: 1
    )
  }
}

final class TaskContextualResurfacingTests: XCTestCase {
  private let baseDate = Date(timeIntervalSince1970: 1_800_000_000)
  private var previousOwnerID: String?

  override func setUp() async throws {
    try await super.setUp()
    previousOwnerID = RuntimeOwnerIdentity.currentOwnerId()
    await transitionContextTestOwner(to: "context-test-owner")
  }

  override func tearDown() async throws {
    await transitionContextTestOwner(to: previousOwnerID)
    try await super.tearDown()
  }

  func testNormalizationHashesRawContextAndCoalescesRapidSwitchesByWorkstream() throws {
    let subject = TaskContextSubject(kind: .task, id: "task-1", workstreamID: "workstream-1")
    let first = try XCTUnwrap(
      TaskLocalContextEvent.appWindow(
        appName: "Slack",
        windowTitle: "Sarah — Project Atlas (3)",
        subject: subject,
        occurredAt: baseDate
      ))
    let cosmeticDuplicate = try XCTUnwrap(
      TaskLocalContextEvent.appWindow(
        appName: "Slack",
        windowTitle: "Sarah — Project Atlas (9)",
        subject: subject,
        occurredAt: baseDate.addingTimeInterval(1)
      ))
    let document = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Project Atlas launch brief",
        subject: subject,
        occurredAt: baseDate.addingTimeInterval(2)
      ))
    var accumulator = TaskContextEventAccumulator()
    accumulator.insert(first, now: baseDate)
    accumulator.insert(cosmeticDuplicate, now: baseDate)
    accumulator.insert(document, now: baseDate)

    XCTAssertEqual(first.referenceHash, cosmeticDuplicate.referenceHash)
    XCTAssertFalse(first.referenceHash.contains("sarah"))
    XCTAssertEqual(accumulator.pendingWorkstreamCount, 1)
    XCTAssertEqual(accumulator.drain(now: baseDate).count, 2)
  }

  func testRapidContextEventsProduceOneEvaluationAndOneBoundedSnapshot() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      deviceIDProvider: { "macos_deadbeef" },
      ownerIDProvider: { "owner-1" }
    )
    let subject = TaskContextSubject(kind: .workstream, id: "workstream-1", workstreamID: "workstream-1")
    for (kind, reference) in [
      (TaskContextEventKind.appWindow, "Slack tab A"),
      (.person, "Sarah"),
      (.document, "Atlas brief"),
    ] {
      let event = try XCTUnwrap(
        TaskLocalContextEvent.normalized(
          kind: kind,
          rawReference: reference,
          subject: subject,
          occurredAt: baseDate
        ))
      await service.observe(event)
    }

    let pendingWorkstreams = await service.pendingWorkstreamCount()
    XCTAssertEqual(pendingWorkstreams, 1)
    await service.flush()

    XCTAssertEqual(client.evaluations.count, 1)
    XCTAssertEqual(client.snapshots.count, 1)
    XCTAssertEqual(client.snapshots[0].deviceId, "macos_deadbeef")
    XCTAssertEqual(client.evaluations[0].deviceId, "macos_deadbeef")
    XCTAssertEqual(client.snapshots[0].matches?.count, 1)
    XCTAssertEqual(
      client.snapshots[0].matches?.first?.signals.map(\.rawValue).sorted(),
      ["app", "document", "person"]
    )

    for (kind, reference) in [
      (TaskContextEventKind.appWindow, "Slack tab A"),
      (.person, "Sarah"),
      (.document, "Atlas brief"),
    ] {
      let repeated = try XCTUnwrap(
        TaskLocalContextEvent.normalized(
          kind: kind,
          rawReference: reference,
          subject: subject,
          occurredAt: baseDate
        ))
      await service.observe(repeated)
    }
    await service.flush()
    XCTAssertEqual(client.evaluations.count, 1)
  }

  func testDifferentUnmatchedRawContextsShareOneSemanticEvaluationWithinFiveMinutes() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { "owner-1" }
    )
    let first = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .appWindow,
        rawReference: "Unmatched window one",
        occurredAt: baseDate
      ))
    let second = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Different unmatched document",
        occurredAt: baseDate.addingTimeInterval(1)
      ))

    await service.observe(first)
    await service.flush()
    await service.observe(second)
    await service.flush()

    XCTAssertEqual(client.snapshots.count, 1)
    XCTAssertEqual(client.snapshots[0].matches?.count, 0)
    XCTAssertEqual(client.evaluations.count, 1)
  }

  func testMatchedContextTransitionToEmptyReevaluatesOnce() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { "owner-1" }
    )
    let subject = TaskContextSubject(kind: .task, id: "task-1", workstreamID: nil)
    let matched = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .appWindow,
        rawReference: "Matched window",
        subject: subject,
        occurredAt: baseDate
      ))
    let unmatched = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Unmatched document",
        occurredAt: baseDate.addingTimeInterval(1)
      ))

    await service.observe(matched)
    await service.flush()
    await service.observe(unmatched)
    await service.flush()

    XCTAssertEqual(client.snapshots.count, 2)
    XCTAssertEqual(client.snapshots[0].matches?.count, 1)
    XCTAssertEqual(client.snapshots[1].matches?.count, 0)
    XCTAssertEqual(client.evaluations.count, 2)
  }

  func testChangedTypedMatchReevaluates() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { "owner-1" }
    )
    let subject = TaskContextSubject(kind: .task, id: "task-1", workstreamID: nil)
    let app = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .appWindow,
        rawReference: "Matched app",
        subject: subject,
        occurredAt: baseDate
      ))
    let document = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Matched document",
        subject: subject,
        occurredAt: baseDate.addingTimeInterval(1)
      ))

    await service.observe(app)
    await service.flush()
    await service.observe(document)
    await service.flush()

    XCTAssertEqual(client.evaluations.count, 2)
    XCTAssertEqual(client.snapshots[0].matches?.first?.signals, [.app])
    XCTAssertEqual(client.snapshots[1].matches?.first?.signals, [.document])
  }

  @MainActor
  func testUrgencyTransitionRechecksServerGateButKeepsSemanticSnapshotStable() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let subject = TaskContextSubject(kind: .task, id: "task-urgent", workstreamID: nil)
    client.recommendations = [recommendation(id: subject.id)]
    var interruptions: [TaskInterruptionCandidate] = []
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { "owner-1" },
      sendInterruption: { interruptions.append($0) }
    )
    let first = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Matched urgent document",
        subject: subject,
        urgency: .canWait
      ))
    let urgent = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Matched urgent document",
        subject: subject,
        urgency: .timeSensitive
      ))

    await service.observe(first)
    await service.flush()
    await service.observe(urgent)
    await service.flush()

    XCTAssertEqual(client.controlRequests, 2)
    XCTAssertEqual(client.evaluations.count, 2)
    XCTAssertEqual(client.snapshots.count, 2)
    XCTAssertEqual(
      client.snapshots[0].matches?.map { "\($0.subjectKind.rawValue):\($0.subjectId)" },
      client.snapshots[1].matches?.map { "\($0.subjectKind.rawValue):\($0.subjectId)" }
    )
    XCTAssertEqual(client.snapshots[0].matches?.first?.signals, client.snapshots[1].matches?.first?.signals)
    XCTAssertEqual(interruptions.map(\.recommendationID), ["output-1:dedupe-task-urgent"])
  }

  @MainActor
  func testUrgencyTransitionCannotReuseProjectionAfterWorkflowIsDisabled() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let subject = TaskContextSubject(kind: .task, id: "task-disabled", workstreamID: nil)
    client.recommendations = [recommendation(id: subject.id)]
    var interruptions: [TaskInterruptionCandidate] = []
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { "owner-1" },
      sendInterruption: { interruptions.append($0) }
    )
    let first = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Matched gated document",
        subject: subject,
        urgency: .canWait
      ))
    let urgent = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Matched gated document",
        subject: subject,
        urgency: .timeSensitive
      ))

    await service.observe(first)
    await service.flush()
    client.workflowMode = .off
    await service.observe(urgent)
    await service.flush()

    XCTAssertEqual(client.controlRequests, 2)
    XCTAssertEqual(client.evaluations.count, 1)
    XCTAssertTrue(interruptions.isEmpty)
  }

  @MainActor
  func testOwnerSwitchInvalidatesLocalEvaluationCache() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let subject = TaskContextSubject(kind: .task, id: "task-owner-switch", workstreamID: nil)
    let ownerID = Box("owner-a")
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { ownerID.value }
    )
    let event = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Matched owner-scoped document",
        subject: subject
      ))

    await service.observe(event)
    await service.flush()
    ownerID.value = "owner-b"
    await service.observe(event)
    await service.flush()

    XCTAssertEqual(client.controlRequests, 2)
    XCTAssertEqual(client.evaluations.count, 2)
  }

  @MainActor
  func testQueuedContextIsClearedWhenOwnerChangesBeforeFlush() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let ownerID = Box("owner-a")
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { ownerID.value }
    )
    let ownerAEvent = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Owner A document",
        subject: TaskContextSubject(kind: .task, id: "task-owner-a", workstreamID: nil)
      ))
    let ownerBEvent = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Owner B document",
        subject: TaskContextSubject(kind: .task, id: "task-owner-b", workstreamID: nil)
      ))

    await service.observe(ownerAEvent)
    ownerID.value = "owner-b"
    await service.observe(ownerBEvent)
    await service.flush()

    XCTAssertEqual(client.snapshots.count, 1)
    XCTAssertEqual(client.snapshots[0].matches?.map(\.subjectId), ["task-owner-b"])
  }

  @MainActor
  func testLegacyDebounceIsCancelledWhenContextBucketsBecomesEnabled() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let flag = Box(false)
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { "owner-1" },
      contextBucketsEnabled: { flag.value }
    )
    let event = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "legacy debounce before flag flip",
        subject: TaskContextSubject(kind: .task, id: "task-flag", workstreamID: nil),
        occurredAt: baseDate
      ))

    await service.observe(event)
    var pending = await service.pendingWorkstreamCount()
    XCTAssertEqual(pending, 1)
    flag.value = true
    // Flag-on observe must cancel the pending legacy debounce immediately.
    await service.observe(event)
    pending = await service.pendingWorkstreamCount()
    XCTAssertEqual(pending, 0)
    await service.flush()
    XCTAssertEqual(client.controlRequests, 0)
    XCTAssertEqual(client.evaluations.count, 0)
    XCTAssertEqual(client.snapshots.count, 0)

    flag.value = false
    await service.observe(event)
    pending = await service.pendingWorkstreamCount()
    XCTAssertEqual(pending, 1)
    flag.value = true
    // A mid-debounce flag flip must also fail closed inside flush.
    await service.flush()
    pending = await service.pendingWorkstreamCount()
    XCTAssertEqual(pending, 0)
    XCTAssertEqual(client.controlRequests, 0)
    XCTAssertEqual(client.evaluations.count, 0)
  }

  @MainActor
  func testOwnerSwitchDuringControlAbortsSnapshotEvaluationAndInterruption() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let ownerID = Box("owner-a")
    client.onControl = { ownerID.value = "owner-b" }
    client.recommendations = [recommendation(id: "task-owner-a")]
    var interruptions: [TaskInterruptionCandidate] = []
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { ownerID.value },
      sendInterruption: { interruptions.append($0) }
    )
    let event = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Owner A urgent document",
        subject: TaskContextSubject(kind: .task, id: "task-owner-a", workstreamID: nil),
        urgency: .timeSensitive
      ))

    await service.observe(event)
    await service.flush()

    XCTAssertEqual(client.controlRequests, 1)
    XCTAssertTrue(client.snapshots.isEmpty)
    XCTAssertTrue(client.evaluations.isEmpty)
    XCTAssertTrue(interruptions.isEmpty)
  }

  @MainActor
  func testOwnerSwitchDuringSnapshotAbortsEvaluationAndInterruption() async throws {
    let client = FakeTaskContextualResurfacingClient()
    let ownerID = Box("owner-a")
    client.onSnapshot = { ownerID.value = "owner-b" }
    client.recommendations = [recommendation(id: "task-owner-a")]
    var interruptions: [TaskInterruptionCandidate] = []
    let service = TaskContextualResurfacingService(
      client: client,
      debounceInterval: 60,
      ownerIDProvider: { ownerID.value },
      sendInterruption: { interruptions.append($0) }
    )
    let event = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Owner A urgent document",
        subject: TaskContextSubject(kind: .task, id: "task-owner-a", workstreamID: nil),
        urgency: .timeSensitive
      ))

    await service.observe(event)
    await service.flush()

    XCTAssertEqual(client.snapshots.count, 1)
    XCTAssertTrue(client.evaluations.isEmpty)
    XCTAssertTrue(interruptions.isEmpty)
  }

  func testSuspendedPromotionInsertCannotCommitOrPublishAcrossOwnerTransition() async {
    let previousOwner = RuntimeOwnerIdentity.currentOwnerId()
    await transitionContextTestOwner(to: "promotion-owner-a")
    let insert = SuspendedPromotionInsert()
    let promotedTask = TaskActionItem(
      id: "promoted-owner-a",
      description: "Owner A private promotion",
      completed: false,
      createdAt: baseDate
    )
    let service = TaskPromotionService(
      operations: .init(
        legacyPromotionEnabled: { _ in true },
        promote: { _ in
          PromoteResponse(promoted: true, reason: nil, promotedTask: promotedTask)
        },
        insertLocal: { _, authorization in
          try await insert.insert(authorization: authorization)
        }
      ))

    let promotion = Task {
      await service.promoteIfNeeded(bypassDebounce: true)
    }
    await insert.waitUntilStarted()
    await transitionContextTestOwner(to: "promotion-owner-b")
    await insert.release()
    let result = await promotion.value

    let committed = await insert.committed
    XCTAssertTrue(result.isEmpty)
    XCTAssertEqual(committed, 0)
    await service.stop()
    await transitionContextTestOwner(to: previousOwner)
  }

  func testDelayedOwnerNotificationCannotEraseAlreadyAdmittedOwnerBPromotionThrottle() async {
    await transitionContextTestOwner(to: "promotion-observer-owner-a")
    let promotedTask = TaskActionItem(
      id: "promoted-observer-owner-b",
      description: "Owner B promotion",
      completed: false,
      createdAt: baseDate
    )
    let recorder = PromotionCallRecorder()
    let service = TaskPromotionService(
      operations: .init(
        legacyPromotionEnabled: { _ in true },
        promote: { _ in
          await recorder.record()
          return PromoteResponse(promoted: true, reason: nil, promotedTask: promotedTask)
        },
        insertLocal: { _, authorization in try authorization.require() }
      ))

    await transitionContextTestOwner(to: "promotion-observer-owner-b")
    let first = await service.promoteIfNeeded(bypassDebounce: true)
    XCTAssertEqual(first.map(\.id), [promotedTask.id])

    // Models an A→B notification queued before B admission whose actor
    // callback is delivered after B has already established its throttle.
    await service.processOwnerChangeNotificationForTesting()
    let second = await service.promoteIfNeeded()
    let promoteCalls = await recorder.callCount()

    XCTAssertTrue(second.isEmpty)
    XCTAssertEqual(promoteCalls, 1)
    await service.stop()
  }

  func testOwnerAContextBatchIsDiscardedWhenControlResumesUnderOwnerB() async throws {
    try await assertContextTransitionFence(pausePoint: .control)
  }

  func testOwnerAContextBatchCannotEvaluateAfterSnapshotResumesUnderOwnerB() async throws {
    try await assertContextTransitionFence(pausePoint: .snapshot)
  }

  func testDelayedOwnerNotificationCannotEraseAlreadyAdmittedOwnerBContext() async throws {
    await transitionContextTestOwner(to: "delayed-observer-owner-a")
    let service = TaskContextualResurfacingService(
      client: FakeTaskContextualResurfacingClient(),
      debounceInterval: 60
    )
    await transitionContextTestOwner(to: "delayed-observer-owner-b")
    let event = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Owner B current document",
        occurredAt: baseDate
      ))
    await service.observe(event)

    // Models an A→B notification that was queued before B admission but whose
    // async observer callback runs afterward.
    await service.processOwnerChangeNotificationForTesting()

    let pending = await service.pendingWorkstreamCount()
    XCTAssertEqual(pending, 1)
  }

  @MainActor
  func testEligibilityDoesNotConsumeFrequencyUntilPresentation() async throws {
    await transitionContextTestOwner(to: "notification-presentation-owner")
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let service = NotificationService(registerWithSystemNotificationCenter: false)
    let priorFrequency = UserDefaults.standard.object(
      forKey: NotificationService.frequencyDefaultsKey)
    defer {
      Self.restoreDefault(priorFrequency, key: NotificationService.frequencyDefaultsKey)
    }
    UserDefaults.standard.set(3, forKey: NotificationService.frequencyDefaultsKey)

    XCTAssertTrue(
      service.proactiveNotificationEligibleForTesting(
        assistantId: "insight", authorizationSnapshot: snapshot, now: baseDate))
    XCTAssertTrue(
      service.proactiveNotificationEligibleForTesting(
        assistantId: "insight", authorizationSnapshot: snapshot,
        now: baseDate.addingTimeInterval(1)),
      "a preflight that never paints must not consume the user's frequency window")

    service.recordProactiveNotificationPresentedForTesting(
      assistantId: "context-director", authorizationSnapshot: snapshot, now: baseDate)
    XCTAssertFalse(
      service.proactiveNotificationEligibleForTesting(
        assistantId: "insight", authorizationSnapshot: snapshot,
        now: baseDate.addingTimeInterval(1)),
      "a visible director notification must advance the shared global frequency clock")
  }

  @MainActor
  func testProactiveEligibilityIgnoresTimeOfDay() async throws {
    await transitionContextTestOwner(to: "notification-always-on-owner")
    let snapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let service = NotificationService(registerWithSystemNotificationCenter: false)
    let priorFrequency = UserDefaults.standard.object(
      forKey: NotificationService.frequencyDefaultsKey)
    defer {
      Self.restoreDefault(priorFrequency, key: NotificationService.frequencyDefaultsKey)
    }
    // Level 3 exercises the real cooldown path; Maximum would return before any timestamp check.
    UserDefaults.standard.set(3, forKey: NotificationService.frequencyDefaultsKey)

    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = try XCTUnwrap(TimeZone(secondsFromGMT: 0))
    let earlyMorning = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 13, hour: 2)))
    let lateNight = try XCTUnwrap(
      calendar.date(from: DateComponents(year: 2026, month: 8, day: 13, hour: 23)))

    XCTAssertTrue(
      service.proactiveNotificationEligibleForTesting(
        assistantId: "insight", authorizationSnapshot: snapshot, now: earlyMorning))
    XCTAssertTrue(
      service.proactiveNotificationEligibleForTesting(
        assistantId: "insight", authorizationSnapshot: snapshot, now: lateNight))
  }

  @MainActor
  func testStaleContextualInterruptionCannotConsumeLedgerMetadataOrOwnerBThrottle() async throws {
    await transitionContextTestOwner(to: "notification-owner-a")
    let ownerASnapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let service = NotificationService(registerWithSystemNotificationCenter: false)
    let persistence = MemoryTaskInterruptionLedger()
    let sentinelDate = baseDate.addingTimeInterval(-60)
    persistence.ledger = TaskInterruptionLedger(sentAt: [sentinelDate])
    service.recordNotificationMetadataForTesting(
      id: "owner-a-notification",
      authorizationSnapshot: ownerASnapshot
    )

    let priorFrequency = UserDefaults.standard.object(
      forKey: NotificationService.frequencyDefaultsKey)
    UserDefaults.standard.set(3, forKey: NotificationService.frequencyDefaultsKey)
    XCTAssertTrue(
      service.allowProactiveNotificationForTesting(
        assistantId: "task",
        authorizationSnapshot: ownerASnapshot,
        now: baseDate
      ))

    await transitionContextTestOwner(to: "notification-owner-b")
    let ownerBSnapshot = try XCTUnwrap(RuntimeOwnerIdentity.captureAuthorizationSnapshot())
    let staleTrace = service.sendContextualTaskInterruption(
      candidate(),
      authorizationSnapshot: ownerASnapshot,
      now: baseDate,
      ledgerPersistence: persistence
    )

    XCTAssertEqual(staleTrace.reason, .staleOwner)
    XCTAssertEqual(persistence.ledger.sentAt, [sentinelDate])
    XCTAssertFalse(service.hasCurrentNotificationMetadataForTesting(id: "owner-a-notification"))
    XCTAssertTrue(
      service.allowProactiveNotificationForTesting(
        assistantId: "task",
        authorizationSnapshot: ownerBSnapshot,
        now: baseDate.addingTimeInterval(1)
      ))

    if let priorFrequency {
      UserDefaults.standard.set(priorFrequency, forKey: NotificationService.frequencyDefaultsKey)
    } else {
      UserDefaults.standard.removeObject(forKey: NotificationService.frequencyDefaultsKey)
    }
  }

  private func assertContextTransitionFence(
    pausePoint: SuspendedContextClient.PausePoint
  ) async throws {
    let previousOwner = RuntimeOwnerIdentity.currentOwnerId()
    await transitionContextTestOwner(to: "context-owner-a")
    let client = SuspendedContextClient(pausePoint: pausePoint)
    let service = TaskContextualResurfacingService(client: client, debounceInterval: 60)
    let event = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: "Owner A confidential document",
        subject: TaskContextSubject(kind: .task, id: "owner-a-task", workstreamID: "owner-a-workstream"),
        occurredAt: baseDate
      ))
    await service.observe(event)
    let flush = Task { await service.flush() }
    await client.waitUntilStarted()
    await transitionContextTestOwner(to: "context-owner-b")
    await client.release()
    await flush.value

    let counts = await client.counts()
    switch pausePoint {
    case .control:
      XCTAssertEqual(counts.snapshots, 0)
    case .snapshot:
      XCTAssertEqual(counts.snapshots, 1)
    }
    XCTAssertEqual(counts.evaluations, 0)
    let pendingCount = await service.pendingWorkstreamCount()
    XCTAssertEqual(pendingCount, 0)
    await transitionContextTestOwner(to: previousOwner)
  }

  @MainActor
  func testLocalMatcherLearnsRecentContextWithoutPersistingRawText() throws {
    let suite = "task-context-matcher-\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    defer { defaults.removePersistentDomain(forName: suite) }
    let matcher = TaskContextSubjectMatcher(defaults: defaults, ownerID: "owner-1")
    let raw = "Sarah — confidential Slack thread"
    let unrelatedRaw = "Unrelated document tab"
    let unrelated = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: unrelatedRaw,
        occurredAt: baseDate.addingTimeInterval(-1)
      ))
    XCTAssertNil(matcher.resolve(unrelated, now: baseDate).subject)
    let first = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .appWindow,
        rawReference: raw,
        occurredAt: baseDate
      ))
    XCTAssertNil(matcher.resolve(first, now: baseDate).subject)

    let subject = TaskContextSubject(kind: .workstream, id: "workstream-1", workstreamID: "workstream-1")
    matcher.bindRecentContext(to: subject, now: baseDate.addingTimeInterval(1))
    matcher.bindRecentContext(
      to: TaskContextSubject(kind: .workstream, id: "workstream-2", workstreamID: "workstream-2"),
      now: baseDate.addingTimeInterval(1)
    )
    let reopened = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .appWindow,
        rawReference: raw,
        occurredAt: baseDate.addingTimeInterval(2)
      ))
    XCTAssertEqual(matcher.resolve(reopened, now: baseDate.addingTimeInterval(2)).subject, subject)
    let unrelatedReopened = try XCTUnwrap(
      TaskLocalContextEvent.normalized(
        kind: .document,
        rawReference: unrelatedRaw,
        occurredAt: baseDate.addingTimeInterval(2)
      ))
    XCTAssertNil(matcher.resolve(unrelatedReopened, now: baseDate.addingTimeInterval(2)).subject)
    XCTAssertEqual(matcher.resolve(reopened, now: baseDate.addingTimeInterval(4)).subject, subject)

    let persisted = defaults.dictionaryRepresentation().values.compactMap { $0 as? Data }
      .compactMap { String(data: $0, encoding: .utf8) }.joined()
    XCTAssertFalse(persisted.localizedCaseInsensitiveContains("sarah"))
    XCTAssertTrue(persisted.contains("workstream-1"))
  }

  @MainActor
  func testContextualNavigationRouteSurvivesUntilDashboardConsumesIt() {
    let router = ContextualTaskNavigationRouter()
    router.request(recommendationID: "output-1:dedupe-1")
    XCTAssertEqual(router.pendingRecommendationID, "output-1:dedupe-1")
    XCTAssertNil(router.consume(requestedID: "different"))
    XCTAssertEqual(router.consume(), "output-1:dedupe-1")
    XCTAssertNil(router.consume())
  }

  func testRecommendationEligibilityIsIndependentFromInterruptionSettings() {
    let denial = TaskRecommendationEligibility.denial(
      for: TaskRecommendationEligibilityInput(
        isOpen: true,
        expiresAt: baseDate.addingTimeInterval(60),
        hasEvidence: true,
        hasConcreteAction: true,
        dedupeAlreadyActive: false
      ),
      now: baseDate
    )
    XCTAssertNil(denial)

    let trace = gate().evaluate(
      candidate: candidate(),
      configuration: configuration(enabled: false),
      environment: environment()
    )
    XCTAssertEqual(trace.reason, .notEnrolled)
  }

  func testRecommendationEligibilityRejectsWeakOrDuplicateItems() {
    XCTAssertEqual(eligibility(hasEvidence: false), .insufficientEvidence)
    XCTAssertEqual(eligibility(hasConcreteAction: false), .missingConcreteAction)
    XCTAssertEqual(eligibility(dedupeAlreadyActive: true), .duplicate)
    XCTAssertEqual(eligibility(expiresAt: baseDate), .expired)
  }

  func testInterruptionGateHonorsSettingsFocusSnoozeExpiryAndCanWait() {
    let cases: [(TaskInterruptionEnvironment, TaskInterruptionCandidate, TaskInterruptionGateReason)] = [
      (environment(master: false), candidate(), .masterDisabled),
      (environment(frequency: false), candidate(), .frequencyDisabled),
      (environment(ambientFrequency: false), candidate(), .frequencyBudget),
      (environment(task: false), candidate(), .taskDisabled),
      (environment(focus: true), candidate(), .focusSuppressed),
      (environment(), candidate(expiresAt: baseDate), .expired),
      (environment(), candidate(canWait: true), .canWait),
    ]
    for (environment, candidate, expected) in cases {
      XCTAssertEqual(
        gate().evaluate(
          candidate: candidate,
          configuration: configuration(),
          environment: environment
        ).reason,
        expected
      )
    }
  }

  func testInterruptionGateEnforcesDedupeSpacingAndDailyBudget() {
    let persistence = MemoryTaskInterruptionLedger()
    let gate = ProactiveTaskInterruptionGate(persistence: persistence)
    let config = configuration(dailyLimit: 2, spacing: 90 * 60)

    XCTAssertEqual(
      gate.evaluate(
        candidate: candidate(id: "one", dedupe: "one"),
        configuration: config,
        environment: environment()
      ).reason, .allowed)
    XCTAssertEqual(
      gate.evaluate(
        candidate: candidate(id: "repeat", dedupe: "one"),
        configuration: config,
        environment: environment(now: baseDate.addingTimeInterval(90 * 60))
      ).reason, .duplicate)
    XCTAssertEqual(
      gate.evaluate(
        candidate: candidate(id: "two", dedupe: "two"),
        configuration: config,
        environment: environment(now: baseDate.addingTimeInterval(60))
      ).reason, .minimumSpacing)
    XCTAssertEqual(
      gate.evaluate(
        candidate: candidate(id: "two", dedupe: "two"),
        configuration: config,
        environment: environment(now: baseDate.addingTimeInterval(90 * 60))
      ).reason, .allowed)
    XCTAssertEqual(
      gate.evaluate(
        candidate: candidate(id: "three", dedupe: "three"),
        configuration: config,
        environment: environment(now: baseDate.addingTimeInterval(3 * 60 * 60))
      ).reason, .dailyBudget)
  }

  func testDailyBudgetResetsAtLocalDayBoundaryButSpacingDoesNot() {
    var calendar = Calendar(identifier: .gregorian)
    calendar.timeZone = TimeZone(secondsFromGMT: 0)!
    let beforeMidnight = ISO8601DateFormatter().date(from: "2027-01-15T23:59:00Z")!
    let afterMidnight = ISO8601DateFormatter().date(from: "2027-01-16T00:01:00Z")!
    let persistence = MemoryTaskInterruptionLedger()
    let gate = ProactiveTaskInterruptionGate(persistence: persistence)
    let config = configuration(dailyLimit: 1, spacing: 90 * 60)

    XCTAssertEqual(
      gate.evaluate(
        candidate: candidate(id: "before", dedupe: "before", expiresAt: beforeMidnight.addingTimeInterval(300)),
        configuration: config,
        environment: environment(now: beforeMidnight, calendar: calendar)
      ).reason, .allowed)
    XCTAssertEqual(
      gate.evaluate(
        candidate: candidate(id: "after", dedupe: "after", expiresAt: afterMidnight.addingTimeInterval(300)),
        configuration: config,
        environment: environment(now: afterMidnight, calendar: calendar)
      ).reason, .minimumSpacing)
  }

  func testDogfoodAndShippedEnrollmentRemainIndependent() {
    let dogfood = configuration(enabled: true, shipped: false)
    XCTAssertTrue(dogfood.isEnrolled(cohort: .dogfood))
    XCTAssertFalse(dogfood.isEnrolled(cohort: .beta))
    XCTAssertFalse(dogfood.isEnrolled(cohort: .production))

    let shipped = configuration(enabled: true, shipped: true)
    XCTAssertTrue(shipped.isEnrolled(cohort: .dogfood))
    XCTAssertTrue(shipped.isEnrolled(cohort: .beta))
    XCTAssertTrue(shipped.isEnrolled(cohort: .production))
    XCTAssertFalse(configuration(enabled: false, shipped: true).isEnrolled(cohort: .production))
  }

  @MainActor
  func testArtifactPreparationRequiresPolicyGrantAndDelegatesVersioningToKernel() async throws {
    let root = FileManager.default.temporaryDirectory
      .appendingPathComponent("task-preparation-\(UUID().uuidString)", isDirectory: true)
    defer { try? FileManager.default.removeItem(at: root) }
    var persistedVersions = 0
    let bridge = KernelPreparedArtifactBridge(root: root) {
      workstreamID, logicalKey, kind, fileURL, contentHash, evidenceRefs, grantID, _ in
      persistedVersions += 1
      let artifactID = "kernel-artifact-\(persistedVersions)"
      XCTAssertEqual(grantID, "grant-1")
      return TaskKernelPreparedArtifactReceipt(
        artifactVersion: TaskKernelArtifactVersion(
          sourceArtifactId: "source-\(persistedVersions)",
          logicalKey: logicalKey,
          version: persistedVersions,
          supersedesArtifactId: persistedVersions == 1 ? nil : "kernel-artifact-\(persistedVersions - 1)",
          evidenceRefs: evidenceRefs,
          artifact: TaskKernelArtifactVersion.Artifact(
            artifactId: artifactID,
            kind: kind,
            uri: fileURL.absoluteString,
            contentHash: contentHash
          )
        ),
        deliveries: []
      )
    }
    let evidence = OmiAPI.EvidenceRef(
      deviceId: "device-1",
      excerptHash: "sha256:\(String(repeating: "a", count: 64))",
      id: "local-evidence-1",
      kind: .local_screen,
      scope: .device_local,
      version: "test.v1"
    )
    let firstProposal = ProactiveTaskArtifactProposal(
      workstreamID: "workstream-1",
      logicalKey: "investor-email-sarah",
      kind: "email_draft",
      content: Data("Version one".utf8),
      evidenceRefs: [evidence],
      executionReady: true,
      coordinatorGrantID: "grant-1"
    )
    let denied = try await bridge.prepare(firstProposal, configuration: .safeDefault)
    XCTAssertNil(denied)
    XCTAssertEqual(persistedVersions, 0)

    var allowed = configuration()
    allowed.allowedPreparationKinds = ["email_draft"]
    let missingGrant = ProactiveTaskArtifactProposal(
      workstreamID: "workstream-1",
      logicalKey: "investor-email-sarah",
      kind: "email_draft",
      content: Data("Version one".utf8),
      evidenceRefs: [evidence],
      executionReady: true,
      coordinatorGrantID: nil
    )
    XCTAssertEqual(
      ProactiveTaskPreparationPolicy.denial(proposal: missingGrant, configuration: allowed),
      .missingCoordinatorGrant
    )
    let firstResult = try await bridge.prepare(firstProposal, configuration: allowed)
    let first = try XCTUnwrap(firstResult)
    let secondResult = try await bridge.prepare(
      ProactiveTaskArtifactProposal(
        workstreamID: "workstream-1",
        logicalKey: "investor-email-sarah",
        kind: "email_draft",
        content: Data("Version two after new evidence".utf8),
        evidenceRefs: [evidence],
        executionReady: true,
        coordinatorGrantID: "grant-1"
      ),
      configuration: allowed
    )
    let second = try XCTUnwrap(secondResult)

    XCTAssertEqual(first.version, 1)
    XCTAssertEqual(second.version, 2)
    XCTAssertEqual(second.supersedesArtifactID, "kernel-artifact-1")
    XCTAssertEqual(try String(contentsOf: first.fileURL), "Version one")
    XCTAssertEqual(try String(contentsOf: second.fileURL), "Version two after new evidence")
    XCTAssertNotEqual(first.contentHash, second.contentHash)
    XCTAssertFalse(first.fileURL.lastPathComponent.contains("v1"))
    XCTAssertEqual(persistedVersions, 2)
  }

  @MainActor
  func testPreparedArtifactContinuityUsesKernelSessionVersionAndDeliveryRPC() async throws {
    let fileURL = FileManager.default.temporaryDirectory
      .appendingPathComponent("prepared-kernel-\(UUID().uuidString).artifact")
    try Data("draft".utf8).write(to: fileURL)
    defer { try? FileManager.default.removeItem(at: fileURL) }
    let evidence = OmiAPI.EvidenceRef(
      deviceId: "device-1",
      excerptHash: "sha256:\(String(repeating: "b", count: 64))",
      id: "local-evidence-1",
      kind: .local_screen,
      scope: .device_local,
      version: "test.v1"
    )
    var capturedName = ""
    var capturedInput: [String: Any] = [:]
    let receipt = try await TaskWorkstreamContinuity.persistPreparedArtifact(
      workstreamId: "workstream-1",
      logicalKey: "investor-email",
      kind: "email_draft",
      fileURL: fileURL,
      contentHash: "sha256:\(String(repeating: "c", count: 64))",
      evidenceRefs: [evidence],
      grantId: "grant-1",
      authorizationSnapshot: try XCTUnwrap(
        RuntimeOwnerIdentity.captureAuthorizationSnapshot()
      )
    ) { name, input in
      capturedName = name
      capturedInput = input
      let response: [String: Any] = [
        "ok": true,
        "artifactVersion": [
          "sourceArtifactId": "source-1",
          "logicalKey": "investor-email",
          "version": 2,
          "supersedesArtifactId": "artifact-1",
          "evidenceRefs": [
            [
              "device_id": "device-1",
              "excerpt_hash": "sha256:\(String(repeating: "b", count: 64))",
              "id": "local-evidence-1",
              "kind": "local_screen",
              "scope": "device_local",
              "version": "test.v1",
            ]
          ],
          "artifact": [
            "artifactId": "artifact-2",
            "kind": "email_draft",
            "uri": fileURL.absoluteString,
            "contentHash": "sha256:\(String(repeating: "c", count: 64))",
          ],
        ],
        "deliveries": [],
      ]
      let data = try JSONSerialization.data(withJSONObject: response)
      return try XCTUnwrap(String(data: data, encoding: .utf8))
    }

    XCTAssertEqual(capturedName, "persist_prepared_workstream_artifact")
    XCTAssertEqual(capturedInput["workstreamId"] as? String, "workstream-1")
    XCTAssertEqual(capturedInput["logicalKey"] as? String, "investor-email")
    XCTAssertEqual(capturedInput["grantId"] as? String, "grant-1")
    XCTAssertNil(capturedInput["context"])
    XCTAssertEqual(receipt.artifactVersion.version, 2)
  }

  func testGateTraceAndNormalizedEventContainNoRawPrivateContent() throws {
    let raw = "Sarah private launch document"
    let event = try XCTUnwrap(TaskLocalContextEvent.normalized(kind: .document, rawReference: raw))
    XCTAssertFalse(event.referenceHash.localizedCaseInsensitiveContains("sarah"))
    XCTAssertFalse(Mirror(reflecting: event).children.compactMap(\.label).contains("rawReference"))

    let trace = gate().evaluate(
      candidate: candidate(headline: raw, dedupe: "secret-dedupe-value"),
      configuration: configuration(),
      environment: environment()
    )
    let encoded = String(data: try JSONEncoder().encode(trace), encoding: .utf8)!
    XCTAssertFalse(encoded.contains(raw))
    XCTAssertFalse(encoded.contains("secret-dedupe-value"))
    XCTAssertTrue(encoded.contains("sha256:"))
  }

  func testLegacyPromotionCannotNotifyOrBypassTheCanonicalGate() throws {
    let testsDirectory = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    let source = try String(
      contentsOf: testsDirectory.deletingLastPathComponent()
        .appendingPathComponent("Sources/ProactiveAssistants/Assistants/TaskExtraction/TaskPromotionService.swift"))
    XCTAssertFalse(source.contains("New task"))
    XCTAssertFalse(source.contains("sendNotification"))
    XCTAssertFalse(source.contains("respectFrequency: false"))
  }

  private func eligibility(
    hasEvidence: Bool = true,
    hasConcreteAction: Bool = true,
    dedupeAlreadyActive: Bool = false,
    expiresAt: Date? = nil
  ) -> TaskRecommendationEligibilityDenial? {
    TaskRecommendationEligibility.denial(
      for: TaskRecommendationEligibilityInput(
        isOpen: true,
        expiresAt: expiresAt ?? baseDate.addingTimeInterval(60),
        hasEvidence: hasEvidence,
        hasConcreteAction: hasConcreteAction,
        dedupeAlreadyActive: dedupeAlreadyActive
      ),
      now: baseDate
    )
  }

  private func gate() -> ProactiveTaskInterruptionGate {
    ProactiveTaskInterruptionGate(persistence: MemoryTaskInterruptionLedger())
  }

  private func candidate(
    id: String = "recommendation-1",
    headline: String = "Review the updated draft",
    dedupe: String = "dedupe-1",
    expiresAt: Date? = nil,
    canWait: Bool = false
  ) -> TaskInterruptionCandidate {
    TaskInterruptionCandidate(
      recommendationID: id,
      interventionID: "intervention-1",
      dedupeKey: dedupe,
      headline: headline,
      whyNow: "The linked conversation changed the assumptions.",
      recommendedAction: "Review update",
      expiresAt: expiresAt ?? baseDate.addingTimeInterval(24 * 60 * 60),
      canWait: canWait
    )
  }

  private func recommendation(id: String) -> OmiAPI.Recommendation {
    OmiAPI.Recommendation(
      alternativeAction: nil,
      dedupeKey: "dedupe-\(id)",
      destinationTaskId: id,
      destinationWorkstreamId: nil,
      evidencePreview: "Linked evidence",
      evidenceRefs: [],
      expiresAt: "2030-01-01T00:00:00Z",
      feedbackSubjectId: id,
      feedbackSubjectKind: .task,
      goalOrWorkstreamLabel: nil,
      headline: "Handle the urgent task",
      interventionId: "intervention-\(id)",
      outputVersion: "output-1",
      recommendedAction: "Open",
      subjectId: id,
      subjectKind: .task,
      whyNow: "The matched context is active."
    )
  }

  private func configuration(
    enabled: Bool = true,
    shipped: Bool = false,
    dailyLimit: Int = 2,
    spacing: TimeInterval = 90 * 60
  ) -> ProactiveTaskInterruptionConfiguration {
    ProactiveTaskInterruptionConfiguration(
      userOptedIn: enabled,
      shippedCohortsEnabled: shipped,
      dailyLimit: dailyLimit,
      minimumSpacing: spacing,
      allowedPreparationKinds: []
    )
  }

  private func environment(
    cohort: ProactiveTaskCohort = .dogfood,
    master: Bool = true,
    frequency: Bool = true,
    ambientFrequency: Bool = true,
    task: Bool = true,
    focus: Bool = false,
    now: Date? = nil,
    calendar: Calendar = Calendar(identifier: .gregorian)
  ) -> TaskInterruptionEnvironment {
    TaskInterruptionEnvironment(
      cohort: cohort,
      masterNotificationsEnabled: master,
      frequencyEnabled: frequency,
      ambientFrequencyEligible: ambientFrequency,
      taskNotificationsEnabled: task,
      focusSuppressed: focus,
      now: now ?? baseDate,
      calendar: calendar
    )
  }

  private static func restoreDefault(_ value: Any?, key: String) {
    if let value {
      UserDefaults.standard.set(value, forKey: key)
    } else {
      UserDefaults.standard.removeObject(forKey: key)
    }
  }
}
