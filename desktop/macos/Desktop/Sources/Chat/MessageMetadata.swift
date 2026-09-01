import Foundation

/// Local-only evidence for one completed assistant turn.
///
/// Response Context only shows facts this client observed: tools and SQL on
/// the turn, whether a screenshot was attached, and the kernel snapshot
/// admitted at send. Token, cache, and cost numbers are not displayed —
/// the managed chat path defaults missing usage to zero and may estimate
/// tokens from prompt length.
struct MessageMetadata: Equatable {
  struct SourceOutcome: Equatable, Identifiable {
    var id: String { source }
    let source: String
    let outcome: String
  }

  var hasScreenshot: Bool
  var screenshotSizeBytes: Int?
  var toolNames: [String]
  var sqlRowsReturned: Int
  var sqlQueryCount: Int
  var sourceOutcomes: [SourceOutcome]
  var retainedTurnCount: Int
  var totalTurnCount: Int
  var omittedTurnCount: Int
  var offeredToolCount: Int
  var adapterId: String
  var credentialScopeLabel: String
  /// Served model identities observed on this turn's completions — captured
  /// from the provider RESPONSE stream (e.g. the gateway lane's resolved
  /// upstream model), never assumed from the request. Empty = unobserved.
  var modelsUsed: [String]
  /// What was on the user's screen when this turn was asked, as text (the voice hub's accepted
  /// screen observation, bounded). Journaled on the user row so later turns can answer "do you
  /// remember what I was reading?" from conversation history even when Rewind has no frame yet.
  var screenContext: String?

  init(
    hasScreenshot: Bool = false,
    screenshotSizeBytes: Int? = nil,
    toolNames: [String] = [],
    sqlRowsReturned: Int = 0,
    sqlQueryCount: Int = 0,
    sourceOutcomes: [SourceOutcome] = [],
    retainedTurnCount: Int = 0,
    totalTurnCount: Int = 0,
    omittedTurnCount: Int = 0,
    offeredToolCount: Int = 0,
    adapterId: String = "",
    credentialScopeLabel: String = "",
    modelsUsed: [String] = [],
    screenContext: String? = nil
  ) {
    self.hasScreenshot = hasScreenshot
    self.screenshotSizeBytes = screenshotSizeBytes
    self.toolNames = toolNames
    self.sqlRowsReturned = sqlRowsReturned
    self.sqlQueryCount = sqlQueryCount
    self.sourceOutcomes = sourceOutcomes
    self.retainedTurnCount = retainedTurnCount
    self.totalTurnCount = totalTurnCount
    self.omittedTurnCount = omittedTurnCount
    self.offeredToolCount = offeredToolCount
    self.adapterId = adapterId
    self.credentialScopeLabel = credentialScopeLabel
    self.modelsUsed = modelsUsed
    self.screenContext = screenContext
  }

  static func fromCompletedTurn(
    snapshot: AgentContextSnapshot,
    profile: AgentExecutionProfile,
    imageByteCount: Int?,
    toolNames: [String],
    sqlRowsReturned: Int,
    sqlQueryCount: Int,
    modelsUsed: [String] = []
  ) -> MessageMetadata {
    let allowedToolNames = snapshot.capabilities["allowedToolNames"] as? [String] ?? []
    return MessageMetadata(
      hasScreenshot: imageByteCount != nil,
      screenshotSizeBytes: imageByteCount,
      toolNames: toolNames,
      sqlRowsReturned: sqlRowsReturned,
      sqlQueryCount: sqlQueryCount,
      sourceOutcomes: admittedSources(from: snapshot),
      retainedTurnCount: snapshot.contextPlan.retainedTurnCount,
      totalTurnCount: snapshot.contextPlan.totalTurnCount,
      omittedTurnCount: snapshot.contextPlan.omittedTurnCount,
      offeredToolCount: allowedToolNames.count,
      adapterId: profile.adapterId,
      credentialScopeLabel: Self.credentialLabel(profile.credentialScope),
      modelsUsed: modelsUsed
    )
  }

  var screenshotSummary: String {
    guard hasScreenshot, let size = screenshotSizeBytes else { return "None" }
    return "1 image (\(max(size, 0) / 1024) KB)"
  }

  var historySummary: String {
    if totalTurnCount == 0 {
      return "none"
    }
    if omittedTurnCount > 0 {
      return "\(retainedTurnCount) of \(totalTurnCount) turns (\(omittedTurnCount) omitted)"
    }
    return "\(retainedTurnCount) of \(totalTurnCount) turns"
  }

  var offeredToolsSummary: String {
    offeredToolCount == 1 ? "1 tool" : "\(offeredToolCount) tools"
  }

  /// "Model" row: the observed served identities, comma-joined. Empty string
  /// = none observed (the row is hidden rather than guessed).
  var modelsSummary: String {
    modelsUsed.joined(separator: ", ")
  }

  var pathSummary: String {
    [adapterId, credentialScopeLabel].filter { !$0.isEmpty }.joined(separator: " · ")
  }

  var sqlSummary: String? {
    guard sqlQueryCount > 0 else { return nil }
    let queryWord = sqlQueryCount == 1 ? "query" : "queries"
    let rowWord = sqlRowsReturned == 1 ? "row" : "rows"
    return "\(sqlQueryCount) \(queryWord) · \(sqlRowsReturned) \(rowWord)"
  }

  private static func admittedSources(from snapshot: AgentContextSnapshot) -> [SourceOutcome] {
    AgentContextSource.allCases.compactMap { source in
      guard
        let row = snapshot.sourceOutcomes.first(where: { $0["source"] as? String == source.rawValue }),
        let outcome = row["outcome"] as? String, !outcome.isEmpty
      else { return nil }
      return SourceOutcome(source: source.rawValue, outcome: outcome)
    }
  }

  private static func credentialLabel(_ scope: AgentExecutionProfile.CredentialScope) -> String {
    switch scope {
    case .managedCloud: return "managed"
    case .localUser: return "BYOK"
    }
  }
}
