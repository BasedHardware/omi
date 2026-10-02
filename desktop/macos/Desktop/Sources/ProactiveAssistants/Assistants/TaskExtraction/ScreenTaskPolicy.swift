import Foundation

enum ScreenTaskFeature {
  static let flagName = "screen_task_jev_gate"
  /// All bundles default off; Beta/dev must also have explicit consent and enablement.
  @MainActor static var isEnabled: Bool { PostHogManager.shared.isFeatureEnabled(flagName) }

  static func enforceQuota() async throws {
    guard await ManagedProactivityDecisionSource.current() != .planGated else { throw ScreenTaskFailure.planGated }
  }
}

struct ScreenTaskDedupe {
  private struct Entry {
    let date: Date
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

  func shouldSkip(key: String, lines: [String], now: Date) -> Bool {
    guard !lines.isEmpty, let entry = entries[key], now >= entry.date,
      now.timeIntervalSince(entry.date) <= 60
    else { return false }
    return lines == entry.lines
  }

  mutating func record(key: String, lines: [String], now: Date) {
    entries = entries.filter { now.timeIntervalSince($0.value.date) <= 60 }
    if entries.count >= 64, let oldest = entries.min(by: { $0.value.date < $1.value.date })?.key {
      entries.removeValue(forKey: oldest)
    }
    entries[key] = Entry(date: now, lines: lines)
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

/// Capture authority at admission, before a queued frame can cross an account transition.
struct ScreenTaskFrameOwners {
  private struct Key: Hashable {
    let app: String
    let number: Int
    let date: Date
    init(_ frame: CapturedFrame) {
      app = frame.appName
      number = frame.frameNumber
      date = frame.captureTime
    }
  }
  private var owners: [Key: RuntimeOwnerAuthorizationSnapshot] = [:]

  mutating func record(_ frame: CapturedFrame, authorization: RuntimeOwnerAuthorizationSnapshot?) {
    let key = Key(frame)
    if owners.count >= 64, let oldest = owners.keys.min(by: { $0.date < $1.date }) {
      owners.removeValue(forKey: oldest)
    }
    owners[key] = authorization
  }

  func authorization(for frame: CapturedFrame) -> RuntimeOwnerAuthorizationSnapshot? { owners[Key(frame)] }
}
