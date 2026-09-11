import Foundation

/// Rewind UI search uses the same `ScreenHistorySearchRoute` as chat.
/// Gemini remains the paid/hard-kill merge (FTS first, then vector-only above 0.5).
/// Free plans read local vectors or FTS and never embed the query with Gemini.
enum RewindScreenSearch {
  static let ftsLimit = 100
  static let vectorTopK = 50
  static let geminiSimilarityFloor: Float = 0.5

  struct Dependencies: @unchecked Sendable {
    var runtime: LocalEmbeddingRuntime = .makeDefault()
    var policy: ScreenEmbeddingPolicy? = nil
    var defaults: UserDefaults? = .standard
    var fts: @Sendable (String, String?) async throws -> [Screenshot] = { query, app in
      try await RewindDatabase.shared.search(
        query: query, appFilter: app, startDate: nil, endDate: nil, limit: RewindScreenSearch.ftsLimit)
    }
    var gemini: @Sendable (String, String?) async throws -> [(screenshotId: Int64, similarity: Float)] = { query, app in
      try await OCREmbeddingService.shared.searchSimilar(
        query: query, startDate: nil, endDate: nil, appFilter: app, topK: RewindScreenSearch.vectorTopK)
    }
    var screenshot: @Sendable (Int64) async throws -> Screenshot? = { id in
      try await RewindDatabase.shared.getScreenshot(id: id)
    }
    var localHits: (@Sendable (String, String?, (any LocalEmbeddingService)?) async throws -> [LocalHybridHit])? = nil
  }

  static func search(
    query: String, appFilter: String?, dependencies: Dependencies = Dependencies()
  ) async throws -> [Screenshot] {
    let runtime = dependencies.runtime
    return try await ScreenHistorySearchRoute.search(
      runtime: runtime, policy: dependencies.policy, defaults: dependencies.defaults
    ) { engine in
      let hits: [LocalHybridHit]
      if let localHits = dependencies.localHits {
        hits = try await localHits(query, appFilter, engine)
      } else {
        guard let owner = RewindCaptureOwnerSnapshot.capture(), owner.isCurrent() else {
          throw LocalMutationAuthorizationError.revoked
        }
        let store = try await RewindDatabase.shared.localEmbeddingStore(owner: owner)
        hits = try await LocalHybridSearch(
          store: store, runtime: runtime,
          authorization: LocalMutationAuthorization { owner.isCurrent() }
        ).search(
          query: query, engine: engine, appFilter: appFilter, limit: Self.vectorTopK, sourceKinds: [.screenshot])
      }
      var screenshots: [Screenshot] = []
      screenshots.reserveCapacity(hits.count)
      for hit in hits {
        if let screenshot = try await dependencies.screenshot(hit.sourceId) {
          screenshots.append(screenshot)
        }
      }
      return screenshots
    } legacy: {
      async let ftsResults = dependencies.fts(query, appFilter)
      async let vectorResults = dependencies.gemini(query, appFilter)
      let fts = try await ftsResults
      let vector = (try? await vectorResults) ?? []
      let ftsIds = Set(fts.compactMap(\.id))
      var merged = fts
      for result in vector where result.similarity > Self.geminiSimilarityFloor && !ftsIds.contains(result.screenshotId)
      {
        if let screenshot = try await dependencies.screenshot(result.screenshotId) {
          merged.append(screenshot)
        }
      }
      return merged
    }
  }
}
