import XCTest
@testable import Omi_Computer

@MainActor
final class SuggestedTasksStoreTests: XCTestCase {
  func testActionPolicyNeverOffersMoreThanThreeChoices() {
    for state in [
      SuggestedCardState.ready, .editing, .dismissReasons, .busy,
    ] {
      XCTAssertLessThanOrEqual(SuggestedActionPolicy.actions(for: state).count, 3)
    }
    XCTAssertEqual(SuggestedActionPolicy.actions(for: .ready), [.doNow, .later, .dismiss])
    XCTAssertEqual(
      SuggestedActionPolicy.actions(for: .dismissReasons),
      [.alreadyHandled, .notMine, .notUseful]
    )
  }

  func testLoadProjectsOnlyPendingCandidatesWithoutManagedNounLeak() async {
    let api = FakeSuggestedTasksClient()
    api.records = [
      candidate(id: "pending", status: .pending),
      candidate(id: "accepted", status: .accepted),
      candidate(id: "rejected", status: .rejected),
      candidate(id: "expired", status: .expired),
      taskMutationCandidate(id: "blind-complete"),
      workProposal(id: "proposal"),
    ]
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())

    await store.load()

    XCTAssertEqual(store.candidates.map(\.id), ["proposal", "pending"])
    XCTAssertEqual(store.candidates.first(where: { $0.id == "proposal" })?.title, "Prepare launch brief")
    XCTAssertFalse(store.candidates.contains { $0.title.localizedCaseInsensitiveContains("workstream") })
    XCTAssertTrue(api.registeredInterventionCandidateIDs.isEmpty)

    await store.presented(candidateID: "pending")
    await store.presented(candidateID: "proposal")

    XCTAssertEqual(api.registeredInterventionCandidateIDs, Set(["pending", "proposal"]))
  }

  func testExactRecommendedCandidateCanBeInsertedOutsideThePagedList() async {
    let api = FakeSuggestedTasksClient()
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())
    await store.load()

    let revealed = store.revealCandidateForNavigation(candidate(id: "candidate-101", status: .pending))

    XCTAssertTrue(revealed)
    XCTAssertEqual(store.candidates.map(\.id), ["candidate-101"])
  }

  func testTaskMutationCandidateFailsClosedWithoutAConcreteDiff() async {
    let api = FakeSuggestedTasksClient()
    api.records = [taskMutationCandidate(id: "blind-complete")]
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())

    await store.load()

    XCTAssertTrue(store.candidates.isEmpty)
  }

  func testCandidateInterventionUsesCanonicalBoundedRecommendationDedupeKey() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())
    await store.load()

    await store.presented(candidateID: "candidate-1")

    XCTAssertEqual(api.registeredInterventionDedupeKeys, ["candidate_fed53ee6b0ddd474f9f2d93dfdb7c003"])
    XCTAssertLessThanOrEqual(api.registeredInterventionDedupeKeys[0].count, 128)
  }

  func testWriteSidecarModeNeverExposesSuggestedCandidates() async {
    let api = FakeSuggestedTasksClient()
    api.workflowMode = .write
    api.records = [candidate(id: "sidecar-only", status: .pending)]
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())

    await store.load()

    XCTAssertTrue(store.candidates.isEmpty)
    XCTAssertTrue(api.registeredInterventionCandidateIDs.isEmpty)
  }

  func testDoNowReconcilesCanonicalReceiptAndRecordsAttribution() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    api.acceptedTaskID = "task-1"
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())
    await store.load()

    let taskID = await store.doNow(candidateID: "candidate-1", editedTitle: nil)

    XCTAssertEqual(taskID, "task-1")
    XCTAssertTrue(store.candidates.isEmpty)
    XCTAssertEqual(api.acceptedCandidateIDs, ["candidate-1"])
    XCTAssertEqual(api.feedback.map(\.action), [.accept_candidate])
  }

  func testEditedDoNowUpdatesCreatedTaskAndRecordsEdit() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    api.acceptedTaskID = "task-1"
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())
    await store.load()

    _ = await store.doNow(candidateID: "candidate-1", editedTitle: "Send the revised budget")

    XCTAssertEqual(api.updatedTaskDescriptions["task-1"], "Send the revised budget")
    XCTAssertEqual(api.feedback.map(\.action), [.edit])
  }

  func testOptimisticResolutionRollsBackOnFailure() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    api.failAccept = true
    let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())
    await store.load()

    _ = await store.doNow(candidateID: "candidate-1", editedTitle: nil)

    XCTAssertEqual(store.candidates.map(\.id), ["candidate-1"])
    XCTAssertNotNil(store.error)
  }

  func testAcceptedCandidateStaysResolvedWhileFeedbackRetriesFromOutbox() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    api.acceptedTaskID = "task-1"
    api.failFeedback = true
    let outbox = MemoryFeedbackOutboxStore()
    let store = SuggestedTasksStore(
      client: api,
      suppressionStore: MemorySuppressionStore(),
      feedbackOutboxStore: outbox
    )
    await store.load()

    let taskID = await store.doNow(candidateID: "candidate-1", editedTitle: nil)

    XCTAssertEqual(taskID, "task-1")
    XCTAssertTrue(store.candidates.isEmpty)
    XCTAssertEqual(outbox.entries.map(\.idempotencyKey), ["suggested:candidate-1:accept_candidate"])

    api.failFeedback = false
    await store.load()

    XCTAssertTrue(outbox.entries.isEmpty)
    XCTAssertEqual(api.feedbackAttempts, 2)
    XCTAssertEqual(api.feedback.map(\.action), [.accept_candidate])
  }

  func testOutboxDropsFeedbackFromAnOlderAccountGeneration() async {
    let api = FakeSuggestedTasksClient()
    let outbox = MemoryFeedbackOutboxStore()
    outbox.entries = [
      PendingSuggestedFeedback(
        request: OmiAPI.FeedbackCreate(
          action: .later,
          contextSnapshotHash: nil,
          interventionId: nil,
          laterUntil: nil,
          reason: nil,
          subjectId: "candidate-from-deleted-account",
          subjectKind: .candidate
        ),
        idempotencyKey: "old-feedback",
        accountGeneration: 6,
        interventionRequest: nil,
        interventionIdempotencyKey: nil
      )
    ]
    let store = SuggestedTasksStore(
      client: api,
      suppressionStore: MemorySuppressionStore(),
      feedbackOutboxStore: outbox
    )

    await store.load()

    XCTAssertTrue(outbox.entries.isEmpty)
    XCTAssertEqual(api.feedbackAttempts, 0)
  }

  func testAttributionRegistrationFailureDoesNotBlockCanonicalAcceptance() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    api.failIntervention = true
    let outbox = MemoryFeedbackOutboxStore()
    let store = SuggestedTasksStore(
      client: api,
      suppressionStore: MemorySuppressionStore(),
      feedbackOutboxStore: outbox
    )
    await store.load()

    let taskID = await store.doNow(candidateID: "candidate-1", editedTitle: nil)

    XCTAssertEqual(taskID, "task-created")
    XCTAssertTrue(store.candidates.isEmpty)
    XCTAssertEqual(api.acceptedCandidateIDs, ["candidate-1"])
    XCTAssertEqual(outbox.entries.count, 1)
    XCTAssertNotNil(outbox.entries.first?.interventionRequest)

    api.failIntervention = false
    await store.load()

    XCTAssertTrue(outbox.entries.isEmpty)
    XCTAssertNotNil(api.feedback.last?.interventionId)
  }

  func testLaterPersistsExactLocalSuppressionWithoutRejectingCandidate() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    let persistence = MemorySuppressionStore()
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let first = SuggestedTasksStore(client: api, suppressionStore: persistence, now: { now })
    await first.load()

    await first.later(candidateID: "candidate-1")

    XCTAssertTrue(first.candidates.isEmpty)
    XCTAssertTrue(api.rejectedCandidateIDs.isEmpty)
    XCTAssertEqual(api.feedback.map(\.action), [.later])

    let reloaded = SuggestedTasksStore(client: api, suppressionStore: persistence, now: { now })
    await reloaded.load()
    XCTAssertTrue(reloaded.candidates.isEmpty)
  }

  func testLaterStaysSuppressedWhileFeedbackRetriesFromOutbox() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    api.failFeedback = true
    let suppression = MemorySuppressionStore()
    let outbox = MemoryFeedbackOutboxStore()
    let store = SuggestedTasksStore(
      client: api,
      suppressionStore: suppression,
      feedbackOutboxStore: outbox
    )
    await store.load()

    await store.later(candidateID: "candidate-1")

    XCTAssertTrue(store.candidates.isEmpty)
    XCTAssertNotNil(suppression.values["candidate-1"])
    XCTAssertEqual(outbox.entries.map(\.request.action), [.later])
  }

  func testLaterUsesANewIdempotencyKeyAfterSuppressionExpires() async {
    let api = FakeSuggestedTasksClient()
    api.records = [candidate(id: "candidate-1", status: .pending)]
    let suppression = MemorySuppressionStore()
    var currentTime = Date(timeIntervalSince1970: 1_800_000_000)
    let store = SuggestedTasksStore(
      client: api,
      suppressionStore: suppression,
      now: { currentTime }
    )
    await store.load()
    await store.later(candidateID: "candidate-1")

    currentTime = currentTime.addingTimeInterval(25 * 60 * 60)
    await store.load()
    await store.later(candidateID: "candidate-1")

    let laterKeys = zip(api.feedback, api.feedbackIdempotencyKeys)
      .filter { $0.0.action == .later }
      .map(\.1)
    XCTAssertEqual(laterKeys.count, 2)
    XCTAssertNotEqual(laterKeys[0], laterKeys[1])
  }

  func testNotMineAndAlreadyHandledPersistReasonAndResolveCandidate() async {
    for reason in [
      OmiAPI.TaskIntelligenceFeedbackReason.not_mine,
      .already_handled,
    ] {
      let api = FakeSuggestedTasksClient()
      api.records = [candidate(id: reason.rawValue, status: .pending)]
      let store = SuggestedTasksStore(client: api, suppressionStore: MemorySuppressionStore())
      await store.load()

      await store.dismiss(candidateID: reason.rawValue, reason: reason)

      XCTAssertTrue(store.candidates.isEmpty)
      XCTAssertEqual(api.feedback.last?.reason, reason)
      XCTAssertEqual(api.rejectedCandidateIDs, [reason.rawValue])
    }
  }

  func testOwnerSwitchReloadsSuppressionsAndOutboxWithoutCrossAccountRetry() async {
    let api = FakeSuggestedTasksClient()
    let suppression = MemorySuppressionStore()
    let outbox = MemoryFeedbackOutboxStore()
    suppression.ownerID = "owner-a"
    outbox.ownerID = "owner-a"
    suppression.values = ["candidate-b": Date.distantFuture]
    outbox.entries = [
      PendingSuggestedFeedback(
        request: OmiAPI.FeedbackCreate(
          action: .later,
          contextSnapshotHash: nil,
          interventionId: "intervention-a",
          laterUntil: nil,
          reason: nil,
          subjectId: "candidate-a",
          subjectKind: .candidate
        ),
        idempotencyKey: "owner-a-feedback",
        accountGeneration: 7,
        interventionRequest: nil,
        interventionIdempotencyKey: nil
      )
    ]
    let store = SuggestedTasksStore(
      client: api,
      suppressionStore: suppression,
      feedbackOutboxStore: outbox
    )

    suppression.ownerID = "owner-b"
    outbox.ownerID = "owner-b"
    api.records = [candidate(id: "candidate-b", status: .pending)]
    await store.load()

    XCTAssertEqual(store.candidates.map(\.id), ["candidate-b"])
    XCTAssertEqual(api.feedbackAttempts, 0)
    XCTAssertTrue(outbox.entries.isEmpty)

    suppression.ownerID = "owner-a"
    outbox.ownerID = "owner-a"
    api.records = []
    await store.load()

    XCTAssertEqual(api.feedbackAttempts, 1)
    XCTAssertTrue(outbox.entries.isEmpty)
  }

  func testOwnerSwitchDuringAcceptDoesNotNavigateOrRestorePriorOwnerCandidate() async {
    for failAccept in [false, true] {
      let api = FakeSuggestedTasksClient()
      let suppression = MemorySuppressionStore()
      let outbox = MemoryFeedbackOutboxStore()
      suppression.ownerID = "owner-a"
      outbox.ownerID = "owner-a"
      api.records = [candidate(id: "candidate-a", status: .pending)]
      api.failAccept = failAccept
      api.onAccept = {
        suppression.ownerID = "owner-b"
        outbox.ownerID = "owner-b"
      }
      let store = SuggestedTasksStore(
        client: api,
        suppressionStore: suppression,
        feedbackOutboxStore: outbox
      )
      await store.load()

      let taskID = await store.doNow(candidateID: "candidate-a", editedTitle: nil)

      XCTAssertNil(taskID)
      XCTAssertTrue(store.candidates.isEmpty)
      XCTAssertNil(store.error)
    }
  }

  func testSuggestedImplementationDoesNotCreateNotificationsOrBadges() throws {
    let root = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
    let source = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Tasks/SuggestedTasksStore.swift"),
      encoding: .utf8
    )
    XCTAssertFalse(source.contains("NotificationService"))
    XCTAssertFalse(source.contains("badge"))
    XCTAssertFalse(source.contains("respectFrequency"))
  }

  private func candidate(id: String, status: OmiAPI.CandidateStatus) -> OmiAPI.CandidateRecord {
    OmiAPI.CandidateRecord(
      accountGeneration: 7,
      candidateId: id,
      captureConfidence: 0.9,
      createdAt: "2026-07-09T12:00:00Z",
      evidenceRefs: [],
      goalId: nil,
      idempotencyKey: "capture-\(id)",
      ownershipConfidence: 0.9,
      proposedAction: .create,
      resolutionReason: nil,
      resolvedAt: nil,
      resultTaskId: nil,
      resultWorkstreamId: nil,
      sourceSurface: "conversation",
      status: status,
      subjectKind: .task,
      taskChange: .create(
        OmiAPI.TaskCreatePayload(
          description_: "Send budget",
          dueAt: nil,
          dueConfidence: nil,
          owner: .user,
          priority: .medium,
          recurrenceParentId: nil,
          recurrenceRule: nil
        )),
      taskId: nil,
      workstreamId: nil,
      workstreamProposal: nil
    )
  }

  private func workProposal(id: String) -> OmiAPI.CandidateRecord {
    let anchor = OmiAPI.TaskCreatePayload(
      description_: "Draft the launch brief",
      dueAt: nil,
      dueConfidence: nil,
      owner: .user,
      priority: .medium,
      recurrenceParentId: nil,
      recurrenceRule: nil
    )
    return OmiAPI.CandidateRecord(
      accountGeneration: 7,
      candidateId: id,
      captureConfidence: 0.9,
      createdAt: "2026-07-10T12:00:00Z",
      evidenceRefs: [],
      goalId: nil,
      idempotencyKey: "capture-\(id)",
      ownershipConfidence: 0.9,
      proposedAction: .create,
      resolutionReason: nil,
      resolvedAt: nil,
      resultTaskId: nil,
      resultWorkstreamId: nil,
      sourceSurface: "integration",
      status: .pending,
      subjectKind: .workstream,
      taskChange: nil,
      taskId: nil,
      workstreamId: nil,
      workstreamProposal: OmiAPI.WorkstreamProposalOutput(
        anchorTask: anchor,
        objective: "Keep launch work moving",
        title: "Prepare launch brief"
      )
    )
  }

  private func taskMutationCandidate(id: String) -> OmiAPI.CandidateRecord {
    OmiAPI.CandidateRecord(
      accountGeneration: 7,
      candidateId: id,
      captureConfidence: 0.9,
      createdAt: "2026-07-09T12:00:00Z",
      evidenceRefs: [],
      goalId: nil,
      idempotencyKey: "capture-\(id)",
      ownershipConfidence: 0.9,
      proposedAction: .complete,
      resolutionReason: nil,
      resolvedAt: nil,
      resultTaskId: nil,
      resultWorkstreamId: nil,
      sourceSurface: "conversation",
      status: .pending,
      subjectKind: .task,
      taskChange: .change(
        OmiAPI.TaskChangePayload(
          description_: nil,
          dueAt: nil,
          dueConfidence: nil,
          owner: nil,
          priority: nil,
          recurrenceParentId: nil,
          recurrenceRule: nil,
          status: .completed,
          supersededBy: nil
        )),
      taskId: "task-1",
      workstreamId: nil,
      workstreamProposal: nil
    )
  }
}

private final class MemorySuppressionStore: SuggestedSuppressionPersisting {
  var ownerID = "test-owner"
  private var valuesByOwner: [String: [String: Date]] = [:]
  var values: [String: Date] {
    get { valuesByOwner[ownerID] ?? [:] }
    set { valuesByOwner[ownerID] = newValue }
  }
  func currentOwnerID() -> String { ownerID }
  func load(ownerID: String) -> [String: Date] { valuesByOwner[ownerID] ?? [:] }
  func save(_ suppressions: [String: Date], ownerID: String) { valuesByOwner[ownerID] = suppressions }
}

private final class MemoryFeedbackOutboxStore: SuggestedFeedbackOutboxPersisting {
  var ownerID = "test-owner"
  private var entriesByOwner: [String: [PendingSuggestedFeedback]] = [:]
  var entries: [PendingSuggestedFeedback] {
    get { entriesByOwner[ownerID] ?? [] }
    set { entriesByOwner[ownerID] = newValue }
  }
  func currentOwnerID() -> String { ownerID }
  func load(ownerID: String) -> [PendingSuggestedFeedback] { entriesByOwner[ownerID] ?? [] }
  func save(_ entries: [PendingSuggestedFeedback], ownerID: String) { entriesByOwner[ownerID] = entries }
}

private final class FakeSuggestedTasksClient: SuggestedTasksClient {
  var records: [OmiAPI.CandidateRecord] = []
  var registeredInterventionCandidateIDs: Set<String> = []
  var registeredInterventionDedupeKeys: [String] = []
  var acceptedCandidateIDs: [String] = []
  var rejectedCandidateIDs: [String] = []
  var feedback: [OmiAPI.FeedbackCreate] = []
  var feedbackIdempotencyKeys: [String] = []
  var updatedTaskDescriptions: [String: String] = [:]
  var acceptedTaskID: String? = "task-created"
  var failAccept = false
  var failIntervention = false
  var failFeedback = false
  var failReject = false
  var feedbackAttempts = 0
  var onRegisterIntervention: (() -> Void)?
  var onAccept: (() -> Void)?
  var onReject: (() -> Void)?
  var onUpdate: (() -> Void)?
  var accountGeneration = 7
  var workflowMode = OmiAPI.TaskWorkflowMode.read

  func getCandidateWorkflowControl() async throws -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(accountGeneration: accountGeneration, workflowMode: workflowMode)
  }

  func listCanonicalCandidates(status: String, limit: Int) async throws -> [OmiAPI.CandidateRecord] {
    Array(records.prefix(limit))
  }

  func registerTaskIntervention(
    _ request: OmiAPI.InterventionCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.InterventionRecord {
    onRegisterIntervention?()
    if failIntervention { throw FakeError.failed }
    registeredInterventionCandidateIDs.insert(request.subjectId)
    registeredInterventionDedupeKeys.append(request.dedupeKey)
    return OmiAPI.InterventionRecord(
      attributionChainId: "attribution-\(request.subjectId)",
      createdAt: "2026-07-09T12:00:00Z",
      dedupeKey: request.dedupeKey,
      evidenceRefs: request.evidenceRefs,
      expiresAt: request.expiresAt,
      interventionId: "intervention-\(request.subjectId)",
      subjectId: request.subjectId,
      subjectKind: request.subjectKind,
      surface: request.surface
    )
  }

  func recordTaskFeedback(
    _ request: OmiAPI.FeedbackCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.FeedbackRecord {
    feedbackAttempts += 1
    if failFeedback { throw FakeError.failed }
    feedback.append(request)
    feedbackIdempotencyKeys.append(idempotencyKey)
    return OmiAPI.FeedbackRecord(
      action: request.action,
      attributionChainId: "attribution-\(request.subjectId)",
      contextSnapshotHash: request.contextSnapshotHash,
      createdAt: "2026-07-09T12:00:00Z",
      dedupeKey: "dedupe-\(request.subjectId)",
      feedbackId: "feedback-\(idempotencyKey)",
      interventionId: request.interventionId,
      laterUntil: request.laterUntil,
      proposedCompletion: false,
      proposedCompletionCandidateId: nil,
      reason: request.reason,
      subjectId: request.subjectId,
      subjectKind: request.subjectKind
    )
  }

  func acceptCanonicalCandidate(
    candidateID: String, accountGeneration: Int
  ) async throws -> OmiAPI.CandidateResolutionReceipt {
    onAccept?()
    if failAccept { throw FakeError.failed }
    acceptedCandidateIDs.append(candidateID)
    return receipt(candidateID: candidateID, status: .accepted, taskID: acceptedTaskID)
  }

  func rejectCanonicalCandidate(
    candidateID: String, reason: String?, accountGeneration: Int
  ) async throws -> OmiAPI.CandidateResolutionReceipt {
    onReject?()
    if failReject { throw FakeError.failed }
    rejectedCandidateIDs.append(candidateID)
    return receipt(candidateID: candidateID, status: .rejected, taskID: nil)
  }

  func updateSuggestedTaskDescription(id: String, description: String) async throws {
    onUpdate?()
    updatedTaskDescriptions[id] = description
  }

  private func receipt(
    candidateID: String, status: OmiAPI.CandidateStatus, taskID: String?
  ) -> OmiAPI.CandidateResolutionReceipt {
    OmiAPI.CandidateResolutionReceipt(
      candidateId: candidateID,
      newlyResolved: true,
      receiptId: "receipt-\(candidateID)",
      resolvedAt: "2026-07-09T12:00:00Z",
      status: status,
      taskId: taskID,
      workstreamId: nil
    )
  }

  enum FakeError: Error {
    case failed
  }
}
