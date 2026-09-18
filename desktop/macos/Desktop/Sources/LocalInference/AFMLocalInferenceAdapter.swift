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

/// Injected window seam. Production reads `SystemLanguageModel.default.contextSize`.
protocol AFMContextWindowProviding: Sendable {
  /// Live on-device window, or `nil` when AFM cannot be queried.
  func liveContextWindowTokens() -> Int?
}

/// Apple Foundation Models adapter for the local-inference port.
///
/// `LocalInferenceRuntime.makeDefault` selects this engine when
/// `AFMAvailabilityChecking` reports `.available`. Pin the other engine with
/// `OMI_FORCE_LOCAL_INFERENCE_ENGINE` / `forceLocalInferenceEngine`. AFM is a
/// selection, not a fallback — a failure here becomes the deterministic
/// minimum, never another engine and never cloud.
struct AFMLocalInferenceAdapter: LocalInferenceService {
  /// Fallback only: used when the OS is older than macOS 26 or the on-device
  /// model cannot be queried. This is **not** the AFM window. The chunker still
  /// needs a positive Int; generation on this path fails closed.
  static let unavailableContextWindowFallback = 4096

  /// Inclusive bounds for a reported window. Outside this range we use
  /// `unavailableContextWindowFallback` so the chunker never subtracts from
  /// `Int.min` and never treats a bogus size as "fits in one prompt".
  static let minimumAcceptedContextWindowTokens = 256
  static let maximumAcceptedContextWindowTokens = 131_072

  static func acceptedContextWindowTokens(_ raw: Int?) -> Int {
    guard let raw,
      raw >= minimumAcceptedContextWindowTokens,
      raw <= maximumAcceptedContextWindowTokens
    else {
      return unavailableContextWindowFallback
    }
    return raw
  }

  var engineID: LocalInferenceEngineID { .afm }
  var capabilities: LocalInferenceCapabilities {
    LocalInferenceCapabilities(
      structuredOutput: true,
      toolLoop: false,
      contextWindowTokens: Self.acceptedContextWindowTokens(contextWindow.liveContextWindowTokens())
    )
  }

  var availability: any AFMAvailabilityChecking
  var session: any AFMStructuredGenerating
  var contextWindow: any AFMContextWindowProviding

  init(
    availability: any AFMAvailabilityChecking = AFMSystemAvailabilityChecker(),
    session: any AFMStructuredGenerating = AFMSystemSession(),
    contextWindow: any AFMContextWindowProviding = AFMSystemContextWindow()
  ) {
    self.availability = availability
    self.session = session
    self.contextWindow = contextWindow
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
    /// CI pins Xcode 26.6 (`desktop/macos/ci/xcode-pin.json`). In the installed
    /// Xcode 27 SDK swiftinterface, `LanguageModelError`,
    /// `SystemLanguageModel.Error`, and `LanguageModelSession.Error` are
    /// `@available(macOS 27.0, *)`. `LanguageModelSession.GenerationError` is
    /// `@available(macOS, introduced: 26.0, deprecated: 27.0)` — not
    /// deprecated-at-26.4 / obsoleted-at-27.0 (that annotation is on
    /// `SystemLanguageModel.Adapter`). The 26.6 ship toolchain therefore
    /// cannot name the replacements, and `#if compiler` is forbidden
    /// (`check-desktop-compiler-gates.py`, #12867/#13548). On macOS 27,
    /// `respond` throws `LanguageModelError.refusal`, which this mapper cannot
    /// see; that misclassification is a known limitation of the Xcode 26.6 pin.
    @available(macOS 26.0, *)
    static func mapFrameworkError(_ error: Error) -> LocalInferenceError {
      if #available(macOS 27.0, *) {
        return .engineFailed("session_failed")
      }
      return mapDeprecatedGenerationError(error)
    }

    @available(macOS, introduced: 26.0, obsoleted: 27.0)
    private static func mapDeprecatedGenerationError(_ error: Error) -> LocalInferenceError {
      guard let generation = error as? LanguageModelSession.GenerationError else {
        return .engineFailed("session_failed")
      }
      switch generation {
      case .exceededContextWindowSize:
        return .invalidResponse("context_size_exceeded")
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

struct AFMSystemContextWindow: AFMContextWindowProviding {
  func liveContextWindowTokens() -> Int? {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        return nil
      }
      switch SystemLanguageModel.default.availability {
      case .available:
        return SystemLanguageModel.default.contextSize
      case .unavailable:
        return nil
      @unknown default:
        return nil
      }
    #else
      return nil
    #endif
  }
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
