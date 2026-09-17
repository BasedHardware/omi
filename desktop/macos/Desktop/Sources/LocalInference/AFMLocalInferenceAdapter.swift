import Foundation

#if canImport(FoundationModels)
  import FoundationModels
#endif

/// Injected availability seam so hermetic tests never touch the on-device model.
protocol AFMAvailabilityChecking: Sendable {
  func resolve() -> AFMModelAvailability
}

enum AFMModelAvailability: Sendable, Equatable {
  case available
  case unavailable
}

/// Injected generation seam. Production talks to `LanguageModelSession`; tests
/// return canned JSON. The adapter still owns schema parsing and `T` decoding.
protocol AFMStructuredGenerating: Sendable {
  func generateJSON(prompt: String, node: AFMJSONSchemaNode) async throws -> Data
}

/// Apple Foundation Models adapter for the local-inference port.
///
/// Dark: `LocalInferenceRuntime.makeDefault` registers this engine but still
/// defaults to `.localServer`. Select it with `OMI_FORCE_LOCAL_INFERENCE_ENGINE=afm`
/// (or the `forceLocalInferenceEngine` default). AFM is a selection, not a
/// fallback — a failure here becomes the deterministic minimum, never another
/// engine and never cloud.
struct AFMLocalInferenceAdapter: LocalInferenceService {
  /// Token window the chunker reads. Cited from FoundationModels
  /// `SystemLanguageModel.contextSize`: the public getter on the macOS 26 SDK
  /// (CI pin Xcode 26.6) returns `4096`, and `ConversationChunkSummarizerTests`
  /// already treats AFM as a 4096-token shared window. Do not change this
  /// without re-citing the SDK — a wrong number silently changes chunking.
  static let contextWindowTokens = 4096

  var engineID: LocalInferenceEngineID { .afm }
  var capabilities: LocalInferenceCapabilities {
    LocalInferenceCapabilities(
      structuredOutput: true,
      toolLoop: false,
      contextWindowTokens: Self.contextWindowTokens
    )
  }

  var availability: any AFMAvailabilityChecking
  var session: any AFMStructuredGenerating

  init(
    availability: any AFMAvailabilityChecking = AFMSystemAvailabilityChecker(),
    session: any AFMStructuredGenerating = AFMSystemSession()
  ) {
    self.availability = availability
    self.session = session
  }

  func generateStructured<T: Decodable>(prompt: String, schema: LocalInferenceJSONSchema) async throws -> T {
    guard availability.resolve() == .available else {
      throw LocalInferenceError.engineUnavailable(.afm)
    }
    let node = try AFMJSONSchemaBridge.parse(schema)
    let data: Data
    do {
      data = try await session.generateJSON(prompt: prompt, node: node)
    } catch is CancellationError {
      throw CancellationError()
    } catch let error as LocalInferenceError {
      throw error
    } catch {
      throw Self.mapUnknownError(error)
    }
    do {
      return try JSONDecoder().decode(T.self, from: data)
    } catch {
      throw LocalInferenceError.invalidResponse("undecodable_content")
    }
  }

  func runToolLoop(prompt _: String, tools _: [LocalInferenceToolSpec], budget _: ToolLoopBudget) async throws
    -> ToolLoopResult
  {
    throw LocalInferenceError.capabilityUnavailable("tool_loop")
  }

  static func mapUnknownError(_ error: Error) -> LocalInferenceError {
    #if canImport(FoundationModels)
      if #available(macOS 26.0, *) {
        return mapFrameworkError(error)
      }
    #endif
    return .engineFailed("session_failed")
  }

  #if canImport(FoundationModels)
    @available(macOS 26.0, *)
    static func mapFrameworkError(_ error: Error) -> LocalInferenceError {
      if let generation = error as? LanguageModelSession.GenerationError {
        return mapGenerationError(generation)
      }
      return .engineFailed("session_failed")
    }

    @available(macOS 26.0, *)
    private static func mapGenerationError(_ error: LanguageModelSession.GenerationError) -> LocalInferenceError {
      switch error {
      case .exceededContextWindowSize:
        return .engineFailed("context_size_exceeded")
      case .assetsUnavailable:
        return .engineUnavailable(.afm)
      case .guardrailViolation:
        return .invalidResponse("guardrail")
      case .unsupportedGuide:
        return .capabilityUnavailable("unsupported_guide")
      case .unsupportedLanguageOrLocale:
        return .capabilityUnavailable("unsupported_locale")
      case .decodingFailure:
        return .invalidResponse("decoding_failure")
      case .rateLimited:
        return .engineFailed("rate_limited")
      case .concurrentRequests:
        return .engineFailed("concurrent_requests")
      case .refusal:
        return .invalidResponse("refusal")
      @unknown default:
        return .engineFailed("session_failed")
      }
    }
  #endif
}

struct AFMSystemAvailabilityChecker: AFMAvailabilityChecking {
  func resolve() -> AFMModelAvailability {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        return .unavailable
      }
      switch SystemLanguageModel.default.availability {
      case .available:
        return .available
      case .unavailable:
        return .unavailable
      @unknown default:
        return .unavailable
      }
    #else
      return .unavailable
    #endif
  }
}

struct AFMSystemSession: AFMStructuredGenerating {
  func generateJSON(prompt: String, node: AFMJSONSchemaNode) async throws -> Data {
    #if canImport(FoundationModels)
      if #available(macOS 26.0, *) {
        return try await generateOnSupportedOS(prompt: prompt, node: node)
      }
    #endif
    throw LocalInferenceError.engineUnavailable(.afm)
  }

  #if canImport(FoundationModels)
    @available(macOS 26.0, *)
    private func generateOnSupportedOS(prompt: String, node: AFMJSONSchemaNode) async throws -> Data {
      let schema: GenerationSchema
      do {
        schema = try AFMJSONSchemaBridge.generationSchema(root: node)
      } catch let error as LocalInferenceError {
        throw error
      } catch {
        throw LocalInferenceError.capabilityUnavailable("generation_schema")
      }

      let session = LanguageModelSession()
      do {
        let response = try await session.respond(to: prompt, schema: schema)
        guard response.content.isComplete else {
          throw LocalInferenceError.invalidResponse("incomplete_content")
        }
        let json = response.content.jsonString
        guard let data = json.data(using: .utf8) else {
          throw LocalInferenceError.invalidResponse("undecodable_content")
        }
        return data
      } catch is CancellationError {
        throw CancellationError()
      } catch let error as LocalInferenceError {
        throw error
      } catch {
        throw AFMLocalInferenceAdapter.mapFrameworkError(error)
      }
    }
  #endif
}
