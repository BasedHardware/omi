import Foundation

extension ChatToolExecutor {
  struct ScreenTextFallback {
    var lines: [String] = []
    var sources: [APIClient.ToolSource] = []
    var count = 0
  }

  /// Vector search only sees frames whose OCR text has been embedded, and embeddings flush in
  /// 60-second batches. A question about something read a moment ago ("the riddle on the first
  /// page") therefore misses the frame that has it. This searches the exact-text FTS index, which
  /// is written with the frame, newest first, so "seen seconds ago" is answerable.
  static func screenTextFallback(
    query: String, appFilter: String?, startDate: Date, endDate: Date, limit: Int
  ) async -> ScreenTextFallback {
    var result = ScreenTextFallback()
    let hits =
      ((try? await RewindDatabase.shared.search(
        query: query, appFilter: appFilter, startDate: startDate, endDate: endDate, limit: limit)) ?? [])
      .sorted { $0.timestamp > $1.timestamp }
    log("Tool semantic_search: text fallback returned \(hits.count) results")
    let displayTimeZone = TimeZone.current
    for screenshot in hits {
      guard let screenshotId = screenshot.id else { continue }
      result.count += 1
      let dateStr = DesktopChatTimestampFormat.userFacing(screenshot.timestamp, timeZone: displayTimeZone)
      let windowTitle = screenshot.windowTitle ?? ""
      let titlePart = windowTitle.isEmpty ? "" : " - \(windowTitle)"
      result.lines.append(
        "\n\(result.count). [\(dateStr)] \(screenshot.appName)\(titlePart) (screenshot_id: \(screenshotId), match: text)"
      )
      if let ocrText = screenshot.ocrText, !ocrText.isEmpty {
        let preview = String(ocrText.prefix(300))
          .replacingOccurrences(of: "\n", with: " ")
          .trimmingCharacters(in: .whitespacesAndNewlines)
        result.lines.append("   Content: \(preview)")
      }
      result.sources.append(
        APIClient.ToolSource(
          kind: ChatCitationReference.Kind.screenshot.rawValue,
          sourceID: String(screenshotId),
          title: windowTitle.isEmpty ? screenshot.appName : windowTitle,
          preview: screenshot.ocrText ?? "",
          createdAt: ISO8601DateFormatter().string(from: screenshot.timestamp),
          momentTimestampMs: nil,
          appName: screenshot.appName,
          url: nil))
      if result.count >= limit { break }
    }
    return result
  }
}
