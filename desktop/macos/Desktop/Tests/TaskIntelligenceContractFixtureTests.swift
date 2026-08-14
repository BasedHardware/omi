import Foundation
import GRDB
import XCTest

@testable import Omi_Computer

private actor LegacyEffectSpy {
  private var calls = 0

  func record() { calls += 1 }
  func callCount() -> Int { calls }
}

private final class FakeCanonicalScreenCandidateClient: CanonicalScreenCandidateClient {
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
    let snapshot = client.snapshot()

    XCTAssertEqual(beforeCrash?.candidateID, "candidate-1")
    XCTAssertEqual(afterRestart?.candidateID, "candidate-1")
    XCTAssertEqual(snapshot.keys, ["screen:device-hash:42", "screen:device-hash:42"])
    XCTAssertEqual(snapshot.acceptCalls, 2)
  }

  func testRepeatedParaphrasesReconcileButDistinctTasksRemainSeparate() {
    let first = canonicalOutboxRecord(
      "Reply to Hermes M4 MBA to approve opening the dev-only PR",
      sourceApp: "Telegram"
    )
    let paraphrase = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let distinctTask = canonicalOutboxRecord(
      "Follow up with Hermes M4 MBA about the staging deploy issue",
      sourceApp: "Telegram"
    )
    let differentPR = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open dev-only PR 11434",
      sourceApp: "Telegram"
    )
    let review = canonicalOutboxRecord(
      "Review Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let close = canonicalOutboxRecord(
      "Close Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )

    XCTAssertTrue(ScreenCandidateReconciliation.isEquivalent(first, paraphrase))
    XCTAssertFalse(ScreenCandidateReconciliation.isEquivalent(first, distinctTask))
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(
        canonicalOutboxRecord("Approve Hermes PR 11433", sourceApp: "Telegram"),
        differentPR
      ),
      "different task identifiers must never be merged")
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(paraphrase, review),
      "Approve vs Review are distinct action intents")
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(paraphrase, close),
      "Approve vs Close are distinct action intents")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(
        for: paraphrase.description, metadata: paraphrase.metadata ?? [:]),
      "approve")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(
        for: first.description, metadata: first.metadata ?? [:]),
      "approve")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(
        for: review.description, metadata: review.metadata ?? [:]),
      "review")
  }

  func testActionSignatureIsPolarityAwareAndSplitsCommonPurposeClasses() {
    let approve = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let doNotApprove = canonicalOutboxRecord(
      "Do not approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let neverApprove = canonicalOutboxRecord(
      "Never approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let replyToApprove = canonicalOutboxRecord(
      "Reply to Hermes M4 MBA to approve opening the dev-only PR",
      sourceApp: "Telegram"
    )
    let fix = canonicalOutboxRecord("Fix the Hermes M4 MBA login flake", sourceApp: "Slack")
    let test = canonicalOutboxRecord("Test the Hermes M4 MBA login flake", sourceApp: "Slack")
    let merge = canonicalOutboxRecord("Merge the Hermes M4 MBA login flake", sourceApp: "Slack")
    let deploy = canonicalOutboxRecord("Deploy the Hermes M4 MBA login flake", sourceApp: "Slack")
    let delete = canonicalOutboxRecord("Delete the Hermes M4 MBA login flake", sourceApp: "Slack")
    let update = canonicalOutboxRecord("Update the Hermes M4 MBA login flake", sourceApp: "Slack")

    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(
        for: approve.description, metadata: approve.metadata ?? [:]),
      "approve")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(
        for: doNotApprove.description, metadata: doNotApprove.metadata ?? [:]),
      "not_approve")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(
        for: neverApprove.description, metadata: neverApprove.metadata ?? [:]),
      "not_approve")
    let cannotApprove = canonicalOutboxRecord(
      "Cannot approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let cantApprove = canonicalOutboxRecord(
      "Cant approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let wontApprove = canonicalOutboxRecord(
      "Wont approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let wonTApprove = canonicalOutboxRecord(
      "Won't approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let shouldntApprove = canonicalOutboxRecord(
      "Shouldnt approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    let shouldnTApprove = canonicalOutboxRecord(
      "Shouldn't approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    for negated in [
      cannotApprove, cantApprove, wontApprove, wonTApprove, shouldntApprove, shouldnTApprove,
    ] {
      XCTAssertEqual(
        ScreenCandidateReconciliation.actionSignature(
          for: negated.description, metadata: negated.metadata ?? [:]),
        "not_approve",
        negated.description)
      XCTAssertFalse(
        ScreenCandidateReconciliation.isEquivalent(approve, negated),
        negated.description)
    }
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(
        for: replyToApprove.description, metadata: replyToApprove.metadata ?? [:]),
      "approve",
      "reply-to-approve must keep positive approve polarity")
    XCTAssertFalse(ScreenCandidateReconciliation.isEquivalent(approve, doNotApprove))
    XCTAssertFalse(ScreenCandidateReconciliation.isEquivalent(approve, neverApprove))
    XCTAssertTrue(ScreenCandidateReconciliation.isEquivalent(approve, replyToApprove))

    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(for: fix.description, metadata: [:]), "fix")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(for: test.description, metadata: [:]), "test")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(for: merge.description, metadata: [:]), "merge")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(for: deploy.description, metadata: [:]),
      "deploy")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(for: delete.description, metadata: [:]),
      "delete")
    XCTAssertEqual(
      ScreenCandidateReconciliation.actionSignature(for: update.description, metadata: [:]),
      "update")
    XCTAssertFalse(ScreenCandidateReconciliation.isEquivalent(fix, test))
    XCTAssertFalse(ScreenCandidateReconciliation.isEquivalent(merge, deploy))
    XCTAssertFalse(ScreenCandidateReconciliation.isEquivalent(delete, update))
  }

  func testNilVersusPresentDueDatesStillBurstDedupeWhileDistinctDuesStaySeparate() {
    let due = Date(timeIntervalSince1970: 1_800_000_000)
    let noDue = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram",
      dueAt: nil
    )
    let withDue = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram",
      dueAt: due
    )
    let nearbyDue = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram",
      dueAt: due.addingTimeInterval(30)
    )
    let distinctDue = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram",
      dueAt: due.addingTimeInterval(24 * 60 * 60)
    )

    XCTAssertTrue(
      ScreenCandidateReconciliation.isEquivalent(noDue, withDue),
      "nil vs present due must stay compatible to prevent inference-flap duplicates")
    XCTAssertTrue(ScreenCandidateReconciliation.isEquivalent(withDue, nearbyDue))
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(withDue, distinctDue),
      "distinct non-nil due dates must remain separate")
  }

  func testCreateDoesNotReconcileWithTargetedRefineOrDuplicate() {
    let create = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    var refine = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    refine.setMetadata([
      "capture_kind": "direct_request",
      "already_done": false,
      "refines_task": "task-42",
    ])
    var duplicate = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    duplicate.setMetadata([
      "capture_kind": "direct_request",
      "already_done": false,
      "duplicate_of": "task-42",
    ])
    var otherTarget = canonicalOutboxRecord(
      "Approve Hermes M4 MBA to open the dev-only PR",
      sourceApp: "Telegram"
    )
    otherTarget.setMetadata([
      "capture_kind": "direct_request",
      "already_done": false,
      "refines_task": "task-99",
    ])

    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(create, refine),
      "pure create must not merge with a targeted refine")
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(create, duplicate),
      "pure create must not merge with a targeted duplicate_of")
    XCTAssertTrue(
      ScreenCandidateReconciliation.isEquivalent(refine, duplicate),
      "same target may still reconcile across refine/duplicate_of")
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(refine, otherTarget),
      "different targets must stay distinct")
  }

  func testCreateNeverMatchesTargetedUpdate() {
    // A create capture (no target) must not reuse a prior targeted update
    // candidate (duplicate_of/refines_task set). Target presence is part of
    // the action identity.
    let createRecord = canonicalOutboxRecord(
      "Reply to Hermes M4 MBA about the dev-only PR",
      sourceApp: "Telegram"
    )
    var updateRecord = canonicalOutboxRecord(
      "Reply to Hermes M4 MBA about the dev-only PR",
      sourceApp: "Telegram"
    )
    updateRecord.setMetadata([
      "capture_kind": "direct_request",
      "already_done": false,
      "duplicate_of": "task-42",
    ])
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(createRecord, updateRecord),
      "a create (no target) must not match a targeted update (duplicate_of set)")
    XCTAssertFalse(
      ScreenCandidateReconciliation.isEquivalent(updateRecord, createRecord),
      "a targeted update must not match a create (no target)")
  }

  func testPendingCanonicalReceiptIsAlreadyCapturedNotCompletedWork() async throws {
    let candidateID = "candidate-pending-dedupe-\(UUID().uuidString)"
    let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(
      canonicalOutboxRecord(
        "Approve Hermes M4 MBA to open the dev-only PR",
        sourceApp: "Telegram"
      )
    )
    let id = try XCTUnwrap(inserted.id)

    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let descriptions = try await StagedTaskStorage.shared.getRecentCanonicalCandidateDescriptions()
    XCTAssertTrue(descriptions.contains(inserted.description))

    let repeated = try await StagedTaskStorage.shared.insertLocalStagedTask(
      canonicalOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the dev-only PR",
        sourceApp: "Telegram"
      )
    )
    let repeatedID = try XCTUnwrap(repeated.id)
    let reused = try await StagedTaskStorage.shared.recentEquivalentCanonicalReceipt(
      for: repeated,
      excludingID: repeatedID
    )
    XCTAssertEqual(reused?.candidateID, candidateID)
    try await StagedTaskStorage.shared.deleteById(repeatedID)
    try await StagedTaskStorage.shared.deleteById(id)
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

  private func canonicalOutboxRecord(
    _ description: String,
    sourceApp: String,
    dueAt: Date? = nil
  ) -> StagedTaskRecord {
    var record = StagedTaskRecord(
      description: description,
      source: "candidate_outbox",
      dueAt: dueAt,
      sourceApp: sourceApp
    )
    record.setMetadata([
      "capture_kind": "direct_request",
      "already_done": false,
    ])
    return record
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

  func testActiveTaskContextExposesOnlyBackendTaskIDs() async throws {
    _ = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(
        backendId: "backend-task-42",
        backendSynced: true,
        description: "Review the release PR",
        source: "test",
        relevanceScore: 1
      ),
      authorization: .unrestricted
    )
    _ = try await ActionItemStorage.shared.insertLocalActionItem(
      ActionItemRecord(
        description: "Unsynced local task",
        source: "test",
        relevanceScore: 2
      ),
      authorization: .unrestricted
    )

    let topTasks = try await ActionItemStorage.shared.getTopRelevanceTasks()
    let recentTasks = try await ActionItemStorage.shared.getRecentActiveTasks()

    XCTAssertEqual(topTasks.compactMap(\.backendId), ["backend-task-42"])
    XCTAssertEqual(recentTasks.compactMap(\.backendId), ["backend-task-42"])
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

  func testMarkCanonicalReceiptReusesCandidateIDWithoutUniqueViolationOrSecondRow() async throws {
    let candidateID = "candidate-reuse-\(UUID().uuidString)"
    let first = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the dev-only PR",
        sourceApp: "Telegram"
      )
    )
    let firstID = try XCTUnwrap(first.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: firstID,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let paraphrase = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the dev-only PR",
        sourceApp: "Telegram"
      )
    )
    let paraphraseID = try XCTUnwrap(paraphrase.id)
    let reused = try await StagedTaskStorage.shared.recentEquivalentCanonicalReceipt(
      for: paraphrase,
      excludingID: paraphraseID
    )
    XCTAssertEqual(reused?.candidateID, candidateID)

    // Production reuse write path: stamp the same candidateID onto R2.
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: paraphraseID,
      candidateID: candidateID,
      status: reused?.status ?? OmiAPI.CandidateStatus.pending.rawValue,
      taskID: reused?.taskID
    )

    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      return XCTFail("database should be initialized")
    }
    let rows = try await dbQueue.read { db in
      try Row.fetchAll(
        db,
        sql: """
              SELECT id, backendId, backendSynced, deleted
              FROM staged_tasks
              WHERE backendId = ?
          """,
        arguments: [candidateID]
      )
    }
    XCTAssertEqual(rows.count, 1, "exactly one local row may own the candidate backendId")
    XCTAssertEqual(rows[0]["id"] as? Int64, firstID)
    XCTAssertEqual(rows[0]["backendSynced"] as? Int64, 1)

    let paraphraseExists = try await dbQueue.read { db in
      try Int.fetchOne(
        db, sql: "SELECT COUNT(*) FROM staged_tasks WHERE id = ?", arguments: [paraphraseID]) ?? 0
    }
    XCTAssertEqual(paraphraseExists, 0, "duplicate outbox row must be retired")

    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: firstID)
    XCTAssertEqual(receipt?.candidateID, candidateID)
    XCTAssertEqual(receipt?.status, OmiAPI.CandidateStatus.pending.rawValue)
  }

  func testAcceptedAndPendingReceiptsAreReusableInsideWindow() async throws {
    let pendingID = "candidate-pending-\(UUID().uuidString)"
    let acceptedID = "candidate-accepted-\(UUID().uuidString)"

    let pending = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the pending PR",
        sourceApp: "Telegram"
      )
    )
    let pendingRowID = try XCTUnwrap(pending.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: pendingRowID,
      candidateID: pendingID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let accepted = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the accepted PR",
        sourceApp: "Telegram"
      )
    )
    let acceptedRowID = try XCTUnwrap(accepted.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: acceptedRowID,
      candidateID: acceptedID,
      status: OmiAPI.CandidateStatus.accepted.rawValue,
      taskID: "task-accepted"
    )

    let pendingRepeat = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the pending PR",
        sourceApp: "Telegram"
      )
    )
    let pendingRepeatID = try XCTUnwrap(pendingRepeat.id)
    let pendingReuse = try await StagedTaskStorage.shared.recentEquivalentCanonicalReceipt(
      for: pendingRepeat,
      excludingID: pendingRepeatID
    )
    XCTAssertEqual(pendingReuse?.candidateID, pendingID)
    XCTAssertEqual(pendingReuse?.status, OmiAPI.CandidateStatus.pending.rawValue)

    let acceptedRepeat = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the accepted PR",
        sourceApp: "Telegram"
      )
    )
    let acceptedRepeatID = try XCTUnwrap(acceptedRepeat.id)
    let acceptedReuse = try await StagedTaskStorage.shared.recentEquivalentCanonicalReceipt(
      for: acceptedRepeat,
      excludingID: acceptedRepeatID
    )
    XCTAssertEqual(acceptedReuse?.candidateID, acceptedID)
    XCTAssertEqual(acceptedReuse?.status, OmiAPI.CandidateStatus.accepted.rawValue)
    XCTAssertEqual(acceptedReuse?.taskID, "task-accepted")
  }

  func testOutsideReuseWindowAllowsLegitimateRepeat() async throws {
    let candidateID = "candidate-window-\(UUID().uuidString)"
    let now = Date()
    var aged = reconciliationOutboxRecord(
      "Approve Hermes M4 MBA to open the timed PR",
      sourceApp: "Telegram"
    )
    aged.createdAt = now.addingTimeInterval(-(ScreenCandidateReconciliation.reuseWindow + 60))
    aged.updatedAt = aged.createdAt
    let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(aged)
    let id = try XCTUnwrap(inserted.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let repeatObservation = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the timed PR",
        sourceApp: "Telegram"
      )
    )
    let repeatID = try XCTUnwrap(repeatObservation.id)
    let reused = try await StagedTaskStorage.shared.recentEquivalentCanonicalReceipt(
      for: repeatObservation,
      excludingID: repeatID,
      now: now
    )
    XCTAssertNil(reused, "outside the 30m window a legitimate repeat must create again")
  }

  func testOwnerScopedInvalidationRefusesForeignRewindOwnerWithoutMutating() async throws {
    let candidateID = "candidate-owner-refuse-\(UUID().uuidString)"
    let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the owner-scoped PR",
        sourceApp: "Telegram"
      )
    )
    let id = try XCTUnwrap(inserted.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    do {
      _ = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
        candidateID: candidateID, ownerID: "some-other-owner")
      XCTFail("expected owner mismatch")
    } catch let error as CanonicalReceiptInvalidationError {
      XCTAssertEqual(
        error, .ownerMismatch(expected: "some-other-owner", actual: testUserId))
    }

    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    XCTAssertEqual(receipt?.status, OmiAPI.CandidateStatus.pending.rawValue)
  }

  func testDismissInvalidatesLocalReceiptSoEquivalentCanCreateAgain() async throws {
    let candidateID = "candidate-dismiss-\(UUID().uuidString)"
    let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the dismissible PR",
        sourceApp: "Telegram"
      )
    )
    let id = try XCTUnwrap(inserted.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let didTerminalize = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
      candidateID: candidateID, ownerID: testUserId)
    XCTAssertTrue(didTerminalize)

    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    XCTAssertEqual(receipt?.status, OmiAPI.CandidateStatus.rejected.rawValue)

    let paraphrase = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the dismissible PR",
        sourceApp: "Telegram"
      )
    )
    let paraphraseID = try XCTUnwrap(paraphrase.id)
    let decision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: paraphrase,
      localOutboxID: paraphraseID
    )
    guard case .proceedAsDeliveryLeader = decision else {
      return XCTFail("rejected local receipts must not block a new create; got \(decision)")
    }
    let paraphraseStillPresent = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(
      id: paraphraseID)
    // Unsynced outbox rows have no receipt yet; presence is checked via retry queue.
    let retryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(
      retryable.contains(where: { $0.id == paraphraseID }),
      "R2 must remain for a fresh create when adoption is refused")
    XCTAssertNil(paraphraseStillPresent)
  }

  func testDismissBeforeAdoptDoesNotResurrectRejectedReceipt() async throws {
    let candidateID = "candidate-dismiss-before-adopt-\(UUID().uuidString)"
    let first = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the race PR",
        sourceApp: "Telegram"
      )
    )
    let firstID = try XCTUnwrap(first.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: firstID,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let paraphrase = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the race PR",
        sourceApp: "Telegram"
      )
    )
    let paraphraseID = try XCTUnwrap(paraphrase.id)

    // Dismiss lands before adoption — the atomic adopt must re-read status and refuse.
    let didTerminalize = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
      candidateID: candidateID, ownerID: testUserId)
    XCTAssertTrue(didTerminalize)
    let decision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: paraphrase,
      localOutboxID: paraphraseID
    )
    guard case .proceedAsDeliveryLeader = decision else {
      return XCTFail("expected proceed after rejected receipt; got \(decision)")
    }

    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: firstID)
    XCTAssertEqual(
      receipt?.status, OmiAPI.CandidateStatus.rejected.rawValue,
      "rejected receipt must stay rejected; adoption must not demote terminal status")
    let retryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(retryable.contains(where: { $0.id == paraphraseID }))
  }

  func testAdoptBeforeDismissRetiresDuplicateThenInvalidationSticks() async throws {
    let candidateID = "candidate-adopt-before-dismiss-\(UUID().uuidString)"
    let first = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the race PR",
        sourceApp: "Telegram"
      )
    )
    let firstID = try XCTUnwrap(first.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: firstID,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let paraphrase = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the race PR",
        sourceApp: "Telegram"
      )
    )
    let paraphraseID = try XCTUnwrap(paraphrase.id)

    let decision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: paraphrase,
      localOutboxID: paraphraseID
    )
    guard case .adoptedExistingReceipt(let adopted) = decision else {
      return XCTFail("expected adopt; got \(decision)")
    }
    XCTAssertEqual(adopted.candidateID, candidateID)
    XCTAssertEqual(adopted.status, OmiAPI.CandidateStatus.pending.rawValue)

    let didTerminalize = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
      candidateID: candidateID, ownerID: testUserId)
    XCTAssertTrue(didTerminalize)

    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: firstID)
    XCTAssertEqual(receipt?.status, OmiAPI.CandidateStatus.rejected.rawValue)
    let paraphraseExists = try await {
      guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
        XCTFail("database should be initialized")
        return -1
      }
      return try await dbQueue.read { db in
        try Int.fetchOne(
          db, sql: "SELECT COUNT(*) FROM staged_tasks WHERE id = ?", arguments: [paraphraseID])
          ?? 0
      }
    }()
    XCTAssertEqual(paraphraseExists, 0, "adopt must retire R2 without leaving a second row")

    // A later stamp must not resurrect pending over rejected.
    let late = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the race PR again",
        sourceApp: "Telegram"
      )
    )
    let lateID = try XCTUnwrap(late.id)
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: lateID,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )
    let afterDemoteAttempt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(
      id: firstID)
    XCTAssertEqual(
      afterDemoteAttempt?.status, OmiAPI.CandidateStatus.rejected.rawValue,
      "markCanonicalReceipt must never demote terminal status")
  }

  func testZeroMatchInvalidationReturnsFalseUntilMarkThenTerminalizes() async throws {
    let candidateID = "candidate-zero-match-\(UUID().uuidString)"
    // Create→mark not landed yet: unsynced outbox has no candidate id to match.
    let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the zero-match PR",
        sourceApp: "Telegram"
      )
    )
    let id = try XCTUnwrap(inserted.id)

    let first = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
      candidateID: candidateID, ownerID: testUserId)
    XCTAssertFalse(first, "zero-match must not pretend cleanup succeeded")

    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )

    let second = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
      candidateID: candidateID, ownerID: testUserId)
    XCTAssertTrue(second)
    let receipt = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    XCTAssertEqual(receipt?.status, OmiAPI.CandidateStatus.rejected.rawValue)
  }

  func testInFlightCreateDismissMarkInvalidationSequence() async throws {
    let candidateID = "candidate-inflight-\(UUID().uuidString)"
    // Simulate: backend create returned C, dismiss ran before local mark.
    let inserted = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the in-flight PR",
        sourceApp: "Telegram"
      )
    )
    let id = try XCTUnwrap(inserted.id)

    let dismissBeforeMark = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
      candidateID: candidateID, ownerID: testUserId)
    XCTAssertFalse(dismissBeforeMark)

    // In-flight mark lands as pending after dismiss cleanup saw zero rows.
    try await StagedTaskStorage.shared.markCanonicalReceipt(
      id: id,
      candidateID: candidateID,
      status: OmiAPI.CandidateStatus.pending.rawValue,
      taskID: nil
    )
    let pending = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    XCTAssertEqual(pending?.status, OmiAPI.CandidateStatus.pending.rawValue)

    // Subsequent apply (load) terminalizes the resurrected pending receipt.
    let retry = try await StagedTaskStorage.shared.invalidateCanonicalReceipt(
      candidateID: candidateID, ownerID: testUserId)
    XCTAssertTrue(retry)
    let terminal = try await StagedTaskStorage.shared.getCanonicalCaptureReceipt(id: id)
    XCTAssertEqual(terminal?.status, OmiAPI.CandidateStatus.rejected.rawValue)
  }

  func testDualUnsyncedEquivalentElectsOldestLeaderInBothCallOrders() async throws {
    let older = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the dual-create PR",
        sourceApp: "Telegram"
      )
    )
    let olderID = try XCTUnwrap(older.id)
    // Ensure deterministic createdAt ordering if inserts share a clock tick.
    try await setOutboxCreatedAt(id: olderID, createdAt: Date().addingTimeInterval(-5))

    let newer = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the dual-create PR",
        sourceApp: "Telegram"
      )
    )
    let newerID = try XCTUnwrap(newer.id)
    try await setOutboxCreatedAt(id: newerID, createdAt: Date())

    // Newer resolves first — must coalesce; older remains sole leader.
    let newerDecision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: newer,
      localOutboxID: newerID
    )
    XCTAssertEqual(newerDecision, .coalescedIntoDeliveryLeader)

    let olderDecision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: older,
      localOutboxID: olderID
    )
    XCTAssertEqual(olderDecision, .proceedAsDeliveryLeader)

    let retryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(retryable.contains(where: { $0.id == olderID }))
    XCTAssertFalse(retryable.contains(where: { $0.id == newerID }))
  }

  func testDualUnsyncedEquivalentOlderFirstStillCoalescesNewer() async throws {
    let older = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the dual-create-order PR",
        sourceApp: "Telegram"
      )
    )
    let olderID = try XCTUnwrap(older.id)
    try await setOutboxCreatedAt(id: olderID, createdAt: Date().addingTimeInterval(-5))

    let newer = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the dual-create-order PR",
        sourceApp: "Telegram"
      )
    )
    let newerID = try XCTUnwrap(newer.id)
    try await setOutboxCreatedAt(id: newerID, createdAt: Date())

    let olderDecision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: older,
      localOutboxID: olderID
    )
    XCTAssertEqual(olderDecision, .proceedAsDeliveryLeader)

    let newerDecision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: newer,
      localOutboxID: newerID
    )
    XCTAssertEqual(newerDecision, .coalescedIntoDeliveryLeader)

    let retryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(retryable.contains(where: { $0.id == olderID }))
    XCTAssertFalse(retryable.contains(where: { $0.id == newerID }))
  }

  func testDeliveryLeaderRemainsForRetryAfterSimulatedFailure() async throws {
    let leader = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the leader-retry PR",
        sourceApp: "Telegram"
      )
    )
    let leaderID = try XCTUnwrap(leader.id)

    let first = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: leader,
      localOutboxID: leaderID
    )
    XCTAssertEqual(first, .proceedAsDeliveryLeader)

    // Simulated deliver failure / crash: no markCanonicalReceipt. Leader stays.
    let stillUnsynced = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(stillUnsynced.contains(where: { $0.id == leaderID }))

    let retry = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: leader,
      localOutboxID: leaderID
    )
    XCTAssertEqual(retry, .proceedAsDeliveryLeader)
  }

  func testNonEquivalentUnsyncedRowsBothProceedAsLeaders() async throws {
    let approve = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the distinct-intent PR",
        sourceApp: "Telegram"
      )
    )
    let approveID = try XCTUnwrap(approve.id)

    let review = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Review Hermes M4 MBA to open the distinct-intent PR",
        sourceApp: "Telegram"
      )
    )
    let reviewID = try XCTUnwrap(review.id)

    XCTAssertFalse(ScreenCandidateReconciliation.isEquivalent(approve, review))

    let approveDecision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: approve,
      localOutboxID: approveID
    )
    let reviewDecision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: review,
      localOutboxID: reviewID
    )
    XCTAssertEqual(approveDecision, .proceedAsDeliveryLeader)
    XCTAssertEqual(reviewDecision, .proceedAsDeliveryLeader)

    let retryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(retryable.contains(where: { $0.id == approveID }))
    XCTAssertTrue(retryable.contains(where: { $0.id == reviewID }))
  }

  func testEquivalentLeaderElectionSearchesBeyondOneHundredUnrelatedRows() async throws {
    let older = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Approve Hermes M4 MBA to open the backlog PR",
        sourceApp: "Telegram"
      )
    )
    let olderID = try XCTUnwrap(older.id)
    try await setOutboxCreatedAt(id: olderID, createdAt: Date().addingTimeInterval(-10))

    for index in 0..<101 {
      let unrelated = try await StagedTaskStorage.shared.insertLocalStagedTask(
        reconciliationOutboxRecord(
          "Review unrelated backlog item \(index)",
          sourceApp: "Slack"
        )
      )
      try await setOutboxCreatedAt(
        id: try XCTUnwrap(unrelated.id),
        createdAt: Date().addingTimeInterval(Double(index - 5))
      )
    }

    let newer = try await StagedTaskStorage.shared.insertLocalStagedTask(
      reconciliationOutboxRecord(
        "Reply to Hermes M4 MBA to approve opening the backlog PR",
        sourceApp: "Telegram"
      )
    )
    let newerID = try XCTUnwrap(newer.id)

    let decision = try await StagedTaskStorage.shared.resolveCanonicalCaptureDelivery(
      for: newer,
      localOutboxID: newerID
    )
    XCTAssertEqual(decision, .coalescedIntoDeliveryLeader)

    let retryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    XCTAssertTrue(retryable.contains(where: { $0.id == olderID }))
    XCTAssertFalse(retryable.contains(where: { $0.id == newerID }))
  }

  func testDefaultOutboxRetryLoadIsNotTruncatedAtFiftyRows() async throws {
    for index in 0..<55 {
      _ = try await StagedTaskStorage.shared.insertLocalStagedTask(
        reconciliationOutboxRecord(
          "Process durable retry item \(index)",
          sourceApp: "Slack"
        )
      )
    }

    let allRetryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox()
    let boundedRetryable = try await StagedTaskStorage.shared.getUnsyncedCanonicalOutbox(limit: 50)
    XCTAssertEqual(allRetryable.count, 55)
    XCTAssertEqual(boundedRetryable.count, 50)
  }

  private func setOutboxCreatedAt(id: Int64, createdAt: Date) async throws {
    guard let dbQueue = await RewindDatabase.shared.getDatabaseQueue() else {
      XCTFail("database should be initialized")
      return
    }
    try await dbQueue.write { db in
      try db.execute(
        sql: "UPDATE staged_tasks SET createdAt = ? WHERE id = ?",
        arguments: [createdAt, id]
      )
    }
  }

  private func reconciliationOutboxRecord(
    _ description: String,
    sourceApp: String
  ) -> StagedTaskRecord {
    var record = StagedTaskRecord(
      description: description,
      source: "candidate_outbox",
      sourceApp: sourceApp
    )
    record.setMetadata([
      "capture_kind": "direct_request",
      "already_done": false,
    ])
    return record
  }
}
