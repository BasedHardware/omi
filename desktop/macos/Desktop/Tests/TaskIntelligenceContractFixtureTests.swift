import Foundation
import XCTest

@testable import Omi_Computer

private actor LegacyEffectSpy {
  private var calls = 0

  func record() { calls += 1 }
  func callCount() -> Int { calls }
}

private actor FakeCanonicalScreenCandidateClient: CanonicalScreenCandidateClient {
  private var idempotencyKeys: [String] = []
  private var acceptCalls = 0

  func create(
    _ candidate: OmiAPI.CandidateCreate,
    idempotencyKey: String,
    accountGeneration: Int
  ) async throws -> CanonicalScreenCandidateState {
    idempotencyKeys.append(idempotencyKey)
    return CanonicalScreenCandidateState(
      candidateID: "candidate-1",
      status: .pending,
      taskID: nil
    )
  }

  func accept(candidateID: String, accountGeneration: Int) async throws -> CanonicalScreenCandidateState {
    acceptCalls += 1
    return CanonicalScreenCandidateState(
      candidateID: candidateID,
      status: .accepted,
      taskID: "task-1"
    )
  }

  func snapshot() -> (keys: [String], acceptCalls: Int) {
    (idempotencyKeys, acceptCalls)
  }
}

final class TaskIntelligenceContractFixtureTests: XCTestCase {
  private func repositoryRoot() -> URL {
    var url = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<4 { url.deleteLastPathComponent() }
    return url
  }

  func testV1ContractHasCrossLaneDomainsAndExamples() throws {
    let url = repositoryRoot().appendingPathComponent("backend/config/task_intelligence_contract_v1.json")
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let definitions = try XCTUnwrap(root["$defs"] as? [String: Any])
    let examples = try XCTUnwrap(root["examples"] as? [String: Any])
    let required = [
      "task", "candidate", "goal", "workstream", "workstream_event", "evidence_ref", "feedback",
      "recommendation", "decision_record", "kernel_workstream_bridge", "attribution_event",
    ]

    XCTAssertEqual(root["schema_version"] as? Int, 1)
    for domain in required {
      XCTAssertNotNil(definitions[domain], "Missing schema for \(domain)")
      XCTAssertNotNil(examples[domain], "Missing examples for \(domain)")
    }
    let taskExamples = try XCTUnwrap(examples["task"] as? [[String: Any]])
    XCTAssertEqual(taskExamples.first?["priority"] as? String, "high")
  }

  func testCaptureFixturesHaveIdenticalRecordedAdapterOutputsAcrossModalities() throws {
    let url = repositoryRoot()
      .appendingPathComponent("backend/tests/unit/fixtures/task_intelligence/capture_v2.json")
    let data = try Data(contentsOf: url)
    let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
    let cases = try XCTUnwrap(root["cases"] as? [[String: Any]])

    XCTAssertFalse(cases.isEmpty)
    for fixture in cases {
      let inputs = try XCTUnwrap(fixture["inputs"] as? [String: [String: Any]])
      let transcript = try XCTUnwrap(inputs["transcript"]?["stub_output"] as? NSDictionary)
      let screen = try XCTUnwrap(inputs["screen"]?["stub_output"] as? NSDictionary)
      XCTAssertEqual(transcript, screen, "Fixture modalities drifted for \(fixture["id"] ?? "unknown")")
    }
  }

  func testScreenCapturePolicyMatchesEverySharedFixture() throws {
    let url = repositoryRoot()
      .appendingPathComponent("backend/tests/unit/fixtures/task_intelligence/capture_v2.json")
    let root = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any]
    )
    let cases = try XCTUnwrap(root["cases"] as? [[String: Any]])

    for fixture in cases {
      let inputs = try XCTUnwrap(fixture["inputs"] as? [String: [String: Any]])
      let screen = try XCTUnwrap(inputs["screen"]?["stub_output"] as? [String: Any])
      let expected = try XCTUnwrap(fixture["expected"] as? [String: Any])
      let facts = ScreenCaptureFacts(
        explicitCommand: screen["explicit_command"] as? Bool ?? false,
        clearCommitment: screen["clear_commitment"] as? Bool ?? false,
        concreteDeliverable: screen["concrete_deliverable"] as? Bool ?? false,
        directRequest: screen["direct_request"] as? Bool ?? false,
        inferredNextStep: screen["inferred_next_step"] as? Bool ?? false,
        owner: screen["owner"] as? String ?? "unknown",
        publicBroadcast: screen["public_broadcast"] as? Bool ?? false,
        directMention: screen["direct_mention"] as? Bool ?? false,
        alreadyDone: screen["already_done"] as? Bool ?? false,
        duplicateOf: screen["duplicate_of"] as? String,
        refinesTask: screen["refines_task"] as? String,
        captureConfidence: (screen["capture_confidence"] as? Double)
          ?? (screen["capture_confidence"] as? NSNumber)?.doubleValue
          ?? 0.0,
        ownershipConfidence: (screen["ownership_confidence"] as? Double)
          ?? (screen["ownership_confidence"] as? NSNumber)?.doubleValue
          ?? 0.5
      )
      XCTAssertEqual(
        ScreenCapturePolicy.evaluate(facts).rawValue,
        expected["outcome"] as? String,
        "Screen adapter drifted for \(fixture["id"] ?? "unknown")"
      )
    }
  }

  func testDiscoveryIgnoresNotificationSettingAndReadModeDisablesLegacyPromotion() {
    XCTAssertTrue(TaskAssistant.discoveryEnabled(settingsEnabled: true, notificationsEnabled: false))
    XCTAssertFalse(TaskAssistant.discoveryEnabled(settingsEnabled: false, notificationsEnabled: true))
    XCTAssertFalse(TaskCaptureModePolicy.usesLegacyStaging(.read))
    XCTAssertTrue(TaskCaptureModePolicy.usesLegacyStaging(.off))
    XCTAssertTrue(TaskCaptureModePolicy.usesLegacyStaging(.shadow))
    XCTAssertTrue(TaskCaptureModePolicy.usesLegacyStaging(.write))
    XCTAssertFalse(TaskCaptureModePolicy.usesLegacyStaging(._unknown))
    XCTAssertFalse(TaskCaptureModePolicy.usesLegacyStaging(nil))
    XCTAssertFalse(TaskCaptureModePolicy.allowsLegacyPromotion(.read))
    XCTAssertFalse(TaskCaptureModePolicy.allowsLegacyRanking(.read))
    XCTAssertFalse(TaskCaptureModePolicy.allowsDestructiveLegacyDeduplication(.read))
    XCTAssertFalse(TaskCaptureModePolicy.allowsTaskCreatedNotification(.read))
  }

  func testReadModeBehaviorallyBlocksEveryLegacyEffectAndRollbackRestoresIt() async {
    let spy = LegacyEffectSpy()
    let readGate = TaskLegacyEffectGate { .read }

    for effect in TaskLegacyEffect.allCases {
      let result = await readGate.perform(effect) {
        await spy.record()
        return true
      }
      XCTAssertNil(result)
    }
    let readCallCount = await spy.callCount()
    XCTAssertEqual(readCallCount, 0)

    let rollbackGate = TaskLegacyEffectGate { .off }
    let result = await rollbackGate.perform(.promotion) {
      await spy.record()
      return true
    }
    XCTAssertEqual(result, true)
    let rollbackCallCount = await spy.callCount()
    XCTAssertEqual(rollbackCallCount, 1)
  }

  func testTaskAttributionUsesFrozenBoundedPrivacySafeShape() throws {
    let occurredAt = Date(timeIntervalSince1970: 1_783_656_000)
    let captured = TaskIntelligenceAttributionEvent.candidateCaptured(
      candidateID: "candidate-1",
      confidenceBand: .high,
      eventID: "attr-captured",
      occurredAt: occurredAt
    )
    let capturedProperties = captured.analyticsProperties

    XCTAssertEqual(capturedProperties["schema_version"] as? Int, 1)
    XCTAssertEqual(capturedProperties["event_type"] as? String, "candidate_captured")
    XCTAssertEqual(capturedProperties["source_class"] as? String, "screen")
    XCTAssertEqual(capturedProperties["confidence_band"] as? String, "high")
    XCTAssertEqual(capturedProperties["candidate_id"] as? String, "candidate-1")
    XCTAssertNil(capturedProperties["outcome"])
    XCTAssertNil(capturedProperties["status"])
    XCTAssertNil(capturedProperties["content"])

    let resolved = try XCTUnwrap(
      TaskIntelligenceAttributionEvent.candidateResolved(
        candidateID: "candidate-1",
        taskID: "task-1",
        resolutionCode: .accepted,
        eventID: "attr-resolved",
        occurredAt: occurredAt
      )
    )
    XCTAssertEqual(resolved.analyticsProperties["event_type"] as? String, "candidate_resolved")
    XCTAssertEqual(resolved.analyticsProperties["resolution_code"] as? String, "accepted")
    XCTAssertEqual(resolved.analyticsProperties["task_id"] as? String, "task-1")
    XCTAssertNil(
      TaskIntelligenceAttributionEvent.candidateResolved(
        candidateID: "candidate-1",
        taskID: nil,
        resolutionCode: .accepted
      )
    )

    let presented = TaskIntelligenceAttributionEvent.interventionPresented(
      interventionID: "intervention-1",
      surface: .whatMattersNow,
      subjectKind: "task",
      subjectID: "task-1",
      eventID: "attr-presented",
      occurredAt: occurredAt
    )
    XCTAssertEqual(presented.analyticsProperties["event_type"] as? String, "intervention_presented")
    XCTAssertEqual(presented.analyticsProperties["surface"] as? String, "what_matters_now")
    XCTAssertEqual(presented.analyticsProperties["intervention_id"] as? String, "intervention-1")
    XCTAssertNil(presented.analyticsProperties["content"])

    let feedback = TaskIntelligenceAttributionEvent.feedbackRecorded(
      interventionID: "intervention-1",
      surface: .suggested,
      action: "do_now",
      subjectKind: "candidate",
      subjectID: "candidate-1",
      candidateID: "candidate-1",
      attributionChainID: "chain-1",
      eventID: "attr-feedback",
      occurredAt: occurredAt
    )
    XCTAssertEqual(feedback.analyticsProperties["event_type"] as? String, "feedback_recorded")
    XCTAssertEqual(feedback.analyticsProperties["feedback_action"] as? String, "do_now")
    XCTAssertNil(feedback.analyticsProperties["headline"])

    let outcome = TaskIntelligenceAttributionEvent.outcomeRecorded(
      interventionID: "intervention-1",
      surface: .suggested,
      outcomeCode: "workstream_advanced",
      subjectKind: "candidate",
      subjectID: "candidate-1",
      candidateID: "candidate-1",
      attributionChainID: "chain-1",
      eventID: "attr-outcome",
      occurredAt: occurredAt
    )
    XCTAssertEqual(outcome.analyticsProperties["event_type"] as? String, "outcome_recorded")
    XCTAssertEqual(outcome.analyticsProperties["outcome_code"] as? String, "workstream_advanced")
    XCTAssertNil(outcome.analyticsProperties["task_text"])
  }

  func testEvidenceKindNeverLeaksWorkstreamNoun() {
    XCTAssertEqual(OmiAPI.EvidenceKind.workstream_event.userFacingLabel, "Thread event")
    XCTAssertFalse(OmiAPI.EvidenceKind.workstream_event.userFacingLabel.localizedCaseInsensitiveContains("workstream"))
    XCTAssertEqual(OmiAPI.EvidenceKind.external.userFacingLabel, "Journal")
  }

  func testCanonicalScreenPayloadContainsOnlyLocalReferenceAndMinimizedTaskFacts() throws {
    let task = ExtractedTask(
      title: "Send Sarah the revised budget",
      description: nil,
      priority: .high,
      sourceApp: "Messages",
      inferredDeadline: nil,
      confidence: 0.95,
      tags: ["budget"],
      sourceCategory: "direct_request",
      sourceSubcategory: "message",
      captureKind: "clear_commitment",
      owner: "user",
      concreteDeliverable: true,
      publicBroadcast: false,
      directMention: true,
      alreadyDone: false,
      duplicateOf: nil,
      refinesTask: nil,
      ownershipConfidence: 0.95
    )
    let decision = ScreenCandidateAdapter.adapt(
      task: task,
      dueAt: nil,
      localEvidenceID: "screen-42",
      deviceID: "device-hash"
    )
    let candidate = try XCTUnwrap(decision.candidate)
    let json = try XCTUnwrap(
      String(data: JSONEncoder().encode(candidate), encoding: .utf8)
    )

    XCTAssertEqual(decision.outcome, .autoAcceptSilent)
    XCTAssertTrue(json.contains("screen-42"))
    XCTAssertTrue(json.contains("device_local"))
    XCTAssertFalse(json.contains("Messages"))
    XCTAssertFalse(json.contains("window"))
    XCTAssertFalse(json.contains("screenshot_bytes"))
  }

  func testScreenCaptureFailsClosedWhenOwnershipConfidenceIsMissing() {
    let task = ExtractedTask(
      title: "Send the revised budget",
      description: nil,
      priority: .high,
      sourceApp: "Messages",
      inferredDeadline: nil,
      confidence: 0.95,
      tags: [],
      sourceCategory: "direct_request",
      sourceSubcategory: "message",
      captureKind: "direct_request",
      owner: "user",
      concreteDeliverable: true,
      publicBroadcast: false,
      directMention: true,
      alreadyDone: false,
      duplicateOf: nil,
      refinesTask: nil,
      ownershipConfidence: nil
    )

    let facts = ScreenCandidateAdapter.facts(for: task)
    let decision = ScreenCandidateAdapter.adapt(
      task: task,
      dueAt: nil,
      localEvidenceID: "screen-ownership-missing",
      deviceID: "macos_device"
    )

    XCTAssertEqual(facts.ownershipConfidence, 0.5)
    XCTAssertEqual(decision.outcome, .ignore)
    XCTAssertNil(decision.candidate)
  }

  func testScreenCompletionRequiresAndPreservesCanonicalTaskIdentity() throws {
    let task = ExtractedTask(
      title: "Mark Sarah budget delivery complete after sending",
      description: nil,
      priority: .medium,
      sourceApp: "Messages",
      inferredDeadline: nil,
      confidence: 0.9,
      tags: [],
      sourceCategory: "direct_request",
      sourceSubcategory: "commitment",
      captureKind: "already_done",
      owner: "user",
      concreteDeliverable: true,
      publicBroadcast: false,
      directMention: true,
      alreadyDone: true,
      duplicateOf: nil,
      refinesTask: "task-budget",
      ownershipConfidence: 0.9
    )

    let decision = ScreenCandidateAdapter.adapt(
      task: task,
      dueAt: nil,
      localEvidenceID: "screen-42",
      deviceID: "macos_device"
    )

    XCTAssertEqual(decision.outcome, .proposeCompletion)
    guard case .taskComplete(let candidate) = try XCTUnwrap(decision.candidate) else {
      return XCTFail("Completion evidence must create a typed completion Candidate")
    }
    XCTAssertEqual(candidate.taskId, "task-budget")
    XCTAssertEqual(candidate.taskChange.status, .completed)
  }

  func testCanonicalDeliveryRetryAfterRestartReusesIdentityAndDoesNotForkCandidate() async throws {
    let task = ExtractedTask(
      title: "Send Sarah the revised budget by Friday",
      description: nil,
      priority: .high,
      sourceApp: "Messages",
      inferredDeadline: nil,
      confidence: 0.95,
      tags: [],
      sourceCategory: "direct_request",
      sourceSubcategory: "commitment",
      captureKind: "clear_commitment",
      owner: "user",
      concreteDeliverable: true,
      publicBroadcast: false,
      directMention: true,
      alreadyDone: false,
      duplicateOf: nil,
      refinesTask: nil,
      ownershipConfidence: 0.95
    )
    let decision = ScreenCandidateAdapter.adapt(
      task: task,
      dueAt: nil,
      localEvidenceID: "screen-42",
      deviceID: "macos_device-hash"
    )
    let client = FakeCanonicalScreenCandidateClient()
    let delivery = CanonicalScreenCandidateDelivery(client: client)

    let beforeCrash = try await delivery.deliver(
      decision,
      localID: 42,
      deviceID: "device-hash",
      accountGeneration: 7
    )
    let afterRestart = try await delivery.deliver(
      decision,
      localID: 42,
      deviceID: "device-hash",
      accountGeneration: 7
    )
    let snapshot = await client.snapshot()

    XCTAssertEqual(beforeCrash?.candidateID, "candidate-1")
    XCTAssertEqual(afterRestart?.candidateID, "candidate-1")
    XCTAssertEqual(snapshot.keys, ["screen:device-hash:42", "screen:device-hash:42"])
    XCTAssertEqual(snapshot.acceptCalls, 2)
  }

  func testCanonicalTaskFieldsSurviveSwiftWireAndCacheRoundTrip() throws {
    let fixtureURL = repositoryRoot()
      .appendingPathComponent("backend/tests/unit/fixtures/task_intelligence/canonical_round_trip_v1.json")
    let fixture = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any]
    )
    let source = try XCTUnwrap(fixture["create_response"] as? [String: Any])
    let createPayload = try XCTUnwrap(fixture["create_request"] as? [String: Any])
    let updatePayload = try XCTUnwrap(fixture["update_request"] as? [String: Any])
    let listPayload = try XCTUnwrap(fixture["list_response"] as? [String: Any])
    let workstreamPayload = try XCTUnwrap(fixture["linked_workstream"] as? [String: Any])
    let createRequest = try JSONDecoder().decode(
      OmiAPI.ActionItemCreateRequest.self,
      from: JSONSerialization.data(withJSONObject: createPayload)
    )
    let updateRequest = try JSONDecoder().decode(
      OmiAPI.ActionItemUpdateRequest.self,
      from: JSONSerialization.data(withJSONObject: updatePayload)
    )
    let listResponse = try JSONDecoder().decode(
      OmiAPI.ActionItemsResponse.self,
      from: JSONSerialization.data(withJSONObject: listPayload)
    )
    let workstream = try JSONDecoder().decode(
      OmiAPI.Workstream.self,
      from: JSONSerialization.data(withJSONObject: workstreamPayload)
    )
    let decoded = try JSONDecoder().decode(TaskActionItem.self, from: JSONSerialization.data(withJSONObject: source))
    let restored = ActionItemRecord.from(decoded).toTaskActionItem()
    let encoded = try JSONEncoder().encode(restored)
    let roundTrip = try XCTUnwrap(JSONSerialization.jsonObject(with: encoded) as? [String: Any])

    XCTAssertEqual(roundTrip["goal_id"] as? String, "goal-1")
    XCTAssertEqual(roundTrip["workstream_id"] as? String, "workstream-1")
    XCTAssertEqual(roundTrip["owner"] as? String, "user")
    XCTAssertEqual(roundTrip["source"] as? String, "conversation")
    XCTAssertEqual(roundTrip["status"] as? String, "active")
    XCTAssertEqual(roundTrip["task_id"] as? String, "task-1")
    XCTAssertEqual(roundTrip["due_confidence"] as? Double, 0.9)
    XCTAssertEqual(roundTrip["sort_order"] as? Int, 4)
    XCTAssertEqual(roundTrip["indent_level"] as? Int, 1)
    XCTAssertEqual(roundTrip["recurrence_rule"] as? String, "weekly")
    XCTAssertNotNil(roundTrip["created_at"])
    XCTAssertNotNil(roundTrip["updated_at"])
    let provenance = try XCTUnwrap(roundTrip["provenance"] as? [[String: Any]])
    XCTAssertEqual(provenance.count, 2)
    XCTAssertEqual(provenance[1]["scope"] as? String, "device_local")
    XCTAssertEqual(provenance[1]["device_id"] as? String, "mac-1")
    XCTAssertEqual(createRequest.workstreamId, "workstream-1")
    guard case .value(.completed) = updateRequest.status else {
      return XCTFail("update fixture must carry an explicit completed status")
    }
    XCTAssertEqual(listResponse.actionItems.first?.workstreamId, "workstream-1")
    XCTAssertEqual(workstream.workstreamId, decoded.workstreamId)
    XCTAssertEqual(workstream.status, .open_)

    let unlink = OmiAPI.ActionItemUpdateRequest(
      description_: .value("Keep this field only"),
      goalId: .null
    )
    let unlinkData = try JSONEncoder().encode(unlink)
    let unlinkJSON = try XCTUnwrap(JSONSerialization.jsonObject(with: unlinkData) as? [String: Any])
    XCTAssertTrue(unlinkJSON.keys.contains("goal_id"))
    XCTAssertTrue(unlinkJSON["goal_id"] is NSNull)
    XCTAssertFalse(unlinkJSON.keys.contains("workstream_id"))

    let goalPatch = OmiAPI.GoalUpdate(
      desiredOutcome: .null,
      title: .value("Keep moving")
    )
    let goalPatchJSON = try XCTUnwrap(
      JSONSerialization.jsonObject(with: JSONEncoder().encode(goalPatch)) as? [String: Any]
    )
    XCTAssertTrue(goalPatchJSON["desired_outcome"] is NSNull)
    XCTAssertFalse(goalPatchJSON.keys.contains("why_it_matters"))

    let workstreamPatch = OmiAPI.WorkstreamUpdate(nextReviewAt: .null)
    let workstreamPatchJSON = try XCTUnwrap(
      JSONSerialization.jsonObject(with: JSONEncoder().encode(workstreamPatch)) as? [String: Any]
    )
    XCTAssertTrue(workstreamPatchJSON["next_review_at"] is NSNull)
    XCTAssertFalse(workstreamPatchJSON.keys.contains("objective"))
  }

  func testCandidateTaskChangeUsesDiscriminatedGeneratedPayload() throws {
    let data = try JSONSerialization.data(withJSONObject: [
      "candidate_id": "candidate-1",
      "subject_kind": "task",
      "proposed_action": "create",
      "task_change": ["description": "Send the budget", "owner": "user"],
      "capture_confidence": 0.9,
      "ownership_confidence": 1.0,
      "evidence_refs": [["kind": "conversation", "id": "conversation-1", "scope": "canonical"]],
      "source_surface": "desktop_screen",
      "status": "pending",
      "account_generation": 7,
      "idempotency_key": "idempotency-1",
      "created_at": "2026-07-09T12:00:00Z",
    ])
    let candidate = try JSONDecoder().decode(OmiAPI.CandidateRecord.self, from: data)

    guard case .create(let payload) = candidate.taskChange else {
      return XCTFail("create Candidate must decode a TaskCreatePayload")
    }
    XCTAssertEqual(payload.description_, "Send the budget")
  }
}

final class TaskIntelligenceSQLiteRoundTripTests: XCTestCase {
  private var testUserId: String!
  private var userDirectory: URL!

  override func setUp() async throws {
    try await super.setUp()
    testUserId = "task-intelligence-contract-\(UUID().uuidString)"
    await RewindDatabase.shared.close()
    await ActionItemStorage.shared.invalidateCache()
    await StagedTaskStorage.shared.invalidateCache()
    let appSupport = FileManager.default
      .urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
    userDirectory =
      appSupport
      .appendingPathComponent("Omi", isDirectory: true)
      .appendingPathComponent("users", isDirectory: true)
      .appendingPathComponent(testUserId, isDirectory: true)
    // Create the isolated destination first so initialization never treats
    // this test identity as a first real user and migrates anonymous data.
    try FileManager.default.createDirectory(
      at: userDirectory,
      withIntermediateDirectories: true
    )
    RewindDatabase.currentUserId = testUserId
    await RewindDatabase.shared.configure(userId: testUserId)
    try await RewindDatabase.shared.initialize()
  }

  override func tearDown() async throws {
    await RewindDatabase.shared.close()
    await ActionItemStorage.shared.invalidateCache()
    await StagedTaskStorage.shared.invalidateCache()
    RewindDatabase.currentUserId = nil
    if let userDirectory { try? FileManager.default.removeItem(at: userDirectory) }
    try await super.tearDown()
  }

  func testCanonicalTaskFieldsSurviveSQLitePersistence() async throws {
    var root = URL(fileURLWithPath: #filePath).deletingLastPathComponent()
    for _ in 0..<4 { root.deleteLastPathComponent() }
    let fixtureURL =
      root
      .appendingPathComponent("backend/tests/unit/fixtures/task_intelligence/canonical_round_trip_v1.json")
    let fixture = try XCTUnwrap(
      JSONSerialization.jsonObject(with: Data(contentsOf: fixtureURL)) as? [String: Any]
    )
    let updateResponse = try XCTUnwrap(fixture["update_response"] as? [String: Any])
    let item = try JSONDecoder().decode(
      TaskActionItem.self,
      from: JSONSerialization.data(withJSONObject: updateResponse)
    )

    // Fixture persistence is intentionally session-independent.
    try await ActionItemStorage.shared.syncTaskActionItems(
      [item],
      authorization: .unrestricted
    )
    let stored = try await ActionItemStorage.shared.getLocalActionItem(byBackendId: item.id)
    let restored = try XCTUnwrap(stored)

    XCTAssertEqual(restored.goalId, "goal-1")
    XCTAssertEqual(restored.taskId, "task-1")
    XCTAssertEqual(restored.taskStatus, "completed")
    XCTAssertEqual(restored.taskOwner, "user")
    XCTAssertEqual(restored.workstreamId, "workstream-1")
    XCTAssertEqual(restored.dueConfidence, 1.0)
    XCTAssertEqual(restored.completedAt, item.completedAt)
    XCTAssertEqual(restored.createdAt, item.createdAt)
    XCTAssertEqual(restored.updatedAt, item.updatedAt)
    XCTAssertEqual(restored.sortOrder, 5)
    XCTAssertEqual(restored.indentLevel, 2)
    XCTAssertEqual(restored.recurrenceRule, "monthly")
    XCTAssertEqual(restored.provenance?.first?.version, "2")
  }

  func testCanonicalCandidateOutboxIsHiddenRetryableAndReceiptReconciled() async throws {
    let row = try await StagedTaskStorage.shared.insertLocalStagedTask(
      StagedTaskRecord(
        description: "Send Sarah the revised budget",
        source: "candidate_outbox",
        confidence: 0.9,
        sourceApp: "Messages"
      )
    )
    let id = try XCTUnwrap(row.id)

    let visibleBeforeReceipt = try await StagedTaskStorage.shared.getAllStagedTasks()
    let retryableBeforeReceipt = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    let retryableAfterRestart = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(visibleBeforeReceipt.isEmpty)
    XCTAssertEqual(retryableBeforeReceipt.map(\.id), [id])
    XCTAssertEqual(retryableAfterRestart.map(\.id), [id])
    XCTAssertEqual(
      ScreenCandidateAdapter.idempotencyKey(deviceID: "device-hash", localID: id),
      ScreenCandidateAdapter.idempotencyKey(deviceID: "device-hash", localID: id)
    )

    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id,
      candidateID: "candidate-1",
      status: "accepted",
      taskID: "task-1"
    )
    let retryableAfterReceipt = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    let visibleAfterReceipt = try await StagedTaskStorage.shared.getAllStagedTasks()
    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    let dedupeRecordAfterReceipt = try await StagedTaskStorage.shared.getStagedTask(id: id)
    XCTAssertTrue(retryableAfterReceipt.isEmpty)
    XCTAssertTrue(visibleAfterReceipt.isEmpty)
    XCTAssertNil(dedupeRecordAfterReceipt)
    XCTAssertEqual(
      receipt,
      CanonicalCaptureReceipt(candidateID: "candidate-1", status: "accepted", taskID: "task-1")
    )
  }
}
