import XCTest
@testable import Omi_Computer

@MainActor
final class DashboardIntelligenceStoreTests: XCTestCase {
  func testEmptyProjectionIsAValidCalmState() async {
    let api = FakeDashboardIntelligenceClient()
    api.projection = projection(items: [])
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())

    await store.load()

    XCTAssertTrue(store.recommendations.isEmpty)
    XCTAssertNil(store.error)
  }

  func testContextProjectionRefreshesDashboardWithoutConsultingNotificationSettings() {
    let defaults = UserDefaults.standard
    let previousMaster = defaults.object(forKey: NotificationService.masterEnabledDefaultsKey)
    let previousFrequency = defaults.object(forKey: NotificationService.frequencyDefaultsKey)
    defer {
      if let previousMaster { defaults.set(previousMaster, forKey: NotificationService.masterEnabledDefaultsKey) }
      else { defaults.removeObject(forKey: NotificationService.masterEnabledDefaultsKey) }
      if let previousFrequency { defaults.set(previousFrequency, forKey: NotificationService.frequencyDefaultsKey) }
      else { defaults.removeObject(forKey: NotificationService.frequencyDefaultsKey) }
    }
    defaults.set(false, forKey: NotificationService.masterEnabledDefaultsKey)
    defaults.set(0, forKey: NotificationService.frequencyDefaultsKey)
    let store = DashboardIntelligenceStore(
      client: FakeDashboardIntelligenceClient(),
      outboxStore: MemoryDashboardOutbox(),
      now: { Date(timeIntervalSince1970: 1_800_000_000) }
    )

    store.applyContextProjection(projection(items: [recommendation(id: "context-task")]))

    XCTAssertEqual(store.recommendations.map(\.subjectID), ["context-task"])
  }

  func testNotificationRecommendationRouteUsesExistingDashboardDestination() async {
    let api = FakeDashboardIntelligenceClient()
    let store = DashboardIntelligenceStore(
      client: api,
      outboxStore: MemoryDashboardOutbox(),
      now: { Date(timeIntervalSince1970: 1_800_000_000) }
    )
    store.applyContextProjection(projection(items: [recommendation(
      id: "artifact-1",
      kind: .artifact,
      destinationWorkstreamID: "workstream-existing"
    )]))
    var openedDestination: DashboardRecommendationDestination?
    store.setRecommendationActionHandler { recommendation in
      openedDestination = recommendation.destination
      return true
    }

    let opened = await store.openRecommendation(id: "output-v1:dedupe-artifact-1")

    XCTAssertTrue(opened)
    XCTAssertEqual(
      openedDestination,
      .thread(workstreamID: "workstream-existing", taskID: nil)
    )
  }

  func testProjectionCapsAtThreeAndKeepsStableIdentityUntilOutputChanges() async {
    let api = FakeDashboardIntelligenceClient()
    api.projection = projection(items: (1...4).map { recommendation(id: "task-\($0)") })
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())
    await store.load()
    let firstIDs = store.recommendations.map(\.id)

    await store.load()
    XCTAssertEqual(store.recommendations.map(\.id), firstIDs)
    XCTAssertEqual(store.recommendations.count, 3)

    api.projection = projection(
      outputVersion: "output-v2",
      items: (1...3).map { recommendation(id: "task-\($0)", outputVersion: "output-v2") }
    )
    await store.load()

    XCTAssertNotEqual(store.recommendations.map(\.id), firstIDs)
  }

  func testExpiredProjectionAndExpiredCardsNeverRender() async {
    let now = Date(timeIntervalSince1970: 1_800_000_000)
    let api = FakeDashboardIntelligenceClient()
    api.projection = projection(expiresAt: "2027-01-15T08:00:00Z", items: [recommendation(id: "task-1")])
    let store = DashboardIntelligenceStore(
      client: api,
      outboxStore: MemoryDashboardOutbox(),
      now: { now }
    )

    await store.load()

    XCTAssertTrue(store.recommendations.isEmpty)
  }

  func testProjectionDedupesAndSkipsExpiredOrUnroutableCardsBeforeCapping() {
    let items = [
      recommendation(id: "expired", expiresAt: "2027-01-01T08:00:00Z"),
      recommendation(id: "unroutable", kind: .artifact),
      recommendation(id: "one", dedupeKey: "same"),
      recommendation(id: "duplicate", dedupeKey: "same"),
      recommendation(id: "two"),
      recommendation(id: "three"),
      recommendation(id: "four"),
    ]

    let projected = DashboardIntelligenceStore.project(
      projection(items: items),
      now: Date(timeIntervalSince1970: 1_800_000_000)
    )

    XCTAssertEqual(projected.map(\.subjectID), ["one", "two", "three"])
    XCTAssertEqual(projected.count, 3)
  }

  func testActionRoutingCoversEverySupportedSubjectKind() {
    let cases: [(OmiAPI.RecommendationSubjectKind, String?, DashboardRecommendationDestination)] = [
      (.candidate, nil, .suggested(candidateID: "subject")),
      (.task, nil, .task(taskID: "subject", workstreamID: nil)),
      (.workstream, "thread-1", .thread(workstreamID: "thread-1", taskID: nil)),
      (.artifact, "thread-1", .thread(workstreamID: "thread-1", taskID: nil)),
      (.decision, "thread-1", .thread(workstreamID: "thread-1", taskID: nil)),
      (.agent_open_loop, "thread-1", .thread(workstreamID: "thread-1", taskID: nil)),
    ]

    for (kind, destinationWorkstreamID, expected) in cases {
      let item = recommendation(
        id: "subject",
        kind: kind,
        destinationWorkstreamID: destinationWorkstreamID
      )
      let projected = DashboardIntelligenceStore.project(
        projection(items: [item]),
        now: Date(timeIntervalSince1970: 1_800_000_000)
      )
      XCTAssertEqual(projected.first?.destination, expected)
    }
  }

  func testNavigationRequestWaitsForExactRenderedTargetBeforeConsuming() {
    let navigation = TaskNavigationRequestStore()
    navigation.request(candidate: candidate(id: "candidate-1"))

    XCTAssertNil(navigation.consumeIfAvailable(taskIDs: [], candidateIDs: []))
    XCTAssertEqual(navigation.peek(), .candidate("candidate-1"))
    XCTAssertEqual(
      navigation.consumeIfAvailable(taskIDs: [], candidateIDs: ["candidate-1"]),
      .candidate("candidate-1")
    )
    XCTAssertNil(navigation.peek())

    navigation.request(
      task: TaskActionItem(
        id: "task-1",
        description: "Exact task",
        completed: false,
        createdAt: Date(timeIntervalSince1970: 0)
      ))
    XCTAssertNil(navigation.consumeIfAvailable(taskIDs: ["other"], candidateIDs: []))
    XCTAssertEqual(
      navigation.consumeIfAvailable(taskIDs: ["task-1"], candidateIDs: []),
      .task("task-1")
    )
  }

  func testExactNavigationTargetsAreHydratedBeforeDashboardAcceptsTheRoute() async {
    let api = FakeDashboardIntelligenceClient()
    api.exactCandidate = candidate(id: "candidate-101")
    api.exactTask = TaskActionItem(
      id: "old-task",
      description: "Old but newly relevant task",
      completed: false,
      createdAt: Date(timeIntervalSince1970: 0)
    )
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())

    let candidate = await store.candidateForNavigation(candidateID: "candidate-101")
    let task = await store.taskForNavigation(taskID: "old-task")

    XCTAssertEqual(candidate?.candidateId, "candidate-101")
    XCTAssertEqual(task?.id, "old-task")
  }

  func testWriteSidecarModeDoesNotExposeDashboardIntelligence() async {
    let api = FakeDashboardIntelligenceClient()
    api.workflowMode = .write
    api.projection = projection(items: [recommendation(id: "task-1")])
    api.goals = [goal(id: "goal-1", status: .focused, rank: 0)]
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())

    await store.load()

    XCTAssertTrue(store.recommendations.isEmpty)
    XCTAssertTrue(store.goals.isEmpty)
    XCTAssertEqual(api.projectionLoads, 0)
  }

  func testCanonicalGoalsRemainAvailableOutsideIntelligenceCohort() async {
    let api = FakeDashboardIntelligenceClient()
    api.failProjection = true
    api.goals = [goal(id: "goal-1", status: .focused, rank: 0)]
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())

    await store.load()

    XCTAssertTrue(store.recommendations.isEmpty)
    XCTAssertEqual(store.focusedGoals.map(\.goalId), ["goal-1"])
  }

  func testGoalFocusUsesExplicitReplacementAndKeepsHistory() async {
    let api = FakeDashboardIntelligenceClient()
    api.goals = [
      goal(id: "focused", status: .focused, rank: 0),
      goal(id: "background", status: .background, rank: nil),
      goal(id: "history", status: .achieved, rank: nil),
    ]
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())
    await store.load()

    let focused = await store.focus(goalID: "background", replacing: "focused")

    XCTAssertTrue(focused)
    XCTAssertEqual(api.focusRequests.last?.goalID, "background")
    XCTAssertEqual(api.focusRequests.last?.replacementID, "focused")
    XCTAssertEqual(store.endedGoals.map(\.goalId), ["history"])
  }

  func testGoalFocusConflictRequestsServerDrivenReplacement() async {
    let api = FakeDashboardIntelligenceClient()
    api.goals = [goal(id: "background", status: .background, rank: nil)]
    api.focusError = APIError.httpError(statusCode: 409, detail: "focus set is full")
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())
    await store.load()

    let focused = await store.focus(goalID: "background", replacing: nil)

    XCTAssertFalse(focused)
    XCTAssertEqual(store.focusReplacementGoalID, "background")
  }

  func testGoalDetailUsesSingleAggregateRequest() async {
    let api = FakeDashboardIntelligenceClient()
    api.detail = OmiAPI.GoalDetailProjection(
      activeThreads: [],
      goal: goal(id: "goal-1", status: .focused, rank: 0),
      progressEvents: [],
      tasks: []
    )
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())

    await store.loadGoalDetail(goalID: "goal-1")

    XCTAssertEqual(api.detailLoads, 1)
    XCTAssertEqual(store.selectedGoalDetail?.goal.goalId, "goal-1")
  }

  func testGoalCreatePreservesQualitativeOutcomeFields() async {
    let api = FakeDashboardIntelligenceClient()
    api.goals = [goal(id: "goal-1", status: .background, rank: nil)]
    let store = DashboardIntelligenceStore(client: api, outboxStore: MemoryDashboardOutbox())
    await store.load()

    let created = await store.createGoal(
      title: "Investor pipeline",
      desiredOutcome: "Build a repeatable investor pipeline",
      whyItMatters: "Fund the next stage",
      successCriteria: ["Ten qualified conversations"],
      idempotencyKey: "goal-create-occurrence"
    )

    XCTAssertTrue(created)
    XCTAssertEqual(api.createdGoal?.desiredOutcome, "Build a repeatable investor pipeline")
    XCTAssertEqual(api.createdGoal?.successCriteria, ["Ten qualified conversations"])
    XCTAssertEqual(api.createdGoal?.generation, 7)
    XCTAssertEqual(api.createdGoal?.idempotencyKey, "goal-create-occurrence")
  }

  func testFeedbackFailurePersistsAndReplaysTheSameOccurrence() async {
    let api = FakeDashboardIntelligenceClient()
    api.projection = projection(items: [recommendation(id: "task-1")])
    api.failFeedback = true
    let outbox = MemoryDashboardOutbox()
    let store = DashboardIntelligenceStore(client: api, outboxStore: outbox)
    await store.load()
    let card = try! XCTUnwrap(store.recommendations.first)

    await store.recordPrimaryAction(card)

    XCTAssertEqual(outbox.entries.count, 1)
    XCTAssertEqual(api.feedbackKeys, ["wmn:intervention-task-1:do-now"])
    api.failFeedback = false
    await store.load()
    XCTAssertTrue(outbox.entries.isEmpty)
    XCTAssertEqual(
      api.feedbackKeys,
      ["wmn:intervention-task-1:do-now", "wmn:intervention-task-1:do-now"]
    )
  }

  func testLoadPassesDeviceScopedContextHash() async {
    let api = FakeDashboardIntelligenceClient()
    api.projection = projection(items: [recommendation(id: "task-1")])
    let store = DashboardIntelligenceStore(
      client: api,
      outboxStore: MemoryDashboardOutbox(),
      deviceIDProvider: { "device-hash-abc" }
    )

    await store.load()

    XCTAssertEqual(api.lastDeviceID, "device-hash-abc")
    XCTAssertEqual(store.recommendations.map(\.subjectID), ["task-1"])
  }

  func testPresentationFeedbackAndDoNowEmitBoundedAttribution() async {
    let api = FakeDashboardIntelligenceClient()
    api.projection = projection(items: [recommendation(id: "task-1")])
    var events: [TaskIntelligenceAttributionEvent] = []
    let store = DashboardIntelligenceStore(
      client: api,
      outboxStore: MemoryDashboardOutbox(),
      deviceIDProvider: { "device-1" },
      reportAttribution: { events.append($0) }
    )

    await store.load()
    XCTAssertEqual(events.map(\.eventType), [.interventionPresented])
    XCTAssertEqual(events[0].interventionID, "intervention-task-1")
    XCTAssertEqual(events[0].surface, .whatMattersNow)
    XCTAssertNil(events[0].analyticsProperties["content"])

    let card = try! XCTUnwrap(store.recommendations.first)
    await store.later(card)

    XCTAssertEqual(events.map(\.eventType), [.interventionPresented, .feedbackRecorded])
    XCTAssertEqual(events[1].feedbackAction, "later")
    XCTAssertEqual(events[1].subjectID, "task-1")

    api.projection = projection(items: [recommendation(id: "task-2")])
    await store.load()
    let doNowCard = try! XCTUnwrap(store.recommendations.first)
    await store.recordPrimaryAction(doNowCard)

    XCTAssertEqual(
      events.map(\.eventType),
      [.interventionPresented, .feedbackRecorded, .interventionPresented, .feedbackRecorded, .outcomeRecorded]
    )
    XCTAssertEqual(api.outcomeRequests.map(\.outcomeCode), [.workstream_advanced])
    XCTAssertEqual(events.last?.outcomeCode, "workstream_advanced")
    XCTAssertNil(events.last?.analyticsProperties["headline"])
  }

  func testDashboardDoesNotPersistOrRewriteTaskOrder() throws {
    let root = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
    let storeSource = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Dashboard/DashboardIntelligenceStore.swift"),
      encoding: .utf8
    )
    XCTAssertFalse(storeSource.contains("TaskPrioritizationService"))
    XCTAssertFalse(storeSource.contains("sortOrder"))
    XCTAssertFalse(storeSource.contains("relevanceScore"))
    XCTAssertFalse(storeSource.contains("UserDefaults.standard.set(recommendations"))
    let tasksSource = try String(
      contentsOf: root.appendingPathComponent("Sources/MainWindow/Pages/TasksPage.swift"),
      encoding: .utf8
    )
    XCTAssertTrue(tasksSource.contains("func revealTaskForNavigation"))
    XCTAssertTrue(tasksSource.contains("searchText = \"\""))
    XCTAssertTrue(tasksSource.contains("selectedTags = [.todo]"))
  }

  private func projection(
    outputVersion: String = "output-v1",
    expiresAt: String = "2027-02-15T08:00:00Z",
    items: [OmiAPI.Recommendation]
  ) -> OmiAPI.WhatMattersNowProjection {
    OmiAPI.WhatMattersNowProjection(
      evaluationId: "evaluation-1",
      expiresAt: expiresAt,
      generatedAt: "2027-01-15T08:00:00Z",
      materialVersion: "material-1",
      outputVersion: outputVersion,
      recommendations: items,
      schemaVersion: 1
    )
  }

  private func recommendation(
    id: String,
    kind: OmiAPI.RecommendationSubjectKind = .task,
    outputVersion: String = "output-v1",
    destinationWorkstreamID: String? = nil,
    expiresAt: String = "2027-02-15T08:00:00Z",
    dedupeKey: String? = nil
  ) -> OmiAPI.Recommendation {
    OmiAPI.Recommendation(
      alternativeAction: nil,
      dedupeKey: dedupeKey ?? "dedupe-\(id)",
      destinationTaskId: kind == .task ? id : nil,
      destinationWorkstreamId: destinationWorkstreamID,
      evidencePreview: "Linked evidence",
      evidenceRefs: [],
      expiresAt: expiresAt,
      feedbackSubjectId: id,
      feedbackSubjectKind: kind == .candidate ? .candidate : .task,
      goalOrWorkstreamLabel: "Launch",
      headline: "Handle \(id)",
      interventionId: "intervention-\(id)",
      outputVersion: outputVersion,
      recommendedAction: "Open",
      subjectId: id,
      subjectKind: kind,
      whyNow: "It changed materially."
    )
  }

  private func goal(id: String, status: OmiAPI.GoalStatus, rank: Int?) -> OmiAPI.GoalResponse {
    OmiAPI.GoalResponse(
      advice: nil,
      createdAt: "2027-01-01T08:00:00Z",
      currentValue: 1,
      desiredOutcome: "Reach the outcome",
      endedAt: status == .achieved ? "2027-01-10T08:00:00Z" : nil,
      focusRank: rank,
      goalId: id,
      goalType: "numeric",
      horizonAt: nil,
      id: id,
      isActive: status != .achieved && status != .abandoned,
      latestProgressSequence: nil,
      maxValue: 10,
      metric: nil,
      minValue: 0,
      source: .user,
      status: status,
      successCriteria: ["Done"],
      targetValue: 10,
      title: "Goal \(id)",
      unit: nil,
      updatedAt: "2027-01-10T08:00:00Z",
      whyItMatters: "Important"
    )
  }

  private func candidate(id: String) -> OmiAPI.CandidateRecord {
    OmiAPI.CandidateRecord(
      accountGeneration: 7,
      candidateId: id,
      captureConfidence: 0.9,
      createdAt: "2027-01-15T08:00:00Z",
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
      status: .pending,
      subjectKind: .task,
      taskChange: .create(
        OmiAPI.TaskCreatePayload(
          description_: "Review exact candidate",
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
}

private final class MemoryDashboardOutbox: DashboardFeedbackOutboxPersisting {
  var entries: [PendingDashboardFeedback] = []
  func currentOwnerID() -> String { "test-owner" }
  func load(ownerID: String) -> [PendingDashboardFeedback] { entries }
  func save(_ entries: [PendingDashboardFeedback], ownerID: String) { self.entries = entries }
}

@MainActor
final class DashboardFeedbackOutboxOwnerIsolationTests: XCTestCase {
  func testDefaultOwnerTracksAuthenticationChanges() {
    let suite = "DashboardFeedbackOutboxOwnerIsolationTests.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let outbox = DashboardFeedbackOutboxDefaults(defaults: defaults)
    let entry = PendingDashboardFeedback(
      request: OmiAPI.FeedbackCreate(
        action: .dismiss,
        contextSnapshotHash: nil,
        interventionId: nil,
        laterUntil: nil,
        reason: .not_useful,
        subjectId: "task-1",
        subjectKind: .task
      ),
      idempotencyKey: "feedback-1",
      accountGeneration: 7
    )
    defaults.set("owner-a", forKey: "auth_userId")
    outbox.save([entry], ownerID: outbox.currentOwnerID())
    defaults.set("owner-b", forKey: "auth_userId")
    XCTAssertTrue(outbox.load(ownerID: outbox.currentOwnerID()).isEmpty)
    defaults.set("owner-a", forKey: "auth_userId")
    XCTAssertEqual(outbox.load(ownerID: outbox.currentOwnerID()).first?.idempotencyKey, "feedback-1")
  }

  func testAccountSwitchDuringFeedbackDoesNotOverwriteNewOwnerQueue() async {
    let suite = "DashboardFeedbackOutboxOwnerIsolationTests.inflight.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set("owner-a", forKey: "auth_userId")
    let outbox = DashboardFeedbackOutboxDefaults(defaults: defaults)
    let client = FakeDashboardIntelligenceClient()
    client.feedbackSuspensionsRemaining = 1
    let store = DashboardIntelligenceStore(client: client, outboxStore: outbox)
    await store.load()
    let recommendation = Self.recommendation(id: "recommendation-1")
    let requestTask = Task { await store.later(recommendation) }
    while client.feedbackRelease == nil { await Task.yield() }
    defaults.set("owner-b", forKey: "auth_userId")
    let ownerBEntry = PendingDashboardFeedback(
      request: OmiAPI.FeedbackCreate(
        action: .dismiss,
        contextSnapshotHash: nil,
        interventionId: nil,
        laterUntil: nil,
        reason: .not_useful,
        subjectId: "task-b",
        subjectKind: .task
      ),
      idempotencyKey: "owner-b-feedback",
      accountGeneration: 7
    )
    outbox.save([ownerBEntry], ownerID: "owner-b")
    client.feedbackRelease?.resume()
    await requestTask.value

    XCTAssertTrue(outbox.load(ownerID: "owner-a").isEmpty)
    XCTAssertEqual(outbox.load(ownerID: "owner-b").map(\.idempotencyKey), ["owner-b-feedback"])
  }

  func testRetryMergesConcurrentSameOwnerEnqueue() async {
    let suite = "DashboardFeedbackOutboxOwnerIsolationTests.retry.\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    defaults.set("owner-a", forKey: "auth_userId")
    let outbox = DashboardFeedbackOutboxDefaults(defaults: defaults)
    let retryEntry = PendingDashboardFeedback(
      request: OmiAPI.FeedbackCreate(
        action: .later,
        contextSnapshotHash: nil,
        interventionId: "intervention-retry",
        laterUntil: "2030-01-01T00:00:00Z",
        reason: nil,
        subjectId: "task-retry",
        subjectKind: .task
      ),
      idempotencyKey: "retry-feedback",
      accountGeneration: 7
    )
    outbox.save([retryEntry], ownerID: "owner-a")
    let client = FakeDashboardIntelligenceClient()
    client.feedbackSuspensionsRemaining = 1
    let store = DashboardIntelligenceStore(client: client, outboxStore: outbox)
    let loadTask = Task { await store.load() }
    while client.feedbackRelease == nil { await Task.yield() }
    client.failFeedback = true
    await store.later(Self.recommendation(id: "new-recommendation"))
    client.failFeedback = false
    client.feedbackRelease?.resume()
    await loadTask.value

    let remaining = outbox.load(ownerID: "owner-a")
    XCTAssertEqual(remaining.count, 1)
    XCTAssertTrue(remaining[0].idempotencyKey.hasPrefix("wmn:intervention-new-recommendation:later:"))
  }

  private static func recommendation(id: String) -> DashboardRecommendation {
    DashboardRecommendation(
      id: id,
      interventionID: "intervention-\(id)",
      outputVersion: "output-1",
      subjectKind: .task,
      subjectID: "task-1",
      feedbackSubjectKind: .task,
      feedbackSubjectID: "task-1",
      headline: "Continue task",
      whyNow: "Ready",
      contextLabel: nil,
      recommendedAction: "Continue",
      evidencePreview: "Evidence",
      evidenceCount: 1,
      dedupeKey: "task-1:v1",
      expiresAt: "2030-01-01T00:00:00Z",
      destination: .task(taskID: "task-1", workstreamID: nil)
    )
  }
}

private final class FakeDashboardIntelligenceClient: DashboardIntelligenceClient {
  var workflowMode = OmiAPI.TaskWorkflowMode.read
  var projection: OmiAPI.WhatMattersNowProjection!
  var goals: [OmiAPI.GoalResponse] = []
  var detail: OmiAPI.GoalDetailProjection?
  var projectionLoads = 0
  var failProjection = false
  var detailLoads = 0
  var focusRequests: [(goalID: String, replacementID: String?)] = []
  var focusError: Error?
  var failFeedback = false
  var feedbackKeys: [String] = []
  var feedbackSuspensionsRemaining = 0
  var feedbackRelease: CheckedContinuation<Void, Never>?
  var outcomeRequests: [OmiAPI.OutcomeCreate] = []
  var outcomeKeys: [String] = []
  var failOutcome = false
  var lastDeviceID: String?
  var createdGoal: (desiredOutcome: String, successCriteria: [String], generation: Int, idempotencyKey: String)?
  var exactCandidate: OmiAPI.CandidateRecord?
  var exactTask: TaskActionItem?

  init() {
    projection = OmiAPI.WhatMattersNowProjection(
      evaluationId: "evaluation-empty",
      expiresAt: "2027-02-15T08:00:00Z",
      generatedAt: "2027-01-15T08:00:00Z",
      materialVersion: "material-empty",
      outputVersion: "output-empty",
      recommendations: [],
      schemaVersion: 1
    )
  }

  func getCandidateWorkflowControl() async throws -> OmiAPI.TaskWorkflowControl {
    OmiAPI.TaskWorkflowControl(accountGeneration: 7, workflowMode: workflowMode)
  }

  func getWhatMattersNow(deviceID: String?) async throws -> OmiAPI.WhatMattersNowProjection {
    projectionLoads += 1
    lastDeviceID = deviceID
    if failProjection { throw FakeError.missing }
    return projection
  }

  func getCanonicalGoals(includeEnded: Bool) async throws -> [OmiAPI.GoalResponse] { goals }

  func getCanonicalGoalDetail(goalID: String) async throws -> OmiAPI.GoalDetailProjection {
    detailLoads += 1
    guard let detail else { throw FakeError.missing }
    return detail
  }

  func getCanonicalCandidate(candidateID: String) async throws -> OmiAPI.CandidateRecord {
    guard let exactCandidate else { throw FakeError.missing }
    return exactCandidate
  }

  func getActionItem(id: String) async throws -> TaskActionItem {
    guard let exactTask else { throw FakeError.missing }
    return exactTask
  }

  func createCanonicalGoal(
    title: String, desiredOutcome: String, whyItMatters: String?, successCriteria: [String],
    accountGeneration: Int, idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    createdGoal = (desiredOutcome, successCriteria, accountGeneration, idempotencyKey)
    return goals.first!
  }

  func recordTaskFeedback(
    _ request: OmiAPI.FeedbackCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.FeedbackRecord {
    feedbackKeys.append(idempotencyKey)
    if feedbackSuspensionsRemaining > 0 {
      feedbackSuspensionsRemaining -= 1
      await withCheckedContinuation { feedbackRelease = $0 }
      feedbackRelease = nil
    }
    if failFeedback { throw FakeError.missing }
    return OmiAPI.FeedbackRecord(
      action: request.action,
      attributionChainId: "attribution",
      contextSnapshotHash: nil,
      createdAt: "2027-01-15T08:00:00Z",
      dedupeKey: "dedupe",
      feedbackId: "feedback",
      interventionId: request.interventionId,
      laterUntil: request.laterUntil,
      proposedCompletion: false,
      proposedCompletionCandidateId: nil,
      reason: request.reason,
      subjectId: request.subjectId,
      subjectKind: request.subjectKind
    )
  }

  func createTaskOutcome(
    _ request: OmiAPI.OutcomeCreate, idempotencyKey: String, accountGeneration: Int
  ) async throws -> OmiAPI.OutcomeRecord {
    outcomeRequests.append(request)
    outcomeKeys.append(idempotencyKey)
    if failOutcome { throw FakeError.missing }
    return OmiAPI.OutcomeRecord(
      attributionChainId: request.attributionChainId,
      occurredAt: "2027-01-15T08:00:00Z",
      outcomeCode: request.outcomeCode,
      outcomeId: "outcome-\(idempotencyKey)",
      subjectId: request.subjectId,
      subjectKind: request.subjectKind
    )
  }

  func focusCanonicalGoal(
    goalID: String, replacementGoalID: String?, focusRank: Int?, accountGeneration: Int,
    idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    focusRequests.append((goalID, replacementGoalID))
    if let focusError { throw focusError }
    return goals.first(where: { $0.goalId == goalID })!
  }

  func unfocusCanonicalGoal(
    goalID: String, accountGeneration: Int, idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    goals.first(where: { $0.goalId == goalID })!
  }

  func transitionCanonicalGoal(
    goalID: String, status: OmiAPI.GoalStatus, relationshipDisposition: String,
    accountGeneration: Int, idempotencyKey: String
  ) async throws -> OmiAPI.GoalResponse {
    goals.first(where: { $0.goalId == goalID })!
  }

  enum FakeError: Error { case missing }
}
