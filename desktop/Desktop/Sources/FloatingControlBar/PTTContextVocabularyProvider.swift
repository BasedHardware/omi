import CoreGraphics
import Foundation

struct PTTContextSnapshot {
  let capturedAt: Date
  let keywords: [String]
  let sourceCount: Int
}

enum PTTContextVocabularyProvider {
  private static let maxKeywords = 100
  private static let maxTextLengthPerScreenshot = 3_000
  private static let maxImmediateOCRLength = 2_000
  private static let lookbackSeconds: TimeInterval = 120

  static func capture(at date: Date = Date(), preOverlayImage: CGImage? = nil) async -> PTTContextSnapshot {
    async let immediateOCRText = captureImmediateScreenText(preferredImage: preOverlayImage)
    let screenshots = await loadContextScreenshots(around: date)
    let settingsVocabulary = await MainActor.run {
      AssistantSettings.shared.effectiveVocabulary
    }

    var collector = KeywordCollector(limit: maxKeywords)
    for term in settingsVocabulary {
      collector.add(term)
    }

    let visibleText = await immediateOCRText
    if let visibleText, !visibleText.isEmpty {
      let clippedText = String(visibleText.prefix(maxImmediateOCRLength))
      collector.addExtractedTerms(from: clippedText, priority: true)
      collector.addVisibleTerms(from: clippedText)
    }

    for screenshot in screenshots {
      collector.add(screenshot.appName)
      if let title = screenshot.windowTitle {
        collector.add(title)
        collector.addExtractedTerms(from: title, priority: true)
      }
      if let ocrText = screenshot.ocrText, !ocrText.isEmpty {
        collector.addExtractedTerms(from: String(ocrText.prefix(maxTextLengthPerScreenshot)), priority: false)
      }
    }

    let keywords = collector.values
    let sample = keywords.prefix(12).joined(separator: ", ")
    let immediateSourceCount = (visibleText?.isEmpty == false) ? 1 : 0
    log("PTTContextVocabulary: captured \(keywords.count) keywords from \(screenshots.count) screenshots + \(immediateSourceCount) immediate OCR source(s); sample=[\(sample)]")
    return PTTContextSnapshot(
      capturedAt: date,
      keywords: keywords,
      sourceCount: screenshots.count + immediateSourceCount
    )
  }

  private static func loadContextScreenshots(around date: Date) async -> [Screenshot] {
    do {
      let startDate = date.addingTimeInterval(-lookbackSeconds)
      let screenshots = try await RewindDatabase.shared.getScreenshots(
        from: startDate,
        to: date.addingTimeInterval(2),
        limit: 12
      )
      if !screenshots.isEmpty {
        return screenshots
      }
      return try await RewindDatabase.shared.getRecentScreenshots(limit: 8)
    } catch {
      logError("PTTContextVocabulary: failed to load screenshot context", error: error)
      return []
    }
  }

  private static func captureImmediateScreenText(preferredImage: CGImage?) async -> String? {
    if let preferredImage,
       let text = await extractVisibleText(from: preferredImage) {
      log("PTTContextVocabulary: immediate OCR used pre-overlay display image")
      return text
    }

    let screenCaptureService = ScreenCaptureService()
    let activeWindowInfo = await ScreenCaptureService.getActiveWindowInfoAsync()
    let activeAppName = activeWindowInfo.appName?.lowercased() ?? ""
    let shouldCaptureActiveWindow = !isOmiApp(activeAppName)
    let activeWindowImage: CGImage?
    if shouldCaptureActiveWindow, let windowID = activeWindowInfo.windowID {
      switch await screenCaptureService.captureWindowCGImage(windowID: windowID) {
      case .success(let image):
        activeWindowImage = image
      case .windowGone, .failed:
        activeWindowImage = nil
      }
    } else {
      activeWindowImage = nil
      if !activeAppName.isEmpty {
        log("PTTContextVocabulary: skipped active-window OCR for Omi window (\(activeAppName))")
      }
    }

    let image: CGImage?
    if let activeWindowImage {
      image = activeWindowImage
    } else {
      image = await MainActor.run(resultType: CGImage?.self, body: {
        ScreenCaptureManager.captureScreenImage()
      })
    }

    guard let image else {
      return nil
    }

    return await extractVisibleText(from: image)
  }

  private static func extractVisibleText(from image: CGImage) async -> String? {
    do {
      let text = try await RewindOCRService.shared.extractText(from: image)
      let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
      if trimmed.isEmpty {
        log("PTTContextVocabulary: immediate OCR found no visible text")
        return nil
      }
      return trimmed
    } catch {
      logError("PTTContextVocabulary: immediate OCR failed", error: error)
      return nil
    }
  }

  private static func isOmiApp(_ appName: String) -> Bool {
    appName.contains("omi") || appName.contains("floating-agent")
  }
}

enum PTTTranscriptContextualCorrector {
  static func correct(_ transcript: String, keywords: [String]) -> String {
    let phraseCorrected = correctCommonPTTPhrases(in: transcript)
    let brandCorrected = correctOmiBrand(in: phraseCorrected)
    let terms = keywords
      .map { canonicalNameTerm($0) }
      .compactMap { $0 }
      .filter { $0.count >= 3 && $0.count <= 32 }

    guard !terms.isEmpty else { return brandCorrected }

    var corrected = brandCorrected
    var replacements: [(String, String)] = []

    let directedNameCorrected = correctDirectedNameObject(in: corrected, terms: terms)
    if directedNameCorrected != corrected {
      replacements.append((corrected, directedNameCorrected))
      corrected = directedNameCorrected
    }

    let greetingCorrected = correctGreetingTarget(in: corrected, terms: terms)
    if greetingCorrected != corrected {
      replacements.append((corrected, greetingCorrected))
      corrected = greetingCorrected
    }

    if corrected != transcript {
      log("PTTTranscriptCorrector: applied \(replacements.count) context correction(s)")
    }

    return corrected
  }

  private static func correctGreetingTarget(in text: String, terms: [String]) -> String {
    let patterns = [
      #"(?i)^\s*(?:hey|hi|hello|yo|lol|help|ok|okay)(?:\s+|[,.;:!?-]+\s*)([A-Za-z][A-Za-z'\-]{1,31})"#,
      #"(?i)^([A-Za-z][A-Za-z'\-]{1,31})(?=(?:[,.;:!?-]+\s*|\s+)(?:how|what|are|is|you)\b|[,.;:!?-])"#
    ]

    for pattern in patterns {
      guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
      let nsText = text as NSString
      guard let match = regex.firstMatch(in: text, range: NSRange(location: 0, length: nsText.length)),
            match.numberOfRanges > 1 else { continue }

      let candidate = nsText.substring(with: match.range(at: 1))
      guard !KeywordCollector.stopWords.contains(candidate.lowercased()),
            let replacement = bestGreetingTargetReplacement(for: candidate, terms: terms),
            replacement.caseInsensitiveCompare(candidate) != .orderedSame,
            let range = Range(match.range(at: 1), in: text)
      else { continue }

      var updated = text
      updated.replaceSubrange(range, with: replacement)
      log("PTTTranscriptCorrector: greeting target '\(candidate)' -> '\(replacement)'")
      return updated
    }

    return text
  }

  private static func correctDirectedNameObject(in text: String, terms: [String]) -> String {
    let patterns = [
      #"(?i)\b(?:say|tell|send)\s+(?:hi|hello|hey)\s+(?:to|two|too)\s+([A-Za-z][A-Za-z'\-]{1,31})\b"#,
      #"(?i)\b(?:say|tell|send)\s+([A-Za-z][A-Za-z'\-]{1,31})\s+(?:hi|hello|hey)\b"#
    ]

    for pattern in patterns {
      guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
      let nsText = text as NSString
      guard let match = regex.firstMatch(in: text, range: NSRange(location: 0, length: nsText.length)),
            match.numberOfRanges > 1 else { continue }

      let candidate = nsText.substring(with: match.range(at: 1))
      guard !KeywordCollector.stopWords.contains(candidate.lowercased()),
            let replacement = bestGreetingTargetReplacement(for: candidate, terms: terms),
            replacement.caseInsensitiveCompare(candidate) != .orderedSame,
            let range = Range(match.range(at: 1), in: text)
      else { continue }

      var updated = text
      updated.replaceSubrange(range, with: replacement)
      log("PTTTranscriptCorrector: directed name '\(candidate)' -> '\(replacement)'")
      return updated
    }

    return text
  }

  private static func bestGreetingTargetReplacement(for candidate: String, terms: [String]) -> String? {
    let lowerCandidate = candidate.lowercased()
    var best: (term: String, score: Int)?

    for term in terms {
      let canonical = canonicalNameTerm(term)
      guard let canonical else { continue }
      let lowerTerm = canonical.lowercased()
      guard lowerTerm != lowerCandidate else { continue }

      let score = greetingTargetScore(candidate: lowerCandidate, term: lowerTerm)
      guard score > 0 else { continue }
      if best == nil || score > best!.score {
        best = (canonical, score)
      }
    }

    return best?.term
  }

  private static func greetingTargetScore(candidate: String, term: String) -> Int {
    let collapsedCandidate = collapseRepeatedLetters(candidate)
    let collapsedTerm = collapseRepeatedLetters(term)
    if collapsedCandidate == collapsedTerm {
      return 124
    }

    if candidate.first == term.first {
      if candidate.count >= 3, candidate.count < term.count {
        let prefix = String(term.prefix(candidate.count))
        let prefixDistance = levenshtein(candidate, prefix)
        if prefixDistance == 0 { return 120 }
        if prefixDistance == 1 { return 112 }
      }

      let distance = levenshtein(candidate, term)
      if distance <= 2 { return 100 - distance }
      if distance <= 3 && min(candidate.count, term.count) >= 5 { return 80 - distance }

      let collapsedDistance = levenshtein(collapsedCandidate, collapsedTerm)
      if collapsedDistance <= 1 { return 98 - collapsedDistance }
    }

    if candidate.count > term.count {
      let maxSuffixLength = min(candidate.count, term.count + 3)
      for length in term.count...maxSuffixLength {
        let suffix = String(candidate.suffix(length))
        let distance = levenshtein(suffix, term)
        if distance <= 1 { return 118 - distance }
        if distance <= 2 && term.count >= 4 { return 96 - distance }
      }
    }

    if sharedSuffixLength(candidate, term) >= 3 {
      return 72
    }

    if phoneticTail(candidate) == phoneticTail(term), phoneticTail(candidate).count >= 2 {
      return 68
    }

    return 0
  }

  private static func collapseRepeatedLetters(_ value: String) -> String {
    var output = ""
    var previous: Character?
    for character in value.lowercased() {
      guard character >= "a", character <= "z" else { continue }
      if character != previous {
        output.append(character)
      }
      previous = character
    }
    return output
  }

  private static func sharedSuffixLength(_ lhs: String, _ rhs: String) -> Int {
    let left = Array(lhs.reversed())
    let right = Array(rhs.reversed())
    var count = 0
    for index in 0..<min(left.count, right.count) {
      guard left[index] == right[index] else { break }
      count += 1
    }
    return count
  }

  private static func phoneticTail(_ value: String) -> String {
    value.lowercased()
      .replacingOccurrences(of: #"[^a-z]"#, with: "", options: .regularExpression)
      .replacingOccurrences(of: #"[aeiouy]"#, with: "", options: .regularExpression)
      .replacingOccurrences(of: #"([a-z])\1+"#, with: "$1", options: .regularExpression)
  }

  private static func correctOmiBrand(in text: String) -> String {
    let pattern = #"\b(?:omi|omni|omie|omy|ohmi|oh me)\b"#
    guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
      return text
    }
    return regex.stringByReplacingMatches(
      in: text,
      range: NSRange(location: 0, length: (text as NSString).length),
      withTemplate: "Omi"
    )
  }

  private static func correctCommonPTTPhrases(in text: String) -> String {
    let replacements: [(pattern: String, template: String)] = [
      (#"\bHome are you\b"#, "How are you")
    ]

    var updated = text
    for replacement in replacements {
      guard let regex = try? NSRegularExpression(pattern: replacement.pattern, options: [.caseInsensitive]) else {
        continue
      }
      updated = regex.stringByReplacingMatches(
        in: updated,
        range: NSRange(location: 0, length: (updated as NSString).length),
        withTemplate: replacement.template
      )
    }
    return updated
  }

  private static func canonicalNameTerm(_ raw: String) -> String? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
      .trimmingCharacters(in: CharacterSet(charactersIn: ".,;:()[]{}<>\"'"))
    guard !trimmed.isEmpty else { return nil }
    guard trimmed.range(of: #"^[A-Za-z][A-Za-z'\-]{2,31}$"#, options: .regularExpression) != nil else { return nil }
    guard !KeywordCollector.stopWords.contains(trimmed.lowercased()) else { return nil }
    if trimmed == trimmed.uppercased(),
       trimmed.count <= 4,
       trimmed.caseInsensitiveCompare("Omi") != .orderedSame {
      return nil
    }
    return trimmed
  }

  private static func levenshtein(_ lhs: String, _ rhs: String) -> Int {
    let left = Array(lhs)
    let right = Array(rhs)
    guard !left.isEmpty else { return right.count }
    guard !right.isEmpty else { return left.count }

    var previous = Array(0...right.count)
    for (i, leftChar) in left.enumerated() {
      var current = [i + 1]
      for (j, rightChar) in right.enumerated() {
        if leftChar == rightChar {
          current.append(previous[j])
        } else {
          current.append(min(previous[j], previous[j + 1], current[j]) + 1)
        }
      }
      previous = current
    }
    return previous[right.count]
  }
}

actor PTTTranscriptCleanupService {
  static let shared = PTTTranscriptCleanupService()

  private let maxContextTerms = 40

  func cleanup(_ transcript: String, keywords: [String]) async -> String {
    let trimmed = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.count >= 4, trimmed.count <= 500 else { return transcript }

    let context = contextTerms(from: keywords)
    let contextText = context.isEmpty ? "None" : context.joined(separator: ", ")
    let prompt = """
      Raw ASR transcript:
      \(trimmed)

      Visible/context terms:
      \(contextText)

      Correct the transcript for obvious speech-to-text errors. Use visible/context terms only to fix proper nouns and product/company names.

      Rules:
      - Return only the corrected transcript, no quotes or explanation.
      - Preserve the user's meaning and wording as much as possible.
      - Do not answer the question.
      - Do not add facts not implied by the raw transcript.
      - Prefer Omi for the company/product name.
      - If uncertain, leave the phrase unchanged.
      """

    do {
      let response = try await withTimeout(seconds: 2) {
        let client = try GeminiClient(model: ModelQoS.Gemini.proactive)
        return try await client.sendTextRequest(
          prompt: prompt,
          systemPrompt: "You clean up short voice ASR transcripts. Return only the corrected transcript.",
          maxRetries: 0,
          timeout: 2
        )
      }
      let cleaned = sanitize(response)
      guard shouldUse(cleaned: cleaned, original: trimmed) else { return transcript }
      if cleaned != trimmed {
        log("PTTTranscriptCleanup: '\(trimmed)' -> '\(cleaned)'")
      }
      return cleaned
    } catch {
      logError("PTTTranscriptCleanup: failed", error: error)
      return transcript
    }
  }

  private func contextTerms(from keywords: [String]) -> [String] {
    var seen = Set<String>()
    var terms: [String] = []
    let pattern = #"\b[A-Za-z][A-Za-z'\-]{1,31}\b"#

    for keyword in keywords {
      let normalized = keyword
        .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        .trimmingCharacters(in: .whitespacesAndNewlines)
      guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
      let nsText = normalized as NSString
      for match in regex.matches(in: normalized, range: NSRange(location: 0, length: nsText.length)) {
        let term = nsText.substring(with: match.range)
        let key = term.lowercased()
        guard !KeywordCollector.stopWords.contains(key), !seen.contains(key) else { continue }
        seen.insert(key)
        terms.append(term)
        if terms.count >= maxContextTerms {
          return terms
        }
      }
    }

    return terms
  }

  private func sanitize(_ raw: String) -> String {
    raw.trimmingCharacters(in: .whitespacesAndNewlines)
      .replacingOccurrences(of: #"^["'`]+|["'`]+$"#, with: "", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  private func shouldUse(cleaned: String, original: String) -> Bool {
    guard !cleaned.isEmpty else { return false }
    guard cleaned.count <= max(original.count * 3, original.count + 80) else { return false }
    guard cleaned.range(of: "\n") == nil else { return false }
    return true
  }

  private func withTimeout<T: Sendable>(
    seconds: UInt64,
    operation: @escaping @Sendable () async throws -> T
  ) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
      group.addTask {
        try await operation()
      }
      group.addTask {
        try await Task.sleep(nanoseconds: seconds * 1_000_000_000)
        throw CancellationError()
      }
      guard let result = try await group.next() else {
        throw CancellationError()
      }
      group.cancelAll()
      return result
    }
  }
}

private struct KeywordCollector {
  static let stopWords: Set<String> = [
    "about", "after", "again", "all", "also", "and", "app", "are", "ask", "back", "browser", "but", "can",
    "chat", "code", "done", "each", "for", "from", "has", "have", "here", "into", "just", "like", "more",
    "hello", "hi", "next", "not", "now", "okay", "open", "orange", "question", "reply", "running", "said",
    "say", "send", "sent", "show", "some", "task", "tell", "test", "text", "that", "the", "this", "thread",
    "time", "to", "too", "two", "use", "user", "voice", "was", "what", "when", "with", "you", "your"
  ]

  private let limit: Int
  private var seen = Set<String>()
  private(set) var values: [String] = []

  init(limit: Int) {
    self.limit = limit
  }

  mutating func add(_ raw: String) {
    guard values.count < limit else { return }
    let term = raw.trimmingCharacters(in: .whitespacesAndNewlines)
      .trimmingCharacters(in: CharacterSet(charactersIn: ".,;:()[]{}<>\"'"))
    guard term.count >= 2 && term.count <= 80 else { return }
    guard term.rangeOfCharacter(from: .letters) != nil else { return }
    let key = term.lowercased()
    guard !Self.stopWords.contains(key), !seen.contains(key) else { return }
    seen.insert(key)
    values.append(term)
  }

  mutating func addExtractedTerms(from text: String, priority: Bool) {
    let patterns = [
      #"\b[A-Z][A-Za-z'\-]{2,}(?:\s+[A-Z][A-Za-z'\-]{2,}){1,2}\b"#,
      #"\b[A-Z][A-Za-z'\-]{2,}\b"#,
      #"\b[A-Z]{2,8}\b"#
    ]

    for pattern in patterns {
      guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
      let nsText = text as NSString
      let matches = regex.matches(in: text, range: NSRange(location: 0, length: nsText.length))
      for match in matches {
        let term = nsText.substring(with: match.range)
        if priority {
          add(term)
        } else if values.count < limit {
          add(term)
        }
      }
    }
  }

  mutating func addVisibleTerms(from text: String) {
    let pattern = #"\b[A-Za-z][A-Za-z'\-]{1,31}\b"#
    guard let regex = try? NSRegularExpression(pattern: pattern) else { return }

    let nsText = text as NSString
    let matches = regex.matches(in: text, range: NSRange(location: 0, length: nsText.length))

    for match in matches {
      add(nsText.substring(with: match.range))
      guard values.count < limit else { return }
    }
  }
}
