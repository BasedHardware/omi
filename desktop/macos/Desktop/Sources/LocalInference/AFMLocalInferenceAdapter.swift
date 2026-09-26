import Foundation
import os

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
      Self.trace("AFM_CALL_START schema=\(schema.name) prompt_bytes=\(prompt.utf8.count)")
      data = try await session.generateJSON(prompt: prompt, node: node)
      Self.trace("AFM_CALL_OK schema=\(schema.name) prompt_bytes=\(prompt.utf8.count) completion_bytes=\(data.count)")
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

  /// Nonisolated on purpose: `mapFrameworkError` is a static called from the
  /// generation path, so it cannot reach a main-actor diagnostics manager.
  /// Stdout trace for an evaluation run, off unless asked for.
  ///
  /// The unified log is where the real error goes, and it is not readable from a
  /// test run or a background agent session. Twice that turned a context
  /// overflow into hours of guessing at load and thermal causes. Sizes only —
  /// never prompt or completion text.
  static func trace(_ line: @autoclosure () -> String) {
    guard ProcessInfo.processInfo.environment["OMI_LOCAL_INFERENCE_TRACE"] == "1" else { return }
    print(line())
  }

  static let engineLog = Logger(subsystem: "com.omi.desktop", category: "local-inference")

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
        // The pinned Xcode 26.6 toolchain cannot name `LanguageModelError`, and
        // `#if compiler` is forbidden (check-desktop-compiler-gates.py), so the
        // typed mapping below is unreachable on the OS users actually run.
        //
        // Discarding the error entirely cost three diagnostic runs and two wrong
        // root causes: the real message was
        // "The session's transcript exceeded the model's context size."
        // reported as the same `session_failed` as every other failure.
        //
        // `NSError` bridging needs no framework type, so the description survives
        // the pin. The reason stays low-cardinality; the detail goes to diagnostics.
        let ns = error as NSError
        Self.engineLog.error(
          "AFM generation failed: domain=\(ns.domain, privacy: .public) code=\(ns.code, privacy: .public) message=\(ns.localizedDescription, privacy: .public)"
        )
        trace("AFM_CALL_FAILED domain=\(ns.domain) code=\(ns.code) message=\(ns.localizedDescription)")
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
