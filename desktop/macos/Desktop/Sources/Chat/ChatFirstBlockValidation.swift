import Foundation

/// Wire-only adapter for the server-authoritative structured-block validator.
/// The server receives snake_case Pydantic contracts; the local journal keeps
/// the established camelCase `ChatContentBlockCodec` contract.
struct ChatFirstBlockValidationRequest: Encodable {
  let sourceSurface = "main_chat"
  let controlGeneration: Int
  let ownerFence: String
  let runID: String
  let attemptID: String
  let blocks: [OmiAnyCodable]

  enum CodingKeys: String, CodingKey {
    case sourceSurface = "source_surface"
    case controlGeneration = "control_generation"
    case ownerFence = "owner_fence"
    case runID = "run_id"
    case attemptID = "attempt_id"
    case blocks
  }
}

struct ChatFirstBlockValidationReceipt: Decodable {
  let accepted: Bool
  let code: String
  let blocks: [OmiAnyCodable]
}

enum ChatFirstBlockWire {
  static func backendBlocks(from input: [String: Any]) -> [[String: Any]]? {
    guard let blocks = input["blocks"] as? [[String: Any]], (1...8).contains(blocks.count) else {
      return nil
    }
    return blocks.compactMap(backendBlock)
  }

  static func journalBlocks(from receipt: ChatFirstBlockValidationReceipt) -> [[String: Any]]? {
    guard receipt.accepted, (1...8).contains(receipt.blocks.count) else { return nil }
    let blocks = receipt.blocks.compactMap { $0.value as? [String: Any] }.compactMap(journalBlock)
    return blocks.count == receipt.blocks.count ? blocks : nil
  }

  private static func backendBlock(_ block: [String: Any]) -> [String: Any]? {
    guard let type = block["type"] as? String else { return nil }
    switch type {
    case "questionCard":
      guard let questionID = block["questionId"] as? String,
        let text = block["text"] as? String,
        let subject = block["subject"] as? [String: Any],
        let kind = subject["kind"] as? String,
        let subjectID = subject["id"] as? String,
        let options = block["options"] as? [[String: Any]]
      else { return nil }
      let backendOptions = options.compactMap { option -> [String: Any]? in
        guard let optionID = option["optionId"] as? String,
          let label = option["label"] as? String,
          let preparedAnswer = option["preparedAnswer"] as? String
        else { return nil }
        var result: [String: Any] = [
          "option_id": optionID,
          "label": label,
          "prepared_answer": preparedAnswer,
        ]
        if let isDeferred = option["defer"] as? Bool { result["defer"] = isDeferred }
        return result
      }
      guard backendOptions.count == options.count else { return nil }
      return [
        "type": type,
        "question_id": questionID,
        "text": text,
        "subject": ["kind": kind, "id": subjectID],
        "options": backendOptions,
      ]
    case "taskCard":
      guard let taskID = block["taskId"] as? String else { return nil }
      return ["type": type, "task_id": taskID]
    case "goalLink":
      guard let goalID = block["goalId"] as? String, let summary = block["summary"] as? String else { return nil }
      return ["type": type, "goal_id": goalID, "summary": summary]
    case "captureLink":
      guard let conversationID = block["conversationId"] as? String, let summary = block["summary"] as? String else { return nil }
      var result: [String: Any] = ["type": type, "conversation_id": conversationID, "summary": summary]
      if let timestamp = block["momentTimestampMs"] as? Int { result["moment_timestamp_ms"] = timestamp }
      return result
    default:
      return nil
    }
  }

  private static func journalBlock(_ block: [String: Any]) -> [String: Any]? {
    guard let id = block["id"] as? String, let type = block["type"] as? String else { return nil }
    switch type {
    case "questionCard":
      guard let questionID = block["question_id"] as? String,
        let text = block["text"] as? String,
        let subject = block["subject"] as? [String: Any],
        let kind = subject["kind"] as? String,
        let subjectID = subject["id"] as? String,
        let options = block["options"] as? [[String: Any]]
      else { return nil }
      let journalOptions = options.compactMap { option -> [String: Any]? in
        guard let optionID = option["option_id"] as? String,
          let label = option["label"] as? String,
          let preparedAnswer = option["prepared_answer"] as? String
        else { return nil }
        var result: [String: Any] = [
          "optionId": optionID,
          "label": label,
          "preparedAnswer": preparedAnswer,
        ]
        if let isDeferred = option["defer"] as? Bool { result["defer"] = isDeferred }
        return result
      }
      guard journalOptions.count == options.count else { return nil }
      return [
        "type": type,
        "id": id,
        "questionId": questionID,
        "text": text,
        "subject": ["kind": kind, "id": subjectID],
        "options": journalOptions,
      ]
    case "taskCard":
      guard let taskID = block["task_id"] as? String else { return nil }
      return ["type": type, "id": id, "taskId": taskID]
    case "goalLink":
      guard let goalID = block["goal_id"] as? String, let summary = block["summary"] as? String else { return nil }
      return ["type": type, "id": id, "goalId": goalID, "summary": summary]
    case "captureLink":
      guard let conversationID = block["conversation_id"] as? String, let summary = block["summary"] as? String else { return nil }
      var result: [String: Any] = ["type": type, "id": id, "conversationId": conversationID, "summary": summary]
      if let timestamp = block["moment_timestamp_ms"] as? Int { result["momentTimestampMs"] = timestamp }
      return result
    default:
      return nil
    }
  }
}
