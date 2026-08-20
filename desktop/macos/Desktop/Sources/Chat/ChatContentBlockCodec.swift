import Foundation

/// Shared encode/decode for structured chat content blocks.
/// Used by task-chat local SQLite and main-chat `saveMessage` metadata so
/// `agentSpawn` / `agentCompletion` survive reload (INV-6 rule 4).
enum ChatContentBlockCodec {
  static let messageMetadataKey = "content_blocks"

  static func encode(_ blocks: [ChatContentBlock]) -> String? {
    guard !blocks.isEmpty else { return nil }
    let encoded = encodeArray(blocks)
    guard !encoded.isEmpty,
      let data = try? JSONSerialization.data(withJSONObject: encoded),
      let json = String(data: data, encoding: .utf8)
    else { return nil }
    return json
  }

  static func encodeArray(_ blocks: [ChatContentBlock]) -> [[String: Any]] {
    blocks.map(persistenceDictionary(for:)).filter { JSONSerialization.isValidJSONObject($0) }
  }

  /// Stable, in-process representation used to compare every persisted
  /// journal-owned field without emitting any block content to telemetry.
  static func comparisonData(_ blocks: [ChatContentBlock]) -> Data? {
    try? JSONSerialization.data(
      withJSONObject: blocks.map(persistenceDictionary(for:)),
      options: [.sortedKeys])
  }

  static func decode(_ json: String) -> [ChatContentBlock]? {
    guard let data = json.data(using: .utf8),
      let array = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return nil }
    return decode(array)
  }

  static func decode(_ array: [[String: Any]]) -> [ChatContentBlock] {
    var blocks: [ChatContentBlock] = []
    for dict in array {
      guard let type = dict["type"] as? String,
        let id = dict["id"] as? String
      else { continue }

      switch type {
      case "text":
        let text = dict["text"] as? String ?? ""
        blocks.append(.text(id: id, text: text))
      case "toolCall":
        guard let name = dict["name"] as? String,
          !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { continue }
        let statusStr = dict["status"] as? String ?? "completed"
        let status: ToolCallStatus
        switch statusStr {
        case "running": status = .running
        case "completed": status = .completed
        case "failed": status = .failed
        default: status = .completed
        }
        let toolUseId = dict["toolUseId"] as? String
        let input: ToolCallInput?
        if let summary = dict["inputSummary"] as? String {
          input = ToolCallInput(summary: summary, details: dict["inputDetails"] as? String)
        } else {
          input = nil
        }
        let output = dict["output"] as? String
        blocks.append(
          .toolCall(
            id: id,
            name: name,
            status: status,
            toolUseId: toolUseId,
            input: input,
            output: output
          )
        )
      case "thinking":
        let text = dict["text"] as? String ?? ""
        blocks.append(.thinking(id: id, text: text))
      case "discoveryCard":
        let title = dict["title"] as? String ?? ""
        let summary = dict["summary"] as? String ?? ""
        let fullText = dict["fullText"] as? String ?? ""
        blocks.append(
          .discoveryCard(id: id, title: title, summary: summary, fullText: fullText)
        )
      case "questionCard":
        guard let questionId = dict["questionId"] as? String,
          let text = dict["text"] as? String,
          let subject = dict["subject"] as? [String: Any],
          let subjectKind = subject["kind"] as? String,
          let subjectId = subject["id"] as? String,
          let options = dict["options"] as? [[String: Any]]
        else { continue }
        blocks.append(
          .questionCard(
            id: id,
            questionId: questionId,
            text: text,
            subjectKind: subjectKind,
            subjectId: subjectId,
            options: options,
            selectedOptionId: dict["selectedOptionId"] as? String
          )
        )
      case "taskCard":
        guard let taskId = dict["taskId"] as? String else { continue }
        blocks.append(.taskCard(id: id, taskId: taskId))
      case "goalLink":
        guard let goalId = dict["goalId"] as? String, let summary = dict["summary"] as? String else { continue }
        blocks.append(.goalLink(id: id, goalId: goalId, summary: summary))
      case "captureLink":
        guard let conversationId = dict["conversationId"] as? String, let summary = dict["summary"] as? String else {
          continue
        }
        blocks.append(
          .captureLink(
            id: id, conversationId: conversationId,
            momentTimestampMs: ChatJSONScalar.int(dict["momentTimestampMs"]),
            summary: summary))
      case "conversationLink":
        guard let conversationId = dict["conversationId"] as? String, let summary = dict["summary"] as? String else {
          continue
        }
        let recommendedActionItems = (dict["recommendedActionItems"] as? [[String: Any]] ?? []).compactMap {
          item -> ConversationLinkActionItem? in
          guard let description = item["description"] as? String,
            !description.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          else { return nil }
          return ConversationLinkActionItem(description: description, taskID: item["taskId"] as? String)
        }
        blocks.append(
          .conversationLink(
            id: id,
            conversationId: conversationId,
            summary: summary,
            recommendedActionItems: recommendedActionItems))
      case "memoryLink":
        guard let memoryId = dict["memoryId"] as? String, let summary = dict["summary"] as? String else { continue }
        blocks.append(.memoryLink(id: id, memoryId: memoryId, summary: summary))
      case "citation":
        guard let ordinal = ChatJSONScalar.int(dict["ordinal"]),
          let kindValue = dict["kind"] as? String,
          let kind = ChatCitationReference.Kind(rawValue: kindValue),
          let sourceID = (dict["sourceId"] as? String) ?? (dict["source_id"] as? String)
        else { continue }
        blocks.append(
          .citation(
            id: id,
            reference: ChatCitationReference(
              ordinal: ordinal,
              kind: kind,
              sourceID: sourceID,
              title: dict["title"] as? String ?? "",
              preview: dict["preview"] as? String ?? "",
              momentTimestampMs: ChatJSONScalar.int(dict["momentTimestampMs"])
                ?? ChatJSONScalar.int(dict["moment_timestamp_ms"]),
              createdAt: dict["createdAt"] as? String ?? dict["created_at"] as? String,
              appName: dict["appName"] as? String ?? dict["app_name"] as? String,
              url: (dict["url"] as? String).flatMap(URL.init(string:)))))
      case "agentSpawn":
        guard let sessionId = dict["sessionId"] as? String,
          !sessionId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
          let runId = dict["runId"] as? String,
          !runId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { continue }
        let pillId = (dict["pillId"] as? String).flatMap(UUID.init(uuidString:))
        let title = dict["title"] as? String ?? ""
        let objective = dict["objective"] as? String ?? ""
        let provider = (dict["provider"] as? String)
          .flatMap(AgentRuntimeRouting.harnessMode(from:))
          .flatMap { $0 == .hermes || $0 == .openclaw ? $0 : nil }
        blocks.append(
          .agentSpawn(
            id: id,
            pillId: pillId,
            sessionId: sessionId,
            runId: runId,
            title: title,
            objective: objective,
            provider: provider
          )
        )
      case "agentCompletion":
        let pillId = (dict["pillId"] as? String).flatMap(UUID.init(uuidString:))
        let sessionId = dict["sessionId"] as? String
        let runId = dict["runId"] as? String
        let title = dict["title"] as? String ?? ""
        let promptSnippet = dict["promptSnippet"] as? String ?? ""
        let output = dict["output"] as? String ?? ""
        let status = dict["status"] as? String ?? "completed"
        blocks.append(
          .agentCompletion(
            id: id,
            pillId: pillId,
            sessionId: sessionId,
            runId: runId,
            title: title,
            promptSnippet: promptSnippet,
            output: output,
            status: status
          )
        )
      default:
        break
      }
    }
    return blocks
  }

  /// Merge structured content blocks into an existing metadata JSON object.
  static func mergeIntoMessageMetadata(
    _ metadataJSON: String?,
    contentBlocks: [ChatContentBlock]
  ) -> String? {
    guard !contentBlocks.isEmpty else { return metadataJSON }
    var root: [String: Any] = [:]
    if let metadataJSON,
      let data = metadataJSON.data(using: .utf8),
      let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    {
      root = parsed
    }
    root[messageMetadataKey] = encodeArray(contentBlocks)
    guard let data = try? JSONSerialization.data(withJSONObject: root),
      let json = String(data: data, encoding: .utf8)
    else { return metadataJSON }
    return json
  }

  static func decodeFromMessageMetadata(_ metadataJSON: String?) -> [ChatContentBlock] {
    guard let metadataJSON,
      let data = metadataJSON.data(using: .utf8),
      let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let array = root[messageMetadataKey] as? [[String: Any]]
    else { return [] }
    return decode(array)
  }

  static func mergingCitationBackup(
    _ blocks: [ChatContentBlock],
    backup: [ChatContentBlock]
  ) -> [ChatContentBlock] {
    var seen = Set(
      blocks.compactMap { block -> Int? in
        guard case .citation(_, let reference) = block else { return nil }
        return reference.ordinal
      })
    let recovered = backup.filter { block in
      guard case .citation(_, let reference) = block else { return false }
      return seen.insert(reference.ordinal).inserted
    }
    return recovered.isEmpty ? blocks : blocks + recovered
  }

  static func citationBlocks(in blocks: [ChatContentBlock]) -> [ChatContentBlock] {
    blocks.filter { block in
      if case .citation = block { return true }
      return false
    }
  }

  private static func persistenceDictionary(for block: ChatContentBlock) -> [String: Any] {
    switch block {
    case .text(let id, let text):
      return ["type": "text", "id": id, "text": text]
    case .toolCall(let id, let name, let status, let toolUseId, let input, let output):
      // Three-way mapping: in-flight (.running, .slow, .stalled) persists as
      // "running" so reload resumes the spinner; .completed / .failed keep codes.
      let statusCode: String
      switch status {
      case .running, .slow, .stalled: statusCode = "running"
      case .completed: statusCode = "completed"
      case .failed: statusCode = "failed"
      }
      var dict: [String: Any] = [
        "type": "toolCall",
        "id": id,
        "name": name,
        "status": statusCode,
      ]
      if let toolUseId { dict["toolUseId"] = toolUseId }
      if let input {
        dict["inputSummary"] = input.summary
        if let details = input.details { dict["inputDetails"] = details }
      }
      if let output { dict["output"] = output }
      return dict
    case .thinking(let id, let text):
      return ["type": "thinking", "id": id, "text": text]
    case .discoveryCard(let id, let title, let summary, let fullText):
      return [
        "type": "discoveryCard",
        "id": id,
        "title": title,
        "summary": summary,
        "fullText": fullText,
      ]
    case .questionCard(
      let id, let questionId, let text, let subjectKind, let subjectId, let options, let selectedOptionId):
      var dictionary: [String: Any] = [
        "type": "questionCard", "id": id, "questionId": questionId, "text": text,
        "subject": ["kind": subjectKind, "id": subjectId], "options": options,
      ]
      if let selectedOptionId { dictionary["selectedOptionId"] = selectedOptionId }
      return dictionary
    case .taskCard(let id, let taskId):
      return ["type": "taskCard", "id": id, "taskId": taskId]
    case .goalLink(let id, let goalId, let summary):
      return ["type": "goalLink", "id": id, "goalId": goalId, "summary": summary]
    case .captureLink(let id, let conversationId, let momentTimestampMs, let summary):
      var dict: [String: Any] = ["type": "captureLink", "id": id, "conversationId": conversationId, "summary": summary]
      if let momentTimestampMs { dict["momentTimestampMs"] = momentTimestampMs }
      return dict
    case .conversationLink(let id, let conversationId, let summary, let recommendedActionItems):
      var dict: [String: Any] = [
        "type": "conversationLink", "id": id, "conversationId": conversationId, "summary": summary,
      ]
      if !recommendedActionItems.isEmpty {
        dict["recommendedActionItems"] = recommendedActionItems.map { item in
          var encoded: [String: Any] = ["description": item.description]
          if let taskID = item.taskID { encoded["taskId"] = taskID }
          return encoded
        }
      }
      return dict
    case .memoryLink(let id, let memoryId, let summary):
      return ["type": "memoryLink", "id": id, "memoryId": memoryId, "summary": summary]
    case .citation(let id, let reference):
      var dict: [String: Any] = [
        "type": "citation",
        "id": id,
        "ordinal": reference.ordinal,
        "kind": reference.kind.rawValue,
        "sourceId": reference.sourceID,
        "title": reference.title,
        "preview": reference.preview,
      ]
      if let value = reference.momentTimestampMs { dict["momentTimestampMs"] = value }
      if let value = reference.createdAt { dict["createdAt"] = value }
      if let value = reference.appName { dict["appName"] = value }
      if let value = reference.url { dict["url"] = value.absoluteString }
      return dict
    case .agentSpawn(
      let id, let pillId, let sessionId, let runId, let title, let objective, let provider
    ):
      var dict: [String: Any] = [
        "type": "agentSpawn",
        "id": id,
        "sessionId": sessionId,
        "runId": runId,
        "title": title,
        "objective": objective,
      ]
      if let pillId { dict["pillId"] = pillId.uuidString }
      if let provider { dict["provider"] = provider.rawValue }
      return dict
    case .agentCompletion(
      let id, let pillId, let sessionId, let runId, let title, let promptSnippet, let output, let status
    ):
      var dict: [String: Any] = [
        "type": "agentCompletion",
        "id": id,
        "title": title,
        "promptSnippet": promptSnippet,
        "output": output,
        "status": status,
      ]
      if let pillId { dict["pillId"] = pillId.uuidString }
      if let sessionId { dict["sessionId"] = sessionId }
      if let runId { dict["runId"] = runId }
      return dict
    }
  }
}

enum ChatJSONScalar {
  static func int(_ value: Any?) -> Int? {
    if let value = value as? Int { return value }
    if let value = value as? Int64 { return Int(value) }
    if let value = value as? NSNumber { return value.intValue }
    if let value = value as? String { return Int(value.trimmingCharacters(in: .whitespacesAndNewlines)) }
    return nil
  }
}
