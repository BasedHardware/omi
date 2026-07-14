import Foundation

// MARK: - AI Clone policy & activity models

/// Per-chat trust ladder. Ordered by increasing autonomy; `auto` additionally
/// requires the reply engine's confidence gate to pass.
enum AICloneChatMode: String, Codable, CaseIterable, Equatable {
  case off
  case draft
  case ask
  case auto

  var displayName: String {
    switch self {
    case .off: return "Off"
    case .draft: return "Draft"
    case .ask: return "Ask me"
    case .auto: return "Auto"
    }
  }
}

/// What the clone actually did for one inbound message.
enum AICloneActionOutcome: String, Codable, Equatable {
  case drafted
  case askedApproval
  case sentAutomatically
  case sentAfterApproval
  case stayedSilent
  case declinedInjection
  case failed
}

struct AICloneActivityEntry: Codable, Equatable, Identifiable {
  let id: UUID
  let date: Date
  let chatID: String
  let chatTitle: String
  let network: String
  let inboundPreview: String
  let replyText: String?
  let outcome: AICloneActionOutcome
  let confidence: Double?

  init(
    id: UUID = UUID(),
    date: Date = Date(),
    chatID: String,
    chatTitle: String,
    network: String,
    inboundPreview: String,
    replyText: String?,
    outcome: AICloneActionOutcome,
    confidence: Double?
  ) {
    self.id = id
    self.date = date
    self.chatID = chatID
    self.chatTitle = chatTitle
    self.network = network
    self.inboundPreview = inboundPreview
    self.replyText = replyText
    self.outcome = outcome
    self.confidence = confidence
  }
}

struct AICloneBenchmarkResult: Codable, Equatable {
  let chatID: String
  let chatTitle: String
  let sampleCount: Int
  /// 0…100 — average LLM-judge similarity between the clone's reply and what
  /// the user actually sent at the same point in the thread.
  let matchScore: Int
  let generatedAt: Date
}

/// Persisted clone configuration. One JSON document in Application Support —
/// policy and log only; never a second transcript store (message content
/// stays in Beeper, only bounded previews are logged).
struct AICloneConfiguration: Codable, Equatable {
  var enabled: Bool = false
  var chatModes: [String: AICloneChatMode] = [:]
  var benchmarkResults: [String: AICloneBenchmarkResult] = [:]
  /// Minimum reply-engine confidence (0…1) required for `auto` to send.
  var autoSendConfidenceThreshold: Double = 0.75
  /// Minimum benchmark match score required before a chat may be set to auto.
  var autoModeMinimumBenchmarkScore: Int = 60
  /// Bounded rolling activity log (newest first).
  var activityLog: [AICloneActivityEntry] = []

  static let activityLogLimit = 200

  func mode(for chatID: String) -> AICloneChatMode {
    chatModes[chatID] ?? .off
  }

  mutating func appendActivity(_ entry: AICloneActivityEntry) {
    activityLog.insert(entry, at: 0)
    if activityLog.count > Self.activityLogLimit {
      activityLog.removeLast(activityLog.count - Self.activityLogLimit)
    }
  }

  /// Auto mode is gated on benchmark evidence (Nik's "benchmark against your
  /// own past decisions" rule): a chat without a passing score can be Draft
  /// or Ask, never Auto.
  func canEnableAuto(for chatID: String) -> Bool {
    guard let result = benchmarkResults[chatID] else { return false }
    return result.matchScore >= autoModeMinimumBenchmarkScore
  }
}

/// File-backed store for `AICloneConfiguration`. Synchronous, tiny payload,
/// injectable directory for tests.
final class AICloneConfigurationStore {
  private let fileURL: URL
  private let queue = DispatchQueue(label: "com.omi.aiclone.config")

  init(directory: URL) {
    self.fileURL = directory.appendingPathComponent("ai-clone.json")
  }

  func load() -> AICloneConfiguration {
    queue.sync {
      guard let data = try? Data(contentsOf: fileURL),
        let config = try? Self.decoder.decode(AICloneConfiguration.self, from: data)
      else { return AICloneConfiguration() }
      return config
    }
  }

  func save(_ configuration: AICloneConfiguration) {
    queue.sync {
      guard let data = try? Self.encoder.encode(configuration) else { return }
      try? FileManager.default.createDirectory(
        at: fileURL.deletingLastPathComponent(), withIntermediateDirectories: true)
      try? data.write(to: fileURL, options: .atomic)
    }
  }

  private static let encoder: JSONEncoder = {
    let encoder = JSONEncoder()
    encoder.dateEncodingStrategy = .iso8601
    encoder.outputFormatting = [.sortedKeys]
    return encoder
  }()

  private static let decoder: JSONDecoder = {
    let decoder = JSONDecoder()
    decoder.dateDecodingStrategy = .iso8601
    return decoder
  }()
}

// MARK: - Reply engine decision

/// Structured verdict for one inbound message. Silence is a first-class
/// outcome: `shouldReply == false` is a successful run, not an error.
struct AICloneReplyDecision: Codable, Equatable {
  var shouldReply: Bool
  var confidence: Double
  var suspectedInjection: Bool
  var reply: String?

  enum CodingKeys: String, CodingKey {
    case shouldReply = "should_reply"
    case confidence
    case suspectedInjection = "suspected_injection"
    case reply
  }

  /// Parses the model's JSON verdict, tolerating a fenced code block wrapper.
  static func parse(_ raw: String) -> AICloneReplyDecision? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
    let candidates: [String]
    if let start = trimmed.range(of: "{"), let end = trimmed.range(of: "}", options: .backwards),
      start.lowerBound < end.upperBound
    {
      candidates = [String(trimmed[start.lowerBound..<end.upperBound]), trimmed]
    } else {
      candidates = [trimmed]
    }
    for candidate in candidates {
      if let data = candidate.data(using: .utf8),
        let decision = try? JSONDecoder().decode(AICloneReplyDecision.self, from: data)
      {
        return decision
      }
    }
    return nil
  }

  /// The action the trust ladder takes for this decision under a chat mode.
  func plannedOutcome(
    mode: AICloneChatMode,
    autoConfidenceThreshold: Double
  ) -> AICloneActionOutcome {
    if suspectedInjection { return .declinedInjection }
    guard shouldReply, let reply, !reply.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else { return .stayedSilent }
    switch mode {
    case .off:
      return .stayedSilent
    case .draft:
      return .drafted
    case .ask:
      return .askedApproval
    case .auto:
      // Low confidence downgrades to a draft rather than sending — the user
      // still sees the proposal in Beeper without the clone speaking for them.
      return confidence >= autoConfidenceThreshold ? .sentAutomatically : .drafted
    }
  }
}
