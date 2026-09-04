import Foundation
import XCTest

@testable import Omi_Computer

private struct ProbeSummary: Decodable, Sendable, Equatable {
  var title: String
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

  func recordedURLs() -> [URL] {
    requests.compactMap(\.url)
  }

  func recordedBodies() -> [Data] {
    requests.compactMap(\.httpBody)
  }
}

final class LocalServerInferenceAdapterTests: XCTestCase {
  func testRejectsNonLoopbackURLWithoutSendingHTTP() async throws {
    let http = RecordingLocalInferenceHTTPClient()
    let adapter = LocalServerInferenceAdapter(
      configuration: LocalServerInferenceConfiguration(
        baseURL: URL(string: "https://api.openai.com/v1")!,
        model: "gpt-4o",
        contextWindowTokens: 8192,
        timeout: 5
      ),
      httpClient: http
    )

    do {
      let _: ProbeSummary = try await adapter.generateStructured(
        prompt: "hi",
        schema: LocalInferenceJSONSchema(name: "probe", json: Data(#"{"type":"object"}"#.utf8))
      )
      XCTFail("non-loopback base URL must throw")
    } catch LocalInferenceError.nonLoopbackBaseURL(let url) {
      XCTAssertTrue(url.contains("api.openai.com"))
    }
    let urls = await http.recordedURLs()
    XCTAssertEqual(urls, [], "a paid/cloud host must never receive a request")
  }

  func testAllowsIPv4LoopbackAndDecodesStructuredJSON() async throws {
    let http = RecordingLocalInferenceHTTPClient()
    let payload = """
      {"choices":[{"message":{"content":"{\\"title\\":\\"on device\\"}"}}]}
      """
    let url = URL(string: "http://127.0.0.1:11434/v1/chat/completions")!
    await http.setResult(
      .success(
        (
          Data(payload.utf8),
          HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)!
        )
      )
    )
    let adapter = LocalServerInferenceAdapter(
      configuration: LocalServerInferenceConfiguration(
        baseURL: URL(string: "http://127.0.0.1:11434/v1")!,
        model: "local",
        contextWindowTokens: 8192,
        timeout: 5
      ),
      httpClient: http
    )

    let summary: ProbeSummary = try await adapter.generateStructured(
      prompt: "summarize",
      schema: LocalInferenceJSONSchema(
        name: "probe",
        json: Data(#"{"type":"object","properties":{"title":{"type":"string"}}}"#.utf8)
      )
    )

    XCTAssertEqual(summary.title, "on device")
    let urls = await http.recordedURLs()
    XCTAssertEqual(urls, [url])
    XCTAssertTrue(LocalInferenceLoopback.isAllowed(url))
  }

  func testRuntimeFailClosedOnCloudBaseURLSendsNoHTTP() async {
    let http = RecordingLocalInferenceHTTPClient()
    let runtime = LocalInferenceRuntime(
      engines: [
        LocalServerInferenceAdapter(
          configuration: LocalServerInferenceConfiguration(
            baseURL: URL(string: "https://generativelanguage.googleapis.com/v1")!,
            model: "gemini",
            contextWindowTokens: 8192,
            timeout: 5
          ),
          httpClient: http
        )
      ],
      killSwitches: .enabled,
      fallback: DesktopLocalInferenceFallbackRecorder()
    )

    let result: LocalInferenceGeneration<ProbeSummary> = await runtime.generateStructuredFailClosed(
      prompt: "summarize",
      schema: LocalInferenceJSONSchema(name: "probe", json: Data(#"{"type":"object"}"#.utf8)),
      minimumInput: DeterministicMinimumInput(
        transcript: "Hello there.",
        startedAt: Date(timeIntervalSince1970: 0),
        timeZone: TimeZone(secondsFromGMT: 0)!
      )
    )

    guard case .deterministicMinimum = result else {
      return XCTFail("cloud-shaped base URL must fail closed")
    }
    let urls = await http.recordedURLs()
    XCTAssertEqual(urls, [])
  }

  func testToolLoopIsStubbedOnTheAdapter() async {
    let adapter = LocalServerInferenceAdapter(
      configuration: LocalServerInferenceConfiguration(
        baseURL: URL(string: "http://127.0.0.1:11434/v1")!,
        model: "local",
        contextWindowTokens: 8192,
        timeout: 5
      )
    )
    do {
      _ = try await adapter.runToolLoop(
        prompt: "x",
        tools: [],
        budget: ToolLoopBudget(maxIterations: 1)
      )
      XCTFail("tool loop must stay stubbed in S9")
    } catch LocalInferenceError.capabilityUnavailable(let name) {
      XCTAssertEqual(name, "tool_loop")
    } catch {
      XCTFail("unexpected error \(error)")
    }
  }

  func testLoopbackHelperRejectsPublicHosts() {
    XCTAssertTrue(LocalInferenceLoopback.isAllowed(URL(string: "http://127.0.0.1:8080/v1")!))
    XCTAssertTrue(LocalInferenceLoopback.isAllowed(URL(string: "http://localhost:11434/v1")!))
    XCTAssertTrue(LocalInferenceLoopback.isAllowed(URL(string: "http://[::1]:8080/v1")!))
    XCTAssertFalse(LocalInferenceLoopback.isAllowed(URL(string: "https://api.openai.com/v1")!))
    XCTAssertFalse(LocalInferenceLoopback.isAllowed(URL(string: "https://generativelanguage.googleapis.com")!))
    XCTAssertFalse(LocalInferenceLoopback.isAllowed(URL(string: "http://10.0.0.4/v1")!))
  }
}

final class LocalInferenceKillSwitchTests: XCTestCase {
  func testEnvironmentDisableWins() {
    let switches = LocalInferenceKillSwitches.resolve(
      environment: [LocalInferenceKillSwitches.disableEnvironmentKey: "1"],
      defaults: UserDefaults(suiteName: UUID().uuidString)!
    )
    XCTAssertTrue(switches.isDisabled)
  }

  func testUserDefaultsDisable() {
    let defaults = UserDefaults(suiteName: UUID().uuidString)!
    defaults.set(true, forKey: LocalInferenceKillSwitches.disableDefaultsKey)
    let switches = LocalInferenceKillSwitches.resolve(environment: [:], defaults: defaults)
    XCTAssertTrue(switches.isDisabled)
  }

  func testForceEngineFromEnvironment() {
    let switches = LocalInferenceKillSwitches.resolve(
      environment: [LocalInferenceKillSwitches.forceEngineEnvironmentKey: "local-server"],
      defaults: UserDefaults(suiteName: UUID().uuidString)!
    )
    XCTAssertEqual(switches.forcedEngine, .localServer)
  }

  func testForceEngineFromDefaultsWhenEnvAbsent() {
    let defaults = UserDefaults(suiteName: UUID().uuidString)!
    defaults.set("afm", forKey: LocalInferenceKillSwitches.forceEngineDefaultsKey)
    let switches = LocalInferenceKillSwitches.resolve(environment: [:], defaults: defaults)
    XCTAssertEqual(switches.forcedEngine, .afm)
  }
}

final class DeterministicConversationMinimumTests: XCTestCase {
  func testUsesFirstSentenceAndEmptyOverview() {
    let minimum = DeterministicConversationMinimum.make(
      from: DeterministicMinimumInput(
        transcript: "Ship the runtime today. Do not call luna.",
        startedAt: Date(timeIntervalSince1970: 0)
      )
    )
    XCTAssertEqual(minimum.title, "Ship the runtime today.")
    XCTAssertEqual(minimum.overview, "")
    XCTAssertEqual(minimum.category, "other")
    XCTAssertEqual(minimum.processingState, "none")
  }

  func testEmptyTranscriptUsesSourceAndStartedAtNotNow() {
    let started = Date(timeIntervalSince1970: 1_704_140_040)
    let minimum = DeterministicConversationMinimum.make(
      from: DeterministicMinimumInput(
        transcript: "   \n",
        startedAt: started,
        sourceLabel: "Recording",
        timeZone: TimeZone(secondsFromGMT: 0)!
      )
    )
    XCTAssertEqual(minimum.title, "Recording · 8:14 PM")
    XCTAssertEqual(minimum.overview, "")
  }

  func testTruncatesLongSentenceOnAWordBoundary() {
    let words = Array(repeating: "word", count: 40).joined(separator: " ")
    let title = DeterministicConversationMinimum.title(
      from: DeterministicMinimumInput(transcript: words, startedAt: Date(timeIntervalSince1970: 0))
    )
    XCTAssertLessThanOrEqual(title.count, 60)
    XCTAssertFalse(title.hasSuffix(" "))
    XCTAssertTrue(title.hasPrefix("word"))
  }

  func testTitleIsPureOverStartedAt() {
    let input = DeterministicMinimumInput(
      transcript: "",
      startedAt: Date(timeIntervalSince1970: 1_704_140_040),
      timeZone: TimeZone(secondsFromGMT: 0)!
    )
    XCTAssertEqual(
      DeterministicConversationMinimum.title(from: input),
      DeterministicConversationMinimum.title(from: input)
    )
  }
}

final class LocalInferenceCloudEscapeTripwireTests: XCTestCase {
  func testLocalInferenceSourcesDoNotNameACloudLLMClient() throws {
    let sourcesRoot = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources")
      .appendingPathComponent("LocalInference")
    let files = try FileManager.default.contentsOfDirectory(atPath: sourcesRoot.path).filter { $0.hasSuffix(".swift") }
    XCTAssertFalse(files.isEmpty)

    let forbidden = [
      "GeminiClient",
      "ProactiveLaneClient",
      "generativelanguage.googleapis.com",
      "api.openai.com",
      "desktop_proxy",
      "get_llm",
    ]
    for file in files {
      // omi-test-quality: source-inspection -- static contract: local inference fail-closed path cannot name a cloud LLM client
      let text = try String(contentsOf: sourcesRoot.appendingPathComponent(file), encoding: .utf8)
      for token in forbidden {
        XCTAssertFalse(
          text.contains(token),
          "\(file) must not name cloud LLM surface \(token)"
        )
      }
    }
  }
}
