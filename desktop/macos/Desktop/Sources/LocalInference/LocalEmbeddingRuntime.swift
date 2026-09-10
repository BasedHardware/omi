import Foundation

/// Kill switch → selected, probed engine → no vectors. No HTTP client or cloud adapter is owned here.
struct LocalEmbeddingRuntime: Sendable {
  enum Selection: Sendable {
    case disabled
    case none
    case engine(any LocalEmbeddingService)
  }

  let engines: [any LocalEmbeddingService]
  var killSwitches: LocalEmbeddingKillSwitches = .enabled
  var defaultEngineID: String? = nil
  var probeBudget: Duration = .seconds(2)
  var probe: @Sendable (any LocalEmbeddingService) async -> LocalEmbeddingProbe = LocalEmbeddingProbe.run
  var record: @Sendable (String, String) -> Void = { from, reason in
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "local_embeddings", from: from, to: "none", reason: reason, outcome: .degraded)
  }

  /// Intentionally empty until an on-device engine is registered by the next implementation.
  static func makeDefault() -> Self {
    Self(engines: [], killSwitches: .resolve())
  }

  func selectEngine() async -> Selection {
    let wanted = killSwitches.forcedEngineRaw ?? defaultEngineID
    guard !killSwitches.isDisabled else {
      record("local_embeddings", "dispatch_disabled")
      return .disabled
    }
    guard !Task.isCancelled, let wanted, let engine = engines.first(where: { $0.engineID == wanted }) else {
      record("local_embeddings", "config_incomplete")
      return .none
    }
    let result = await probe(engine)
    guard !Task.isCancelled, result.permits(engine, budget: probeBudget) else {
      record("local_embeddings", "capability_mismatch")
      return .none
    }
    return .engine(engine)
  }

  /// Also used after selection so an engine failure cannot change the search route to Gemini.
  func embed(_ texts: [String], task: LocalEmbeddingTask, using engine: any LocalEmbeddingService) async -> [[Float]]? {
    guard !killSwitches.isDisabled, !Task.isCancelled else { return nil }
    do {
      guard texts.count <= engine.capabilities.maxBatchSize else {
        throw LocalInferenceError.invalidResponse("invalid local vector shape")
      }
      let vectors = try await engine.embed(texts, task: task)
      guard !Task.isCancelled, vectors.count == texts.count,
        vectors.allSatisfy({ LocalEmbeddingProbe.valid($0, dimension: engine.dimension) })
      else { throw LocalInferenceError.invalidResponse("invalid local vector shape") }
      return vectors
    } catch {
      record("local_embeddings", "engine_failed")
      return nil
    }
  }
}
