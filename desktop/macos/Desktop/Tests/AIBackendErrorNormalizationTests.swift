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
}
