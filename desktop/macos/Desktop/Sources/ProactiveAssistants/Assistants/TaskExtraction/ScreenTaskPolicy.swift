import Foundation

enum ScreenTaskFeature {
  static let flagName = "screen_task_jev_gate"
  /// All bundles default off; Beta/dev must also have explicit consent and enablement.
  @MainActor static var isConfigured: Bool { PostHogManager.shared.isFeatureEnabled(flagName) }
  @MainActor static var isEnabled: Bool {
    ScreenTaskFlagRefresh.start()
    if !PostHogManager.shared.isFeatureEnabled(flagName) { authority.disable() }
    return lease() != nil
  }
  static let authority = ScreenTaskAdmissionAuthority()
  static let serverAuthority = ScreenTaskAdmissionAuthority()
  static func lease() -> ScreenTaskLease? {
    guard let flag = authority.snapshot(), let server = serverAuthority.snapshot() else { return nil }
    return ScreenTaskLease(flag: flag, server: server)
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
