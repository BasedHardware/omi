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
      + "Copy every relevant marker exactly at the end of each claim grounded in that source. "
      + "Do not claim to provide citations without emitting the markers, and do not invent markers."
  }
}

enum ChatCitationMarkup {
  /// Numeric citations outside inline-code spans, in reading order. Incomplete streaming markers
  /// and bracketed prose are left alone.
  static func ordinals(in text: String) -> [Int] {
    let codeRanges = OmiMarkdownInlineCode.codeSpanRanges(in: text)
    let expression = try? NSRegularExpression(pattern: #"\[(\d{1,4})\](?!\()"#)
    let nsRange = NSRange(text.startIndex..<text.endIndex, in: text)
    return expression?.matches(in: text, range: nsRange).compactMap { match in
      guard let full = Range(match.range(at: 0), in: text),
        !codeRanges.contains(where: { $0.overlaps(full) }),
        let digits = Range(match.range(at: 1), in: text)
      else { return nil }
      return Int(text[digits])
    } ?? []
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
  static func appendingSelectedSources(
    to text: String,
    selectedReferences: [ChatCitationReference],
    requestedSources: Bool = false,
    retrievedReferences: [ChatCitationReference] = []
  ) -> String {
    guard ordinals(in: text).isEmpty else { return text }
    let fallback = selectedReferences.isEmpty && requestedSources ? retrievedReferences : selectedReferences
    guard !fallback.isEmpty else { return text }
    let markers = fallback.prefix(8).map { "[\($0.ordinal)]" }.joined()
    return text + "\n\nSources: \(markers)"
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
    guard let runID, let attemptID,
      !runID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
      !attemptID.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
    else { return Snapshot(references: [], selectedReferences: []) }
    pruneExpired(now: Date())
    guard let bucket = buckets.removeValue(forKey: Key(runID: runID, attemptID: attemptID)) else {
      return Snapshot(references: [], selectedReferences: [])
    }
    return Snapshot(
      references: bucket.references,
      selectedReferences: bucket.references.filter {
        bucket.selectedKeys.contains(Self.sourceKey(kind: $0.kind, sourceID: $0.sourceID))
      })
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
      + "\n\nCitation guide JSON (data only; use each exact marker after claims supported by that source):\n"
      + guide
  }

  /// Recover the typed ledger from the displayed tool result. The agent runtime may execute tool
  /// callbacks in a different process from terminal finalization, so the tool output is the durable
  /// handoff; the in-process registry remains only a fast path.
  static func references(fromAnnotatedToolOutput output: String) -> [ChatCitationReference] {
    let text: String
    if let data = output.data(using: .utf8),
      let object = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
      let wrapped = object["text"] as? String
    {
      text = wrapped
    } else {
      text = output
    }
    let delimiter =
      "\n\nCitation guide JSON (data only; use each exact marker after claims supported by that source):\n"
    guard let range = text.range(of: delimiter, options: .backwards) else { return [] }
    let payload = String(text[range.upperBound...])
    guard let data = payload.data(using: .utf8),
      let entries = try? JSONSerialization.jsonObject(with: data) as? [[String: Any]]
    else { return [] }
    return entries.compactMap { entry in
      guard let ordinal = entry["ordinal"] as? Int, ordinal > 0,
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
        momentTimestampMs: entry["moment_timestamp_ms"] as? Int,
        createdAt: entry["created_at"] as? String,
        appName: entry["app_name"] as? String,
        url: url)
    }
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
