@preconcurrency import UserNotifications
import XCTest

@testable import Omi_Computer

final class JITAmbientFeedbackTests: XCTestCase {
  private actor SuspensionGate {
    private var entered = false
    private var enteredWaiters: [CheckedContinuation<Void, Never>] = []
    private var releaseContinuation: CheckedContinuation<Void, Never>?

    func suspend() async {
      entered = true
      enteredWaiters.forEach { $0.resume() }
      enteredWaiters.removeAll()
      await withCheckedContinuation { releaseContinuation = $0 }
    }

    func waitUntilEntered() async {
      if entered { return }
      await withCheckedContinuation { enteredWaiters.append($0) }
    }

    func release() {
      releaseContinuation?.resume()
      releaseContinuation = nil
    }
  }

  private final class Recorder: @unchecked Sendable {
    private let lock = NSLock()
    private(set) var calls: [(JITAmbientFeedbackContext, JITTriggerFeedbackAction)] = []

    func append(_ context: JITAmbientFeedbackContext, _ action: JITTriggerFeedbackAction) {
      lock.lock()
      calls.append((context, action))
      lock.unlock()
    }
  }

  private final class LockedCounter: @unchecked Sendable {
    private let lock = NSLock()
    private var value = 0

    func increment() -> Int {
      lock.withLock {
        value += 1
        return value
      }
    }
  }

  private func authorization(ownerID: String = "owner") throws -> RuntimeOwnerAuthorizationSnapshot {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: ownerID)
    return try XCTUnwrap(authority.capture(ownerID: ownerID, expectedOwnerID: ownerID))
  }

  private func context(
    ownerID: String = "owner",
    accountGeneration: Int = 4
  ) -> JITAmbientFeedbackContext {
    let candidateID = JITProactivityReservation.opaqueIdentifier(
      ["candidate", "ambient-feedback"], installationIdentity: "fixture")
    let eventID = JITProactivityReservation.opaqueIdentifier(
      ["notification", candidateID], installationIdentity: "fixture")
    return JITAmbientFeedbackContext(
      ownerID: ownerID,
      eventID: eventID,
      candidateID: candidateID,
      accountGeneration: accountGeneration,
      suggestionIdentity: SuggestionAssistantTelemetry.NotificationIdentity(
        evaluationID: UUID(uuidString: "00000000-0000-0000-0000-000000000101") ?? UUID(),
        suggestionID: UUID(uuidString: "00000000-0000-0000-0000-000000000102") ?? UUID()
      )
    )
  }

  func testAmbientContextUsesReservationAndCandidateProvenance() {
    let context = context()

    XCTAssertTrue(context.isValid)
    XCTAssertEqual(context.provenance.lane, JITProactivityLane.ambient.rawValue)
    XCTAssertEqual(context.provenance.ownerID, context.ownerID)
    XCTAssertEqual(context.provenance.deliveryID, context.eventID)
    XCTAssertEqual(context.provenance.candidateID, context.candidateID)
    XCTAssertEqual(context.provenance.accountGeneration, context.accountGeneration)
  }

  func testAmbientRouterRecordsOnlyUsefulAndNotRelevant() async throws {
    let authorization = try authorization()
    let context = context()
    let recorder = Recorder()

    for action in JITAmbientFeedbackActionRouter.visibleActions {
      await JITAmbientFeedbackActionRouter.record(
        action,
        context: context,
        authorizationSnapshot: authorization,
        currentAccountGeneration: context.accountGeneration,
        authorizationCurrent: { _ in true },
        recorder: { context, action, _ in recorder.append(context, action) }
      )
    }

    await JITAmbientFeedbackActionRouter.record(
      .snooze,
      context: context,
      authorizationSnapshot: authorization,
      currentAccountGeneration: context.accountGeneration,
      authorizationCurrent: { _ in true },
      recorder: { context, action, _ in recorder.append(context, action) }
    )

    XCTAssertEqual(
      recorder.calls.map(\.1),
      [.useful, .falsePositive],
      "ambient cards must not expose or record trigger-only controls")
    XCTAssertTrue(recorder.calls.allSatisfy { $0.0.provenance.lane == "ambient" })
  }

  func testAmbientRouterDropsStaleOwnerGenerationAndAuthorization() async throws {
    let authorization = try authorization()
    let context = context()
    let recorder = Recorder()
    let record: JITAmbientFeedbackActionRouter.Record = { context, action, _ in
      recorder.append(context, action)
    }

    await JITAmbientFeedbackActionRouter.record(
      .useful,
      context: context,
      authorizationSnapshot: authorization,
      currentAccountGeneration: context.accountGeneration + 1,
      authorizationCurrent: { _ in true },
      recorder: record
    )
    await JITAmbientFeedbackActionRouter.record(
      .useful,
      context: context,
      authorizationSnapshot: authorization,
      currentAccountGeneration: context.accountGeneration,
      authorizationCurrent: { _ in false },
      recorder: record
    )
    await JITAmbientFeedbackActionRouter.record(
      .useful,
      context: context,
      authorizationSnapshot: authorization,
      currentAccountGeneration: context.accountGeneration,
      authorizationCurrent: { _ in true },
      recorder: record
    )

    XCTAssertEqual(recorder.calls.count, 1)
  }

  func testAmbientMutationRechecksOwnerAfterSuspendedRecorderHop() async throws {
    let authority = RuntimeOwnerAuthorizationAuthority()
    authority.endTransition(ownerID: "owner")
    let authorization = try XCTUnwrap(authority.capture(ownerID: "owner", expectedOwnerID: "owner"))
    let context = context()
    let store = InterjectSuggestionFeedbackStore()
    let gate = SuspensionGate()

    let task = Task {
      await JITAmbientFeedbackActionRouter.record(
        .useful,
        context: context,
        authorizationSnapshot: authorization,
        currentAccountGeneration: context.accountGeneration,
        authorizationCurrent: { snapshot in authority.isCurrent(snapshot, ownerID: "owner") },
        recorder: { context, action, snapshot in
          await gate.suspend()
          _ = await InterjectSuggestionFeedbackMutation.record(
            evaluationID: context.suggestionIdentity.evaluationID,
            suggestionID: context.suggestionIdentity.suggestionID,
            verb: action.interjectVerb,
            provenance: context.provenance,
            store: store,
            emitAnalytics: false,
            authorizationSnapshot: snapshot,
            authorizationCurrent: { candidate in authority.isCurrent(candidate, ownerID: "owner") }
          )
        }
      )
    }

    await gate.waitUntilEntered()
    authority.beginTransition()
    authority.endTransition(ownerID: "new-owner")
    await gate.release()
    await task.value

    let record = await store.current(
      evaluationID: context.suggestionIdentity.evaluationID,
      suggestionID: context.suggestionIdentity.suggestionID
    )
    XCTAssertNil(record, "old-owner feedback must not cross an account transition")
  }

  func testAmbientMutationRechecksAccountGenerationAfterSuspendedRecorderHop() async throws {
    let authorizationAuthority = RuntimeOwnerAuthorizationAuthority()
    authorizationAuthority.endTransition(ownerID: "owner")
    let authorization = try XCTUnwrap(
      authorizationAuthority.capture(ownerID: "owner", expectedOwnerID: "owner"))
    let context = context()
    let store = InterjectSuggestionFeedbackStore()
    let generationAuthority = AccountCutoverGenerationAuthority(
      generation: context.accountGeneration)
    let gate = SuspensionGate()

    let task = Task {
      await JITAmbientFeedbackActionRouter.record(
        .useful,
        context: context,
        authorizationSnapshot: authorization,
        currentAccountGeneration: context.accountGeneration,
        authorizationCurrent: { snapshot in
          authorizationAuthority.isCurrent(snapshot, ownerID: "owner")
        },
        recorder: { context, action, snapshot in
          await gate.suspend()
          _ = await InterjectSuggestionFeedbackMutation.record(
            evaluationID: context.suggestionIdentity.evaluationID,
            suggestionID: context.suggestionIdentity.suggestionID,
            verb: action.interjectVerb,
            provenance: context.provenance,
            store: store,
            emitAnalytics: false,
            authorizationSnapshot: snapshot,
            authorizationCurrent: { candidate in
              authorizationAuthority.isCurrent(candidate, ownerID: "owner")
            },
            accountGeneration: context.accountGeneration,
            accountGenerationCurrent: generationAuthority.isCurrent
          )
        }
      )
    }

    await gate.waitUntilEntered()
    generationAuthority.update(context.accountGeneration + 1)
    await gate.release()
    await task.value

    let record = await store.current(
      evaluationID: context.suggestionIdentity.evaluationID,
      suggestionID: context.suggestionIdentity.suggestionID
    )
    XCTAssertNil(record, "feedback from an older cutover generation must be rejected")
  }

  func testAmbientMutationRollsBackWhenAccountGenerationChangesAtTelemetrySeam() async throws {
    let authorizationAuthority = RuntimeOwnerAuthorizationAuthority()
    authorizationAuthority.endTransition(ownerID: "owner")
    let authorization = try XCTUnwrap(
      authorizationAuthority.capture(ownerID: "owner", expectedOwnerID: "owner"))
    let context = context()
    let store = InterjectSuggestionFeedbackStore()
    let generationAuthority = AccountCutoverGenerationAuthority(
      generation: context.accountGeneration)
    let generationCheck = LockedCounter()

    let didRecord = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: context.suggestionIdentity.evaluationID,
      suggestionID: context.suggestionIdentity.suggestionID,
      verb: .useful,
      provenance: context.provenance,
      store: store,
      authorizationSnapshot: authorization,
      authorizationCurrent: { snapshot in
        authorizationAuthority.isCurrent(snapshot, ownerID: "owner")
      },
      accountGeneration: context.accountGeneration,
      accountGenerationCurrent: { expectedGeneration in
        let check = generationCheck.increment()
        if check == 3 {
          generationAuthority.update(expectedGeneration + 1)
        }
        return generationAuthority.isCurrent(expectedGeneration)
      }
    )

    XCTAssertFalse(didRecord)
    let record = await store.current(
      evaluationID: context.suggestionIdentity.evaluationID,
      suggestionID: context.suggestionIdentity.suggestionID
    )
    XCTAssertNil(record, "a stale generation must not survive the telemetry recheck")
  }

  @MainActor
  func testAmbientSystemBannerRoundTripsOpaqueContext() throws {
    let context = context()
    let content = UNMutableNotificationContent()
    content.userInfo = NotificationService.jitAmbientFeedbackUserInfo(for: context)

    XCTAssertEqual(NotificationService.jitAmbientFeedbackContext(from: content.userInfo), context)
    XCTAssertEqual(
      NotificationService.openAction(
        assistantId: "context-director",
        title: "A useful reminder",
        jitAmbientFeedbackContext: context),
      .openJITDetail)
  }

  func testAmbientBannerGenerationFenceRejectsStaleControl() {
    XCTAssertTrue(NotificationService.jitFeedbackGenerationMatches(4, currentGeneration: 4))
    XCTAssertFalse(NotificationService.jitFeedbackGenerationMatches(4, currentGeneration: 5))
  }

  @MainActor
  func testAccountCutoverGenerationAuthorityTracksAuthoritativeControl() {
    let manager = AccountCutoverControlManager(
      fetchControl: { .legacyDefault },
      currentOwnerID: { "owner" })
    manager.resetForTesting()
    XCTAssertTrue(manager.generationAuthority.isCurrent(0))

    var control = AccountCutoverControl.legacyDefault
    control.accountGeneration = 4
    manager.apply(control)
    XCTAssertTrue(manager.generationAuthority.isCurrent(4))
    XCTAssertFalse(manager.generationAuthority.isCurrent(0))

    manager.resetForTesting()
    XCTAssertTrue(manager.generationAuthority.isCurrent(0))
  }
}
