import Foundation

/// Engine identifiers the runtime knows how to select.
///
/// AFM is named so `forceLocalInferenceEngine=afm` fails closed in this shard
/// (S12 lands the adapter). There is no cloud case: a missing or failed local
/// engine becomes the deterministic minimum, never luna.
enum LocalInferenceEngineID: String, Sendable, Equatable, CaseIterable {
  case localServer = "local-server"
  case afm = "afm"

  static func parse(_ raw: String) -> LocalInferenceEngineID? {
    let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
    switch trimmed {
    case Self.localServer.rawValue, "local_server", "local", "ollama", "llamacpp":
      return .localServer
    case Self.afm.rawValue, "foundation-models", "foundation_models":
      return .afm
    default:
      return nil
    }
  }
}

struct LocalInferenceCapabilities: Sendable, Equatable {
  var structuredOutput: Bool
  var toolLoop: Bool
  var contextWindowTokens: Int
}

struct LocalInferenceJSONSchema: Sendable, Equatable {
  var name: String
  var json: Data
}

struct LocalInferenceToolSpec: Sendable, Equatable {
  var name: String
  var description: String
  var parametersJSON: Data
}

struct ToolLoopBudget: Sendable, Equatable {
  var maxIterations: Int
}

struct ToolLoopResult: Sendable, Equatable {
  var content: String
  var toolCallNames: [String]
}

enum LocalInferenceError: Error, Equatable {
  case disabled
  case engineUnavailable(LocalInferenceEngineID)
  case unknownEngine(String)
  case nonLoopbackBaseURL(String)
  case engineFailed(String)
  case capabilityUnavailable(String)
  case invalidResponse(String)
  case httpStatus(Int)
}

/// Local LLM execution port. Engines implement this; the runtime selects one
/// and fail-closes to the deterministic minimum. Tool loops ship as a stub
/// (TBD-2 / S12) and stay feature-detected per engine.
protocol LocalInferenceService: Sendable {
  var engineID: LocalInferenceEngineID { get }
  var capabilities: LocalInferenceCapabilities { get }

  func generateStructured<T: Decodable>(prompt: String, schema: LocalInferenceJSONSchema) async throws -> T
  func runToolLoop(prompt: String, tools: [LocalInferenceToolSpec], budget: ToolLoopBudget) async throws
    -> ToolLoopResult
}

enum LocalInferenceGeneration<T: Sendable>: Sendable {
  case engine(T, engineID: LocalInferenceEngineID)
  case deterministicMinimum(DeterministicConversationMinimum)
}

protocol LocalInferenceFallbackRecording: Sendable {
  func recordLocalInferenceFallback(
    from: String,
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome
  )
}

struct DesktopLocalInferenceFallbackRecorder: LocalInferenceFallbackRecording {
  func recordLocalInferenceFallback(
    from: String,
    to: String,
    reason: String,
    outcome: DesktopFallbackOutcome
  ) {
    DesktopDiagnosticsManager.shared.recordFallback(
      area: "local_llm",
      from: from,
      to: to,
      reason: reason,
      outcome: outcome
    )
  }
}
