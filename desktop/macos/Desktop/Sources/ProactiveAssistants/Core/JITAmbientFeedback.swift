import CryptoKit
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
    suggestionIdentity: SuggestionAssistantTelemetry.NotificationIdentity? = nil
  ) {
    self.ownerID = ownerID
    self.eventID = eventID
    self.candidateID = candidateID
    self.accountGeneration = accountGeneration
    self.suggestionIdentity =
      suggestionIdentity
      ?? Self.stableSuggestionIdentity(
        ownerID: ownerID,
        eventID: eventID,
        candidateID: candidateID,
        accountGeneration: accountGeneration)
  }

  /// Ambient candidates do not have the suggestion assistant's evaluation
  /// object to supply an identity. Derive the pair from the admitted delivery
  /// provenance so retries and a system-banner round trip refer to the same
  /// feedback row instead of minting a fresh random pair.
  private static func stableSuggestionIdentity(
    ownerID: String,
    eventID: String,
    candidateID: String,
    accountGeneration: Int
  ) -> SuggestionAssistantTelemetry.NotificationIdentity {
    let seed = "\(ownerID)\u{1f}\(eventID)\u{1f}\(candidateID)\u{1f}\(accountGeneration)"
    return SuggestionAssistantTelemetry.NotificationIdentity(
      evaluationID: deterministicUUID("evaluation\u{1f}\(seed)"),
      suggestionID: deterministicUUID("suggestion\u{1f}\(seed)"))
  }

  private static func deterministicUUID(_ seed: String) -> UUID {
    let digest = SHA256.hash(data: Data(seed.utf8))
    let hex = digest.map { String(format: "%02x", $0) }.joined()
    let characters = Array(hex)
    let uuidString = [
      String(characters[0..<8]),
      String(characters[8..<12]),
      String(characters[12..<16]),
      String(characters[16..<20]),
      String(characters[20..<32]),
    ].joined(separator: "-")
    return UUID(uuidString: uuidString)!
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

    let generationAuthority = await MainActor.run {
      AccountCutoverControlManager.shared.generationAuthority
    }
    let generationMatches = await MainActor.run {
      guard authorizationCurrent(authorizationSnapshot) else { return false }
      return generationAuthority.isCurrent(context.accountGeneration)
    }
    guard generationMatches else { return }
    _ = await InterjectSuggestionFeedbackMutation.record(
      evaluationID: context.suggestionIdentity.evaluationID,
      suggestionID: context.suggestionIdentity.suggestionID,
      verb: action.interjectVerb,
      provenance: context.provenance,
      authorizationSnapshot: authorizationSnapshot,
      authorizationCurrent: authorizationCurrent,
      accountGeneration: context.accountGeneration,
      accountGenerationCurrent: generationAuthority.isCurrent
    )
  }
}
