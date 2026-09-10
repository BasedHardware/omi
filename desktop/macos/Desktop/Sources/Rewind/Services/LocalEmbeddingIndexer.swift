import Foundation

/// Indexes screenshots, transcript chunks, and memories into local_embeddings.
/// Capture never waits on this path. Backfill is AC-bounded like OCR embeddings.
actor LocalEmbeddingIndexer {
  static let shared = LocalEmbeddingIndexer()

  private var isBackfillRunning = false
  private var runtime: LocalEmbeddingRuntime = .makeDefault()

  func setRuntimeForTesting(_ runtime: LocalEmbeddingRuntime) {
    self.runtime = runtime
  }

  func indexFinalizedSession(sessionId: Int64) async {
    guard let owner = RewindCaptureOwnerSnapshot.capture(), owner.isCurrent() else { return }
    do {
      let store = try await RewindDatabase.shared.localEmbeddingStore(owner: owner)
      let authorization = LocalMutationAuthorization { owner.isCurrent() }
      try await indexSession(sessionId: sessionId, store: store, authorization: authorization)
    } catch {
      log("LocalEmbeddingIndexer: session \(sessionId) indexing skipped")
    }
  }

  func indexMemory(id: Int64, content: String) async {
    guard let owner = RewindCaptureOwnerSnapshot.capture(), owner.isCurrent() else { return }
    do {
      let store = try await RewindDatabase.shared.localEmbeddingStore(owner: owner)
      let authorization = LocalMutationAuthorization { owner.isCurrent() }
      try await embedTexts(
        [(id, content)], sourceKind: .memory, store: store, authorization: authorization)
    } catch {
      log("LocalEmbeddingIndexer: memory \(id) indexing skipped")
    }
  }

  func backfillIfNeeded() async {
    guard !isBackfillRunning else { return }
    isBackfillRunning = true
    defer { isBackfillRunning = false }
    guard !PowerMonitor.cachedBatteryState() else { return }
    guard let owner = RewindCaptureOwnerSnapshot.capture(), owner.isCurrent() else { return }
    let authorization = LocalMutationAuthorization { owner.isCurrent() }
    do {
      let store = try await RewindDatabase.shared.localEmbeddingStore(owner: owner)
      let sessionIds = try store.sessionsNeedingTranscriptChunks(limit: 20)
      for sessionId in sessionIds {
        guard owner.isCurrent() else { return }
        try await indexSession(sessionId: sessionId, store: store, authorization: authorization)
      }
      try await embedPending(store: store, authorization: authorization)
    } catch {
      log("LocalEmbeddingIndexer: backfill paused")
    }
  }

  private func indexSession(
    sessionId: Int64, store: LocalEmbeddingStore, authorization: LocalMutationAuthorization
  ) async throws {
    let segments = try await TranscriptionStorage.shared.getSegments(sessionId: sessionId)
    let origin = (try? await TranscriptionStorage.shared.getSession(id: sessionId))?.startedAt ?? Date()
    let chunkInput = segments.map {
      TranscriptChunker.Segment(
        text: $0.text, order: $0.segmentOrder, startedAt: origin.addingTimeInterval($0.startTime))
    }
    let chunks = TranscriptChunker.chunks(sessionId: sessionId, segments: chunkInput)
    let stored = try await store.upsertTranscriptChunks(chunks, authorization: authorization)
    try await embedTexts(
      stored.compactMap { chunk in
        guard let id = chunk.id else { return nil }
        return (id, chunk.text)
      },
      sourceKind: .transcriptChunk, store: store, authorization: authorization)
  }

  private func embedPending(store: LocalEmbeddingStore, authorization: LocalMutationAuthorization) async throws {
    guard case .engine(let engine) = await runtime.selectEngine() else { return }
    let cutoff = Date().addingTimeInterval(-5 * 60)
    let screenshots = try store.screenshotsNeedingEmbedding(modelID: engine.modelID, olderThan: cutoff, limit: 50)
    try await embedTexts(
      screenshots.map { ($0.id, $0.text) }, sourceKind: .screenshot, store: store, authorization: authorization,
      engine: engine)
    let chunks = try store.transcriptChunksNeedingEmbedding(modelID: engine.modelID, limit: 50)
    try await embedTexts(
      chunks.compactMap { chunk in
        guard let id = chunk.id else { return nil }
        return (id, chunk.text)
      },
      sourceKind: .transcriptChunk, store: store, authorization: authorization, engine: engine)
    let memories = try store.memoriesNeedingEmbedding(modelID: engine.modelID, limit: 50)
    try await embedTexts(memories, sourceKind: .memory, store: store, authorization: authorization, engine: engine)
  }

  private func embedTexts(
    _ items: [(Int64, String)], sourceKind: LocalEmbeddingSourceKind, store: LocalEmbeddingStore,
    authorization: LocalMutationAuthorization, engine: (any LocalEmbeddingService)? = nil
  ) async throws {
    guard !items.isEmpty else { return }
    let selected: any LocalEmbeddingService
    if let engine {
      selected = engine
    } else if case .engine(let runtimeEngine) = await runtime.selectEngine() {
      selected = runtimeEngine
    } else {
      return
    }
    for batchStart in stride(from: 0, to: items.count, by: selected.capabilities.maxBatchSize) {
      try Task.checkCancellation()
      try authorization.require()
      let slice = Array(items[batchStart..<min(batchStart + selected.capabilities.maxBatchSize, items.count)])
      guard let vectors = await runtime.embed(slice.map(\.1), task: .document, using: selected) else { return }
      for (item, vector) in zip(slice, vectors) {
        try await store.write(
          sourceKind: sourceKind, sourceId: item.0, modelID: selected.modelID, text: item.1, vector: vector,
          authorization: authorization)
      }
    }
  }
}
