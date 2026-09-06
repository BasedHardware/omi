import Foundation

/// Joins context visits to the default-off JIT authority. Returning `false`
/// means the rollout contract explicitly selected the released legacy path;
/// every enabled/unknown-new-lane outcome is fully consumed here.
actor JITProactivityCoordinator {
  static let shared = JITProactivityCoordinator()

  func handle(
    fence: ContextVisitFence,
    snapshot: ContextBucketSnapshot,
    frame: CapturedFrame,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot
  ) async -> Bool {
    // The observation is built behind the rollout gate, never in front of it. The calendar leg
    // queries EventKit, and this runs on every context visit — a default-off install must not
    // pay for (or prompt for) calendar access to reach a decision that ignores the observation.
    let decision = await JITProactivityRuntime.shared.admission(
      authorizationSnapshot: authorizationSnapshot,
      ambient: JITAmbientRuntimeContext(
        id: snapshot.bucketID,
        semanticFingerprint: JITAmbientRuntimeContext.semanticFingerprint(
          contextID: snapshot.bucketID, validatedFacts: snapshot.validatedFacts),
        locallyRelevant: snapshot.notifyWorthiness > 0,
        boundedEvidence: snapshot.validatedFacts.prefix(20).map { String($0.prefix(400)) }
          .joined(separator: "\n")),
      observationProvider: {
        let calendarEvents = await SystemCalendarMeetingContextService.shared
          .authorizedTriggerEvents(around: frame.captureTime)
        return KnowledgeLedgerTriggerObservation(
          eventID: frame.screenshotId.map(String.init),
          text: snapshot.validatedFacts.joined(separator: "\n"),
          appName: frame.appName,
          windowTitle: frame.windowTitle,
          occurredAt: frame.captureTime,
          calendarEvents: calendarEvents)
      })
    switch decision {
    case .legacyContextBucketFallback(let reason):
      await MainActor.run {
        JITProactivityLaneState.update(ownerID: authorizationSnapshot.ownerID, active: false)
      }
      await ContextProactivityTelemetry.recordJITAdmission(outcome: "legacy_fallback", reason: reason)
      return false
    case .suppressed(let reason):
      await MainActor.run {
        JITProactivityLaneState.update(ownerID: authorizationSnapshot.ownerID, active: true)
      }
      await ContextProactivityTelemetry.recordJITAdmission(outcome: "suppressed", reason: reason)
      return true
    case .deliver(_, _, let continuityKey):
      await MainActor.run {
        JITProactivityLaneState.update(ownerID: authorizationSnapshot.ownerID, active: true)
      }
      guard
        let execution = await JITProactivityRuntime.shared.takeExecution(continuityKey: continuityKey)
      else {
        await ContextProactivityTelemetry.recordJITAdmission(
          outcome: "suppressed", reason: "jit_execution_missing")
        return true
      }
      await JITProactivityDelivery.shared.deliver(
        execution: execution, fence: fence, snapshot: snapshot, currentFrame: frame,
        authorizationSnapshot: authorizationSnapshot)
      return true
    }
  }
}
