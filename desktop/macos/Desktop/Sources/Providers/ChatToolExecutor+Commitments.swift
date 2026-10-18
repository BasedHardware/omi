import Foundation

/// `get_commitments`: what the signed-in person promised other people, read from
/// `GET /v1/tools/commitments`. The backend does the join (task, source conversation,
/// who was speaking), so no transcript reaches the Mac. Read-only: nothing here
/// creates, edits or completes a task.
extension ChatToolExecutor {
  static let commitmentsDefaultLimitPeople = 10
  static let commitmentsMaxLimitPeople = 20
  nonisolated static let commitmentsMaxPersonCharacters = 120

  typealias CommitmentsFetch =
    @Sendable (_ since: String?, _ person: String?, _ limitPeople: Int) async throws ->
    APIClient.CommitmentsToolResponse

  static func executeGetCommitments(
    _ arguments: [String: Any],
    runID: String?,
    attemptID: String?,
    expectedOwnerID: String?,
    api: APIClient
  ) async -> String {
    await executeGetCommitments(
      arguments,
      runID: runID,
      attemptID: attemptID,
      expectedOwnerID: expectedOwnerID,
      fetch: { since, person, limitPeople in
        try await api.toolGetCommitments(
          since: since,
          person: person,
          limitPeople: limitPeople,
          expectedOwnerId: expectedOwnerID,
          authorizationSnapshot: currentOwnerAuthorizationSnapshot)
      })
  }

  static func executeGetCommitments(
    _ arguments: [String: Any],
    runID: String?,
    attemptID: String?,
    expectedOwnerID: String?,
    ownerIsCurrent: (String?) -> Bool = { isExpectedOwnerCurrent($0) },
    fetch: CommitmentsFetch
  ) async -> String {
    var since: String?
    if let raw = arguments["since"] as? String,
      !raw.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    {
      let validated = validateISODate(raw, paramName: "since")
      if let error = validated.error {
        return toolFailureEnvelope(code: "invalid_argument", message: error)
      }
      since = validated.valid
    }
    let person = (arguments["person"] as? String)
      .map { boundedPersonFilter($0.trimmingCharacters(in: .whitespacesAndNewlines)) }
      .flatMap { $0.isEmpty ? nil : $0 }
    let requestedLimit = (arguments["limit_people"] as? NSNumber)?.intValue ?? commitmentsDefaultLimitPeople
    let limitPeople = min(max(requestedLimit, 1), commitmentsMaxLimitPeople)

    let response: APIClient.CommitmentsToolResponse
    do {
      response = try await fetch(since, person, limitPeople)
    } catch APIError.httpError(statusCode: 404, _) {
      // A Mac build can ship before the backend route is deployed.
      return toolFailureEnvelope(
        code: "commitments_unavailable",
        message: "This Omi server cannot list commitments yet. Use get_action_items for the task list.")
    } catch {
      // Type only, and a fixed message: transport errors can carry server text.
      log("get_commitments: backend error \(type(of: error))")
      return toolFailureEnvelope(
        code: "backend_tool_unreachable",
        message: "Omi could not reach the server to list commitments. Try again in a moment.")
    }
    guard ownerIsCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    if response.isError {
      return toolFailureEnvelope(code: "backend_tool_failed", message: response.resultText)
    }

    let references = await ChatCitationProvenanceRegistry.shared.register(
      response.sources ?? [], runID: runID, attemptID: attemptID)
    guard ownerIsCurrent(expectedOwnerID) else { return authorizedOwnerChangedResult() }
    log(
      "get_commitments: people=\(response.groups.count) unattributed=\(response.unattributed.count) truncated=\(response.truncated)"
    )
    return commitmentsToolResult(response, references: references)
  }

  /// The backend counts `max_length` in code points (Python `str`), so cut on Unicode
  /// scalars; a grapheme-cluster cut can still be too long for names with combining marks.
  nonisolated static func boundedPersonFilter(_ value: String) -> String {
    var scalars = String.UnicodeScalarView()
    scalars.append(contentsOf: value.unicodeScalars.prefix(commitmentsMaxPersonCharacters))
    return String(scalars)
  }

  /// Flat, per-commitment items keep each one small enough for the result projector's
  /// per-item budget; `people` carries the per-person counts the answer is grouped by.
  nonisolated static func commitmentsToolResult(
    _ response: APIClient.CommitmentsToolResponse,
    references: [ChatCitationReference]
  ) -> String {
    var markers: [String: String] = [:]
    for reference in references where reference.kind == .conversation && markers[reference.sourceID] == nil {
      markers[reference.sourceID] = "[\(reference.ordinal)]"
    }

    func item(_ commitment: APIClient.Commitment) -> [String: Any] {
      var item: [String: Any] = [
        "taskId": commitment.taskID,
        "title": commitment.description,
        "basis": commitment.attribution.basis,
        "likely": commitment.attribution.likely ?? false,
        "partialMatch": commitment.partialMatch ?? false,
        "conversationId": commitment.conversationID,
      ]
      if !commitment.attribution.names.isEmpty {
        item["person"] = commitment.attribution.names.joined(separator: ", ")
      }
      if let value = commitment.dueAt { item["dueAt"] = value }
      if let value = commitment.dueCertainty { item["dueCertainty"] = value }
      if let value = commitment.createdAt { item["createdAt"] = value }
      if let value = commitment.conversationTitle { item["conversationTitle"] = value }
      if let value = commitment.excerpt { item["excerpt"] = value }
      if let value = commitment.context { item["context"] = value }
      if let marker = markers[commitment.conversationID] { item["citationMarker"] = marker }
      return item
    }

    let people: [[String: Any]] = response.groups.map { group in
      [
        "person": group.names.joined(separator: ", "),
        "basis": group.basis,
        "likely": group.likely ?? false,
        "partialMatch": group.partialMatch ?? false,
        "openCount": group.openCount,
        "shown": group.commitments.count,
      ]
    }
    let commitments = response.groups.flatMap { $0.commitments.map(item) }
    let unattributed = response.unattributed.map(item)
    let totals = response.totals
    return typedReadToolResult(
      toolName: "get_commitments",
      sections: [
        ["name": "window", "total": 1, "items": [["since": response.since ?? "unknown"]]],
        ["name": "people", "total": max(totals.people, people.count), "items": people],
        ["name": "commitments", "total": max(totals.commitments, commitments.count), "items": commitments],
        ["name": "unattributed", "total": max(totals.unattributed, unattributed.count), "items": unattributed],
      ],
      totals: [
        "people": totals.people,
        "commitments": totals.commitments,
        "unattributed": totals.unattributed,
        "excludedUnknownOwner": totals.excludedUnknownOwner,
        "notChecked": totals.notChecked,
        "truncated": response.truncated ? 1 : 0,
      ])
  }
}
