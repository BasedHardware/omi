import XCTest

@testable import Omi_Computer

final class ProactiveLaneClientTests: XCTestCase {
  func testEnvelopeParsingPreservesGatewayAccounting() throws {
    let data = try JSONSerialization.data(withJSONObject: [
      "operation": "proactive_reasoning",
      "lane": "omi:auto:desktop-proactive-reasoning",
      "provider_model": "gpt-5.6-luna",
      "usage": ["cached_tokens": 900, "cache_write_tokens": 0],
      "cache_write": false,
      "fallback_class": "unknown",
      "response": ["choices": [["message": ["content": "{\"decision\":\"silence\"}"]]]],
    ])
    let parsed = try ProactiveLaneClient.parseEnvelope(data)
    XCTAssertEqual(parsed.usage.cachedTokens, 900)
    XCTAssertEqual(parsed.lane, "omi:auto:desktop-proactive-reasoning")
    XCTAssertEqual(parsed.content, "{\"decision\":\"silence\"}")
  }

  func testTelemetryProviderModelIsBounded() {
    XCTAssertEqual(ContextProactivityTelemetry.boundedProviderModel("gpt-5.6-luna"), "gpt-5.6-luna")
    XCTAssertEqual(ContextProactivityTelemetry.boundedProviderModel("attacker-controlled-model"), "other")
  }

  func testClientErrorsExposeOnlyStableSafeClassifications() {
    XCTAssertEqual(ProactiveLaneClientError.invalidResponse.localizedDescription, "proactive_invalid_response")
    XCTAssertEqual(
      ProactiveLaneClientError.http(status: 429, retryAfterSeconds: nil).localizedDescription,
      "proactive_http_error status=429")
    XCTAssertEqual(ProactiveLaneClientError.ownerChanged.localizedDescription, "proactive_owner_changed")
  }

  func testGarbageEnvelopeThrowsInvalidResponseNotARawSerializationError() {
    do {
      _ = try ProactiveLaneClient.parseEnvelope(Data("not-json".utf8))
      XCTFail("expected invalid_response")
    } catch ProactiveLaneClientError.invalidResponse {
      // Expected: envelope parse failures are a bounded class, not a Cocoa error.
    } catch {
      XCTFail("unexpected error: \(error)")
    }
  }
}
