import Foundation

/// Physical transport for the T08 kernel-owned deferral outbox. It deliberately
/// has no relationship to desktop message reconciliation: the backend receiver
/// persists task-intelligence state only and never writes a Chat row.
struct ChatFirstDeferralDeliveryRequest: Sendable, Equatable {
  struct Subject: Codable, Sendable, Equatable {
    let kind: String
    let id: String
  }

  struct Option: Codable, Sendable, Equatable {
    let optionID: String
    let label: String
    let preparedAnswer: String
    let isDeferred: Bool

    enum CodingKeys: String, CodingKey {
      case optionID = "option_id"
      case label
      case preparedAnswer = "prepared_answer"
      case isDeferred = "defer"
    }
  }

  struct Question: Codable, Sendable, Equatable {
    let questionID: String
    let text: String
    let subject: Subject
    let options: [Option]

    enum CodingKeys: String, CodingKey {
      case questionID = "question_id"
      case text, subject, options
    }
  }

  let ownerID: String
  let continuityKey: String
  let controlGeneration: Int
  let subject: Subject
  let question: Question
  let attemptCount: Int
  let deliveryGeneration: Int
  let payloadHash: String

  init?(payload: [String: Any]) {
    guard
      let ownerID = payload["ownerId"] as? String, !ownerID.isEmpty,
      let continuityKey = payload["continuityKey"] as? String, !continuityKey.isEmpty,
      let controlGeneration = payload["controlGeneration"] as? Int, controlGeneration >= 0,
      let subjectPayload = payload["subject"] as? [String: Any],
      let subjectKind = subjectPayload["kind"] as? String,
      ["task", "goal", "capture"].contains(subjectKind),
      let subjectID = subjectPayload["id"] as? String, !subjectID.isEmpty,
      let questionPayload = payload["question"] as? [String: Any],
      let questionID = questionPayload["questionId"] as? String, !questionID.isEmpty,
      let questionText = questionPayload["text"] as? String,
      !questionText.isEmpty, questionText.count <= 300,
      let questionSubject = questionPayload["subject"] as? [String: Any],
      let questionSubjectKind = questionSubject["kind"] as? String,
      questionSubjectKind == subjectKind,
      let questionSubjectID = questionSubject["id"] as? String,
      questionSubjectID == subjectID,
      let optionsPayload = questionPayload["options"] as? [[String: Any]],
      (1...4).contains(optionsPayload.count),
      let attemptCount = payload["attemptCount"] as? Int, attemptCount > 0,
      let deliveryGeneration = payload["deliveryGeneration"] as? Int, deliveryGeneration > 0,
      let payloadHash = payload["payloadHash"] as? String, !payloadHash.isEmpty
    else { return nil }

    let options = optionsPayload.compactMap { option -> Option? in
      guard
        let optionID = option["optionId"] as? String, !optionID.isEmpty,
        let label = option["label"] as? String, !label.isEmpty, label.count <= 80,
        let preparedAnswer = option["preparedAnswer"] as? String,
        !preparedAnswer.isEmpty, preparedAnswer.count <= 500
      else { return nil }
      return Option(
        optionID: optionID,
        label: label,
        preparedAnswer: preparedAnswer,
        isDeferred: option["defer"] as? Bool ?? false
      )
    }
    guard options.count == optionsPayload.count,
          Set(options.map(\.optionID)).count == options.count,
          options.filter(\.isDeferred).count <= 1
    else { return nil }

    self.ownerID = ownerID
    self.continuityKey = continuityKey
    self.controlGeneration = controlGeneration
    self.subject = Subject(kind: subjectKind, id: subjectID)
    self.question = Question(
      questionID: questionID,
      text: questionText,
      subject: Subject(kind: questionSubjectKind, id: questionSubjectID),
      options: options
    )
    self.attemptCount = attemptCount
    self.deliveryGeneration = deliveryGeneration
    self.payloadHash = payloadHash
  }
}

private struct ChatFirstDeferralCreateBody: Encodable {
  let sourceSurface: String = "main_chat"
  let controlGeneration: Int
  let ownerFence: String
  let continuityKey: String
  let subject: ChatFirstDeferralDeliveryRequest.Subject
  let question: ChatFirstDeferralDeliveryRequest.Question

  enum CodingKeys: String, CodingKey {
    case sourceSurface = "source_surface"
    case controlGeneration = "control_generation"
    case ownerFence = "owner_fence"
    case continuityKey = "continuity_key"
    case subject, question
  }
}

private struct ChatFirstDeferralReceipt: Decodable {
  let deferralID: String

  enum CodingKeys: String, CodingKey {
    case deferralID = "deferral_id"
  }
}

extension APIClient {
  func recordChatFirstDeferral(
    _ request: ChatFirstDeferralDeliveryRequest
  ) async throws {
    let body = ChatFirstDeferralCreateBody(
      controlGeneration: request.controlGeneration,
      ownerFence: request.ownerID,
      continuityKey: request.continuityKey,
      subject: request.subject,
      question: request.question
    )
    let receipt: ChatFirstDeferralReceipt = try await post(
      "v1/chat/deferrals",
      body: body,
      expectedOwnerId: request.ownerID
    )
    guard !receipt.deferralID.isEmpty else { throw APIError.invalidResponse }
  }
}

extension AgentRuntimeProcess {
  nonisolated static func boundedChatFirstDeferralErrorCode(for error: Error) -> String {
    if let authError = error as? AuthError, case .userChangedDuringRequest = authError {
      return "chat_first_deferral_owner_changed"
    }
    if case let APIError.httpError(statusCode, _) = error {
      return [408, 425, 429].contains(statusCode) || (500...599).contains(statusCode)
        ? "chat_first_deferral_retryable"
        : "chat_first_deferral_4xx"
    }
    return "chat_first_deferral_failed"
  }
}
