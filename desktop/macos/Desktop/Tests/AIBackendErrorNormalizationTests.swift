import XCTest

@testable import Omi_Computer

final class AIBackendErrorNormalizationTests: XCTestCase {
  func testEmbeddingTrialExpiredIsProductGateAndNotSentryActionable() {
    let error = EmbeddingService.EmbeddingError.serverError(
      statusCode: 402,
      body: #"{"error":"trial_expired"}"#)

    XCTAssertEqual(error.reasonCode, "product_gate")
    XCTAssertTrue(error.isExpectedProductState)
    XCTAssertTrue(error.isNonActionableForSentry)
    XCTAssertEqual(
      error.localizedDescription,
      "Embedding API unavailable: active plan or BYOK keys required.")
  }

  func testEmbeddingRateLimitAndUnavailableAreTransient() {
    let rateLimited = EmbeddingService.EmbeddingError.serverError(
      statusCode: 429,
      body: #"{"error":"rate limit exceeded"}"#)
    let unavailable = EmbeddingService.EmbeddingError.serverError(
      statusCode: 503,
      body: #"{"error":"service unavailable"}"#)

    XCTAssertEqual(rateLimited.reasonCode, "rate_limited")
    XCTAssertTrue(rateLimited.isTransient)
    XCTAssertTrue(rateLimited.isNonActionableForSentry)
    XCTAssertEqual(unavailable.reasonCode, "temporarily_unavailable")
    XCTAssertTrue(unavailable.isTransient)
    XCTAssertTrue(unavailable.isNonActionableForSentry)
  }

  func testEmbeddingMalformedResponseRemainsActionable() {
    let error = EmbeddingService.EmbeddingError.invalidResponse

    XCTAssertEqual(error.reasonCode, "malformed_response")
    XCTAssertFalse(error.isNonActionableForSentry)
  }

  func testEmbeddingMissingConfigurationRemainsActionable() {
    let error = EmbeddingService.EmbeddingError.missingAPIKey

    XCTAssertEqual(error.reasonCode, "missing_api_key")
    XCTAssertFalse(error.isExpectedProductState)
    XCTAssertFalse(error.isNonActionableForSentry)
  }

  func testGeminiTrialExpiredIsExpectedProductState() {
    let error = GeminiClient.GeminiClientError.apiError("HTTP 402: trial_expired")

    XCTAssertTrue(error.isExpectedProductState)
    XCTAssertFalse(error.isTransient)
    XCTAssertEqual(error.localizedDescription, "AI features require an active plan or BYOK keys.")
  }

  func testGeminiQuotaExceededUsesProductGateMessage() {
    let error = GeminiClient.GeminiClientError.apiError("quota exceeded")

    XCTAssertTrue(error.isExpectedProductState)
    XCTAssertFalse(error.isTransient)
    XCTAssertEqual(error.localizedDescription, "AI features require an active plan or BYOK keys.")
  }

  func testGeminiRetryRequiresTypedBackendAuthorization() throws {
    let body = Data(#"{"error":"provider_unavailable"}"#.utf8)
    let authorizedResponse = try XCTUnwrap(
      HTTPURLResponse(
        url: URL(string: "https://api.omi.me/v1/proxy/gemini")!,
        statusCode: 503,
        httpVersion: nil,
        headerFields: ["X-Omi-Retryable": "true"]
      ))
    let deniedResponse = try XCTUnwrap(
      HTTPURLResponse(
        url: URL(string: "https://api.omi.me/v1/proxy/gemini")!,
        statusCode: 503,
        httpVersion: nil,
        headerFields: ["X-Omi-Retryable": "false"]
      ))
    let absentResponse = try XCTUnwrap(
      HTTPURLResponse(
        url: URL(string: "https://api.omi.me/v1/proxy/gemini")!,
        statusCode: 503,
        httpVersion: nil,
        headerFields: nil
      ))

    let authorized = try XCTUnwrap(GeminiClient.httpError(response: authorizedResponse, data: body))
    let denied = try XCTUnwrap(GeminiClient.httpError(response: deniedResponse, data: body))
    let absent = try XCTUnwrap(GeminiClient.httpError(response: absentResponse, data: body))

    XCTAssertTrue(GeminiClient.shouldAutoRetry(authorized))
    XCTAssertFalse(GeminiClient.shouldAutoRetry(denied))
    XCTAssertFalse(GeminiClient.shouldAutoRetry(absent))
  }

  /// A *response* still needs the backend's `X-Omi-Retryable` authorization to be replayed
  /// — that contract is unchanged and asserted above. A transport failure produces no
  /// response, so there is no authority to consult, and the previous policy discarded it
  /// after a single attempt.
  ///
  /// That excluded the one error class most worth retrying.
  /// `NSURLErrorNetworkConnectionLost` (-1005) is a stale pooled-connection race, not an
  /// outage: URLSession reuses a keep-alive socket the server has already closed and the
  /// request dies in milliseconds. Measured on a live desktop session, 12 of 13 suggestion
  /// evaluations failed this way — 4-7s apart, with plain requests to the same host
  /// returning 200 in ~0.4s throughout — and every one was dropped without a second try.
  ///
  /// Replay is safe here because every call this client makes is a `generateContent`
  /// inference: prompt plus image in, text out, no server-side state change. A duplicate
  /// costs one extra inference and nothing else.
  func testTransportFailuresAreReplayedWithoutBackendAuthorization() {
    for code in [
      URLError.Code.networkConnectionLost, .timedOut, .cannotConnectToHost,
      .notConnectedToInternet, .dnsLookupFailed, .cannotFindHost,
    ] {
      XCTAssertTrue(
        GeminiClient.shouldAutoRetry(URLError(code)),
        "expected transport failure \(code.rawValue) to be replayable")
    }
  }

  /// The widened replay must stay bounded to transport failures. A cancelled request is the
  /// user or a superseding evaluation withdrawing the work, and replaying it would resurrect
  /// work nobody is waiting for.
  func testNonTransportURLErrorsAreStillNotReplayed() {
    XCTAssertFalse(GeminiClient.shouldAutoRetry(URLError(.cancelled)))
    XCTAssertFalse(GeminiClient.shouldAutoRetry(URLError(.badURL)))
    XCTAssertFalse(GeminiClient.shouldAutoRetry(URLError(.userAuthenticationRequired)))
  }
}
