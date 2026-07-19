import Foundation

// MARK: - Composition

/// Builds the three home ask-bar suggestion chips: a fixed universal first
/// question plus two personalized follow-ups generated from the user's own
/// memories, conversations, tasks, and goals.
enum HomeSuggestionComposer {
  static let universalFirstQuestion = "What should I do today?"

  /// Longest personalized question that still fits a single chip line.
  static let maxPersonalizedLength = 72

  /// Universal first-slot questions (current and legacy onboarding wording)
  /// that must not repeat in the personalized slots.
  private static let universalQuestions: Set<String> = [
    "what should i do today?",
    "what should i focus on today to achieve my goals?",
  ]

  static let staticFallbacks = [
    "What did I spend my time on this week?",
    "What's the highest-leverage thing I can do next?",
  ]

  /// Trim, drop empties/duplicates/universal repeats, and drop questions too
  /// long to render on one chip line.
  static func sanitize(_ questions: [String]) -> [String] {
    var seen = Set<String>()
    return
      questions
      .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
      .filter { question in
        guard !question.isEmpty, question.count <= maxPersonalizedLength else { return false }
        let key = question.lowercased()
        guard !universalQuestions.contains(key), !seen.contains(key) else { return false }
        seen.insert(key)
        return true
      }
  }

  /// The three chips: universal first, then personalized questions, topped up
  /// from onboarding-scan suggestions and static fallbacks when fewer than
  /// two personalized questions are available.
  static func compose(personalized: [String], onboarding: [String]) -> [String] {
    let rest = sanitize(personalized + onboarding + staticFallbacks)
    return [universalFirstQuestion] + rest.prefix(2)
  }
}

// MARK: - Generation seam

protocol HomeSuggestionGenerating: Sendable {
  /// Returns personalized questions, or an empty array when the user's
  /// context is too thin to reference anything real. Throws on transport
  /// failure so the caller can retry later without burning the daily slot.
  /// Every context read must be bound to `snapshot` so a mid-generation
  /// account switch can never return another owner's data.
  func generatePersonalizedQuestions(
    snapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> [String]
}

// MARK: - Store

/// Owns the two personalized home suggestion chips: generates them at most
/// once per day per account and caches them per owner so an account switch
/// never shows another account's questions.
@MainActor
final class HomeSuggestionsStore: ObservableObject {
  static let shared = HomeSuggestionsStore()

  @Published private(set) var personalizedQuestions: [String] = []

  private struct CacheEntry: Codable {
    let questions: [String]
    let dayStamp: String
  }

  private static let dayStampFormatter: DateFormatter = {
    let formatter = DateFormatter()
    formatter.calendar = Calendar(identifier: .gregorian)
    formatter.locale = Locale(identifier: "en_US_POSIX")
    formatter.dateFormat = "yyyy-MM-dd"
    return formatter
  }()

  private let defaults: UserDefaults
  private let generator: any HomeSuggestionGenerating
  private let now: () -> Date
  private var generatingOwnerID: String?
  private nonisolated(unsafe) var ownerObserver: NSObjectProtocol?

  init(
    defaults: UserDefaults = .standard,
    generator: (any HomeSuggestionGenerating)? = nil,
    now: @escaping () -> Date = Date.init
  ) {
    self.defaults = defaults
    self.generator = generator ?? GeminiHomeSuggestionGenerator()
    self.now = now
    publishCache(for: RuntimeOwnerIdentity.currentOwnerId() ?? "signed-out")
    ownerObserver = NotificationCenter.default.addObserver(
      forName: .runtimeOwnerDidChange, object: nil, queue: .main
    ) { [weak self] _ in
      Task { @MainActor in
        await self?.refreshIfNeeded()
      }
    }
  }

  deinit {
    if let ownerObserver { NotificationCenter.default.removeObserver(ownerObserver) }
  }

  /// Publish the current owner's cached questions and generate fresh ones at
  /// most once per day per owner. The owner-authorization snapshot captured
  /// up front bounds every context fetch, the cache write, and the publish,
  /// so a mid-generation account switch drops the result entirely. Transport
  /// failures leave the cache untouched so a later call retries; a
  /// successful-but-empty generation is cached to hold one attempt per day.
  func refreshIfNeeded() async {
    guard let snapshot = RuntimeOwnerIdentity.captureAuthorizationSnapshot() else {
      // Signed out or mid account transition — never render a previous
      // owner's questions.
      personalizedQuestions = []
      return
    }
    let ownerID = snapshot.ownerID
    publishCache(for: ownerID)

    let today = Self.dayStampFormatter.string(from: now())
    if let cache = loadCache(for: ownerID), cache.dayStamp == today { return }
    guard generatingOwnerID == nil else { return }

    generatingOwnerID = ownerID
    defer { generatingOwnerID = nil }

    do {
      let generated = try await generator.generatePersonalizedQuestions(snapshot: snapshot)
      guard RuntimeOwnerIdentity.isAuthorizationCurrent(snapshot) else {
        log("HomeSuggestions: dropped generation result after account switch")
        return
      }
      let questions = Array(HomeSuggestionComposer.sanitize(generated).prefix(2))
      let entry = CacheEntry(questions: questions, dayStamp: today)
      defaults.set(try? JSONEncoder().encode(entry), forKey: Self.cacheKey(ownerID: ownerID))
      personalizedQuestions = questions
      log("HomeSuggestions: generated \(questions.count) personalized questions for \(today)")
    } catch {
      log(
        "HomeSuggestions: generation failed (will retry on next visit): \(error.localizedDescription)"
      )
    }
  }

  static func cacheKey(ownerID: String) -> String {
    "homePersonalizedSuggestions.v1.\(ownerID)"
  }

  private func loadCache(for ownerID: String) -> CacheEntry? {
    guard let data = defaults.data(forKey: Self.cacheKey(ownerID: ownerID)) else { return nil }
    return try? JSONDecoder().decode(CacheEntry.self, from: data)
  }

  private func publishCache(for ownerID: String) {
    personalizedQuestions = loadCache(for: ownerID)?.questions ?? []
  }
}

// MARK: - Gemini generation

struct GeminiHomeSuggestionGenerator: HomeSuggestionGenerating {
  private struct Response: Decodable {
    let questions: [String]
  }

  private var responseSchema: GeminiRequest.GenerationConfig.ResponseSchema {
    GeminiRequest.GenerationConfig.ResponseSchema(
      type: "object",
      properties: [
        "questions": .init(
          type: "array",
          description: "Up to two short personalized questions, empty when context is too thin",
          items: .init(type: "string", properties: nil, required: nil)
        )
      ],
      required: ["questions"]
    )
  }

  func generatePersonalizedQuestions(
    snapshot: RuntimeOwnerAuthorizationSnapshot
  ) async throws -> [String] {
    async let memoriesFetch = { () async -> [ServerMemory] in
      (try? await APIClient.shared.getMemories(limit: 200, authorizationSnapshot: snapshot)) ?? []
    }()
    async let conversationsFetch = { () async -> [ServerConversation] in
      (try? await APIClient.shared.getConversations(
        limit: 30, statuses: [.completed], authorizationSnapshot: snapshot)) ?? []
    }()
    async let actionItemsFetch = { () async -> ActionItemsListResponse? in
      try? await APIClient.shared.getActionItems(
        limit: 50, completed: false, authorizationSnapshot: snapshot)
    }()
    async let goalsFetch = { () async -> [Goal] in
      (try? await APIClient.shared.getGoals(authorizationSnapshot: snapshot)) ?? []
    }()

    let (memories, conversations, actionItems, goals) = await (
      memoriesFetch, conversationsFetch, actionItemsFetch, goalsFetch
    )

    let memoryContext = memories.map { $0.content }.joined(separator: "\n")
    let conversationContext =
      conversations
      .compactMap { $0.structured.overview.isEmpty ? nil : $0.structured.overview }
      .joined(separator: "\n")
    let tasksContext = (actionItems?.items ?? []).map { $0.description }.joined(separator: "\n")
    let goalsContext = goals.map { $0.title }.joined(separator: "\n")

    if memoryContext.isEmpty && conversationContext.isEmpty && tasksContext.isEmpty
      && goalsContext.isEmpty
    {
      return []
    }

    let dateFormatter = DateFormatter()
    dateFormatter.locale = Locale(identifier: "en_US_POSIX")
    dateFormatter.dateFormat = "EEEE, MMMM d, yyyy"

    let prompt = """
      Today is \(dateFormatter.string(from: Date())).

      USER MEMORIES:
      \(memoryContext.isEmpty ? "None" : memoryContext)

      RECENT CONVERSATION SUMMARIES:
      \(conversationContext.isEmpty ? "None" : conversationContext)

      OPEN TASKS:
      \(tasksContext.isEmpty ? "None" : tasksContext)

      ACTIVE GOALS:
      \(goalsContext.isEmpty ? "None" : goalsContext)

      Write up to 2 suggested questions this user would genuinely want to ask right now.

      Rules:
      - Each question must reference something concrete and current from the context above by name — a project, person, goal, task, or topic.
      - Phrase them in first person, as the user asking their assistant (e.g. "How do I unblock the Atlas launch?").
      - Keep each under 48 characters so it fits on one line.
      - No generic productivity questions ("What should I focus on?", "How can I be more productive?") — the first suggestion slot already covers that.
      - Skip anything sensitive or awkward to show on a home screen.
      - Return an empty list if the context doesn't contain enough real, current material.
      """

    let client = try GeminiClient()
    let responseText = try await client.sendRequest(
      prompt: prompt,
      systemPrompt:
        "You write the suggested questions shown under the ask bar of omi, the user's personal AI assistant. The questions are ones the user would tap to ask about their own life and work.",
      responseSchema: responseSchema
    )

    guard let data = responseText.data(using: .utf8) else { return [] }
    return try JSONDecoder().decode(Response.self, from: data).questions
  }
}
