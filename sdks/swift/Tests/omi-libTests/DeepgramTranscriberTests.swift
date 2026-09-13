import XCTest
@testable import omi_lib

final class DeepgramTranscriberTests: XCTestCase {
  func testBuildRequestDefaults() {
    let request = OmiDeepgramTranscriber.buildRequest(apiKey: "dg_test_key_123")
    guard let url = request.url else {
      XCTFail("Expected non-nil request URL")
      return
    }

    XCTAssertEqual(url.scheme, "wss")
    XCTAssertEqual(url.host, "api.deepgram.com")
    XCTAssertEqual(url.path, "/v1/listen")

    let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
    let queryDict = Dictionary(uniqueKeysWithValues: (components?.queryItems ?? []).map { ($0.name, $0.value) })

    XCTAssertEqual(queryDict["punctuate"], "true")
    XCTAssertEqual(queryDict["model"], "nova")
    XCTAssertEqual(queryDict["language"], "en-US")
    XCTAssertEqual(queryDict["encoding"], "linear16")
    XCTAssertEqual(queryDict["sample_rate"], "16000")
    XCTAssertEqual(queryDict["channels"], "1")

    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token dg_test_key_123")
  }

  func testBuildRequestCustomModelAndLanguage() {
    let request = OmiDeepgramTranscriber.buildRequest(
      apiKey: "secret_token",
      sampleRate: 8000,
      model: "nova-2",
      language: "de"
    )
    guard let url = request.url else {
      XCTFail("Expected non-nil request URL")
      return
    }

    let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
    let queryDict = Dictionary(uniqueKeysWithValues: (components?.queryItems ?? []).map { ($0.name, $0.value) })

    XCTAssertEqual(queryDict["punctuate"], "true")
    XCTAssertEqual(queryDict["model"], "nova-2")
    XCTAssertEqual(queryDict["language"], "de")
    XCTAssertEqual(queryDict["encoding"], "linear16")
    XCTAssertEqual(queryDict["sample_rate"], "8000")
    XCTAssertEqual(queryDict["channels"], "1")

    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token secret_token")
  }

  func testBuildRequestMultilingualOption() {
    let request = OmiDeepgramTranscriber.buildRequest(
      apiKey: "token_abc",
      sampleRate: 16000,
      model: "nova-2-general",
      language: "ja"
    )
    guard let url = request.url else {
      XCTFail("Expected non-nil request URL")
      return
    }

    let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
    let queryDict = Dictionary(uniqueKeysWithValues: (components?.queryItems ?? []).map { ($0.name, $0.value) })

    XCTAssertEqual(queryDict["model"], "nova-2-general")
    XCTAssertEqual(queryDict["language"], "ja")
    XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token token_abc")
  }

  func testTranscriberInitializationOffline() {
    let deepgram = OmiDeepgramTranscriber(
      apiKey: "test_key",
      sampleRate: 8000,
      model: "nova-2",
      language: "es",
      autoConnect: false,
      onTranscript: { _ in }
    )
    XCTAssertEqual(deepgram.model, "nova-2")
    XCTAssertEqual(deepgram.language, "es")
    XCTAssertEqual(deepgram.sampleRate, 8000)
  }

  func testSttFactoryRequiresDeepgramAPIKey() {
    XCTAssertThrowsError(
      try OmiSttFactory.makeStreaming(
        engine: .deepgram,
        deepgramAPIKey: nil,
        onTranscript: { _ in }
      )
    ) { error in
      let nsError = error as NSError
      XCTAssertEqual(nsError.domain, "omi.stt")
      XCTAssertEqual(nsError.code, 2)
    }

    XCTAssertThrowsError(
      try OmiSttFactory.makeStreaming(
        engine: .deepgram,
        deepgramAPIKey: "",
        onTranscript: { _ in }
      )
    ) { error in
      let nsError = error as NSError
      XCTAssertEqual(nsError.domain, "omi.stt")
      XCTAssertEqual(nsError.code, 2)
    }
  }
}
