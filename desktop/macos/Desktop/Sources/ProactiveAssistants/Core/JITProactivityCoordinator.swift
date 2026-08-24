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
    let observation = KnowledgeLedgerTriggerObservation(
      eventID: frame.screenshotId.map(String.init),
      text: snapshot.validatedFacts.joined(separator: "\n"),
      appName: frame.appName,
      windowTitle: frame.windowTitle,
      occurredAt: frame.captureTime)
    let decision = await JITProactivityRuntime.shared.admission(
      authorizationSnapshot: authorizationSnapshot,
      observation: observation,
      ambient: JITAmbientRuntimeContext(
        id: snapshot.bucketID,
        semanticFingerprint: JITAmbientRuntimeContext.semanticFingerprint(
          contextID: snapshot.bucketID, validatedFacts: snapshot.validatedFacts),
        locallyRelevant: snapshot.notifyWorthiness > 0,
        boundedEvidence: snapshot.validatedFacts.prefix(20).map { String($0.prefix(400)) }
          .joined(separator: "\n")))
    switch decision {
    case .legacyContextBucketFallback(let reason):
      await ContextProactivityTelemetry.recordJITAdmission(outcome: "legacy_fallback", reason: reason)
      return false
    case .suppressed(let reason):
      await ContextProactivityTelemetry.recordJITAdmission(outcome: "suppressed", reason: reason)
      return true
    case .deliver(_, _, let continuityKey):
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
