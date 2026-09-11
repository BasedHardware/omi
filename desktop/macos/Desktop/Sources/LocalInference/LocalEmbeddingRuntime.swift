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
  var embedBudget: Duration = .seconds(30)
  var probeTTL: Duration = .seconds(60)
  var probeCache: LocalEmbeddingProbeCache = LocalEmbeddingProbeCache()
  var clock: @Sendable () -> ContinuousClock.Instant = { ContinuousClock.now }
  var thermalState: @Sendable () -> ProcessInfo.ThermalState = { ProcessInfo.processInfo.thermalState }
  var probe: @Sendable (any LocalEmbeddingService) async -> LocalEmbeddingProbe = {
    await LocalEmbeddingProbe.run($0)
  }
  var record: @Sendable (String, String) -> Void = { from, reason in
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "local_embeddings", from: from, to: "keyword", reason: reason, outcome: .degraded)
  }

  /// Apple NLCE is the registered engine. Free and unknown plans default on;
  /// paid production bundles opt in. Selection fail-closes until the probe passes.
  /// Probe cache and engine are process-wide so chat search pays the 32-token probe once.
  static func makeDefault() -> Self {
    let apple = AppleNLContextualEmbeddingEngine.shared
    return Self(
      engines: [apple], killSwitches: .resolve(), defaultEngineID: apple.engineID,
      probeCache: .shared)
  }

  func selectEngine() async -> Selection {
    let wanted = killSwitches.forcedEngineRaw ?? defaultEngineID
    guard !killSwitches.isDisabled else {
      record("local_embeddings", "dispatch_disabled")
      return .disabled
    }
    guard killSwitches.isEnabled else {
      return .disabled
    }
    guard !Task.isCancelled, let wanted, let engine = engines.first(where: { $0.engineID == wanted }) else {
      record("local_embeddings", "config_incomplete")
      return .none
    }
    let key = LocalEmbeddingProbeCache.Key(
      engineID: engine.engineID,
      modelID: engine.modelID,
      thermalState: thermalState().rawValue,
      disabled: killSwitches.isDisabled,
      forcedEngine: killSwitches.forcedEngineRaw ?? "")
    let now = clock()
    let result = await probeCache.getOrCompute(key, ttl: probeTTL, now: now) {
      do {
        return try await LocalEmbeddingCallBound.run(probeBudget) {
          await probe(engine)
        }
      } catch is CancellationError {
        return LocalEmbeddingProbe(
          appleSilicon: true, assetsAvailable: false, fixtureSucceeded: false, elapsed: probeBudget,
          dimension: 0, reason: "cancelled")
      } catch {
        return LocalEmbeddingProbe(
          appleSilicon: true, assetsAvailable: false, fixtureSucceeded: false, elapsed: probeBudget,
          dimension: 0, reason: "engine_timeout")
      }
    }
    guard !Task.isCancelled, result.reason != "cancelled" else { return .none }
    guard result.permits(engine, budget: probeBudget) else {
      record("local_embeddings", result.reason.isEmpty ? "capability_mismatch" : result.reason)
      return .none
    }
    return .engine(engine)
  }

  /// Also used after selection so an engine failure cannot change the search route to Gemini.
  func embed(_ texts: [String], task: LocalEmbeddingTask, using engine: any LocalEmbeddingService) async -> [[Float]]? {
    guard killSwitches.isEnabled, !killSwitches.isDisabled, !Task.isCancelled else { return nil }
    do {
      guard texts.count <= engine.capabilities.maxBatchSize else {
        throw LocalInferenceError.invalidResponse("invalid local vector shape")
      }
      let vectors = try await LocalEmbeddingCallBound.run(embedBudget) {
        try await engine.embed(texts, task: task)
      }
      guard !Task.isCancelled, vectors.count == texts.count,
        vectors.allSatisfy({ LocalEmbeddingProbe.valid($0, dimension: engine.dimension) })
      else { throw LocalInferenceError.invalidResponse("invalid local vector shape") }
      return vectors
    } catch is LocalEmbeddingTimeoutError {
      record("local_embeddings", "engine_timeout")
      return nil
    } catch is CancellationError {
      return nil
    } catch {
      record("local_embeddings", "engine_failed")
      return nil
    }
  }
}
