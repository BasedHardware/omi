import Foundation

/// Keeps conversation reads useful inside the realtime relay's bounded model-facing result.
/// Main Chat retains the full result and citation guide; voice gets one compact, structured copy.
enum RealtimeConversationToolProjection {
  static let maximumItems = 8
  private static let defaultItems = 5
  private static let maximumTitleBytes = 160
  private static let maximumSummaryBytes = 420
  private static let maximumFallbackBytes = 5_500

  static func applies(to surfaceKind: String?) -> Bool {
    surfaceKind == "realtime_voice" || surfaceKind == "realtime"
  }

  static func requestLimit(_ value: Any?, default defaultValue: Int = defaultItems) -> Int {
    min(max(value as? Int ?? defaultValue, 1), maximumItems)
  }

  static func makeResult(_ response: APIClient.ToolResponse, limit: Int) -> String {
    let boundedLimit = min(max(limit, 1), maximumItems)
    var payload: [String: Any] = [
      "ok": !response.isError,
      "tool": response.toolName,
    ]

    if response.isError {
      payload["error"] = boundedUTF8(response.resultText, maximumBytes: maximumFallbackBytes)
    } else if let sources = response.sources, !sources.isEmpty {
      payload["order"] = "newest_first"
      payload["items"] = sources.prefix(boundedLimit).map { source in
        var item: [String: Any] = [
          "title": boundedUTF8(source.title, maximumBytes: maximumTitleBytes),
          "summary": boundedUTF8(source.preview, maximumBytes: maximumSummaryBytes),
        ]
        if let createdAt = source.createdAt, !createdAt.isEmpty {
          item["created_at"] = createdAt
        }
        return item
      }
    } else {
      // Older backends may not return typed sources. Keep their human-readable result bounded
      // instead of turning a valid read into an artifact-only failure the voice model cannot open.
      payload["text"] = boundedUTF8(response.resultText, maximumBytes: maximumFallbackBytes)
    }

    guard let data = try? JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys]),
      let result = String(data: data, encoding: .utf8)
    else {
      return #"{"ok":false,"error":"conversation_result_encoding_failed"}"#
    }
    return result
  }

  private static func boundedUTF8(_ value: String, maximumBytes: Int) -> String {
    guard value.utf8.count > maximumBytes else { return value }
    var bytes = 0
    var end = value.startIndex
    while end < value.endIndex {
      let next = value.index(after: end)
      let width = value[end..<next].utf8.count
      guard bytes + width <= maximumBytes else { break }
      bytes += width
      end = next
    }
    return String(value[..<end])
  }
}
