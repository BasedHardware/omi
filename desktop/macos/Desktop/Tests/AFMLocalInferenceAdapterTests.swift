import Foundation
import XCTest

@testable import Omi_Computer

#if canImport(FoundationModels)
  import FoundationModels
#endif

private struct ProbeSummary: Codable, Sendable, Equatable {
  var title: String
}

private struct FixedAvailability: AFMAvailabilityChecking {
  var value: AFMModelAvailability
  func resolve() -> AFMModelAvailability { value }
}

private final class ScriptedSession: AFMStructuredGenerating, @unchecked Sendable {
  private let lock = NSLock()
  private var results: [Result<Data, Error>]
  private(set) var callCount = 0
  private(set) var lastNode: AFMJSONSchemaNode?
  private(set) var lastPrompt: String?

  init(results: [Result<Data, Error>]) {
    self.results = results
  }

  func generateJSON(prompt: String, node: AFMJSONSchemaNode) async throws -> Data {
    let result: Result<Data, Error> = lock.withLock {
      callCount += 1
      lastNode = node
      lastPrompt = prompt
      if results.isEmpty {
        return .failure(LocalInferenceError.engineFailed("exhausted_script"))
      }
      return results.removeFirst()
    }
    return try result.get()
  }
}

private struct FixedContextWindow: AFMContextWindowProviding {
  var tokens: Int?
  func liveContextWindowTokens() -> Int? { tokens }
}

private func schemaProperty(_ properties: [AFMJSONSchemaNode.ObjectProperty], _ name: String)
  -> AFMJSONSchemaNode.ObjectProperty?
{
  properties.first { $0.name == name }
}

private enum ProbeSchema {
  static let emptyObject = LocalInferenceJSONSchema(name: "probe", json: Data(#"{"type":"object"}"#.utf8))
  static let title = LocalInferenceJSONSchema(
    name: "probe",
    json: Data(#"{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}"#.utf8)
  )
}

final class AFMLocalInferenceAdapterTests: XCTestCase {
  func testCapabilitiesAndEngineID() {
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .unavailable),
      session: ScriptedSession(results: []),
      contextWindow: FixedContextWindow(tokens: nil)
    )
    XCTAssertEqual(adapter.engineID, .afm)
    XCTAssertEqual(adapter.capabilities.structuredOutput, true)
    XCTAssertEqual(adapter.capabilities.toolLoop, false)
    XCTAssertEqual(
      adapter.capabilities.contextWindowTokens,
      AFMLocalInferenceAdapter.unavailableContextWindowFallback
    )
  }

  func testUnavailableReportsFallbackWindowNotTheLiveWindow() {
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .unavailable),
      session: ScriptedSession(results: []),
      contextWindow: FixedContextWindow(tokens: nil)
    )
    XCTAssertEqual(
      adapter.capabilities.contextWindowTokens,
      AFMLocalInferenceAdapter.unavailableContextWindowFallback
    )
    XCTAssertEqual(AFMLocalInferenceAdapter.unavailableContextWindowFallback, 4096)
  }

  func testQueryableWindowIsReportedToTheChunker() {
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .available),
      session: ScriptedSession(results: []),
      contextWindow: FixedContextWindow(tokens: 8192)
    )
    XCTAssertEqual(adapter.capabilities.contextWindowTokens, 8192)
  }

  func testOutOfRangeWindowFallsBackWithoutTrapping() {
    for tokens: Int? in [nil, 0, -1, 255, Int.min, Int.max, 131_073] {
      let adapter = AFMLocalInferenceAdapter(
        availability: FixedAvailability(value: .available),
        session: ScriptedSession(results: []),
        contextWindow: FixedContextWindow(tokens: tokens)
      )
      XCTAssertEqual(
        adapter.capabilities.contextWindowTokens,
        AFMLocalInferenceAdapter.unavailableContextWindowFallback,
        "out-of-range window \(String(describing: tokens)) must fall back"
      )
    }
  }

  func testProductionWindowReadsSystemLanguageModelContextSize() throws {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        throw XCTSkip("FoundationModels needs macOS 26+")
      }
      let adapter = AFMLocalInferenceAdapter()
      switch SystemLanguageModel.default.availability {
      case .available:
        let raw = SystemLanguageModel.default.contextSize
        XCTAssertEqual(AFMSystemContextWindow().liveContextWindowTokens(), raw)
        XCTAssertEqual(
          adapter.capabilities.contextWindowTokens,
          AFMLocalInferenceAdapter.acceptedContextWindowTokens(raw)
        )
      case .unavailable:
        XCTAssertNil(AFMSystemContextWindow().liveContextWindowTokens())
        XCTAssertEqual(
          adapter.capabilities.contextWindowTokens,
          AFMLocalInferenceAdapter.unavailableContextWindowFallback
        )
      @unknown default:
        break
      }
    #else
      throw XCTSkip("FoundationModels SDK is not present")
    #endif
  }

  func testParsesEmptyObjectProbeSchema() throws {
    let node = try AFMJSONSchemaBridge.parse(ProbeSchema.emptyObject)
    guard case .object(let name, let properties, _) = node else {
      return XCTFail("empty object schema must parse as an object")
    }
    XCTAssertEqual(name, "probe")
    XCTAssertEqual(properties, [])
  }

  func testParsesRequiredStringTitleProbeSchema() throws {
    let node = try AFMJSONSchemaBridge.parse(ProbeSchema.title)
    guard case .object(_, let properties, _) = node else {
      return XCTFail("title probe must parse as an object")
    }
    XCTAssertEqual(properties.count, 1)
    XCTAssertEqual(properties[0].name, "title")
    XCTAssertEqual(properties[0].node, .string)
    XCTAssertFalse(properties[0].isOptional)
  }

  func testParsesLocalSummaryDraftSchema() throws {
    let node = try AFMJSONSchemaBridge.parse(LocalSummaryDraft.jsonSchema)
    guard case .object(let name, let properties, _) = node else {
      return XCTFail("draft schema must parse as an object")
    }
    XCTAssertEqual(name, "client_processing_draft")
    XCTAssertEqual(schemaProperty(properties, "title")?.node, .string)
    XCTAssertEqual(schemaProperty(properties, "title")?.isOptional, false)
    XCTAssertEqual(schemaProperty(properties, "overview")?.isOptional, false)
    XCTAssertEqual(schemaProperty(properties, "sections")?.isOptional, false)
    XCTAssertEqual(schemaProperty(properties, "action_items")?.isOptional, false)
    XCTAssertEqual(schemaProperty(properties, "emoji")?.isOptional, true)
    XCTAssertEqual(schemaProperty(properties, "events")?.isOptional, true)
    XCTAssertEqual(schemaProperty(properties, "emoji")?.node, .string)
    XCTAssertEqual(schemaProperty(properties, "category")?.node, .string)

    guard case .array(let sectionItems) = schemaProperty(properties, "sections")?.node,
      case .object(_, let sectionProperties, _) = sectionItems
    else {
      return XCTFail("sections must be an array of objects")
    }
    XCTAssertEqual(schemaProperty(sectionProperties, "heading")?.isOptional, false)
    XCTAssertEqual(schemaProperty(sectionProperties, "body_markdown")?.isOptional, false)

    guard case .array(let eventItems) = schemaProperty(properties, "events")?.node,
      case .object(_, let eventProperties, _) = eventItems
    else {
      return XCTFail("events must be an array of objects")
    }
    XCTAssertEqual(schemaProperty(eventProperties, "duration")?.node, .integer)
    XCTAssertEqual(schemaProperty(eventProperties, "title")?.isOptional, false)
    XCTAssertEqual(schemaProperty(eventProperties, "start")?.isOptional, false)
    XCTAssertEqual(schemaProperty(eventProperties, "description")?.isOptional, true)

    guard case .array(let actionItems) = schemaProperty(properties, "action_items")?.node,
      case .object(_, let actionProperties, _) = actionItems
    else {
      return XCTFail("action_items must be an array of objects")
    }
    XCTAssertEqual(schemaProperty(actionProperties, "description")?.node, .string)
    XCTAssertEqual(schemaProperty(actionProperties, "completed")?.node, .boolean)
    XCTAssertEqual(schemaProperty(actionProperties, "description")?.isOptional, false)
    XCTAssertEqual(schemaProperty(actionProperties, "completed")?.isOptional, true)
  }

  func testUnsupportedShapesThrowCapabilityUnavailable() {
    let cases: [(String, String)] = [
      (#"{"type":"number"}"#, "unsupported_type:number"),
      (#"{"type":"null"}"#, "unsupported_type:null"),
      (#"{"type":["string","null"],"properties":{"title":{"type":"string"}}}"#, "unsupported_type at"),
      (#"{"type":"object","properties":{"status":{"type":"string","enum":["a","b"]}}}"#, "unsupported_keyword:enum"),
      (#"{"type":"object","anyOf":[]}"#, "unsupported_keyword:anyOf"),
      (#"{"type":"object","oneOf":[]}"#, "unsupported_keyword:oneOf"),
      (#"{"type":"object","$ref":"defs/x"}"#, "unsupported_keyword:$ref"),
      (#"{"type":"object","additionalProperties":false}"#, "unsupported_keyword:additionalProperties"),
      (#"{"type":"array","items":{"type":"string"}}"#, "root_must_be_object"),
      (#"{"type":"object","properties":{"tags":{"type":"array"}}}"#, "array_missing_items"),
      (#"{"type":"object","description":1}"#, "description_must_be_string"),
      (#"{"type":"object","properties":{"title":{"type":"string","description":1}}}"#, "description_must_be_string"),
    ]
    for (json, expected) in cases {
      let schema = LocalInferenceJSONSchema(name: "probe", json: Data(json.utf8))
      XCTAssertThrowsError(try AFMJSONSchemaBridge.parse(schema), json) { error in
        guard case LocalInferenceError.capabilityUnavailable(let reason) = error else {
          return XCTFail("expected capabilityUnavailable for \(json), got \(error)")
        }
        XCTAssertTrue(reason.contains(expected), "reason \(reason) should mention \(expected) for \(json)")
      }
    }
  }

  func testRootDescriptionIsPreservedOnTheObjectNode() throws {
    let schema = LocalInferenceJSONSchema(
      name: "probe",
      json: Data(#"{"type":"object","description":"A draft","properties":{"title":{"type":"string"}}}"#.utf8)
    )
    let node = try AFMJSONSchemaBridge.parse(schema)
    guard case .object(let name, _, let description) = node else {
      return XCTFail("root must parse as an object")
    }
    XCTAssertEqual(name, "probe")
    XCTAssertEqual(description, "A draft")
  }

  func testNestingBeyondTheDepthCapIsCapabilityUnavailable() {
    var json = #"{"type":"object"}"#
    for _ in 0...AFMJSONSchemaBridge.maximumNestingDepth {
      json = #"{"type":"object","properties":{"child":\#(json)}}"#
    }
    let schema = LocalInferenceJSONSchema(name: "probe", json: Data(json.utf8))
    XCTAssertThrowsError(try AFMJSONSchemaBridge.parse(schema)) { error in
      guard case LocalInferenceError.capabilityUnavailable(let reason) = error else {
        return XCTFail("expected capabilityUnavailable, got \(error)")
      }
      XCTAssertTrue(reason.contains("nesting_too_deep"), "reason \(reason)")
    }
  }

  func testGenerationSchemaBuildsForEachSupportedShape() throws {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        throw XCTSkip("FoundationModels needs macOS 26+")
      }
      try AFMJSONSchemaBridge.validateGenerationSchema(ProbeSchema.emptyObject)
      try AFMJSONSchemaBridge.validateGenerationSchema(ProbeSchema.title)
      try AFMJSONSchemaBridge.validateGenerationSchema(LocalSummaryDraft.jsonSchema)
    #else
      throw XCTSkip("FoundationModels SDK is not present")
    #endif
  }

  func testUnavailableModelThrowsEngineUnavailableAndDoesNotCallSession() async {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"no"}"#.utf8))])
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .unavailable),
      session: session,
      contextWindow: FixedContextWindow(tokens: nil)
    )
    do {
      let _: ProbeSummary = try await adapter.generateStructured(prompt: "summarize", schema: ProbeSchema.title)
      XCTFail("unavailable AFM must throw")
    } catch LocalInferenceError.engineUnavailable(.afm) {
      XCTAssertEqual(session.callCount, 0)
    } catch {
      XCTFail("expected engineUnavailable(.afm), got \(error)")
    }
  }

  func testMalformedOutputIsInvalidResponse() async {
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .available),
      session: ScriptedSession(results: [.success(Data(#"{"title":"#.utf8))]),
      contextWindow: FixedContextWindow(tokens: 8192)
    )
    do {
      let _: ProbeSummary = try await adapter.generateStructured(prompt: "summarize", schema: ProbeSchema.title)
      XCTFail("malformed JSON must not decode as a partial object")
    } catch LocalInferenceError.invalidResponse(let reason) {
      XCTAssertEqual(reason, "undecodable_content")
    } catch {
      XCTFail("expected invalidResponse, got \(error)")
    }
  }

  func testSuccessfulStructuredDecode() async throws {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"Standup"}"#.utf8))])
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .available),
      session: session,
      contextWindow: FixedContextWindow(tokens: 8192)
    )
    let prompt = ConversationChunkSummarizer.finalPrompt("SPEAKER_00: We decided to ship today.")
    let summary: ProbeSummary = try await adapter.generateStructured(prompt: prompt, schema: ProbeSchema.title)
    XCTAssertEqual(summary, ProbeSummary(title: "Standup"))
    XCTAssertEqual(session.callCount, 1)
    XCTAssertEqual(session.lastPrompt, prompt)
  }

  func testRunToolLoopThrowsCapabilityUnavailable() async {
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .available),
      session: ScriptedSession(results: []),
      contextWindow: FixedContextWindow(tokens: 8192)
    )
    do {
      _ = try await adapter.runToolLoop(
        prompt: "agent",
        tools: [],
        budget: ToolLoopBudget(maxIterations: 1)
      )
      XCTFail("AFM does not implement tool loops")
    } catch LocalInferenceError.capabilityUnavailable(let reason) {
      XCTAssertEqual(reason, "tool_loop")
    } catch {
      XCTFail("expected capabilityUnavailable(tool_loop), got \(error)")
    }
  }

  func testMakeDefaultRegistersBothEngines() throws {
    let runtime = LocalInferenceRuntime.makeDefault(
      killSwitches: .enabled,
      configuration: LocalServerInferenceConfiguration(
        baseURL: try XCTUnwrap(URL(string: "http://127.0.0.1:11434/v1")),
        model: "local",
        contextWindowTokens: 2048,
        timeout: 60
      ),
      afmAvailability: FixedAvailability(value: .unavailable),
      afmSession: ScriptedSession(results: []),
      afmContextWindow: FixedContextWindow(tokens: nil)
    )
    XCTAssertEqual(Set(runtime.engines.map(\.engineID)), [.localServer, .afm])
    XCTAssertEqual(runtime.defaultEngineID, .localServer)
  }

  func testForcedAFMSelectsTheRegisteredAdapter() async throws {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"on-device"}"#.utf8))])
    let afm = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .available),
      session: session,
      contextWindow: FixedContextWindow(tokens: 8192)
    )
    let runtime = LocalInferenceRuntime(
      engines: [
        LocalServerInferenceAdapter(
          configuration: LocalServerInferenceConfiguration(
            baseURL: try XCTUnwrap(URL(string: "http://127.0.0.1:11434/v1")),
            model: "local",
            contextWindowTokens: 8192,
            timeout: 60
          ),
          httpClient: URLSessionLocalInferenceHTTPClient()
        ),
        afm,
      ],
      killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "afm"),
      fallback: DesktopLocalInferenceFallbackRecorder(),
      defaultEngineID: .localServer
    )
    XCTAssertEqual(runtime.selectedContextWindowTokens(), 8192)

    let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
      prompt: "summarize",
      schema: ProbeSchema.title,
      minimumInput: DeterministicMinimumInput(
        transcript: "We decided to ship the local runtime today.",
        startedAt: Date(timeIntervalSince1970: 1_704_140_040)
      )
    )
    guard case .engine(let summary, let engineID) = result else {
      return XCTFail("forced afm must select the AFM adapter, not local-server or the minimum")
    }
    XCTAssertEqual(engineID, .afm)
    XCTAssertEqual(summary.title, "on-device")
    XCTAssertEqual(session.callCount, 1)
  }

  func testMakeDefaultForcedAFMUsesSystemLanguageModelContextSize() throws {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        throw XCTSkip("FoundationModels needs macOS 26+")
      }
      let runtime = LocalInferenceRuntime.makeDefault(
        killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "afm")
      )
      switch SystemLanguageModel.default.availability {
      case .available:
        XCTAssertEqual(
          runtime.selectedContextWindowTokens(),
          AFMLocalInferenceAdapter.acceptedContextWindowTokens(SystemLanguageModel.default.contextSize)
        )
        XCTAssertEqual(
          AFMSystemContextWindow().liveContextWindowTokens(),
          SystemLanguageModel.default.contextSize
        )
      case .unavailable:
        XCTAssertEqual(
          runtime.selectedContextWindowTokens(),
          AFMLocalInferenceAdapter.unavailableContextWindowFallback
        )
      @unknown default:
        break
      }
    #else
      throw XCTSkip("FoundationModels SDK is not present")
    #endif
  }

  func testGenerationErrorRefusalIsInvalidResponseAndNotRetryable() async throws {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        throw XCTSkip("FoundationModels needs macOS 26+")
      }
      if #available(macOS 27.0, *) {
        throw XCTSkip(
          "LanguageModelError mapping waits on an Xcode pin newer than 26.6; GenerationError is deprecated on this SDK"
        )
      } else {
        let refusal = AFMDeprecatedGenerationErrorFixtures.refusal
        let mapped = AFMLocalInferenceAdapter.mapUnknownError(refusal)
        XCTAssertEqual(mapped, .invalidResponse("refusal"))
        XCTAssertFalse(LocalInferenceRuntime.isRetryable(mapped))

        let session = ScriptedSession(results: [.failure(refusal), .success(Data(#"{"title":"retry"}"#.utf8))])
        let adapter = AFMLocalInferenceAdapter(
          availability: FixedAvailability(value: .available),
          session: session,
          contextWindow: FixedContextWindow(tokens: 8192)
        )
        let runtime = LocalInferenceRuntime(
          engines: [adapter],
          killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "afm"),
          fallback: DesktopLocalInferenceFallbackRecorder(),
          defaultEngineID: .localServer
        )
        let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
          prompt: "summarize",
          schema: ProbeSchema.title,
          minimumInput: DeterministicMinimumInput(
            transcript: "We decided to ship the local runtime today.",
            startedAt: Date(timeIntervalSince1970: 1_704_140_040)
          )
        )
        guard case .deterministicMinimum = result else {
          return XCTFail("refusal must fail closed without retrying")
        }
        XCTAssertEqual(session.callCount, 1)
      }
    #else
      throw XCTSkip("FoundationModels SDK is not present")
    #endif
  }

  func testGenerationErrorClassificationAndRetryability() throws {
    #if canImport(FoundationModels)
      guard #available(macOS 26.0, *) else {
        throw XCTSkip("FoundationModels needs macOS 26+")
      }
      if #available(macOS 27.0, *) {
        throw XCTSkip(
          "LanguageModelError mapping waits on an Xcode pin newer than 26.6; GenerationError is deprecated on this SDK"
        )
      } else {
        for (error, expected) in AFMDeprecatedGenerationErrorFixtures.nonretryable {
          let mapped = AFMLocalInferenceAdapter.mapUnknownError(error)
          XCTAssertEqual(mapped, expected, "\(error) -> \(mapped)")
          XCTAssertFalse(LocalInferenceRuntime.isRetryable(mapped), "\(expected) must not retry")
        }
        for (error, expected) in AFMDeprecatedGenerationErrorFixtures.retryable {
          let mapped = AFMLocalInferenceAdapter.mapUnknownError(error)
          XCTAssertEqual(mapped, expected, "\(error) -> \(mapped)")
          XCTAssertTrue(LocalInferenceRuntime.isRetryable(mapped), "\(expected) must remain retryable")
        }
      }
    #else
      throw XCTSkip("FoundationModels SDK is not present")
    #endif
  }
}

#if canImport(FoundationModels)
  @available(macOS, introduced: 26.0, obsoleted: 27.0)
  private enum AFMDeprecatedGenerationErrorFixtures {
    static let context = LanguageModelSession.GenerationError.Context(debugDescription: "t")
    static var refusal: LanguageModelSession.GenerationError {
      .refusal(.init(transcriptEntries: []), context)
    }

    static var nonretryable: [(Error, LocalInferenceError)] {
      [
        (LanguageModelSession.GenerationError.guardrailViolation(context), .invalidResponse("guardrail")),
        (
          LanguageModelSession.GenerationError.exceededContextWindowSize(context),
          .invalidResponse("context_size_exceeded")
        ),
        (LanguageModelSession.GenerationError.unsupportedGuide(context), .capabilityUnavailable("unsupported_guide")),
        (
          LanguageModelSession.GenerationError.unsupportedLanguageOrLocale(context),
          .capabilityUnavailable("unsupported_locale")
        ),
        (LanguageModelSession.GenerationError.assetsUnavailable(context), .engineUnavailable(.afm)),
        (LanguageModelSession.GenerationError.decodingFailure(context), .invalidResponse("decoding_failure")),
        (refusal, .invalidResponse("refusal")),
      ]
    }

    static var retryable: [(Error, LocalInferenceError)] {
      [
        (LanguageModelSession.GenerationError.rateLimited(context), .engineFailed("rate_limited")),
        (LanguageModelSession.GenerationError.concurrentRequests(context), .engineFailed("concurrent_requests")),
      ]
    }
  }
#endif
