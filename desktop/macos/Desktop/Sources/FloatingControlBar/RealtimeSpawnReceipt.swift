import Foundation

/// Kernel-authored proof that a successful realtime `spawn_agent` invocation
/// already materialized the producing voice exchange in the canonical journal.
/// The receipt is accepted only when both stable turn IDs match the local
/// continuity-key derivation; provider text can never substitute for it.
struct RealtimeSpawnJournalReceipt: Equatable {
  /// Canonical child identities returned alongside the kernel-owned journal
  /// receipt. These let the realtime surface create the same immediate pill
  /// projection as typed chat, rather than waiting for a later reconciliation
  /// pass to discover an already-accepted background run.
  struct PillProjection: Equatable {
    let pillID: UUID
    let sessionID: String
    let runID: String
    let attemptID: String?
    let provider: String?
    let title: String
    let objective: String
  }

  let continuityKey: String
  let userTurnID: String
  let assistantTurnID: String
  let assistantText: String
  let pillProjection: PillProjection?

  static func parse(
    output: String,
    expectedContinuityKey: String
  ) -> RealtimeSpawnJournalReceipt? {
    guard !expectedContinuityKey.isEmpty,
      let data = output.data(using: .utf8),
      let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      payload["schemaVersion"] as? Int == 1,
      payload["ok"] as? Bool == true,
      let raw = payload["journalReceipt"] as? [String: Any],
      raw["accepted"] as? Bool == true,
      let continuityKey = raw["continuityKey"] as? String,
      continuityKey == expectedContinuityKey,
      let userTurnID = raw["userTurnId"] as? String,
      userTurnID
        == KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "user"),
      let assistantTurnID = raw["assistantTurnId"] as? String,
      assistantTurnID
        == KernelTurnProjection.stableTurnID(
          continuityKey: continuityKey, role: "assistant"),
      let rawAssistantText = raw["assistantText"] as? String,
      let child = canonicalChild(in: payload)
    else { return nil }
    let assistantText = rawAssistantText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !assistantText.isEmpty, assistantText.utf8.count <= 4_096 else { return nil }
    return RealtimeSpawnJournalReceipt(
      continuityKey: continuityKey,
      userTurnID: userTurnID,
      assistantTurnID: assistantTurnID,
      assistantText: assistantText,
      pillProjection: pillProjection(in: child))
  }

  /// The kernel attaches the journal receipt only after the agent-control
  /// invocation has accepted its child run. Parse the child from that same
  /// result; never derive identities from the provider's tool arguments.
  /// The external surface returns one compact semantic child. The provider
  /// mirror must describe that exact child and carry the same digest; accepting
  /// only a journal receipt would let a missing/failed launch masquerade as a
  /// successful voice delegation.
  private static func canonicalChild(in payload: [String: Any]) -> [String: Any]? {
    guard let child = payload["child"] as? [String: Any],
      let providerResult = payload["providerResult"] as? [String: Any],
      providerResult["schemaVersion"] as? Int == 1,
      providerResult["ok"] is Bool,
      let providerChild = providerResult["child"] as? [String: Any],
      let digest = text(payload["semanticDigest"]),
      text(providerResult["semanticDigest"]) == digest,
      let lifecycle = child["lifecycle"] as? [String: Any],
      let sessionID = text(child["sessionId"]),
      let runID = text(child["runId"]),
      let attemptID = text(child["attemptId"]),
      text(child["title"]) != nil,
      text(child["objective"]) != nil,
      let provider = text(child["provider"]),
      let state = text(lifecycle["state"]),
      let attemptState = text(lifecycle["attemptState"]),
      let adapterID = text(lifecycle["adapterId"]),
      lifecycle["revision"] as? Int != nil,
      lifecycle["updatedAtMs"] as? NSNumber != nil,
      text(providerChild["sessionId"]) == sessionID,
      text(providerChild["runId"]) == runID,
      text(providerChild["attemptId"]) == attemptID,
      text(providerChild["state"]) == state,
      text(providerChild["attemptState"]) == attemptState,
      text(providerChild["adapterId"]) == adapterID,
      text(providerResult["code"]) != nil,
      text(providerResult["message"]) != nil,
      provider == adapterID
    else { return nil }
    return child
  }

  private static func text(_ value: Any?) -> String? {
    guard let raw = value as? String else { return nil }
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? nil : trimmed
  }

  private static func pillProjection(in child: [String: Any]) -> PillProjection? {
    guard let pillID = text(child["pillId"]).flatMap(UUID.init(uuidString:)),
      let sessionID = text(child["sessionId"]),
      let runID = text(child["runId"])
    else { return nil }
    return PillProjection(
      pillID: pillID,
      sessionID: sessionID,
      runID: runID,
      attemptID: text(child["attemptId"]),
      provider: text(child["provider"]),
      title: text(child["title"]) ?? "Background agent",
      objective: text(child["objective"]) ?? "Background agent")
  }
}

/// Grants at most one open-turn continuation after a failed `spawn_agent` so
/// the realtime model can relay setup instructions or retry with a different
/// installed agent in the same turn. The second failure in a turn terminates
/// it, so a looping model can never spin on spawn retries. Tracks the failed
/// provider so a successful same-turn retry can emit fallback telemetry.
struct RealtimeSpawnFailureContinuationPolicy {
  private var continuedTurnIDs: Set<UUID> = []
  private var lastFailedProviderByTurnID: [UUID: String] = [:]

  /// Returns true when this turn may stay open after the failure (first
  /// spawn failure of the turn); false when it must terminate (repeat).
  mutating func beginContinuationIfAllowed(turnID: UUID, failedProvider: String?) -> Bool {
    if continuedTurnIDs.count > 16 {
      continuedTurnIDs.removeAll()
      lastFailedProviderByTurnID.removeAll()
    }
    guard !continuedTurnIDs.contains(turnID) else { return false }
    continuedTurnIDs.insert(turnID)
    if let failedProvider {
      lastFailedProviderByTurnID[turnID] = failedProvider
    }
    return true
  }

  /// Consumes and returns the provider whose spawn failed earlier in this
  /// turn, if a continuation was granted — the "from" side of a fallback.
  mutating func takeFailedProvider(turnID: UUID) -> String? {
    lastFailedProviderByTurnID.removeValue(forKey: turnID)
  }
}

/// A realtime provider may receive a transport-level success for a control
/// tool whose semantic result is still a rejection (`{"ok":false,...}`).  A
/// spawn is accepted only when the kernel returns its canonical journal
/// receipt.  Keeping this distinction typed prevents the voice parent from
/// being persisted as successful when no child agent was actually created.
enum RealtimeSpawnAgentToolOutcome: Equatable {
  case accepted(RealtimeSpawnJournalReceipt)
  case setupNeeded(AgentPillsManager.DirectedProvider)
  case rejected

  static func classify(output: String, expectedContinuityKey: String) -> Self {
    if let receipt = RealtimeSpawnJournalReceipt.parse(
      output: output,
      expectedContinuityKey: expectedContinuityKey)
    {
      return .accepted(receipt)
    }
    guard
      let data = output.data(using: .utf8),
      let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let error = payload["error"] as? [String: Any],
      error["code"] as? String == "provider_setup_needed",
      let rawProvider = error["provider"] as? String,
      let provider = AgentPillsManager.DirectedProvider(rawValue: rawProvider)
    else {
      return .rejected
    }
    return .setupNeeded(provider)
  }
}
