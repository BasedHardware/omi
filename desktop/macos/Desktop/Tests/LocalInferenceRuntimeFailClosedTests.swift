import Foundation
import XCTest

@testable import Omi_Computer

private struct ProbeSummary: Codable, Sendable, Equatable {
  var title: String
}

private final class CallCountingEngine: LocalInferenceService, @unchecked Sendable {
  let engineID: LocalInferenceEngineID
  let capabilities: LocalInferenceCapabilities
  private let lock = NSLock()
  private var generateResults: [Result<ProbeSummary, Error>]
  private var toolLoopError: Error?
  private(set) var generateCallCount = 0
  private(set) var toolLoopCallCount = 0

  init(
    engineID: LocalInferenceEngineID,
    capabilities: LocalInferenceCapabilities = LocalInferenceCapabilities(
      structuredOutput: true,
      toolLoop: false,
      contextWindowTokens: 2048
    ),
    generateResults: [Result<ProbeSummary, Error>],
    toolLoopError: Error? = LocalInferenceError.capabilityUnavailable("tool_loop")
  ) {
    self.engineID = engineID
    self.capabilities = capabilities
    self.generateResults = generateResults
    self.toolLoopError = toolLoopError
  }

  func generateStructured<T: Decodable>(prompt _: String, schema _: LocalInferenceJSONSchema) async throws -> T {
    let result: Result<ProbeSummary, Error> = lock.withLock {
      generateCallCount += 1
      if generateResults.isEmpty {
        return .failure(LocalInferenceError.engineFailed("exhausted_script"))
      }
      return generateResults.removeFirst()
    }
    let summary = try result.get()
    return try JSONDecoder().decode(T.self, from: JSONEncoder().encode(summary))
  }

  func runToolLoop(prompt _: String, tools _: [LocalInferenceToolSpec], budget _: ToolLoopBudget) async throws
    -> ToolLoopResult
  {
    lock.withLock { toolLoopCallCount += 1 }
    if let toolLoopError {
      throw toolLoopError
    }
    return ToolLoopResult(content: "", toolCallNames: [])
  }
}

private actor RecordingLocalInferenceHTTPClient: LocalInferenceHTTPClient {
  private(set) var requests: [URLRequest] = []
  var result: Result<(Data, URLResponse), Error> = .failure(URLError(.cannotConnectToHost))

  func send(_ request: URLRequest) async throws -> (Data, URLResponse) {
    requests.append(request)
    return try result.get()
  }

  func recordedURLs() -> [URL] {
    requests.compactMap(\.url)
  }
}

private struct ProbeSchema {
  static let json = LocalInferenceJSONSchema(
    name: "probe",
    json: Data(
      #"{"type":"object","properties":{"title":{"type":"string"}},"required":["title"]}"#.utf8)
  )
}

private func minimumInput() -> DeterministicMinimumInput {
  DeterministicMinimumInput(
    transcript: "We decided to ship the local runtime today. Extra sentence.",
    startedAt: Date(timeIntervalSince1970: 1_704_140_040),  // 2024-01-01 20:14:00 UTC
    sourceLabel: "Recording",
    timeZone: TimeZone.gmt
  )
}

#if DEBUG
  final class LocalInferenceRuntimeFailClosedTests: XCTestCase {
    override func setUp() {
      super.setUp()
      DesktopDiagnosticsManager.shared.resetForTests()
    }

    override func tearDown() {
      DesktopDiagnosticsManager.shared.resetForTests()
      super.tearDown()
    }

    // red-proof: delete the `guard Self.isRetryable(error)` in `invoke`
    func testPolicyRefusalIsNotAttemptedTwice() async {
      let local = CallCountingEngine(
        engineID: .localServer,
        generateResults: [
          .failure(LocalInferenceError.nonLoopbackBaseURL("https://api.openai.com/v1")),
          .success(ProbeSummary(title: "a retry must never reach this")),
        ]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local],
        killSwitches: .enabled,
        fallback: DesktopLocalInferenceFallbackRecorder(),
        defaultEngineID: .localServer
      )

      let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
        prompt: "summarize",
        schema: ProbeSchema.json,
        minimumInput: minimumInput()
      )

      guard case .deterministicMinimum = result else {
        return XCTFail("a refused request must fail closed, and its retry must not be able to succeed")
      }
      XCTAssertEqual(local.generateCallCount, 1, "a fail-closed component must not re-attempt a refused request")
    }

    func testRetryClassifierSeparatesTransientFromDeterministic() {
      XCTAssertTrue(LocalInferenceRuntime.isRetryable(LocalInferenceError.httpStatus(429)))
      XCTAssertTrue(LocalInferenceRuntime.isRetryable(LocalInferenceError.httpStatus(503)))
      XCTAssertTrue(LocalInferenceRuntime.isRetryable(LocalInferenceError.engineFailed("transport")))
      XCTAssertTrue(LocalInferenceRuntime.isRetryable(URLError(.cannotConnectToHost)))

      XCTAssertFalse(LocalInferenceRuntime.isRetryable(LocalInferenceError.httpStatus(400)))
      XCTAssertFalse(LocalInferenceRuntime.isRetryable(LocalInferenceError.httpStatus(401)))
      XCTAssertFalse(LocalInferenceRuntime.isRetryable(LocalInferenceError.nonLoopbackBaseURL("https://x")))
      XCTAssertFalse(LocalInferenceRuntime.isRetryable(LocalInferenceError.capabilityUnavailable("tool_loop")))
      XCTAssertFalse(LocalInferenceRuntime.isRetryable(LocalInferenceError.invalidResponse("empty_content")))
      XCTAssertFalse(LocalInferenceRuntime.isRetryable(LocalInferenceError.disabled))
      XCTAssertFalse(LocalInferenceRuntime.isRetryable(CancellationError()))
    }

    func testForcedEngineFailureReturnsDeterministicMinimumRecordsFallbackAndDoesNotCallCloud() async throws {
      let local = CallCountingEngine(
        engineID: .localServer,
        generateResults: [
          .failure(LocalInferenceError.engineFailed("forced failure")),
          .failure(LocalInferenceError.engineFailed("forced failure")),
        ]
      )
      let cloud = CallCountingEngine(
        engineID: .afm,
        generateResults: [.success(ProbeSummary(title: "cloud should never run"))]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local, cloud],
        killSwitches: .enabled,
        fallback: DesktopLocalInferenceFallbackRecorder(),
        defaultEngineID: .localServer
      )

      let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
        prompt: "summarize",
        schema: ProbeSchema.json,
        minimumInput: minimumInput()
      )

      guard case .deterministicMinimum(let minimum) = result else {
        return XCTFail("forced engine failure must yield the deterministic minimum, not an engine payload")
      }
      XCTAssertEqual(minimum.title, "We decided to ship the local runtime today.")
      XCTAssertEqual(minimum.overview, "")
      XCTAssertEqual(minimum.category, "other")
      XCTAssertEqual(minimum.processingState, "none")
      XCTAssertEqual(local.generateCallCount, 2)
      XCTAssertEqual(cloud.generateCallCount, 0, "failure must not cascade to another engine or a cloud path")

      let snapshot = try latestFallbackSnapshot()
      XCTAssertEqual(snapshot["event"] as? String, "fallback_triggered")
      XCTAssertEqual(snapshot["area"] as? String, "local_llm")
      XCTAssertEqual(snapshot["from"] as? String, "local-server")
      XCTAssertEqual(snapshot["to"] as? String, "deterministic_minimum")
      XCTAssertEqual(snapshot["reason"] as? String, "engine_failed")
      XCTAssertEqual(snapshot["outcome"] as? String, "exhausted")
    }

    func testDisableKillSwitchSkipsEveryEngine() async {
      let local = CallCountingEngine(
        engineID: .localServer,
        generateResults: [.success(ProbeSummary(title: "should not run"))]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local],
        killSwitches: LocalInferenceKillSwitches(isDisabled: true, forcedEngineRaw: nil),
        fallback: DesktopLocalInferenceFallbackRecorder()
      )

      let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
        prompt: "summarize",
        schema: ProbeSchema.json,
        minimumInput: minimumInput()
      )

      guard case .deterministicMinimum = result else {
        return XCTFail("disableLocalInference must fail closed")
      }
      XCTAssertEqual(local.generateCallCount, 0)

      let snapshot = try? latestFallbackSnapshot()
      XCTAssertEqual(snapshot?["reason"] as? String, "dispatch_disabled")
      XCTAssertEqual(snapshot?["area"] as? String, "local_llm")
    }

    func testForcedAFMWithoutAdapterDoesNotFallThroughToLocalServer() async {
      let local = CallCountingEngine(
        engineID: .localServer,
        generateResults: [.success(ProbeSummary(title: "local would be a leak"))]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local],
        killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "afm"),
        fallback: DesktopLocalInferenceFallbackRecorder()
      )

      let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
        prompt: "summarize",
        schema: ProbeSchema.json,
        minimumInput: minimumInput()
      )

      guard case .deterministicMinimum = result else {
        return XCTFail("unimplemented AFM must fail closed, not select local-server or cloud")
      }
      XCTAssertEqual(local.generateCallCount, 0)
      let snapshot = try? latestFallbackSnapshot()
      XCTAssertEqual(snapshot?["reason"] as? String, "capability_mismatch")
    }

    func testUnknownForcedEngineFailsClosed() async {
      let local = CallCountingEngine(
        engineID: .localServer,
        generateResults: [.success(ProbeSummary(title: "no"))]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local],
        killSwitches: LocalInferenceKillSwitches(isDisabled: false, forcedEngineRaw: "luna"),
        fallback: DesktopLocalInferenceFallbackRecorder()
      )

      let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
        prompt: "summarize",
        schema: ProbeSchema.json,
        minimumInput: minimumInput()
      )

      guard case .deterministicMinimum = result else {
        return XCTFail("unknown engine id must not route anywhere")
      }
      XCTAssertEqual(local.generateCallCount, 0)
    }

    func testRetryOnceCanRecoverWithoutTouchingAnotherEngine() async {
      let local = CallCountingEngine(
        engineID: .localServer,
        generateResults: [
          .failure(LocalInferenceError.engineFailed("transient")),
          .success(ProbeSummary(title: "recovered locally")),
        ]
      )
      let other = CallCountingEngine(
        engineID: .afm,
        generateResults: [.success(ProbeSummary(title: "other engine"))]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local, other],
        killSwitches: .enabled,
        fallback: DesktopLocalInferenceFallbackRecorder()
      )

      let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
        prompt: "summarize",
        schema: ProbeSchema.json,
        minimumInput: minimumInput()
      )

      guard case .engine(let summary, let engineID) = result else {
        return XCTFail("retry on the same local engine should recover")
      }
      XCTAssertEqual(summary.title, "recovered locally")
      XCTAssertEqual(engineID, .localServer)
      XCTAssertEqual(local.generateCallCount, 2)
      XCTAssertEqual(other.generateCallCount, 0)
      let snapshot = try? latestFallbackSnapshot()
      XCTAssertEqual(snapshot?["outcome"] as? String, "recovered")
      XCTAssertEqual(snapshot?["area"] as? String, "local_llm")
    }

    func testToolLoopStubFailsClosedWithoutCallingASecondEngine() async {
      let local = CallCountingEngine(
        engineID: .localServer,
        generateResults: [.success(ProbeSummary(title: "unused"))]
      )
      let other = CallCountingEngine(
        engineID: .afm,
        generateResults: [.success(ProbeSummary(title: "unused"))]
      )
      let runtime = LocalInferenceRuntime(
        engines: [local, other],
        killSwitches: .enabled,
        fallback: DesktopLocalInferenceFallbackRecorder()
      )

      let result = await runtime.runToolLoopFailClosed(
        prompt: "agent",
        tools: [],
        budget: ToolLoopBudget(maxIterations: 1),
        minimumInput: minimumInput()
      )

      guard case .deterministicMinimum = result else {
        return XCTFail("tool loops are stubbed and must fail closed")
      }
      XCTAssertEqual(local.toolLoopCallCount, 0)
      XCTAssertEqual(other.toolLoopCallCount, 0)
    }

    private func latestFallbackSnapshot() throws -> [String: Any] {
      let url = try XCTUnwrap(DesktopDiagnosticsManager.shared.writeDiagnosticsAttachment())
      defer { try? FileManager.default.removeItem(at: url) }
      let data = try Data(contentsOf: url)
      let root = try XCTUnwrap(JSONSerialization.jsonObject(with: data) as? [String: Any])
      let snapshots = try XCTUnwrap(root["snapshots"] as? [[String: Any]])
      return try XCTUnwrap(snapshots.last { ($0["event"] as? String) == "fallback_triggered" })
    }
  }
#endif
