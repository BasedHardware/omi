import Foundation

extension APIClient {
  func prepareSummaryTask(
    _ selected: OmiAPI.SummaryTaskReference,
    idempotencyKey: String,
    accountGeneration: Int,
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.CandidateRecord {
    try await taskIntelligenceMutation(
      endpoint: "v1/candidates/from-conversation", method: "POST", body: selected,
      idempotencyKey: idempotencyKey, accountGeneration: accountGeneration,
      expectedOwnerId: authorization.ownerID, authorizationSnapshot: authorization)
  }

  func acceptSummaryTask(
    candidateID: String,
    selected: OmiAPI.SummaryTaskReference,
    accountGeneration: Int,
    authorization: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> OmiAPI.CandidateResolutionReceipt {
    try await taskIntelligenceMutation(
      endpoint: "v1/candidates/\(candidateID)/accept", method: "POST",
      body: OmiAPI.CandidateAcceptanceRequest(summaryItem: selected),
      idempotencyKey: nil, accountGeneration: accountGeneration,
      expectedOwnerId: authorization.ownerID, authorizationSnapshot: authorization)
  }
}
