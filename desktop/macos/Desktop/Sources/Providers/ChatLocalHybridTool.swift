import Foundation

enum ChatLocalHybridTool {
  static func execute(
    _ args: [String: Any],
    runID: String?,
    attemptID: String?,
    expectedOwnerID: String?,
    sourceKinds: Set<LocalEmbeddingSourceKind>,
    runtime: LocalEmbeddingRuntime = .makeDefault()
  ) async -> String {
    guard ChatToolExecutor.isExpectedOwnerCurrent(expectedOwnerID) else {
      return ChatToolExecutor.authorizedOwnerChangedResult()
    }
    guard let query = args["query"] as? String, !query.isEmpty else {
      return "Error: query is required"
    }
    let days: Int = {
      if let value = args["days"] as? Int { return max(1, value) }
      if let value = args["days"] as? Double { return max(1, Int(value)) }
      return 7
    }()
    let limit: Int = {
      if let value = args["limit"] as? Int { return min(max(1, value), 50) }
      if let value = args["limit"] as? Double { return min(max(1, Int(value)), 50) }
      return 15
    }()
    let endDate = Date()
    let startDate = Calendar.current.date(byAdding: .day, value: -days, to: endDate) ?? endDate
    do {
      guard let owner = RewindCaptureOwnerSnapshot.capture(), owner.isCurrent() else {
        throw LocalMutationAuthorizationError.revoked
      }
      let store = try await RewindDatabase.shared.localEmbeddingStore(owner: owner)
      let engine: (any LocalEmbeddingService)?
      if case .engine(let selected) = await runtime.selectEngine() {
        engine = selected
      } else {
        engine = nil
      }
      let hits = try await LocalHybridSearch(
        store: store, runtime: runtime,
        authorization: LocalMutationAuthorization { owner.isCurrent() }
      ).search(
        query: query, engine: engine, startDate: startDate, endDate: endDate, limit: limit,
        sourceKinds: sourceKinds)
      if hits.isEmpty {
        return "No transcript matches for \"\(query)\"."
      }
      let previews = try store.transcriptChunkPreviews(ids: hits.map(\.sourceId), limit: limit)
      let displayTimeZone = TimeZone.current
      var lines = ["Found \(hits.count) transcript match(es) for \"\(query)\":"]
      for (index, hit) in hits.enumerated() {
        let dateStr = DesktopChatTimestampFormat.userFacing(hit.capturedAt, timeZone: displayTimeZone)
        lines.append(
          "\n\(index + 1). [\(dateStr)] \(hit.appName) (id: \(hit.sourceId), hybrid: \(hit.matchedBy.rawValue))")
        if let preview = previews[hit.sourceId] {
          let text = String(preview.text.prefix(300))
            .replacingOccurrences(of: "\n", with: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
          if !text.isEmpty {
            lines.append("   Content: \(text)")
          }
        }
      }
      return lines.joined(separator: "\n")
    } catch {
      return "Failed to search transcripts: \(error.localizedDescription)"
    }
  }
}
