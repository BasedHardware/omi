import Foundation

/// One real historical (contact-said → I-replied) exchange retrieved as a few-shot
/// example for the current incoming message.
struct RetrievedExchange: Sendable {
  let them: String
  /// My real reply — bubbles joined with "\n" (one line per message bubble).
  let me: String
  let instanceKey: String
  let score: Double
}

/// Per-contact retrieval index over real (them → me) reply pairs. For each incoming
/// message the clone fetches the k most similar historical situations and shows the
/// model my *actual verbatim replies* to them — dynamic few-shot conditioning, which
/// carries far more signal than a static persona description alone.
///
/// Similarity is a hybrid of Gemini embedding cosine (semantic) and token-overlap
/// (lexical); if the embedding backend is unavailable the index degrades to pure
/// lexical scoring instead of failing.
actor AICloneRetrievalService {
  static let shared = AICloneRetrievalService()

  private struct Entry {
    let them: String
    let me: String
    let instanceKey: String
    let tokens: Set<String>
    let recency: Double  // 0 (oldest) … 1 (newest)
    var embedding: [Float]?
  }

  private struct Index {
    let fingerprint: String
    var entries: [Entry]
    var hasEmbeddings: Bool
  }

  private var indices: [String: Index] = [:]

  /// Stable key for one historical pair instance (text + turn timestamp), so a
  /// backtest can exclude exactly the held-out instance while a *different* historical
  /// occurrence of the same text stays retrievable (that's legitimate evidence).
  static func instanceKey(them: String, me: String, date: Date) -> String {
    "\(Int(date.timeIntervalSinceReferenceDate))|\(them.hashValue)|\(me.hashValue)"
  }

  /// Build (or reuse) the index for this contact from its message history.
  /// Cheap when the fingerprint hasn't changed.
  func ensureIndex(contactId: String, messages: [ImportedMessage]) async {
    let fingerprint = Self.fingerprint(for: messages)
    if let existing = indices[contactId], existing.fingerprint == fingerprint { return }

    let chronological: [ImportedMessage] =
      messages.count > 1 && messages.first!.date > messages.last!.date
      ? Array(messages.reversed()) : messages
    let pairs = AICloneBacktestService.buildPairs(from: chronological)
    guard !pairs.isEmpty else { return }

    let dates = pairs.map { $0.turnDate.timeIntervalSinceReferenceDate }
    let minDate = dates.min() ?? 0
    let dateSpan = max(1, (dates.max() ?? 1) - minDate)

    var entries = pairs.map { pair in
      Entry(
        them: pair.contactMessage,
        me: pair.actualReply,
        instanceKey: Self.instanceKey(
          them: pair.contactMessage, me: pair.actualReply, date: pair.turnDate),
        tokens: Self.tokenSet(pair.contactMessage),
        recency: (pair.turnDate.timeIntervalSinceReferenceDate - minDate) / dateSpan,
        embedding: nil)
    }

    // Embed the "them" side in batches; on any failure fall back to lexical-only.
    var hasEmbeddings = false
    do {
      var vectors: [[Float]] = []
      var cursor = 0
      while cursor < entries.count {
        let chunk = Array(entries[cursor..<min(cursor + 100, entries.count)])
        let batch = try await EmbeddingService.shared.embedBatch(
          texts: chunk.map { String($0.them.prefix(600)) }, taskType: "RETRIEVAL_DOCUMENT")
        guard batch.count == chunk.count else { throw EmbeddingService.EmbeddingError.invalidResponse }
        vectors.append(contentsOf: batch)
        cursor += 100
      }
      for i in entries.indices { entries[i].embedding = vectors[i] }
      hasEmbeddings = true
      log("AICloneRetrieval: embedded \(entries.count) pairs for contact index")
    } catch {
      log("AICloneRetrieval: embeddings unavailable, lexical-only index (\(error.localizedDescription))")
    }

    indices[contactId] = Index(fingerprint: fingerprint, entries: entries, hasEmbeddings: hasEmbeddings)
  }

  var isReady: Bool { !indices.isEmpty }

  func hasIndex(for contactId: String) -> Bool { indices[contactId] != nil }

  /// The k most similar historical exchanges for `incoming`, excluding specific
  /// held-out instances (leak prevention during backtests) and deduplicating identical
  /// replies so the example block shows variety.
  func retrieve(
    contactId: String, incoming: String, k: Int, excluding excludedKeys: Set<String> = []
  ) async -> [RetrievedExchange] {
    guard let index = indices[contactId], !index.entries.isEmpty else { return [] }

    var queryVector: [Float]? = nil
    if index.hasEmbeddings {
      queryVector = try? await EmbeddingService.shared.embed(
        text: String(incoming.prefix(600)), taskType: "RETRIEVAL_QUERY")
    }
    let queryTokens = Self.tokenSet(incoming)

    var scored: [(entry: Entry, score: Double)] = []
    scored.reserveCapacity(index.entries.count)
    for entry in index.entries where !excludedKeys.contains(entry.instanceKey) {
      let lexical = Self.overlap(queryTokens, entry.tokens)
      var semantic = 0.0
      if let queryVector, let entryVector = entry.embedding {
        semantic = Double(Self.cosine(queryVector, entryVector))
        semantic = max(0, min(1, (semantic + 1) / 2))  // map [-1,1] → [0,1]
      }
      let base = queryVector != nil ? (0.7 * semantic + 0.3 * lexical) : lexical
      scored.append((entry, base + 0.04 * entry.recency))
    }

    scored.sort { $0.score > $1.score }
    var seenReplies = Set<String>()
    var results: [RetrievedExchange] = []
    for (entry, score) in scored {
      let replyKey = entry.me.lowercased()
      guard seenReplies.insert(replyKey).inserted else { continue }
      results.append(
        RetrievedExchange(them: entry.them, me: entry.me, instanceKey: entry.instanceKey, score: score))
      if results.count >= k { break }
    }
    return results
  }

  // MARK: - Helpers

  private static func fingerprint(for messages: [ImportedMessage]) -> String {
    let first = messages.first.map { "\($0.date.timeIntervalSinceReferenceDate)" } ?? "-"
    let last = messages.last.map { "\($0.date.timeIntervalSinceReferenceDate)" } ?? "-"
    return "\(messages.count)|\(first)|\(last)"
  }

  private static func tokenSet(_ text: String) -> Set<String> {
    Set(
      text.lowercased()
        .components(separatedBy: CharacterSet.alphanumerics.inverted)
        .filter { $0.count > 1 })
  }

  /// Symmetric token overlap (cosine of binary vectors): |A∩B| / sqrt(|A||B|).
  private static func overlap(_ a: Set<String>, _ b: Set<String>) -> Double {
    guard !a.isEmpty, !b.isEmpty else { return 0 }
    let shared = a.intersection(b).count
    return Double(shared) / (Double(a.count) * Double(b.count)).squareRoot()
  }

  private static func cosine(_ a: [Float], _ b: [Float]) -> Float {
    guard a.count == b.count, !a.isEmpty else { return 0 }
    var dot: Float = 0
    for i in a.indices { dot += a[i] * b[i] }
    return dot  // embeddings are pre-normalized by EmbeddingService
  }
}
