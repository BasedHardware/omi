import Accelerate
import Foundation

struct LocalHybridHit: Sendable, Equatable {
  enum Match: String, Sendable { case keyword, vector, both }
  let sourceKind: LocalEmbeddingSourceKind
  let sourceId: Int64
  let fusedScore: Double
  let matchedBy: Match
  let capturedAt: Date
  let appName: String
}

struct LocalHybridSearch: Sendable {
  let store: LocalEmbeddingStore
  let runtime: LocalEmbeddingRuntime
  let authorization: LocalMutationAuthorization

  enum RetrievalMode: Sendable { case keyword, vector, hybrid }

  /// FTS remains available if the selected local engine fails. No cloud step exists here.
  func search(
    query: String, engine: (any LocalEmbeddingService)?, startDate: Date? = nil,
    endDate: Date? = nil, appFilter: String? = nil, limit: Int = 50,
    maxScannedEmbeddings: Int = 20_000,
    sourceKinds: Set<LocalEmbeddingSourceKind> = [.screenshot],
    retrieval: RetrievalMode = .hybrid
  ) async throws -> [LocalHybridHit] {
    try authorization.require()
    let keywords =
      retrieval == .vector
      ? []
      : try store.keywordCandidates(
        query: query, startDate: startDate, endDate: endDate, appFilter: appFilter, sourceKinds: sourceKinds)
    var vectors: [(candidate: LocalEmbeddingCandidate, score: Float)] = []
    if retrieval != .keyword, let engine,
      let queryVector = await runtime.embed([query], task: .query, using: engine)?.first
    {
      var scanned = 0
      let budget = max(0, min(maxScannedEmbeddings, 20_000))
      while scanned < budget {
        try Task.checkCancellation()
        try authorization.require()
        let batch = try store.readBatch(
          modelID: engine.modelID, dimension: engine.dimension,
          startDate: startDate, endDate: endDate, appFilter: appFilter,
          limit: min(5000, budget - scanned), offset: scanned, sourceKinds: sourceKinds)
        if batch.isEmpty { break }
        scanned += batch.count
        for candidate in batch {
          guard let score = Self.cosine(queryVector, candidate.vector), score > 0 else { continue }
          vectors.append((candidate, score))
        }
        vectors.sort {
          $0.score == $1.score ? Self.precedes($0.candidate, $1.candidate) : $0.score > $1.score
        }
        vectors = Array(vectors.prefix(50))
      }
    }
    try authorization.require()
    try Task.checkCancellation()
    if retrieval == .vector {
      return vectors.prefix(max(0, min(limit, 50))).map { candidate, score in
        LocalHybridHit(
          sourceKind: candidate.sourceKind, sourceId: candidate.sourceId,
          fusedScore: Double(score), matchedBy: .vector,
          capturedAt: candidate.capturedAt, appName: candidate.appName)
      }
    }
    return Self.fuse(keywords: keywords, vectors: vectors.map(\.candidate), limit: limit)
  }

  private struct Key: Hashable {
    let kind: String
    let id: Int64
    init(_ candidate: LocalEmbeddingCandidate) {
      kind = candidate.sourceKind.rawValue
      id = candidate.sourceId
    }
  }

  static func fuse(keywords: [LocalEmbeddingCandidate], vectors: [LocalEmbeddingCandidate], limit: Int)
    -> [LocalHybridHit]
  {
    var hits: [Key: LocalHybridHit] = [:]
    for (candidates, match) in [(keywords, LocalHybridHit.Match.keyword), (vectors, .vector)] {
      var seen = Set<Key>()
      for (rank, candidate) in candidates.prefix(50).enumerated() {
        let key = Key(candidate)
        guard seen.insert(key).inserted else { continue }
        let previous = hits[key]
        hits[key] = LocalHybridHit(
          sourceKind: candidate.sourceKind, sourceId: candidate.sourceId,
          fusedScore: (previous?.fusedScore ?? 0) + 1.0 / Double(60 + rank + 1),
          matchedBy: previous == nil ? match : .both, capturedAt: candidate.capturedAt, appName: candidate.appName)
      }
    }
    return Array(
      hits.values.sorted {
        if $0.fusedScore != $1.fusedScore { return $0.fusedScore > $1.fusedScore }
        if $0.capturedAt != $1.capturedAt { return $0.capturedAt > $1.capturedAt }
        if $0.sourceKind != $1.sourceKind { return $0.sourceKind.rawValue < $1.sourceKind.rawValue }
        return $0.sourceId > $1.sourceId
      }.prefix(max(0, min(limit, 50))))
  }

  private static func precedes(_ a: LocalEmbeddingCandidate, _ b: LocalEmbeddingCandidate) -> Bool {
    a.capturedAt == b.capturedAt ? a.sourceId > b.sourceId : a.capturedAt > b.capturedAt
  }

  static func cosine(_ a: [Float], _ b: [Float]) -> Float? {
    guard LocalEmbeddingProbe.valid(a, dimension: b.count), LocalEmbeddingProbe.valid(b, dimension: a.count) else {
      return nil
    }
    var dot: Float = 0
    var aSquared: Float = 0
    var bSquared: Float = 0
    vDSP_dotpr(a, 1, b, 1, &dot, vDSP_Length(a.count))
    vDSP_svesq(a, 1, &aSquared, vDSP_Length(a.count))
    vDSP_svesq(b, 1, &bSquared, vDSP_Length(b.count))
    let score = dot / (sqrt(aSquared) * sqrt(bSquared))
    return score.isFinite ? score : nil
  }
}

/// The chat route is selected once. A local query failure must never invoke the legacy closure.
/// Probe failure (`.none`) stays on local FTS-only. Opt-out and the hard kill (`.disabled`)
/// keep Gemini.
enum ScreenHistorySearchRoute {
  static func search<T: Sendable>(
    runtime: LocalEmbeddingRuntime,
    local: @Sendable ((any LocalEmbeddingService)?) async throws -> T,
    legacy: @Sendable () async throws -> T
  ) async throws -> T {
    switch await runtime.selectEngine() {
    case .engine(let engine): return try await local(engine)
    case .none: return try await local(nil)
    case .disabled: return try await legacy()
    }
  }
}
