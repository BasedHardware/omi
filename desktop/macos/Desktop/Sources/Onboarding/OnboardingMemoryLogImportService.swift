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

  enum ImportFailure: String, Sendable {
    case authentication = "extract_auth_failed"
    case planRequired = "extract_plan_required"
    case rateLimited = "extract_rate_limited"
    case network = "extract_network_failed"
    case timeout = "extract_timeout"
    case server = "extract_backend_5xx"
    case invalidResponse = "extract_invalid_response"
    case requestRejected = "extract_backend_4xx"
    case saveFailed = "save_failed"
    case fixtureUnavailable = "fixture_unavailable"
  }

  struct ExtractedMemoryLog: Sendable {
    let memories: [String]
    let profileSummary: String
  }

  /// Distinguishes "the text had nothing durable" (an expected outcome the
  /// user can fix by pasting the right content) from "the import itself
  /// broke" (LLM/parse/save failure worth retrying as-is).
  enum ImportOutcome: Sendable {
    case imported(memories: Int, failed: Int, profileSummary: String)
    case noDurableMemories
    case failed(ImportFailure)
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
        return .failed(.fixtureUnavailable)
      }
      extracted = extractedFixture
    } else if let taggedMemories = Self.extractTaggedMemories(from: trimmed) {
      // Omi's export prompt asks ChatGPT/Claude to produce one explicitly tagged,
      // durable memory per line. That output is already the final memory shape, so
      // importing it locally avoids an unnecessary provider call and keeps the
      // documented paste flow working during an extraction-service outage.
      extracted = ExtractedMemoryLog(memories: taggedMemories, profileSummary: "")
    } else {
      do {
        let response = try await APIClient.shared.extractMemoryLog(
          text: String(trimmed.prefix(40_000)),
          textSource: source.rawValue)
        extracted = ExtractedMemoryLog(
          memories: response.memories,
          profileSummary: response.profile)
      } catch {
        let failure = Self.failure(for: error)
        log(
          "OnboardingMemoryLogImportService: \(source.displayName) extraction failed [\(failure.rawValue)]"
        )
        return .failed(failure)
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
      return .failed(.saveFailed)
    }
    return .imported(
      memories: saveResult.saved,
      failed: saveResult.failed,
      profileSummary: extracted.profileSummary)
  }

  /// Parses the explicit one-memory-per-line format requested by Omi's own
  /// ChatGPT/Claude export prompt. Returns nil when the paste is unstructured so
  /// the managed extractor remains the fallback; an empty tagged item is ignored.
  static func extractTaggedMemories(from rawText: String) -> [String]? {
    let pattern =
      #"^\s*(?:(?:[-*•]|\d+[.)])\s+)?\[((?:\d{4}-\d{2}-\d{2})|recent|earlier|long-term|unknown)\]\s*(.+?)\s*$"#
    guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
      return nil
    }

    var memories: [String] = []
    var seen: Set<String> = []
    for rawLine in rawText.components(separatedBy: .newlines) {
      let trimmedLine = rawLine.trimmingCharacters(in: .whitespacesAndNewlines)
      guard !trimmedLine.isEmpty, !trimmedLine.hasPrefix("```") else { continue }

      let range = NSRange(rawLine.startIndex..<rawLine.endIndex, in: rawLine)
      guard
        let match = regex.firstMatch(in: rawLine, range: range),
        let tagRange = Range(match.range(at: 1), in: rawLine),
        let contentRange = Range(match.range(at: 2), in: rawLine)
      else {
        // A mixed-format paste is not safe to import locally: silently ignoring
        // its untagged lines could lose durable memories. Let the managed
        // extractor interpret the complete paste instead.
        return nil
      }

      let tag = String(rawLine[tagRange]).lowercased()
      let content = String(rawLine[contentRange])
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard !content.isEmpty else { continue }

      let boundedContent = String(content.prefix(2_000))
      let memory = tag == "unknown" ? boundedContent : "[\(tag)] \(boundedContent)"
      let dedupeKey = memory.lowercased().split(whereSeparator: \Character.isWhitespace).joined(
        separator: " ")
      guard seen.insert(dedupeKey).inserted else { continue }
      memories.append(memory)
      if memories.count == 200 { break }
    }

    return memories.isEmpty ? nil : memories
  }

  static func failure(for error: Error) -> ImportFailure {
    if let authError = error as? AuthError {
      switch authError {
      case .timeout: return .timeout
      default: return .authentication
      }
    }
    if let urlError = error as? URLError {
      return urlError.code == .timedOut ? .timeout : .network
    }
    if let apiError = error as? APIError {
      switch apiError {
      case .unauthorized:
        return .authentication
      case .httpError(let statusCode, _):
        switch statusCode {
        case 401, 403: return .authentication
        case 402: return .planRequired
        case 408: return .timeout
        case 429: return .rateLimited
        case 500...599: return .server
        default: return .requestRejected
        }
      case .invalidResponse, .decodingError:
        return .invalidResponse
      default:
        return .requestRejected
      }
    }
    if error is DecodingError { return .invalidResponse }
    return .invalidResponse
  }
}
