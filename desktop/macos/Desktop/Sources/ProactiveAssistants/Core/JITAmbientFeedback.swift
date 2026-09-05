import Foundation

/// Opaque provenance for an ambient JIT notification. Ambient work has no
/// standing trigger, so trigger identifiers and revisions are intentionally
/// absent. The reservation event and candidate remain the only join keys.
struct JITAmbientFeedbackContext: Equatable, Sendable {
  let ownerID: String
  let eventID: String
  let candidateID: String
  let accountGeneration: Int
  let suggestionIdentity: SuggestionAssistantTelemetry.NotificationIdentity

  init(
    ownerID: String,
    eventID: String,
    candidateID: String,
    accountGeneration: Int,
    suggestionIdentity: SuggestionAssistantTelemetry.NotificationIdentity =
      SuggestionAssistantTelemetry.NotificationIdentity(evaluationID: UUID(), suggestionID: UUID())
  ) {
    self.ownerID = ownerID
    self.eventID = eventID
    self.candidateID = candidateID
    self.accountGeneration = accountGeneration
    self.suggestionIdentity = suggestionIdentity
  }

  var isValid: Bool {
    !ownerID.isEmpty
      && JITProactivityReservation.isIdentifier(eventID)
      && JITProactivityReservation.isIdentifier(candidateID)
      && accountGeneration >= 0
  }

  var provenance: InterjectFeedbackProvenance {
    InterjectFeedbackProvenance(
      lane: JITProactivityLane.ambient.rawValue,
      ownerID: ownerID,
      deliveryID: eventID,
      candidateID: candidateID,
      accountGeneration: accountGeneration
    )
  }
}

/// Ambient cards intentionally expose only teach-rate actions. Trigger
/// snooze/disable/missed semantics belong to planned rows and must never be
/// fabricated for a context that has no standing trigger.
enum JITAmbientFeedbackActionRouter {
  static let visibleActions: [JITTriggerFeedbackAction] = [.useful, .falsePositive]

  typealias Record =
    @Sendable (
      JITAmbientFeedbackContext,
      JITTriggerFeedbackAction,
      RuntimeOwnerAuthorizationSnapshot
    ) async -> Void

  static func record(
    _ action: JITTriggerFeedbackAction,
    context: JITAmbientFeedbackContext,
    authorizationSnapshot: RuntimeOwnerAuthorizationSnapshot,
    currentAccountGeneration: Int,
    authorizationCurrent: @escaping @Sendable (RuntimeOwnerAuthorizationSnapshot) -> Bool =
      RuntimeOwnerIdentity.isAuthorizationCurrent,
    recorder: Record? = nil
  ) async {
    guard context.isValid,
      context.ownerID == authorizationSnapshot.ownerID,
      context.accountGeneration == currentAccountGeneration,
      authorizationCurrent(authorizationSnapshot),
      visibleActions.contains(action)
    else { return }
    if let recorder {
      await recorder(context, action, authorizationSnapshot)
      return
    }

    let generationMatches = await MainActor.run {
      guard authorizationCurrent(authorizationSnapshot) else { return false }
      return AccountCutoverControlManager.shared.control.accountGeneration == context.accountGeneration
    }
    guard generationMatches else { return }
    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: context.suggestionIdentity.evaluationID,
      suggestionID: context.suggestionIdentity.suggestionID,
      verb: action.interjectVerb,
      provenance: context.provenance,
      authorizationSnapshot: authorizationSnapshot,
      authorizationCurrent: authorizationCurrent
    )
  }
}
