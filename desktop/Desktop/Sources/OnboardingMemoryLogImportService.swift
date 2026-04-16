import Foundation

enum OnboardingMemoryLogSource: String, CaseIterable, Sendable {
  case chatgpt
  case claude

  var displayName: String {
    switch self {
    case .chatgpt: return "ChatGPT"
    case .claude: return "Claude"
    }
  }

  var browserURL: URL {
    switch self {
    case .chatgpt: return URL(string: "https://chatgpt.com/")!
    case .claude: return URL(string: "https://claude.ai/")!
    }
  }

  var prefilledBrowserURL: URL {
    var components = URLComponents(url: browserURL, resolvingAgainstBaseURL: false)

    switch self {
    case .chatgpt:
      components?.path = "/"
      components?.queryItems = [URLQueryItem(name: "q", value: prompt)]
    case .claude:
      components?.path = "/new"
      components?.queryItems = [URLQueryItem(name: "q", value: prompt)]
    }

    return components?.url ?? browserURL
  }

  var tags: [String] {
    [rawValue, "import", "memory_log"]
  }

  var memorySource: String {
    "\(rawValue)_memory_log"
  }

  var headline: String {
    "\(displayName) Memory Import"
  }

  var prompt: String {
    """
    Return everything you know about me inside one fenced code block. Include long-term memory, bio details, and any model-set context you have with dates when available. I want a thorough memory export of what you've learned about me. Skip tool details and include only information that is actually about me. Be exhaustive and careful.
    """
  }
}

actor OnboardingMemoryLogImportService {
  static let shared = OnboardingMemoryLogImportService()

  func importMemoryLog(
    _ rawText: String,
    source: OnboardingMemoryLogSource
  ) async -> (memories: Int, profileSummary: String) {
    let trimmed = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return (0, "") }

    let importPrompt = """
      Analyze this exported \(source.displayName) memory log and extract persistent facts about the user.

      MEMORY LOG:
      \(String(trimmed.prefix(40_000)))

      Respond ONLY with valid JSON (no markdown, no code fences):
      {
        "memories": [
          "clear factual statement about the user"
        ],
        "profile": "2-3 sentence summary of what this memory log says about the user"
      }

      RULES:
      - Extract 12-18 memories grounded in the provided memory log
      - Keep only durable, user-specific facts, preferences, relationships, projects, interests, and goals
      - Deduplicate overlapping memories
      - Exclude tool details, implementation notes, and meta-instructions
      - Each memory should be one concise factual statement
      """

    do {
      let bridge = ACPBridge(passApiKey: true, harnessMode: "piMono")
      try await bridge.start()
      defer { Task { await bridge.stop() } }

      let result = try await bridge.query(
        prompt: importPrompt,
        systemPrompt:
          "You convert memory-log exports into concise durable user memories. Output only valid JSON.",
        model: "claude-opus-4-6",
        onTextDelta: { @Sendable _ in },
        onToolCall: { @Sendable _, _, _ in "" },
        onToolActivity: { @Sendable _, _, _, _ in }
      )

      let responseText = Self.extractJSONObject(from: result.text)
      guard
        let jsonData = responseText.data(using: .utf8),
        let parsed = try JSONSerialization.jsonObject(with: jsonData) as? [String: Any]
      else {
        log("OnboardingMemoryLogImportService: Failed to parse \(source.displayName) response")
        return (0, "")
      }

      let memoryStrings = (parsed["memories"] as? [String] ?? []).filter {
        !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      }
      let profileSummary = parsed["profile"] as? String ?? ""

      var memoriesSaved = 0
      for memory in memoryStrings {
        do {
          _ = try await APIClient.shared.createMemory(
            content: memory,
            visibility: "private",
            tags: source.tags,
            source: source.memorySource,
            headline: source.headline
          )
          memoriesSaved += 1
        } catch {
          log(
            "OnboardingMemoryLogImportService: Failed saving \(source.displayName) memory: \(error)"
          )
        }
      }

      return (memoriesSaved, profileSummary)
    } catch {
      log("OnboardingMemoryLogImportService: \(source.displayName) import failed: \(error)")
      return (0, "")
    }
  }

  private static func extractJSONObject(from text: String) -> String {
    var responseText = text.trimmingCharacters(in: .whitespacesAndNewlines)

    if responseText.hasPrefix("```") {
      if let firstNewline = responseText.firstIndex(of: "\n") {
        responseText = String(responseText[responseText.index(after: firstNewline)...])
      }
      if responseText.hasSuffix("```") {
        responseText = String(responseText.dropLast(3)).trimmingCharacters(
          in: .whitespacesAndNewlines)
      }
    }

    if let braceIndex = responseText.firstIndex(of: "{") {
      responseText = String(responseText[braceIndex...])
    }

    return responseText.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
