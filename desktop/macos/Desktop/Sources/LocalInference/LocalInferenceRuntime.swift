import Foundation

/// Fail-closed coordinator in front of `LocalInferenceService` engines.
///
/// Ladder: selected local engine → retry once → deterministic minimum.
/// There is no cloud step. A second registered engine is never consulted on
/// failure (AFM is a selection, not a fallback). Kill switches short-circuit
/// before any HTTP.
struct LocalInferenceRuntime: Sendable {
  var engines: [any LocalInferenceService]
  var killSwitches: LocalInferenceKillSwitches
  var fallback: any LocalInferenceFallbackRecording
  var defaultEngineID: LocalInferenceEngineID

  init(
    engines: [any LocalInferenceService],
    killSwitches: LocalInferenceKillSwitches = .enabled,
    fallback: any LocalInferenceFallbackRecording = DesktopLocalInferenceFallbackRecorder(),
    defaultEngineID: LocalInferenceEngineID = .localServer
  ) {
    self.engines = engines
    self.killSwitches = killSwitches
    self.fallback = fallback
    self.defaultEngineID = defaultEngineID
  }

  static func makeDefault(
    httpClient: any LocalInferenceHTTPClient = URLSessionLocalInferenceHTTPClient(),
    killSwitches: LocalInferenceKillSwitches = .resolve(),
    configuration: LocalServerInferenceConfiguration = .fromKillSwitchSources()
  ) -> LocalInferenceRuntime {
    LocalInferenceRuntime(
      engines: [LocalServerInferenceAdapter(configuration: configuration, httpClient: httpClient)],
      killSwitches: killSwitches,
      fallback: DesktopLocalInferenceFallbackRecorder(),
      defaultEngineID: .localServer
    )
  }

  func generateStructuredFailClosed<T: Decodable & Sendable>(
    prompt: String,
    schema: LocalInferenceJSONSchema,
    minimumInput: DeterministicMinimumInput
  ) async -> LocalInferenceGeneration<T> {
    if killSwitches.isDisabled {
      return failClosed(
        from: selectedEngineID()?.rawValue ?? "none",
        reason: "dispatch_disabled",
        input: minimumInput
      )
    }

    switch selectEngine() {
    case .failure(let reason, let from):
      return failClosed(from: from, reason: reason, input: minimumInput)
    case .success(let engine):
      return await invoke(engine, prompt: prompt, schema: schema, minimumInput: minimumInput)
    }
  }

  func runToolLoopFailClosed(
    prompt: String,
    tools: [LocalInferenceToolSpec],
    budget: ToolLoopBudget,
    minimumInput: DeterministicMinimumInput
  ) async -> LocalInferenceGeneration<ToolLoopResult> {
    if killSwitches.isDisabled {
      return failClosed(
        from: selectedEngineID()?.rawValue ?? "none",
        reason: "dispatch_disabled",
        input: minimumInput
      )
    }
    switch selectEngine() {
    case .failure(let reason, let from):
      return failClosed(from: from, reason: reason, input: minimumInput)
    case .success(let engine):
      guard engine.capabilities.toolLoop else {
        return failClosed(from: engine.engineID.rawValue, reason: "capability_mismatch", input: minimumInput)
      }
      do {
        let result = try await engine.runToolLoop(prompt: prompt, tools: tools, budget: budget)
        return .engine(result, engineID: engine.engineID)
      } catch {
        return failClosed(from: engine.engineID.rawValue, reason: reason(for: error), input: minimumInput)
      }
    }
  }

  private enum Selection {
    case success(any LocalInferenceService)
    case failure(reason: String, from: String)
  }

  private func selectedEngineID() -> LocalInferenceEngineID? {
    if let raw = killSwitches.forcedEngineRaw, !raw.isEmpty {
      return LocalInferenceEngineID.parse(raw)
    }
    return defaultEngineID
  }

  private func selectEngine() -> Selection {
    if let raw = killSwitches.forcedEngineRaw, !raw.isEmpty, killSwitches.forcedEngine == nil {
      return .failure(reason: "config_incomplete", from: raw)
    }
    let wanted = selectedEngineID() ?? defaultEngineID
    if wanted == .afm {
      // S12 lands the AFM adapter. Selecting it today is a closed door, not luna.
      if let engine = engines.first(where: { $0.engineID == .afm }) {
        return .success(engine)
      }
      return .failure(reason: "capability_mismatch", from: wanted.rawValue)
    }
    guard let engine = engines.first(where: { $0.engineID == wanted }) else {
      return .failure(reason: "engine_failed", from: wanted.rawValue)
    }
    return .success(engine)
  }

  private func invoke<T: Decodable & Sendable>(
    _ engine: any LocalInferenceService,
    prompt: String,
    schema: LocalInferenceJSONSchema,
    minimumInput: DeterministicMinimumInput
  ) async -> LocalInferenceGeneration<T> {
    guard engine.capabilities.structuredOutput else {
      return failClosed(from: engine.engineID.rawValue, reason: "capability_mismatch", input: minimumInput)
    }
    do {
      let value: T = try await engine.generateStructured(prompt: prompt, schema: schema)
      return .engine(value, engineID: engine.engineID)
    } catch {
      guard Self.isRetryable(error) else {
        // A refusal, a permanent 4xx, an undecodable response, or a cancelled
        // task: attempting it a second time cannot change the answer, and a
        // fail-closed component must not re-attempt an operation policy has
        // already refused.
        return failClosed(from: engine.engineID.rawValue, reason: reason(for: error), input: minimumInput)
      }
      do {
        let value: T = try await engine.generateStructured(prompt: prompt, schema: schema)
        fallback.recordLocalInferenceFallback(
          from: engine.engineID.rawValue,
          to: engine.engineID.rawValue,
          reason: reason(for: error),
          outcome: .recovered
        )
        return .engine(value, engineID: engine.engineID)
      } catch let retryError {
        return failClosed(
          from: engine.engineID.rawValue,
          reason: reason(for: retryError),
          input: minimumInput
        )
      }
    }
  }

  private func failClosed<T: Sendable>(
    from: String,
    reason: String,
    input: DeterministicMinimumInput
  ) -> LocalInferenceGeneration<T> {
    fallback.recordLocalInferenceFallback(
      from: from,
      to: "deterministic_minimum",
      reason: reason,
      outcome: .exhausted
    )
    return .deterministicMinimum(DeterministicConversationMinimum.make(from: input))
  }

  /// Only a failure a second identical attempt could plausibly survive.
  ///
  /// Transport faults, 429, and 5xx are the engine being briefly unavailable.
  /// Everything else — policy refusal, capability mismatch, unknown engine,
  /// undecodable output, any other 4xx, cancellation — is deterministic, and
  /// retrying it doubles the work and (for `nonLoopbackBaseURL`) attempts a
  /// refused request twice.
  static func isRetryable(_ error: Error) -> Bool {
    if error is CancellationError { return false }
    switch error as? LocalInferenceError {
    case .httpStatus(let status):
      return status == 429 || status >= 500
    case .disabled, .nonLoopbackBaseURL, .capabilityUnavailable, .unknownEngine, .engineUnavailable,
      .invalidResponse:
      return false
    case .engineFailed:
      return true
    case .none:
      // Not one of ours: a URLError or another transport-layer failure.
      return true
    }
  }

  private func reason(for error: Error) -> String {
    switch error as? LocalInferenceError {
    case .disabled:
      return "dispatch_disabled"
    case .nonLoopbackBaseURL:
      return "policy"
    case .httpStatus(let status) where status == 429:
      return "provider_429"
    case .httpStatus(let status) where status >= 500:
      return "provider_5xx"
    case .capabilityUnavailable:
      return "capability_mismatch"
    case .engineUnavailable, .unknownEngine:
      return "config_incomplete"
    default:
      return "engine_failed"
    }
  }
}
