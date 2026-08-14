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
    Return everything you know about me inside one fenced code block. Include long-term memory, bio details, and any model-set context you have. Prefix every item with when you learned it, using a bracket tag: an exact [YYYY-MM-DD] only if you genuinely have a real date, otherwise the coarse recency tier you actually have — [recent], [earlier], or [long-term]. Never invent or guess a date; if you truly have no recency signal at all, use [unknown]. I want a thorough memory export of what you've learned about me. Skip tool details and include only information that is actually about me. Be exhaustive and careful.
    """
  }
}

actor OnboardingMemoryLogImportService {
  static let shared = OnboardingMemoryLogImportService()

  struct ExtractedMemoryLog: Sendable {
    let memories: [String]
    let profileSummary: String
  }

  /// Distinguishes "the text had nothing durable" (an expected outcome the
  /// user can fix by pasting the right content) from "the import itself
  /// broke" (LLM/parse/save failure worth retrying as-is).
  enum ImportOutcome: Sendable {
    case imported(memories: Int, profileSummary: String)
    case noDurableMemories
    case failed
  }

  func importMemoryLog(
    _ rawText: String,
    source: OnboardingMemoryLogSource,
    extractedFixture: ExtractedMemoryLog? = nil
  ) async -> ImportOutcome {
    let trimmed = rawText.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !trimmed.isEmpty else { return .noDurableMemories }

    let extracted: ExtractedMemoryLog
    if let extractedFixture {
      guard AppBuild.isNonProduction else {
        return .failed
      }
      extracted = extractedFixture
    } else {
      do {
        let response = try await APIClient.shared.extractMemoryLog(
          text: String(trimmed.prefix(40_000)),
          textSource: source.rawValue)
        extracted = ExtractedMemoryLog(
          memories: response.memories,
          profileSummary: response.profile)
      } catch {
        log("OnboardingMemoryLogImportService: \(source.displayName) import failed: \(error)")
        return .failed
      }
    }

    let memoryStrings = extracted.memories.filter {
      !$0.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
    guard !memoryStrings.isEmpty else {
      log("OnboardingMemoryLogImportService: No durable \(source.displayName) memories found")
      return .noDurableMemories
    }

    let items = memoryStrings.map { memory in
      ImportEvidenceBatchItem(
        title: source.headline,
        snippet: memory,
        content: memory,
        metadata: ["import_kind": "memory_log"]
      )
    }
    let legacyMemories = memoryStrings.map { memory in
      MemoryBatchItem(
        content: memory,
        tags: source.tags,
        headline: source.headline,
        source: source.memorySource
      )
    }
    let saveResult = await OnboardingImportEvidenceService.save(
      items,
      sourceType: source.memorySource,
      logPrefix: "OnboardingMemoryLogImportService",
      legacyMemories: legacyMemories
    )
    if saveResult.failed > 0 {
      log(
        "OnboardingMemoryLogImportService: Saved \(saveResult.saved) \(source.displayName) memories; \(saveResult.failed) failed"
      )
    }

    guard saveResult.saved > 0 else {
      return .failed
    }
    return .imported(memories: saveResult.saved, profileSummary: extracted.profileSummary)
  }
}
