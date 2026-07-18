import Foundation

/// Shared encode/decode for structured chat content blocks.
/// Used by task-chat local SQLite and main-chat `saveMessage` metadata so
/// `agentSpawn` / `agentCompletion` survive reload (INV-6 rule 4).
enum ChatContentBlockCodec {
  static let messageMetadataKey = "content_blocks"

  static func encode(_ blocks: [ChatContentBlock]) -> String? {
    guard !blocks.isEmpty else { return nil }
    let encoded = blocks.map(persistenceDictionary(for:))
    guard let data = try? JSONSerialization.data(withJSONObject: encoded),
      let json = String(data: data, encoding: .utf8)
    else { return nil }
    return json
  }

  static func encodeArray(_ blocks: [ChatContentBlock]) -> [[String: Any]] {
    blocks.map(persistenceDictionary(for:))
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
          .flatMap { $0 == .hermes || $0 == .openclaw || $0 == .codex ? $0 : nil }
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
