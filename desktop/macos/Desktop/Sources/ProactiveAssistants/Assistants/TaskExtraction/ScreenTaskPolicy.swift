import Foundation

enum ScreenTaskFeature {
  /// This path is enabled by the client build. The server admission lease remains
  /// the live kill switch, while privacy, owner and quota checks stay per-frame.
  @MainActor static var isConfigured: Bool { true }
  @MainActor static func lease(for authorization: RuntimeOwnerAuthorizationSnapshot?) async -> ScreenTaskLease? {
    guard let authorization, RuntimeOwnerIdentity.isAuthorizationCurrent(authorization) else { return nil }
    guard await APIKeyService.activeHealthyGeminiBYOK(forOwnerID: authorization.ownerID) == nil else { return nil }
    ScreenTaskAdmissionRefresh.start()
    guard let server = serverAuthority.snapshot() else { return nil }
    return ScreenTaskLease(server: server)
  }

  @MainActor static func isEnabled(for authorization: RuntimeOwnerAuthorizationSnapshot?) async -> Bool {
    let lease = await lease(for: authorization)
    return lease != nil
  }

  static let serverAuthority = ScreenTaskAdmissionAuthority()

  static func shouldUseManagedPath(
    serverAdmitted: Bool, ownerCurrent: Bool, hasSelectedGeminiBYOK: Bool
  ) -> Bool {
    serverAdmitted && ownerCurrent && !hasSelectedGeminiBYOK
  }

  static func enforceQuota() async throws {
    guard await ManagedProactivityDecisionSource.current() != .planGated else { throw ScreenTaskFailure.planGated }
  }
}

struct ScreenTaskDedupe {
  private struct Entry {
    let time: TimeInterval
    let lines: [String]
  }
  private var entries: [String: Entry] = [:]

  static func lines(ocr: OCRResult, app: String) -> [String] {
    let blocks = ocr.blocks.filter { block in
      !["Telegram", "Messages"].contains(app) || (block.x + block.width / 2 >= 0.28 && block.y > 0.06 && block.y < 0.94)
    }
    return blocks.map { block in
      block.text.lowercased().components(
        separatedBy: CharacterSet.alphanumerics.union(CharacterSet(charactersIn: "_")).inverted
      )
      .filter { !$0.isEmpty }.joined(separator: " ")
    }.filter { !$0.isEmpty }
  }

  func shouldSkip(key: String, lines: [String], now: TimeInterval) -> Bool {
    guard !lines.isEmpty, let entry = entries[key], now >= entry.time,
      now - entry.time <= 60
    else { return false }
    return lines == entry.lines
  }

  mutating func record(key: String, lines: [String], now: TimeInterval) {
    entries = entries.filter { now - $0.value.time <= 60 }
    if entries.count >= 64, let oldest = entries.min(by: { $0.value.time < $1.value.time })?.key {
      entries.removeValue(forKey: oldest)
    }
    entries[key] = Entry(time: now, lines: lines)
  }
}

enum ScreenTaskContext {
  /// Rank the two local FTS result sets together; IDs alone authorize relations.
  static func select(keywords: [TaskSearchResult], query: String, limit: Int = 8) -> [TaskSearchResult] {
    func tokens(_ text: String) -> Set<String> {
      Set(text.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.count >= 3 })
    }
    let queryTerms = tokens(query)
    let ranked = keywords.enumerated().sorted { left, right in
      let a = tokens(left.element.description).intersection(queryTerms).count
      let b = tokens(right.element.description).intersection(queryTerms).count
      return a == b ? left.offset < right.offset : a > b
    }.map(\.element)
    var seen = Set<String>()
    return Array(
      ranked.filter { row in
        let key = "\(row.status):\(row.taskID ?? ""):\(row.description)"
        return seen.insert(key).inserted
      }.prefix(max(0, min(limit, 8))))
  }
}
