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

private final class CountingAvailability: AFMAvailabilityChecking, @unchecked Sendable {
  private let lock = NSLock()
  private let value: AFMModelAvailability
  private(set) var resolveCount = 0

  init(value: AFMModelAvailability) {
    self.value = value
  }

  func resolve() -> AFMModelAvailability {
    lock.withLock { resolveCount += 1 }
    return value
  }
}

private final class ScriptedSession: AFMStructuredGenerating, @unchecked Sendable {
  private let lock = NSLock()
  private var results: [Result<Data, Error>]
  private(set) var callCount = 0

  init(results: [Result<Data, Error>]) {
    self.results = results
  }

  func generateJSON(prompt _: String, node _: AFMJSONSchemaNode) async throws -> Data {
    let result: Result<Data, Error> = lock.withLock {
      callCount += 1
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

private actor RecordingLocalInferenceHTTPClient: LocalInferenceHTTPClient {
  private(set) var requests: [URLRequest] = []
  var result: Result<(Data, URLResponse), Error> = .failure(URLError(.cannotConnectToHost))

  func setResult(_ result: Result<(Data, URLResponse), Error>) {
    self.result = result
  }

  func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
    requests.append(request)
    return try result.get()
  }

  func requestCount() -> Int { requests.count }
}

private enum ProbeSchema {
  static let title = LocalInferenceJSONSchema(
    name: "probe",
    json: Data(#"{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}"#.utf8)
  )
}

private func minimumInput() -> DeterministicMinimumInput {
  DeterministicMinimumInput(
    transcript: "We decided to ship the local runtime today. Extra sentence.",
    startedAt: Date(timeIntervalSince1970: 1_704_140_040),
    sourceLabel: "Recording",
    timeZone: TimeZone.gmt
  )
}

private func loopbackConfiguration(contextWindowTokens: Int) throws -> LocalServerInferenceConfiguration {
  LocalServerInferenceConfiguration(
    baseURL: try XCTUnwrap(URL(string: "http://127.0.0.1:11434/v1")),
    model: "local",
    contextWindowTokens: contextWindowTokens,
    timeout: 60
  )
}

private func successfulLocalServerResponse() throws -> (Data, URLResponse) {
  let url = try XCTUnwrap(URL(string: "http://127.0.0.1:11434/v1/chat/completions"))
  let response = try XCTUnwrap(
    HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: nil)
  )
  let body = Data(#"{"choices":[{"message":{"content":"{\"title\":\"from-local-server\"}"}}]}"#.utf8)
  return (body, response)
}

final class LocalInferenceRuntimeDefaultEngineTests: XCTestCase {
  func testResolveDefaultEngineIDUsesAvailabilitySnapshot() {
    XCTAssertEqual(
      LocalInferenceRuntime.resolveDefaultEngineID(availability: FixedAvailability(value: .available)),
      .afm
    )
    XCTAssertEqual(
      LocalInferenceRuntime.resolveDefaultEngineID(availability: FixedAvailability(value: .unavailable)),
      .localServer
    )
  }

  func testMakeDefaultSelectsAFMWhenAvailable() throws {
    let availability = CountingAvailability(value: .available)
    let runtime = try makeRuntime(
      availability: availability,
      session: ScriptedSession(results: []),
      afmWindow: 8192,
      localServerWindow: 2048
    )
    XCTAssertEqual(runtime.defaultEngineID, .afm)
    XCTAssertEqual(runtime.selectedContextWindowTokens(), 8192)
    XCTAssertEqual(availability.resolveCount, 1, "availability is a construction-time snapshot, not a per-select loop")
  }

  func testMakeDefaultSelectsLocalServerWhenAFMUnavailable() throws {
    let runtime = try makeRuntime(
      availability: FixedAvailability(value: .unavailable),
      session: ScriptedSession(results: []),
      afmWindow: 8192,
      localServerWindow: 2048
    )
    XCTAssertEqual(runtime.defaultEngineID, .localServer)
    XCTAssertEqual(runtime.selectedContextWindowTokens(), 2048)
  }

  func testForceLocalServerWinsEvenWhenAFMIsAvailable() async throws {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"from-afm"}"#.utf8))])
    let http = RecordingLocalInferenceHTTPClient()
    await http.setResult(.success(try successfulLocalServerResponse()))
    let runtime = try makeRuntime(
      availability: FixedAvailability(value: .available),
      session: session,
      afmWindow: 8192,
      localServerWindow: 2048,
      killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "local-server"),
      httpClient: http
    )
    XCTAssertEqual(runtime.defaultEngineID, .afm, "force overlays selection; it does not rewrite the snapshot")
    XCTAssertEqual(runtime.selectedContextWindowTokens(), 2048)

    let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
      prompt: "summarize",
      schema: ProbeSchema.title,
      minimumInput: minimumInput()
    )
    guard case .engine(let summary, let engineID) = result else {
      return XCTFail("forced local-server must run the loopback adapter")
    }
    XCTAssertEqual(engineID, .localServer)
    XCTAssertEqual(summary.title, "from-local-server")
    XCTAssertEqual(session.callCount, 0)
    let requests = await http.requestCount()
    XCTAssertEqual(requests, 1)
  }

  func testForceAFMWinsEvenWhenAFMIsUnavailable() async throws {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"must not generate"}"#.utf8))])
    let http = RecordingLocalInferenceHTTPClient()
    await http.setResult(.success(try successfulLocalServerResponse()))
    let runtime = try makeRuntime(
      availability: FixedAvailability(value: .unavailable),
      session: session,
      afmWindow: nil,
      localServerWindow: 2048,
      killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "afm"),
      httpClient: http
    )
    XCTAssertEqual(runtime.defaultEngineID, .localServer)
    XCTAssertEqual(
      runtime.selectedContextWindowTokens(),
      AFMLocalInferenceAdapter.unavailableContextWindowFallback
    )

    let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
      prompt: "summarize",
      schema: ProbeSchema.title,
      minimumInput: minimumInput()
    )
    guard case .deterministicMinimum = result else {
      return XCTFail("forced AFM that cannot run must fail closed, not local-server")
    }
    XCTAssertEqual(session.callCount, 0, "unavailable AFM must not start a session")
    let requests = await http.requestCount()
    XCTAssertEqual(requests, 0, "force=afm must not fall through to the loopback server")
  }

  func testAvailableAFMGenerationDoesNotCallLocalServer() async throws {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"on-device"}"#.utf8))])
    let http = RecordingLocalInferenceHTTPClient()
    await http.setResult(.success(try successfulLocalServerResponse()))
    let runtime = try makeRuntime(
      availability: FixedAvailability(value: .available),
      session: session,
      afmWindow: 8192,
      localServerWindow: 2048,
      httpClient: http
    )

    let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
      prompt: "summarize",
      schema: ProbeSchema.title,
      minimumInput: minimumInput()
    )
    guard case .engine(let summary, let engineID) = result else {
      return XCTFail("available AFM must be the selected engine")
    }
    XCTAssertEqual(engineID, .afm)
    XCTAssertEqual(summary.title, "on-device")
    XCTAssertEqual(session.callCount, 1)
    let requests = await http.requestCount()
    XCTAssertEqual(requests, 0)
  }

  func testUnavailableAFMGenerationUsesLocalServer() async throws {
    let session = ScriptedSession(results: [.success(Data(#"{"title":"from-afm"}"#.utf8))])
    let http = RecordingLocalInferenceHTTPClient()
    await http.setResult(.success(try successfulLocalServerResponse()))
    let runtime = try makeRuntime(
      availability: FixedAvailability(value: .unavailable),
      session: session,
      afmWindow: 8192,
      localServerWindow: 2048,
      httpClient: http
    )

    let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
      prompt: "summarize",
      schema: ProbeSchema.title,
      minimumInput: minimumInput()
    )
    guard case .engine(let summary, let engineID) = result else {
      return XCTFail("unavailable AFM must select local-server, not the deterministic minimum")
    }
    XCTAssertEqual(engineID, .localServer)
    XCTAssertEqual(summary.title, "from-local-server")
    XCTAssertEqual(session.callCount, 0)
    let requests = await http.requestCount()
    XCTAssertEqual(requests, 1)
  }

  func testSelectedAFMEngineFailureDoesNotConsultLocalServer() async throws {
    let session = ScriptedSession(
      results: [
        .failure(LocalInferenceError.engineFailed("afm failed")),
        .failure(LocalInferenceError.engineFailed("afm failed")),
      ]
    )
    let http = RecordingLocalInferenceHTTPClient()
    await http.setResult(.success(try successfulLocalServerResponse()))
    let runtime = try makeRuntime(
      availability: FixedAvailability(value: .available),
      session: session,
      afmWindow: 8192,
      localServerWindow: 2048,
      httpClient: http
    )

    let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
      prompt: "summarize",
      schema: ProbeSchema.title,
      minimumInput: minimumInput()
    )
    guard case .deterministicMinimum = result else {
      return XCTFail("AFM failure must become the deterministic minimum, not local-server")
    }
    XCTAssertEqual(session.callCount, 2, "retry once on the selected engine")
    let requests = await http.requestCount()
    XCTAssertEqual(requests, 0, "a second registered engine is never consulted on failure")
  }

  func testChunkerWindowFollowsTheSelectedAFMEngine() throws {
    let afmWindow = 8192
    let localServerWindow = 2048
    let runtime = try makeRuntime(
      availability: FixedAvailability(value: .available),
      session: ScriptedSession(results: []),
      afmWindow: afmWindow,
      localServerWindow: localServerWindow
    )
    let selected = try XCTUnwrap(runtime.selectedContextWindowTokens())
    XCTAssertEqual(selected, afmWindow)
    XCTAssertNotEqual(selected, localServerWindow)

    let filler = String(repeating: "word ", count: 2500)
    let segments = [TranscriptHash.Segment(speaker: "SPEAKER_00", text: filler)]
    let afmChunks = ConversationChunkSummarizer.chunk(segments, windowTokens: selected)
    let localChunks = ConversationChunkSummarizer.chunk(segments, windowTokens: localServerWindow)
    XCTAssertEqual(afmChunks.count, 1, "the AFM window must keep this transcript in one prompt")
    XCTAssertGreaterThan(localChunks.count, 1, "the local-server window must not be what the chunker honors")
  }

  private func makeRuntime(
    availability: any AFMAvailabilityChecking,
    session: ScriptedSession,
    afmWindow: Int?,
    localServerWindow: Int,
    killSwitches: LocalInferenceKillSwitches = .enabled,
    httpClient: any LocalInferenceHTTPClient = URLSessionLocalInferenceHTTPClient()
  ) throws -> LocalInferenceRuntime {
    LocalInferenceRuntime.makeDefault(
      httpClient: httpClient,
      killSwitches: killSwitches,
      configuration: try loopbackConfiguration(contextWindowTokens: localServerWindow),
      afmAvailability: availability,
      afmSession: session,
      afmContextWindow: FixedContextWindow(tokens: afmWindow)
    )
  }
}
