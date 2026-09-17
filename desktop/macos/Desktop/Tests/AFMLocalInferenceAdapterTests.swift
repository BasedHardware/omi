import Foundation
import XCTest

@testable import Omi_Computer

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

  init(results: [Result<Data, Error>]) {
    self.results = results
  }

  func generateJSON(prompt _: String, node: AFMJSONSchemaNode) async throws -> Data {
    let result: Result<Data, Error> = lock.withLock {
      callCount += 1
      lastNode = node
      if results.isEmpty {
        return .failure(LocalInferenceError.engineFailed("exhausted_script"))
      }
      return results.removeFirst()
    }
    return try result.get()
  }
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
      session: ScriptedSession(results: [])
    )
    XCTAssertEqual(adapter.engineID, .afm)
    XCTAssertEqual(adapter.capabilities.structuredOutput, true)
    XCTAssertEqual(adapter.capabilities.toolLoop, false)
    XCTAssertEqual(adapter.capabilities.contextWindowTokens, AFMLocalInferenceAdapter.contextWindowTokens)
    XCTAssertEqual(AFMLocalInferenceAdapter.contextWindowTokens, 4096)
  }

  func testParsesEmptyObjectProbeSchema() throws {
    let node = try AFMJSONSchemaBridge.parse(ProbeSchema.emptyObject)
    guard case .object(let name, let properties) = node else {
      return XCTFail("empty object schema must parse as an object")
    }
    XCTAssertEqual(name, "probe")
    XCTAssertEqual(properties, [])
  }

  func testParsesRequiredStringTitleProbeSchema() throws {
    let node = try AFMJSONSchemaBridge.parse(ProbeSchema.title)
    guard case .object(_, let properties) = node else {
      return XCTFail("title probe must parse as an object")
    }
    XCTAssertEqual(properties.count, 1)
    XCTAssertEqual(properties[0].name, "title")
    XCTAssertEqual(properties[0].node, .string)
    XCTAssertFalse(properties[0].isOptional)
  }

  func testParsesLocalSummaryDraftSchema() throws {
    let node = try AFMJSONSchemaBridge.parse(LocalSummaryDraft.jsonSchema)
    guard case .object(let name, let properties) = node else {
      return XCTFail("draft schema must parse as an object")
    }
    XCTAssertEqual(name, "client_processing_draft")
    XCTAssertEqual(schemaProperty(properties, "title")?.node, .string)
    XCTAssertEqual(schemaProperty(properties, "title")?.isOptional, false)
    XCTAssertEqual(schemaProperty(properties, "overview")?.isOptional, true)
    XCTAssertEqual(schemaProperty(properties, "emoji")?.node, .string)
    XCTAssertEqual(schemaProperty(properties, "category")?.node, .string)

    guard case .array(let sectionItems) = schemaProperty(properties, "sections")?.node,
      case .object(_, let sectionProperties) = sectionItems
    else {
      return XCTFail("sections must be an array of objects")
    }
    XCTAssertEqual(schemaProperty(sectionProperties, "heading")?.isOptional, false)
    XCTAssertEqual(schemaProperty(sectionProperties, "body_markdown")?.isOptional, false)

    guard case .array(let eventItems) = schemaProperty(properties, "events")?.node,
      case .object(_, let eventProperties) = eventItems
    else {
      return XCTFail("events must be an array of objects")
    }
    XCTAssertEqual(schemaProperty(eventProperties, "duration")?.node, .integer)
    XCTAssertEqual(schemaProperty(eventProperties, "title")?.isOptional, false)
    XCTAssertEqual(schemaProperty(eventProperties, "start")?.isOptional, false)
    XCTAssertEqual(schemaProperty(eventProperties, "description")?.isOptional, true)

    guard case .array(let actionItems) = schemaProperty(properties, "action_items")?.node,
      case .object(_, let actionProperties) = actionItems
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
      session: session
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
      session: ScriptedSession(results: [.success(Data(#"{"title":"#.utf8))])
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
      session: session
    )
    let summary: ProbeSummary = try await adapter.generateStructured(prompt: "summarize", schema: ProbeSchema.title)
    XCTAssertEqual(summary, ProbeSummary(title: "Standup"))
    XCTAssertEqual(session.callCount, 1)
  }

  func testRunToolLoopThrowsCapabilityUnavailable() async {
    let adapter = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .available),
      session: ScriptedSession(results: [])
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

  func testMakeDefaultStillSelectsLocalServer() throws {
    let runtime = LocalInferenceRuntime.makeDefault(
      killSwitches: .enabled,
      configuration: LocalServerInferenceConfiguration(
        baseURL: try XCTUnwrap(URL(string: "http://127.0.0.1:11434/v1")),
        model: "local",
        contextWindowTokens: 8192,
        timeout: 60
      )
    )
    XCTAssertEqual(runtime.defaultEngineID, .localServer)
    XCTAssertEqual(Set(runtime.engines.map(\.engineID)), [.localServer, .afm])
    XCTAssertEqual(runtime.selectedContextWindowTokens(), 8192)
  }

  func testForcedAFMSelectsTheRegisteredAdapter() async throws {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"on-device"}"#.utf8))])
    let afm = AFMLocalInferenceAdapter(
      availability: FixedAvailability(value: .available),
      session: session
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
    XCTAssertEqual(runtime.selectedContextWindowTokens(), AFMLocalInferenceAdapter.contextWindowTokens)

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

  func testMakeDefaultForcedAFMUsesAFMWindow() {
    let runtime = LocalInferenceRuntime.makeDefault(
      killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "foundation-models")
    )
    XCTAssertEqual(runtime.selectedContextWindowTokens(), AFMLocalInferenceAdapter.contextWindowTokens)
  }
}

final class AFMLocalInferenceLiveTests: XCTestCase {
  func testLiveStructuredGeneration() async throws {
    try XCTSkipUnless(isLiveAFMAvailable(), "Apple Foundation Models is not available on this Mac")
    let adapter = AFMLocalInferenceAdapter()
    let summary: ProbeSummary = try await adapter.generateStructured(
      prompt: "Return JSON with title set to the two-word phrase On Device. Do not invent extra fields.",
      schema: ProbeSchema.title
    )
    print("AFM_LIVE_STRUCTURED: title=\(summary.title)")
    XCTAssertFalse(summary.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
  }

  func testLiveConversationChunkSummarizerProducesStoredProjection() async throws {
    try XCTSkipUnless(isLiveAFMAvailable(), "Apple Foundation Models is not available on this Mac")
    let runtime = LocalInferenceRuntime.makeDefault(
      killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "afm")
    )
    XCTAssertEqual(runtime.selectedContextWindowTokens(), AFMLocalInferenceAdapter.contextWindowTokens)
    let store = MemoryLocalProjectionStore()
    let summarizer = ConversationChunkSummarizer(
      runtime: runtime,
      store: store,
      now: { Date(timeIntervalSince1970: 1_704_140_040) },
      deviceClass: "macos",
      sourceLabel: "Recording",
      timeZone: TimeZone.gmt
    )
    let segments = [
      TranscriptHash.Segment(speaker: "SPEAKER_00", text: "We decided to ship the on-device summarizer today."),
      TranscriptHash.Segment(speaker: "SPEAKER_01", text: "I will write the adapter tests this afternoon."),
    ]
    let stored = try await summarizer.summarize(
      sessionId: 42,
      segments: segments,
      startedAt: Date(timeIntervalSince1970: 1_704_140_040)
    )
    let payload = try ClientProcessingContract.decode(stored.json)
    let json = String(decoding: stored.json, as: UTF8.self)
    print("AFM_LIVE_PROJECTION_JSON: \(json)")
    print(
      "AFM_LIVE_PROJECTION: title=\(payload.structure.title) runtime=\(payload.provenance.runtime) model=\(payload.provenance.modelId) overview=\(payload.structure.overview ?? "")"
    )
    XCTAssertEqual(payload.schemaVersion, ClientProcessingContract.schemaVersion)
    XCTAssertEqual(payload.transcriptSha256, TranscriptHash.sha256(segments: segments))
    XCTAssertFalse(payload.structure.title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
    XCTAssertEqual(payload.provenance.runtime, ClientProcessingContract.localRuntime)
    XCTAssertEqual(payload.provenance.modelId, LocalInferenceEngineID.afm.rawValue)
  }

  private func isLiveAFMAvailable() -> Bool {
    AFMSystemAvailabilityChecker().resolve() == .available
  }
}
