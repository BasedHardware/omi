import Foundation

/// Durable provenance for an inline answer citation. The numeric marker is presentation; this
/// canonical reference is what navigation and preview use.
struct ChatCitationReference: Equatable, Sendable {
  enum Kind: String, Equatable, Sendable {
    case conversation
    case memory
    case task
    case goal
    case screenshot
    case web
    case unavailable

    var title: String {
      switch self {
      case .conversation: return "Conversation"
      case .memory: return "Memory"
      case .task: return "Task"
      case .goal: return "Goal"
      case .screenshot: return "Rewind"
      case .web: return "Web"
      case .unavailable: return "Source unavailable"
      }
    }

    var systemImage: String {
      switch self {
      case .conversation: return "text.bubble"
      case .memory: return "brain.head.profile"
      case .task: return "checkmark.circle"
      case .goal: return "target"
      case .screenshot: return "clock.arrow.circlepath"
      case .web: return "globe"
      case .unavailable: return "questionmark.circle"
      }
    }
  }

  let ordinal: Int
  let kind: Kind
  let sourceID: String
  let title: String
  let preview: String
  let momentTimestampMs: Int?
  let createdAt: String?
  let appName: String?
  let url: URL?

  init(
    ordinal: Int,
    kind: Kind,
    sourceID: String,
    title: String = "",
    preview: String = "",
    momentTimestampMs: Int? = nil,
    createdAt: String? = nil,
    appName: String? = nil,
    url: URL? = nil
  ) {
    self.ordinal = ordinal
    self.kind = kind
    self.sourceID = Self.bounded(sourceID, limit: 512, flattenLines: true)
    self.title = Self.bounded(title, limit: 160, flattenLines: true)
    self.preview = Self.bounded(preview, limit: 600, flattenLines: false)
    self.momentTimestampMs = momentTimestampMs
    self.createdAt = createdAt.map { Self.bounded($0, limit: 80, flattenLines: true) }
    self.appName = appName.map { Self.bounded($0, limit: 80, flattenLines: true) }
    self.url = url
  }

  private static func bounded(_ value: String, limit: Int, flattenLines: Bool) -> String {
    let normalized =
      flattenLines
      ? value.replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      : value
    return String(normalized.prefix(limit))
  }

  var displayTitle: String {
    let trimmed = title.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? kind.title : trimmed
  }

  var displayPreview: String {
    let trimmed = preview.trimmingCharacters(in: .whitespacesAndNewlines)
    return trimmed.isEmpty ? "Preview unavailable" : trimmed
  }

  static func merging(_ lists: [ChatCitationReference]...) -> [ChatCitationReference] {
    var result = [ChatCitationReference]()
    for list in lists {
      for reference in list {
        let duplicate = result.contains {
          $0.ordinal == reference.ordinal && $0.kind == reference.kind && $0.sourceID == reference.sourceID
        }
        if !duplicate { result.append(reference) }
      }
    }
    return result
  }

  /// Adds lookup-only sources (local memories/conversations) without colliding with prompt or tool ordinals.
  static func appendingLookup(
    _ extras: [ChatCitationReference],
    to existing: [ChatCitationReference]
  ) -> [ChatCitationReference] {
    var result = existing
    var seen = Set(existing.map { "\($0.kind.rawValue):\($0.sourceID)" })
    var nextOrdinal = max(8000, existing.map(\.ordinal).max() ?? 0) + 1
    for extra in extras {
      let sourceID = extra.sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
      guard extra.kind != .unavailable, !sourceID.isEmpty else { continue }
      let key = "\(extra.kind.rawValue):\(sourceID)"
      guard seen.insert(key).inserted else { continue }
      result.append(
        ChatCitationReference(
          ordinal: nextOrdinal,
          kind: extra.kind,
          sourceID: sourceID,
          title: extra.title,
          preview: extra.preview,
          momentTimestampMs: extra.momentTimestampMs,
          createdAt: extra.createdAt,
          appName: extra.appName,
          url: extra.url
        ))
      nextOrdinal += 1
    }
    return result
  }

  var canOpen: Bool {
    guard ordinal > 0 else { return false }
    switch kind {
    case .web:
      guard let url, let scheme = url.scheme?.lowercased() else { return false }
      return (scheme == "http" || scheme == "https") && url.host != nil
    case .unavailable:
      return false
    default:
      return !sourceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    }
  }
}

/// A canonical source admitted directly into the model context before a run exists. Tool-returned
/// sources use low ordinals assigned by `ChatCitationProvenanceRegistry`; prompt sources use a
/// disjoint range so both ledgers can be merged safely when the terminal result arrives.
struct ChatPromptCitationSource: Equatable, Sendable {
  let kind: ChatCitationReference.Kind
  let sourceID: String
  let title: String
  let preview: String
  let createdAt: String?
}

struct ChatPromptCitationLedger: Equatable, Sendable {
  static let firstOrdinal = 5001
  static let maximumReferences = 128

  let references: [ChatCitationReference]

  init(sources: [ChatPromptCitationSource]) {
    var seen = Set<String>()
    var values = [ChatCitationReference]()
    for source in sources {
      let sourceID = source.sourceID.trimmingCharacters(in: .whitespacesAndNewlines)
      guard source.kind != .unavailable, !sourceID.isEmpty else { continue }
      let key = "\(source.kind.rawValue):\(sourceID)"
      guard seen.insert(key).inserted else { continue }
      values.append(
        ChatCitationReference(
          ordinal: Self.firstOrdinal + values.count,
          kind: source.kind,
          sourceID: sourceID,
          title: source.title,
          preview: source.preview,
          createdAt: source.createdAt
        ))
      if values.count >= Self.maximumReferences { break }
    }
    references = values
  }

  func marker(kind: ChatCitationReference.Kind, sourceID: String) -> String? {
    references.first { $0.kind == kind && $0.sourceID == sourceID }
      .map { "[\($0.ordinal)]" }
  }

  var responseInstruction: String? {
    guard !references.isEmpty else { return nil }
    return
      "Source markers such as [5001] in the supplied context are citations. "
      + "Copy every relevant numeric marker exactly, for example [5001], at the end of each claim grounded in that source. "
      + "Never write [memory], [conversation], or other kind labels as citations. "
      + "Do not claim to provide citations without emitting the markers, and do not invent markers."
  }
}

enum ChatCitationMarkup {
  /// Bare `[20]` or a kind-prefixed copy of the context label (`[memory 5023]`, `[task:12]`).
  static let numericMarkerPattern =
    #"\[(?:(?:memory|task|goal|conversation|screenshot|web|source|capture|rewind)[:\s]+)?(\d{1,4})\](?!\()"#
  /// Same markers, including numeric markdown links the citation mask still has to replace.
  static let numericMarkerOrMarkdownLinkPattern =
    #"\[(?:(?:memory|task|goal|conversation|screenshot|web|source|capture|rewind)[:\s]+)?(\d{1,4})\](?:\(https?://[^\s)]+\))?"#
  /// Kind-only copies such as `[memory]` or `[conversation]` with no ordinal.
  static let kindOnlyMarkerPattern =
    #"\[(memory|task|goal|conversation|screenshot|web|source|capture|rewind)\](?![\s:]*\d)"#

  static func explicitlyRequestsSources(_ text: String) -> Bool {
    guard
      let expression = try? NSRegularExpression(
        pattern: #"\b(?:citations?|cite|sources)\b"#, options: [.caseInsensitive])
    else { return false }
    return expression.firstMatch(
      in: text,
      range: NSRange(text.startIndex..<text.endIndex, in: text)) != nil
  }

  /// Numeric citations outside inline-code spans, in reading order. Incomplete streaming markers
  /// and bracketed prose are left alone. Kind-prefixed copies such as `[memory 5023]` still count.
  static func ordinals(in text: String) -> [Int] {
    markerMatches(in: text, pattern: numericMarkerPattern).map(\.ordinal)
  }

  static func markerMatches(
    in text: String,
    pattern: String
  ) -> [(range: Range<String.Index>, ordinal: Int)] {
    let codeRanges = OmiMarkdownInlineCode.codeSpanRanges(in: text)
    guard
      let expression = try? NSRegularExpression(
        pattern: pattern, options: [.caseInsensitive])
    else { return [] }
    let nsRange = NSRange(text.startIndex..<text.endIndex, in: text)
    return expression.matches(in: text, range: nsRange).compactMap { match in
      guard let full = Range(match.range(at: 0), in: text),
        !codeRanges.contains(where: { $0.overlaps(full) }),
        let digits = Range(match.range(at: 1), in: text),
        let ordinal = Int(text[digits])
      else { return nil }
      return (full, ordinal)
    }
  }

  static func containsKindOnlyMarkers(_ text: String) -> Bool {
    !kindOnlyMatches(in: text).isEmpty
  }

  /// References a follow-up borrows from the turns before it.
  ///
  /// Ordinals are assigned per attempt, so `[1]` in one answer and `[1]` in the
  /// next can name different sources. But a turn that retrieved nothing has no
  /// ordinals of its own, and when the model writes `[1]` there it is pointing
  /// back at the list the reader was just shown — "pick one conversation from
  /// that day" answered without a tool call is exactly this. Left unbound the
  /// marker drew as plain text next to a title the reader could not open.
  ///
  /// Only ordinals this turn cannot resolve itself are borrowed, and each from
  /// the nearest earlier assistant turn that persisted it, so a turn's own
  /// provenance always outranks the past and a stale list is never reached
  /// past a fresher one that has the same number.
  static func inheritedReferences(
    citedIn message: ChatMessage,
    resolved: [ChatCitationReference],
    earlierTurns: [ChatMessage],
    lookback: Int = 8
  ) -> [ChatCitationReference] {
    var unresolved = message.citedCitationOrdinals.subtracting(resolved.map(\.ordinal))
    guard !unresolved.isEmpty else { return [] }
    var inherited = [ChatCitationReference]()
    var searched = 0
    for earlier in earlierTurns.reversed() where earlier.sender == .ai && earlier.id != message.id {
      guard searched < lookback else { break }
      searched += 1
      for block in earlier.contentBlocks {
        guard case .citation(_, let reference) = block, unresolved.remove(reference.ordinal) != nil
        else { continue }
        inherited.append(reference)
      }
      if unresolved.isEmpty { break }
    }
    return inherited.sorted { $0.ordinal < $1.ordinal }
  }

  /// Replace `[memory]` / `[conversation]` with the numeric marker for the best matching source of
  /// that kind. Unmatched labels stay inert instead of opening a random row.
  static func resolvingKindLabels(
    in text: String,
    using references: [ChatCitationReference],
    allowUniqueKindFallback: Bool = true
  ) -> (text: String, references: [ChatCitationReference]) {
    let matches = kindOnlyMatches(in: text)
    guard !matches.isEmpty else { return (text, []) }
    var pool = [ChatCitationReference.Kind: [ChatCitationReference]]()
    for reference in references where reference.canOpen {
      pool[reference.kind, default: []].append(reference)
    }
    var used = Set<String>()
    var replacements = [(range: Range<String.Index>, marker: String, reference: ChatCitationReference)]()
    for match in matches {
      guard let kind = kind(fromLabel: match.label),
        let chosen = pickReference(
          kind: kind,
          claim: claimText(before: match.range, in: text),
          pool: pool[kind] ?? [],
          used: &used,
          allowUniqueKindFallback: allowUniqueKindFallback)
      else { continue }
      replacements.append((match.range, "[\(chosen.ordinal)]", chosen))
    }
    guard !replacements.isEmpty else { return (text, []) }
    var rewritten = text
    for replacement in replacements.reversed() {
      rewritten.replaceSubrange(replacement.range, with: replacement.marker)
    }
    var bound = [ChatCitationReference]()
    var seen = Set<String>()
    for replacement in replacements {
      let key = "\(replacement.reference.kind.rawValue):\(replacement.reference.sourceID)"
      if seen.insert(key).inserted {
        bound.append(replacement.reference)
      }
    }
    return (rewritten, bound)
  }

  private static func kindOnlyMatches(
    in text: String
  ) -> [(range: Range<String.Index>, label: String)] {
    let codeRanges = OmiMarkdownInlineCode.codeSpanRanges(in: text)
    guard
      let expression = try? NSRegularExpression(
        pattern: kindOnlyMarkerPattern, options: [.caseInsensitive])
    else { return [] }
    let nsRange = NSRange(text.startIndex..<text.endIndex, in: text)
    return expression.matches(in: text, range: nsRange).compactMap { match in
      guard let full = Range(match.range(at: 0), in: text),
        !codeRanges.contains(where: { $0.overlaps(full) }),
        let labelRange = Range(match.range(at: 1), in: text)
      else { return nil }
      return (full, String(text[labelRange]).lowercased())
    }
  }

  private static func kind(fromLabel label: String) -> ChatCitationReference.Kind? {
    switch label.lowercased() {
    case "memory": return .memory
    case "conversation", "capture": return .conversation
    case "task": return .task
    case "goal": return .goal
    case "screenshot", "rewind": return .screenshot
    case "web": return .web
    default: return nil
    }
  }

  private static func claimText(before range: Range<String.Index>, in text: String) -> String {
    let prefix = text[text.startIndex..<range.lowerBound]
    let lineStart = prefix.lastIndex(of: "\n").map { text.index(after: $0) } ?? text.startIndex
    return String(text[lineStart..<range.lowerBound]).trimmingCharacters(in: .whitespaces)
  }

  private static func sourceKey(_ reference: ChatCitationReference) -> String {
    "\(reference.kind.rawValue):\(reference.sourceID)"
  }

  private static func pickReference(
    kind: ChatCitationReference.Kind,
    claim: String,
    pool: [ChatCitationReference],
    used: inout Set<String>,
    allowUniqueKindFallback: Bool
  ) -> ChatCitationReference? {
    guard !pool.isEmpty else { return nil }
    if pool.count == 1 {
      if allowUniqueKindFallback { return pool[0] }
      return overlapScore(claim: claim, reference: pool[0]) >= 2 ? pool[0] : nil
    }
    let scored = pool.map { ($0, overlapScore(claim: claim, reference: $0)) }
    let unused = scored.filter { !used.contains(sourceKey($0.0)) }
    func uniqueBest(in candidates: [(ChatCitationReference, Int)]) -> ChatCitationReference? {
      guard let best = candidates.max(by: { $0.1 < $1.1 }), best.1 >= 2 else { return nil }
      let tied = candidates.filter { $0.1 == best.1 }
      guard tied.count == 1 else { return nil }
      return best.0
    }
    if let best = uniqueBest(in: unused) {
      used.insert(sourceKey(best))
      return best
    }
    return uniqueBest(in: scored)
  }

  static func kindOnlySearchQueries(
    in text: String
  ) -> [(kind: ChatCitationReference.Kind, query: String, fallback: String)] {
    kindOnlyMatches(in: text).compactMap { match in
      guard let kind = kind(fromLabel: match.label) else { return nil }
      let claim = claimText(before: match.range, in: text)
      return (kind, searchQuery(fromClaim: claim), searchFallback(fromClaim: claim))
    }
  }

  static func searchQuery(fromClaim claim: String) -> String {
    let bold = firstBoldPhrase(in: claim)
    if let bold, bold.count >= 4 { return sanitizeSearchQuery(bold) }
    return sanitizeSearchQuery(tokenize(claim).sorted { $0.count > $1.count }.prefix(4).joined(separator: " "))
  }

  private static func searchFallback(fromClaim claim: String) -> String {
    tokenize(claim).first { $0.count >= 6 }.map(sanitizeSearchQuery) ?? ""
  }

  private static func overlapScore(claim: String, reference: ChatCitationReference) -> Int {
    let haystack = (reference.title + " " + reference.preview).lowercased()
    if let bold = firstBoldPhrase(in: claim), bold.count >= 8, haystack.contains(bold) {
      return 100
    }
    let stripped = strippedClaim(claim)
    if stripped.count >= 12, haystack.contains(stripped) { return 100 }
    let haystackWords = Set(tokenize(haystack))
    return tokenize(claim).filter { haystackWords.contains($0) }.count
  }

  private static func firstBoldPhrase(in claim: String) -> String? {
    guard let expression = try? NSRegularExpression(pattern: #"\*\*(.+?)\*\*"#),
      let match = expression.firstMatch(
        in: claim, range: NSRange(claim.startIndex..<claim.endIndex, in: claim)),
      let range = Range(match.range(at: 1), in: claim)
    else { return nil }
    let phrase = String(claim[range]).trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    return phrase.isEmpty ? nil : phrase
  }

  private static func strippedClaim(_ claim: String) -> String {
    claim.replacingOccurrences(of: "*", with: "")
      .replacingOccurrences(of: "`", with: "")
      .trimmingCharacters(in: .whitespacesAndNewlines)
      .lowercased()
  }

  private static func tokenize(_ text: String) -> [String] {
    text.lowercased().split { !$0.isLetter }.map(String.init).filter {
      $0.count >= 4 && !overlapStopwords.contains($0)
    }
  }

  private static let overlapStopwords: Set<String> = [
    "about", "after", "around", "asked", "been", "being", "could", "from", "have", "into",
    "issue", "just", "later", "make", "made", "other", "planned", "should", "than", "that",
    "their", "them", "then", "there", "these", "they", "this", "those", "today", "used",
    "using", "were", "what", "when", "where", "which", "while", "with", "would", "your",
  ]

  private static func sanitizeSearchQuery(_ value: String) -> String {
    let allowed = value.unicodeScalars.filter {
      CharacterSet.alphanumerics.union(.whitespaces).contains($0)
    }
    return String(String.UnicodeScalarView(allowed))
      .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
      .trimmingCharacters(in: .whitespacesAndNewlines)
  }

  /// Resolve only durable, explicit provenance. A visible ordinal and an independently ordered
  /// rich-link list are not an authoritative mapping, so legacy markers remain inert instead of
  /// opening a plausible-but-wrong source.
  static func references(text: String, blocks: [ChatContentBlock]) -> [ChatCitationReference] {
    let explicit = blocks.compactMap { block -> ChatCitationReference? in
      guard case .citation(_, let reference) = block else { return nil }
      return reference
    }
    let web = webReferences(in: text)
    let occupied = Set(explicit.map(\.ordinal))
    return explicit + web.filter { !occupied.contains($0.ordinal) }
  }

  /// Rich blocks are an authoritative selection made by the model. If it omits inline markers
  /// after rendering those blocks, retain source discoverability as one compact inline fallback.
  ///
  /// `renderedEntityIDs` are the entities the turn already draws as their own
  /// components. A rendered task card is a better citation of that task than
  /// `[3]` is — it opens the same thing and says what it is — so a rail that
  /// only repeats those ids is noise printed under the cards, and now that
  /// components are a turn's whole answer rather than a garnish, it is noise on
  /// every such turn.
  static func appendingSelectedSources(
    to text: String,
    selectedReferences: [ChatCitationReference],
    requestedSources: Bool = false,
    retrievedReferences: [ChatCitationReference] = [],
    renderedEntityIDs: Set<String> = []
  ) -> String {
    let selection = selectedReferences.isEmpty && requestedSources ? retrievedReferences : selectedReferences
    let fallback = selection.filter { !renderedEntityIDs.contains($0.sourceID) }
    guard !fallback.isEmpty else { return text }
    let fallbackOrdinals = Set(fallback.map(\.ordinal))
    let hasResolvedNumericCitation = ordinals(in: text).contains { fallbackOrdinals.contains($0) }
    // Markdown web citations are already a complete, user-openable citation even though the
    // numeric parser intentionally excludes their labels. Do not append a second source rail.
    guard !hasResolvedNumericCitation, webReferences(in: text).isEmpty else { return text }
    let markers = fallback.prefix(8).map { "[\($0.ordinal)]" }.joined()
    return text + "\n\nSources: \(markers)"
  }

  /// The entities this turn already draws as components, by the id a citation
  /// would carry for the same thing.
  static func renderedEntityIDs(in blocks: [ChatContentBlock]) -> Set<String> {
    var identifiers = Set<String>()
    for block in blocks {
      switch block {
      case .taskCard(_, let taskId): identifiers.insert(taskId)
      case .goalLink(_, let goalId, _): identifiers.insert(goalId)
      case .captureLink(_, let conversationId, _, _): identifiers.insert(conversationId)
      case .conversationLink(_, let conversationId, _, _): identifiers.insert(conversationId)
      case .memoryLink(_, let memoryId, _): identifiers.insert(memoryId)
      default: continue
      }
    }
    return identifiers
  }

  private static func webReferences(in text: String) -> [ChatCitationReference] {
    guard
      let expression = try? NSRegularExpression(
        pattern: #"\[(\d{1,4})\]\((https?://[^\s)]+)\)"#)
    else { return [] }
    let codeRanges = OmiMarkdownInlineCode.codeSpanRanges(in: text)
    var seen = Set<Int>()
    return expression.matches(
      in: text, range: NSRange(text.startIndex..<text.endIndex, in: text)
    ).compactMap { match in
      guard let full = Range(match.range(at: 0), in: text),
        !codeRanges.contains(where: { $0.overlaps(full) }),
        let digits = Range(match.range(at: 1), in: text),
        let ordinal = Int(text[digits]),
        seen.insert(ordinal).inserted,
        let value = Range(match.range(at: 2), in: text),
        let url = URL(string: String(text[value])),
        let scheme = url.scheme?.lowercased(), scheme == "http" || scheme == "https"
      else { return nil }
      return ChatCitationReference(
        ordinal: ordinal,
        kind: .web,
        sourceID: url.absoluteString,
        title: url.host ?? "Web source",
        preview: url.absoluteString,
        url: url)
    }
  }

}

extension ChatMessage {
  var inlineCitationReferences: [ChatCitationReference] {
    ChatCitationMarkup.references(text: text, blocks: contentBlocks)
  }

  var hasKindOnlyCitationMarkers: Bool {
    if ChatCitationMarkup.containsKindOnlyMarkers(text) { return true }
    return contentBlocks.contains { block in
      if case .text(_, let blockText) = block {
        return ChatCitationMarkup.containsKindOnlyMarkers(blockText)
      }
      return false
    }
  }

  var hasPersistedCitationBlocks: Bool {
    contentBlocks.contains { block in
      if case .citation = block { return true }
      return false
    }
  }

  mutating func bindInlineCitations(
    using references: [ChatCitationReference],
    allowUniqueKindFallback: Bool = true
  ) {
    rewriteKindOnlyCitations(using: references, allowUniqueKindFallback: allowUniqueKindFallback)
    persistCitedReferences(from: references)
  }

  mutating func rewriteKindOnlyCitations(
    using references: [ChatCitationReference],
    allowUniqueKindFallback: Bool = true
  ) {
    text =
      ChatCitationMarkup.resolvingKindLabels(
        in: text, using: references, allowUniqueKindFallback: allowUniqueKindFallback
      ).text
    contentBlocks = contentBlocks.map { block in
      guard case .text(let id, let blockText) = block else { return block }
      return .text(
        id: id,
        text: ChatCitationMarkup.resolvingKindLabels(
          in: blockText, using: references, allowUniqueKindFallback: allowUniqueKindFallback
        ).text)
    }
  }

  /// Every numeric marker the answer writes, in its body and its text blocks.
  var citedCitationOrdinals: Set<Int> {
    var cited = Set(ChatCitationMarkup.ordinals(in: text))
    for block in contentBlocks {
      if case .text(_, let blockText) = block {
        cited.formUnion(ChatCitationMarkup.ordinals(in: blockText))
      }
    }
    return cited
  }

  mutating func persistCitedReferences(from references: [ChatCitationReference]) {
    let cited = citedCitationOrdinals
    let existing = Set(
      contentBlocks.compactMap { block -> Int? in
        guard case .citation(_, let reference) = block else { return nil }
        return reference.ordinal
      })
    contentBlocks.append(
      contentsOf: references.filter {
        cited.contains($0.ordinal) && !existing.contains($0.ordinal)
      }.map { reference in
        .citation(
          id: "citation-\(reference.ordinal)-\(reference.sourceID)",
          reference: reference)
      })
  }

  /// The adapter's terminal result is the complete provider response. Streaming
  /// deltas are only a low-latency projection and may legally omit the final
  /// chunk, so a successful turn must settle its visible answer from this text
  /// before citation decoration and journal persistence.
  mutating func applyAuthoritativeTerminalAnswer(_ terminalText: String) {
    guard !terminalText.isEmpty else { return }

    text = terminalText
    let lastToolIndex = contentBlocks.lastIndex { block in
      if case .toolCall = block { return true }
      return false
    }
    let answerStartIndex = lastToolIndex.map { $0 + 1 } ?? contentBlocks.startIndex
    var reconciled: [ChatContentBlock] = []
    var replacedAnswerText = false

    for (index, block) in contentBlocks.enumerated() {
      guard index >= answerStartIndex, case .text(let id, _) = block else {
        reconciled.append(block)
        continue
      }
      if !replacedAnswerText {
        reconciled.append(.text(id: id, text: terminalText))
        replacedAnswerText = true
      }
    }

    if !replacedAnswerText {
      let insertionIndex = lastToolIndex.map { min($0 + 1, reconciled.count) } ?? 0
      reconciled.insert(.text(id: "\(id):terminal", text: terminalText), at: insertionIndex)
    }
    contentBlocks = reconciled
  }

  mutating func applySelectedSourceFallback(
    selectedReferences: [ChatCitationReference],
    requestedSources: Bool,
    retrievedReferences: [ChatCitationReference],
    fallbackText: String = ""
  ) {
    let rendered = ChatCitationMarkup.renderedEntityIDs(in: contentBlocks)
    func apply(_ value: String) -> String {
      ChatCitationMarkup.appendingSelectedSources(
        to: value,
        selectedReferences: selectedReferences,
        requestedSources: requestedSources,
        retrievedReferences: retrievedReferences,
        renderedEntityIDs: rendered)
    }
    if text.isEmpty {
      text = fallbackText
    }
    text = apply(text)
    guard let index = lastVisibleAnswerTextIndex,
      case .text(let id, let blockText) = contentBlocks[index]
    else { return }
    contentBlocks[index] = .text(id: id, text: apply(blockText))
  }

  private var lastVisibleAnswerTextIndex: Int? {
    func lastNonEmptyText(in range: Range<Int>) -> Int? {
      for index in range.reversed() {
        if case .text(_, let text) = contentBlocks[index],
          !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        {
          return index
        }
      }
      return nil
    }
    let lastTool = contentBlocks.lastIndex { block in
      if case .toolCall = block { return true }
      return false
    }
    if let lastTool {
      if let after = lastNonEmptyText(in: (lastTool + 1)..<contentBlocks.count) {
        return after
      }
      return lastNonEmptyText(in: contentBlocks.startIndex..<lastTool)
    }
    return lastNonEmptyText(in: contentBlocks.indices)
  }
}

/// Per-attempt source ledger. Tool output teaches the model the assigned ordinals; the terminal
/// result consumes the same ledger and persists the canonical references. Attempt identity prevents
/// a late or retried tool result from contaminating another answer.
actor ChatCitationProvenanceRegistry {
  static let shared = ChatCitationProvenanceRegistry()

  private struct Key: Hashable {
    let runID: String
    let attemptID: String
  }

  private struct Bucket {
    var references: [ChatCitationReference]
    var selectedKeys: Set<String>
    var lastAccess: Date
  }

  struct Snapshot: Sendable {
    let references: [ChatCitationReference]
    let selectedReferences: [ChatCitationReference]
  }

  private var buckets: [Key: Bucket] = [:]
  private let maximumBuckets = 64
  private let maximumReferencesPerBucket = 128
  private let maximumIdleInterval: TimeInterval = 60 * 60

  func register(
    _ sources: [APIClient.ToolSource],
    runID: String?,
    attemptID: String?
  ) -> [ChatCitationReference] {
    guard let runID, let attemptID,
      !runID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !attemptID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !sources.isEmpty
    else { return [] }
    pruneExpired(now: Date())
    let key = Key(runID: runID, attemptID: attemptID)
    var bucket = buckets[key]?.references ?? []
    var added = [ChatCitationReference]()
    for source in sources {
      guard let kind = ChatCitationReference.Kind(rawValue: source.kind), !source.sourceID.isEmpty else {
        continue
      }
      if let existing = bucket.first(where: {
        $0.kind == kind && $0.sourceID == source.sourceID
      }) {
        added.append(existing)
        continue
      }
      guard bucket.count < maximumReferencesPerBucket else { break }
      let reference = ChatCitationReference(
        ordinal: bucket.count + 1,
        kind: kind,
        sourceID: source.sourceID,
        title: source.title,
        preview: source.preview,
        momentTimestampMs: source.momentTimestampMs,
        createdAt: source.createdAt,
        appName: source.appName,
        url: source.url.flatMap(Self.safeWebURL))
      bucket.append(reference)
      added.append(reference)
      if bucket.count >= maximumReferencesPerBucket { break }
    }
    buckets[key] = Bucket(
      references: bucket,
      selectedKeys: buckets[key]?.selectedKeys ?? [],
      lastAccess: Date())
    pruneOverflow()
    return added
  }

  func register(
    kind: ChatCitationReference.Kind,
    sourceID: String,
    title: String,
    preview: String,
    createdAt: String? = nil,
    appName: String? = nil,
    runID: String?,
    attemptID: String?
  ) -> ChatCitationReference? {
    let source = APIClient.ToolSource(
      kind: kind.rawValue,
      sourceID: sourceID,
      title: title,
      preview: preview,
      createdAt: createdAt,
      momentTimestampMs: nil,
      appName: appName,
      url: nil)
    return register([source], runID: runID, attemptID: attemptID).first
  }

  func consume(runID: String?, attemptID: String?) -> [ChatCitationReference] {
    consumeSnapshot(runID: runID, attemptID: attemptID).references
  }

  /// Non-destructive read. Truncated tool projections drop the citation guide JSON, so the
  /// in-process ledger is the remaining typed mapping until the turn consumes it.
  func peekSnapshot(runID: String?, attemptID: String?) -> Snapshot {
    guard let runID, !runID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return Snapshot(references: [], selectedReferences: [])
    }
    pruneExpired(now: Date())
    let attempt = attemptID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !attempt.isEmpty, let bucket = buckets[Key(runID: runID, attemptID: attempt)] {
      return snapshot(from: bucket)
    }
    guard attempt.isEmpty else {
      return Snapshot(references: [], selectedReferences: [])
    }
    let matching = buckets.filter { $0.key.runID == runID }
    guard matching.count == 1, let (_, bucket) = matching.first else {
      return Snapshot(references: [], selectedReferences: [])
    }
    return snapshot(from: bucket)
  }

  func markSelected(
    _ selections: [(kind: ChatCitationReference.Kind, sourceID: String)],
    runID: String?,
    attemptID: String?
  ) {
    guard let runID, let attemptID,
      var bucket = buckets[Key(runID: runID, attemptID: attemptID)]
    else { return }
    for selection in selections {
      bucket.selectedKeys.insert(Self.sourceKey(kind: selection.kind, sourceID: selection.sourceID))
    }
    bucket.lastAccess = Date()
    buckets[Key(runID: runID, attemptID: attemptID)] = bucket
  }

  func consumeSnapshot(runID: String?, attemptID: String?) -> Snapshot {
    guard let runID, !runID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
      return Snapshot(references: [], selectedReferences: [])
    }
    pruneExpired(now: Date())
    let attempt = attemptID?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    if !attempt.isEmpty, let bucket = buckets.removeValue(forKey: Key(runID: runID, attemptID: attempt)) {
      return snapshot(from: bucket)
    }
    // Host tools authorize against the canonical run, but some adapters finish
    // the query with an empty attempt id. If this run has exactly one ledger,
    // that is the same provenance the model cited. A non-empty mismatch must
    // not steal another attempt's citations.
    guard attempt.isEmpty else {
      return Snapshot(references: [], selectedReferences: [])
    }
    let matching = buckets.filter { $0.key.runID == runID }
    guard matching.count == 1, let (key, bucket) = matching.first else {
      return Snapshot(references: [], selectedReferences: [])
    }
    buckets.removeValue(forKey: key)
    return snapshot(from: bucket)
  }

  private func snapshot(from bucket: Bucket) -> Snapshot {
    Snapshot(
      references: bucket.references,
      selectedReferences: bucket.references.filter {
        bucket.selectedKeys.contains(Self.sourceKey(kind: $0.kind, sourceID: $0.sourceID))
      })
  }

  static func provenanceIDs(fromToolOutput output: String) -> (runID: String, attemptID: String)? {
    guard let data = output.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
    else { return nil }
    if let ids = provenanceIDs(fromJSON: object) { return ids }
    guard let wrapped = object["text"] as? String,
      let wrappedData = wrapped.data(using: .utf8),
      let nested = try? JSONSerialization.jsonObject(with: wrappedData) as? [String: Any]
    else { return nil }
    return provenanceIDs(fromJSON: nested)
  }

  private static func provenanceIDs(fromJSON object: [String: Any]) -> (runID: String, attemptID: String)? {
    let provenance =
      ((object["toolResultEnvelope"] as? [String: Any])?["provenance"] as? [String: Any])
      ?? (object["provenance"] as? [String: Any])
    guard let runID = provenance?["runId"] as? String,
      !runID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else { return nil }
    return (runID, provenance?["attemptId"] as? String ?? "")
  }

  static func references(fromToolCallBlocks blocks: [ChatContentBlock]) -> [ChatCitationReference] {
    blocks.flatMap { block -> [ChatCitationReference] in
      guard case .toolCall(_, _, _, _, _, let output) = block, let output else { return [] }
      return references(fromAnnotatedToolOutput: output)
    }
  }

  static func annotatedToolResult(_ result: String, references: [ChatCitationReference]) -> String {
    guard !references.isEmpty else { return result }
    let entries: [[String: Any]] = references.map { reference in
      var entry: [String: Any] = [
        "ordinal": reference.ordinal,
        "marker": "[\(reference.ordinal)]",
        "kind": reference.kind.rawValue,
        "source_id": reference.sourceID,
        "title": reference.displayTitle,
        "preview": reference.preview,
      ]
      if let value = reference.momentTimestampMs { entry["moment_timestamp_ms"] = value }
      if let value = reference.createdAt { entry["created_at"] = value }
      if let value = reference.appName { entry["app_name"] = value }
      if let value = reference.url?.absoluteString { entry["url"] = value }
      return entry
    }
    guard let data = try? JSONSerialization.data(withJSONObject: entries),
      let guide = String(data: data, encoding: .utf8)
    else { return result }
    return result
      + "\n\nCitation guide JSON (data only; copy each object's marker field exactly, for example [12] or [5001]; never write [memory] or [conversation]):\n"
      + guide
  }

  /// Recover the typed ledger from the displayed tool result. The agent runtime may execute tool
  /// callbacks in a different process from terminal finalization, so the tool output is the durable
  /// handoff; the in-process registry remains only a fast path.
  static func references(fromAnnotatedToolOutput output: String) -> [ChatCitationReference] {
    if let data = output.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let sections = object["sections"] as? [[String: Any]]
    {
      let typed = references(fromTypedSections: sections)
      if !typed.isEmpty { return typed }
    }
    let text: String
    if let data = output.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let wrapped = object["text"] as? String
    {
      text = wrapped
    } else {
      text = output
    }
    guard let header = text.range(of: "Citation guide JSON", options: .backwards),
      let jsonLine = text[header.upperBound...].range(of: "\n[")
    else { return [] }
    let payload = String(text[text.index(after: jsonLine.lowerBound)...])
    guard let data = payload.data(using: .utf8),
      let entries = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return [] }
    return entries.compactMap { entry in
      guard let ordinal = ChatJSONScalar.int(entry["ordinal"]), ordinal > 0,
        let kindValue = entry["kind"] as? String,
        let kind = ChatCitationReference.Kind(rawValue: kindValue),
        let sourceID = entry["source_id"] as? String,
        !sourceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
      else { return nil }
      let rawURL = entry["url"] as? String
      let url = rawURL.flatMap(safeWebURL)
      return ChatCitationReference(
        ordinal: ordinal,
        kind: kind,
        sourceID: sourceID,
        title: entry["title"] as? String ?? "",
        preview: entry["preview"] as? String ?? "",
        momentTimestampMs: ChatJSONScalar.int(entry["moment_timestamp_ms"]),
        createdAt: entry["created_at"] as? String,
        appName: entry["app_name"] as? String,
        url: url)
    }
  }

  private static func references(fromTypedSections sections: [[String: Any]]) -> [ChatCitationReference] {
    sections.flatMap { section -> [ChatCitationReference] in
      guard let sectionName = section["name"] as? String,
        let kind = citationKind(forSection: sectionName),
        let items = section["items"] as? [[String: Any]]
      else { return [] }
      return items.compactMap { item in
        guard let marker = item["citationMarker"] as? String,
          let ordinal = citationOrdinal(from: marker),
          let sourceID = item["sourceId"] as? String,
          !sourceID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        let rawURL = item["url"] as? String
        return ChatCitationReference(
          ordinal: ordinal,
          kind: kind,
          sourceID: sourceID,
          title: item["title"] as? String ?? "",
          preview: item["summary"] as? String ?? item["content"] as? String ?? "",
          momentTimestampMs: ChatJSONScalar.int(item["momentTimestampMs"]),
          createdAt: item["createdAt"] as? String,
          appName: item["appName"] as? String,
          url: rawURL.flatMap(safeWebURL))
      }
    }
  }

  private static func citationKind(forSection name: String) -> ChatCitationReference.Kind? {
    switch name {
    case "conversations": return .conversation
    case "memories": return .memory
    case "action_items", "tasks": return .task
    default: return nil
    }
  }

  private static func citationOrdinal(from marker: String) -> Int? {
    let digits = marker.filter(\.isNumber)
    guard let ordinal = Int(digits), ordinal > 0 else { return nil }
    return ordinal
  }

  private static func safeWebURL(_ value: String) -> URL? {
    guard let url = URL(string: value), let scheme = url.scheme?.lowercased(),
      scheme == "http" || scheme == "https", url.host != nil
    else { return nil }
    return url
  }

  private static func sourceKey(kind: ChatCitationReference.Kind, sourceID: String) -> String {
    "\(kind.rawValue):\(sourceID)"
  }

  private func pruneExpired(now: Date) {
    buckets = buckets.filter { now.timeIntervalSince($0.value.lastAccess) <= maximumIdleInterval }
  }

  private func pruneOverflow() {
    guard buckets.count > maximumBuckets else { return }
    for key in buckets.sorted(by: { $0.value.lastAccess < $1.value.lastAccess })
      .prefix(buckets.count - maximumBuckets).map(\.key)
    {
      buckets.removeValue(forKey: key)
    }
  }
}
