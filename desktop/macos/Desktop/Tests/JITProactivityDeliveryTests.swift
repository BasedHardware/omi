import Foundation
import XCTest

@testable import Omi_Computer

final class JITProactivityDeliveryTests: XCTestCase {
  private final class AuthorizationProbe: @unchecked Sendable {
    private let lock = NSLock()
    private var checks = 0

    func current(_: RuntimeOwnerAuthorizationSnapshot) -> Bool {
      lock.lock()
      defer { lock.unlock() }
      checks += 1
      return checks == 1
    }

    var checkCount: Int {
      lock.lock()
      defer { lock.unlock() }
      return checks
    }
  }

  private actor CandidateRecorder {
    private(set) var calls: [(String, [String])] = []

    func record(deliveryID: String, factIDs: [String]) {
      calls.append((deliveryID, factIDs))
    }
  }

  private func snapshot() throws -> RuntimeOwnerAuthorizationSnapshot {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "owner")
    return try XCTUnwrap(authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
  }

  private func request(mode: String = "ask") throws -> JITProactivityAgentRequest {
    JITProactivityAgentRequest(
      surface: .service("jit-test"),
      prompt: "prompt",
      systemPrompt: "system",
      mode: mode,
      authorizationSnapshot: try snapshot())
  }

  func testAgentAuthorityRequiresAskModeBeforeRunnerSubmission() async throws {
    let invoked = AuthorizationProbe()
    do {
      _ = try await JITProactivityAgentAuthority.run(
        request(mode: "act"),
        runner: { request in
          _ = invoked.current(request.authorizationSnapshot)
          return JITProactivityAgentResult(text: "", runID: "run", inputTokens: 0, outputTokens: 0)
        },
        authorizationCurrent: { _ in true })
      XCTFail("act mode must be rejected")
    } catch {
      XCTAssertEqual(error as? JITProactivityAgentAuthorityError, .readOnlyModeRequired)
    }
    XCTAssertEqual(invoked.checkCount, 0)
  }

  func testQAWithoutBudgetCannotSubmitAnAgentTurn() async throws {
    let probe = AuthorizationProbe()
    do {
      _ = try await JITProactivityAgentAuthority.run(
        request(),
        runner: { request in
          _ = probe.current(request.authorizationSnapshot)
          return JITProactivityAgentResult(text: "{}", runID: "run", inputTokens: 1, outputTokens: 1)
        },
        requiresBoundedBudget: true,
        authorizationCurrent: { _ in true })
      XCTFail("QA must not silently use the ordinary unbounded route")
    } catch {
      XCTAssertEqual(error as? JITProactivityAgentAuthorityError, .qualificationBudgetRequired)
    }
    XCTAssertEqual(probe.checkCount, 0)
    XCTAssertTrue(JITProactivityAgentAuthority.requiresQualificationBudget(bundleIdentifier: "com.omi.omi-jit-qa"))
    XCTAssertFalse(JITProactivityAgentAuthority.requiresQualificationBudget(bundleIdentifier: "com.omi.computer"))
  }

  func testExistingNonQualificationRouteRemainsAvailableWithoutBudget() async throws {
    let result = try await JITProactivityAgentAuthority.run(
      request(),
      runner: { _ in JITProactivityAgentResult(text: "existing", runID: "run", inputTokens: 1, outputTokens: 1) },
      requiresBoundedBudget: false,
      authorizationCurrent: { _ in true })
    XCTAssertEqual(result.text, "existing")
  }

  func testAgentAuthorityRejectsOwnerTransitionAcrossFullAwait() async throws {
    let probe = AuthorizationProbe()
    do {
      _ = try await JITProactivityAgentAuthority.run(
        request(),
        runner: { _ in
          await Task.yield()
          return JITProactivityAgentResult(text: "{}", runID: "run", inputTokens: 1, outputTokens: 1)
        },
        authorizationCurrent: probe.current)
      XCTFail("stale owner result must not publish")
    } catch {
      XCTAssertEqual(error as? JITProactivityAgentAuthorityError, .ownerChanged)
    }
  }

  func testOutputContractKeepsPlannedInsightOnlyAndAmbientTaskCandidateExplicit() throws {
    let task = """
      {"decision":"task_candidate","title":"Ship","message":"Ship build","reasoning":"fact",\
      "bucket_entry_refs":[],"fact_ids":["fact:1"]}
      """
    XCTAssertThrowsError(try JITProactivityOutputPolicy.decode(task, lane: .planned))
    XCTAssertEqual(try JITProactivityOutputPolicy.decode(task, lane: .ambient).decision, "task_candidate")
    XCTAssertThrowsError(
      try JITProactivityOutputPolicy.decode(
        task.replacingOccurrences(of: "[\"fact:1\"]", with: "[]"), lane: .ambient))
  }

  func testFocusNudgeIsAnAmbientOnlyDecisionUnderTheFocusBadge() throws {
    let nudge = """
      {"decision":"focus_nudge","title":"Focus","message":"Reply to Sam before standup",\
      "reasoning":"fact","bucket_entry_refs":[],"fact_ids":["fact:1"]}
      """
    XCTAssertEqual(try JITProactivityOutputPolicy.decode(nudge, lane: .ambient).decision, "focus_nudge")
    XCTAssertThrowsError(try JITProactivityOutputPolicy.decode(nudge, lane: .planned))
    XCTAssertEqual(ProactiveNotificationKind.from(decisionType: "focus_nudge"), .suggestion)
  }

  func testReservationIdentifiersAreContentFreeAndOnlyAdmissionCanResume() {
    let candidateID = JITProactivityReservation.identifier("candidate", "raw local context")
    let eventID = JITProactivityReservation.identifier("notification", candidateID)
    XCTAssertEqual(candidateID.count, 64)
    XCTAssertEqual(eventID.count, 64)
    XCTAssertTrue(candidateID.allSatisfy { Set("0123456789abcdef").contains($0) })

    let admission = JITProactivityReservation(
      eventID: eventID, candidateID: candidateID, operation: .ambientNotification,
      accountGeneration: 1, triggerMemoryID: nil, triggerRevision: nil)
    let full = JITProactivityReservation(
      eventID: JITProactivityReservation.identifier("full", candidateID),
      candidateID: candidateID, operation: .fullTurn,
      accountGeneration: 1, triggerMemoryID: nil, triggerRevision: nil,
      parentEventID: eventID)
    XCTAssertTrue(admission.acceptsExistingReceipt)
    XCTAssertFalse(full.acceptsExistingReceipt)
  }

  func testReservationReceiptMustMatchEveryAuthorityField() {
    let candidateID = JITProactivityReservation.identifier("candidate", "receipt")
    let eventID = JITProactivityReservation.identifier("notification", candidateID)
    let reservation = JITProactivityReservation(
      eventID: eventID,
      candidateID: candidateID,
      operation: .ambientNotification,
      accountGeneration: 2,
      triggerMemoryID: nil,
      triggerRevision: nil)
    let receipt = JITProactivityReservationReceipt(
      eventID: eventID,
      candidateID: candidateID,
      operation: .ambientNotification,
      accountGeneration: 2,
      deviceID: JITProactivityReservation.identifier("device", "test"),
      triggerMemoryID: nil,
      triggerRevision: nil,
      parentEventID: nil)
    let envelope = JITProactivityReservationEnvelope(reserved: true, receipt: receipt)
    XCTAssertTrue(
      JITProactivityReservationClient.validates(
        envelope,
        reservation: reservation,
        deviceID: receipt.deviceID))
    let mismatched = JITProactivityReservation(
      eventID: eventID,
      candidateID: candidateID,
      operation: .ambientNotification,
      accountGeneration: 3,
      triggerMemoryID: nil,
      triggerRevision: nil)
    XCTAssertFalse(
      JITProactivityReservationClient.validates(
        envelope,
        reservation: mismatched,
        deviceID: receipt.deviceID))
  }

  func testPaidBoundaryPlanBindsFullTurnToMatchingPlannedAdmission() throws {
    let candidateID = JITProactivityReservation.identifier("candidate", "planned")
    let row = JITTriggerSnapshotRow(
      memoryID: "trigger", itemRevision: 7, updatedAt: Date(timeIntervalSince1970: 10),
      triggerConditionJSON: "{}",
      action: JITTriggerSnapshotAction(type: "agent_prompt", prompt: "prompt"),
      wakeupBudgetPerDay: 1)
    let receipt = JITTriggerMirrorReceipt(
      ownerID: "owner", accountGeneration: 3, commitSequence: 4,
      snapshotRevision: "snapshot", rowCount: 1)
    let execution = JITPlannedExecution(
      lane: .planned, triggerID: "trigger", continuityKey: "continuity", prompt: "prompt",
      claim: JITTriggerWakeupClaim(
        continuityKey: "continuity", triggerID: "trigger", leaseToken: "lease"),
      plannedAuthority: JITPlannedExecutionAuthority(receipt: receipt, triggerRow: row),
      candidateID: candidateID, accountGeneration: 3, policy: .ratifiedV1)

    let plan = try XCTUnwrap(JITProactivityPaidBoundaryPlan.make(for: execution))
    XCTAssertEqual(plan.notificationAdmission.operation, .plannedNotification)
    XCTAssertEqual(plan.fullTurn.operation, .fullTurn)
    XCTAssertEqual(plan.fullTurn.parentEventID, plan.notificationAdmission.eventID)
    XCTAssertEqual(plan.fullTurn.candidateID, plan.notificationAdmission.candidateID)
    XCTAssertEqual(plan.fullTurn.accountGeneration, plan.notificationAdmission.accountGeneration)
    XCTAssertEqual(plan.fullTurn.triggerMemoryID, plan.notificationAdmission.triggerMemoryID)
    XCTAssertEqual(plan.fullTurn.triggerRevision, plan.notificationAdmission.triggerRevision)
    XCTAssertEqual(plan.fullTurn.triggerRevision, 7)
    XCTAssertTrue(JITProactivityReservation.isIdentifier(plan.notificationAdmission.eventID))
    XCTAssertTrue(JITProactivityReservation.isIdentifier(plan.fullTurn.eventID))
    let feedbackContext = try XCTUnwrap(
      JITTriggerFeedbackContext.planned(ownerID: "owner", execution: execution, paidPlan: plan))
    XCTAssertEqual(feedbackContext.eventID, plan.notificationAdmission.eventID)
    XCTAssertNotEqual(feedbackContext.eventID, execution.candidateID)
    XCTAssertEqual(feedbackContext.triggerMemoryID, plan.notificationAdmission.triggerMemoryID)
    XCTAssertEqual(feedbackContext.triggerRevision, plan.notificationAdmission.triggerRevision)
  }

  func testPaidBoundaryPlanRejectsDriftedPlannedAuthority() {
    let row = JITTriggerSnapshotRow(
      memoryID: "different-trigger", itemRevision: 7, updatedAt: Date(),
      triggerConditionJSON: "{}",
      action: JITTriggerSnapshotAction(type: "agent_prompt", prompt: "prompt"),
      wakeupBudgetPerDay: 1)
    let receipt = JITTriggerMirrorReceipt(
      ownerID: "owner", accountGeneration: 3, commitSequence: 4,
      snapshotRevision: "snapshot", rowCount: 1)
    let execution = JITPlannedExecution(
      lane: .planned, triggerID: "trigger", continuityKey: "continuity", prompt: "prompt",
      claim: JITTriggerWakeupClaim(
        continuityKey: "continuity", triggerID: "trigger", leaseToken: "lease"),
      plannedAuthority: JITPlannedExecutionAuthority(receipt: receipt, triggerRow: row),
      candidateID: JITProactivityReservation.identifier("candidate", "planned"),
      accountGeneration: 3, policy: .ratifiedV1)

    XCTAssertNil(JITProactivityPaidBoundaryPlan.make(for: execution))
  }

  func testPaidBoundaryReservesNotificationThenParentFullTurnBeforeAgent() async throws {
    let execution = JITPlannedExecution(
      lane: .ambient,
      triggerID: "ambient",
      continuityKey: "continuity",
      prompt: "prompt",
      claim: JITTriggerWakeupClaim(
        continuityKey: "continuity", triggerID: "ambient", leaseToken: "lease"),
      plannedAuthority: nil,
      candidateID: JITProactivityReservation.identifier("candidate", "boundary"),
      accountGeneration: 1,
      policy: .ratifiedV1)
    let plan = try XCTUnwrap(JITProactivityPaidBoundaryPlan.make(for: execution))
    let authorization = try snapshot()
    let recorder = BoundaryRecorder()

    _ = try await JITProactivityPaidBoundary.run(
      plan: plan,
      authorizationSnapshot: authorization,
      reserve: { reservation, _ in
        await recorder.append("reserve:\(reservation.operation.rawValue)")
        return true
      },
      agentRunner: {
        await recorder.append("agent")
        return JITProactivityAgentResult(text: "{}", runID: "run", inputTokens: 1, outputTokens: 1)
      })

    let values = await recorder.values
    XCTAssertEqual(values, ["reserve:ambient_notification", "reserve:full_turn", "agent"])
  }

  func testPaidBoundaryDenialPreventsAgentWork() async throws {
    let execution = JITPlannedExecution(
      lane: .ambient,
      triggerID: "ambient",
      continuityKey: "continuity",
      prompt: "prompt",
      claim: JITTriggerWakeupClaim(
        continuityKey: "continuity", triggerID: "ambient", leaseToken: "lease"),
      plannedAuthority: nil,
      candidateID: JITProactivityReservation.identifier("candidate", "denied"),
      accountGeneration: 1,
      policy: .ratifiedV1)
    let plan = try XCTUnwrap(JITProactivityPaidBoundaryPlan.make(for: execution))
    let recorder = BoundaryRecorder()

    do {
      _ = try await JITProactivityPaidBoundary.run(
        plan: plan,
        authorizationSnapshot: try snapshot(),
        reserve: { reservation, _ in
          await recorder.append("reserve:\(reservation.operation.rawValue)")
          return reservation.operation != .fullTurn
        },
        agentRunner: {
          await recorder.append("agent")
          return JITProactivityAgentResult(text: "{}", runID: "run", inputTokens: 0, outputTokens: 0)
        })
      XCTFail("full-turn denial must stop before model work")
    } catch JITProactivityPaidBoundaryError.fullTurnReservationDenied {
      // Expected.
    }
    let values = await recorder.values
    XCTAssertEqual(values, ["reserve:ambient_notification", "reserve:full_turn"])
  }

  func testVisibleFeedbackActionsRouteOnlyThroughExplicitRecorder() async throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "owner")
    let authorization = try XCTUnwrap(
      authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
    let context = JITTriggerFeedbackContext(
      ownerID: "owner",
      eventID: JITProactivityReservation.identifier("event", "feedback"),
      triggerMemoryID: "trigger",
      accountGeneration: 1,
      triggerRevision: 2)
    let recorder = FeedbackActionRecorder()

    for action in JITTriggerFeedbackActionRouter.visibleActions {
      await JITTriggerFeedbackActionRouter.record(
        action,
        context: context,
        snoozedUntil: action == .snooze ? Date().addingTimeInterval(60) : nil,
        authorizationSnapshot: authorization,
        authorizationCurrent: { _ in true },
        recorder: { action, context, snoozedUntil, _ in
          await recorder.append(action, context, snoozedUntil)
        })
    }

    let records = await recorder.records
    XCTAssertEqual(records.map(\.action), JITTriggerFeedbackActionRouter.visibleActions)
    XCTAssertNotNil(records.first(where: { $0.action == .snooze })?.snoozedUntil)
    XCTAssertNil(records.first(where: { $0.action != .snooze })?.snoozedUntil)
  }

  func testFeedbackOutboxRetriesOnLifecycleRestoration() async throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "owner")
    let authorization = try XCTUnwrap(
      authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
    let defaults = try XCTUnwrap(UserDefaults(suiteName: "jit-feedback-test-\(UUID().uuidString)"))
    let feedback = JITTriggerFeedback(
      feedbackID: JITProactivityReservation.identifier("feedback", "queued"),
      eventID: JITProactivityReservation.identifier("event", "queued"),
      triggerMemoryID: "trigger",
      accountGeneration: 1,
      triggerRevision: 1,
      action: .useful)
    let failed = JITTriggerFeedbackClient(
      defaults: JITTriggerFeedbackDefaults(defaults), submitter: { _, _ in false },
      authorizationCurrent: { _ in true }, authorizationSnapshotProvider: { authorization })
    await failed.record(feedback, authorizationSnapshot: authorization)
    let queuedCount = await failed.pendingCount(ownerID: "owner")
    XCTAssertEqual(queuedCount, 1)

    let attempts = FeedbackAttemptRecorder()
    let recovered = JITTriggerFeedbackClient(
      defaults: JITTriggerFeedbackDefaults(defaults),
      submitter: { _, _ in
        await attempts.append()
        return true
      }, authorizationCurrent: { _ in true }, authorizationSnapshotProvider: { authorization })
    await recovered.installLifecycleRetry()
    // On the main thread, as `performEffectiveOwnerTransition` posts it. Posting
    // from this async test body instead delivered it straight onto a cooperative
    // thread, where the first `@MainActor` observer to have been constructed by
    // an earlier suite trapped on entry and took the whole test host with it.
    await MainActor.run {
      NotificationCenter.default.post(name: .runtimeOwnerDidChange, object: nil)
    }
    for _ in 0..<20 {
      if await recovered.pendingCount(ownerID: "owner") == 0 { break }
      // omi-test-quality: wall-clock-wait -- lifecycle observer scheduling has no injectable clock
      try await Task.sleep(nanoseconds: 10_000_000)
    }
    let remainingCount = await recovered.pendingCount(ownerID: "owner")
    let attemptCount = await attempts.count
    XCTAssertEqual(remainingCount, 0)
    XCTAssertGreaterThanOrEqual(attemptCount, 1)
  }

  func testFeedbackOutboxConcurrentAppendSurvivesAwaitedFlush() async throws {
    let authorization = try snapshot()
    let defaults = try XCTUnwrap(UserDefaults(suiteName: "jit-feedback-concurrency-\(UUID().uuidString)"))
    let gate = FeedbackSubmitGate()
    let submitted = FeedbackAttemptRecorder()
    let firstFeedbackID = JITProactivityReservation.identifier("feedback", "first")
    let client = JITTriggerFeedbackClient(
      defaults: JITTriggerFeedbackDefaults(defaults),
      submitter: { feedback, _ in
        await submitted.append(feedback.feedbackID)
        await gate.waitForRelease()
        // Let the first item drain but leave the concurrently appended item
        // queued so the test can prove the stale first flush did not erase it.
        return feedback.feedbackID == firstFeedbackID
      },
      authorizationCurrent: { _ in true },
      authorizationSnapshotProvider: { authorization })
    let first = JITTriggerFeedback(
      feedbackID: firstFeedbackID,
      eventID: JITProactivityReservation.identifier("event", "first"),
      triggerMemoryID: "trigger",
      accountGeneration: 1,
      triggerRevision: 1,
      action: .useful)
    let second = JITTriggerFeedback(
      feedbackID: JITProactivityReservation.identifier("feedback", "second"),
      eventID: JITProactivityReservation.identifier("event", "second"),
      triggerMemoryID: "trigger",
      accountGeneration: 1,
      triggerRevision: 1,
      action: .snooze,
      snoozedUntil: Date().addingTimeInterval(60))

    let firstTask = Task {
      await client.record(first, authorizationSnapshot: authorization)
    }
    await gate.waitUntilStarted()
    let submitterStarted = await gate.hasStarted
    XCTAssertTrue(submitterStarted)

    // The first submitter is suspended at an actor await. A second explicit
    // action must append to the durable queue, not be lost when the first
    // flush resumes and removes its now-stale head array.
    await client.record(second, authorizationSnapshot: authorization)
    await gate.release()
    await firstTask.value

    let submittedIDs = await submitted.ids
    let pendingIDs = await client.pendingFeedbackIDs(ownerID: authorization.ownerID)
    XCTAssertEqual(submittedIDs, [first.feedbackID, second.feedbackID])
    XCTAssertEqual(pendingIDs, [second.feedbackID])
  }

  private actor FeedbackActionRecorder {
    struct Record: Sendable {
      let action: JITTriggerFeedbackAction
      let context: JITTriggerFeedbackContext
      let snoozedUntil: Date?
    }
    private(set) var records: [Record] = []

    func append(
      _ action: JITTriggerFeedbackAction,
      _ context: JITTriggerFeedbackContext,
      _ snoozedUntil: Date?
    ) {
      records.append(Record(action: action, context: context, snoozedUntil: snoozedUntil))
    }
  }

  private actor FeedbackAttemptRecorder {
    private(set) var ids: [String] = []

    func append(_ id: String = "attempt") { ids.append(id) }

    var count: Int { ids.count }
  }

  private actor FeedbackSubmitGate {
    private var releaseContinuation: CheckedContinuation<Void, Never>?
    private var startedContinuation: CheckedContinuation<Void, Never>?
    private var released = false
    private(set) var hasStarted = false

    func waitUntilStarted() async {
      if hasStarted { return }
      await withCheckedContinuation { continuation in
        startedContinuation = continuation
      }
    }

    func waitForRelease() async {
      hasStarted = true
      startedContinuation?.resume()
      startedContinuation = nil
      if released { return }
      await withCheckedContinuation { continuation in
        releaseContinuation = continuation
      }
    }

    func release() {
      released = true
      releaseContinuation?.resume()
      releaseContinuation = nil
    }
  }

  func testTaskCandidateUsesInjectedCandidateSinkBoundaryBeforePresentation() async throws {
    let recorder = CandidateRecorder()
    let delivery = JITProactivityDelivery(
      agentRunner: { _ in
        JITProactivityAgentResult(text: "", runID: "", inputTokens: 0, outputTokens: 0)
      },
      candidateGraduator: { deliveryID, factIDs, _ in
        await recorder.record(deliveryID: deliveryID, factIDs: factIDs)
        return .graduated
      })

    let result = await delivery.graduateCandidate(
      decisionType: "task_candidate",
      deliveryID: "delivery",
      factIDs: ["fact:1"],
      authorizationSnapshot: try snapshot())
    let insight = await delivery.graduateCandidate(
      decisionType: "insight",
      deliveryID: "not-a-candidate",
      factIDs: ["fact:2"],
      authorizationSnapshot: try snapshot())

    XCTAssertEqual(result, .graduated)
    XCTAssertEqual(insight, .graduated)
    let calls = await recorder.calls
    XCTAssertEqual(calls.count, 1)
    XCTAssertEqual(calls.first?.0, "delivery")
    XCTAssertEqual(calls.first?.1, ["fact:1"])
  }
}

private actor BoundaryRecorder {
  private(set) var values: [String] = []

  func append(_ value: String) {
    values.append(value)
  }
}
