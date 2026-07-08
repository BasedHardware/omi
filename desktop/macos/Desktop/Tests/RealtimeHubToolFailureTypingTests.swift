import XCTest

@testable import Omi_Computer

final class RealtimeHubToolFailureTypingTests: XCTestCase {
  func testClassifiesBackendHttpFailuresIntoStableBuckets() {
    XCTAssertEqual(
      RealtimeHubToolFailureKind.classify(APIError.httpError(statusCode: 401)),
      .backendUnauthorized)
    XCTAssertEqual(
      RealtimeHubToolFailureKind.classify(APIError.httpError(statusCode: 429)),
      .backendRateLimited)
    XCTAssertEqual(
      RealtimeHubToolFailureKind.classify(APIError.httpError(statusCode: 422)),
      .backendClientRejected)
    XCTAssertEqual(
      RealtimeHubToolFailureKind.classify(APIError.httpError(statusCode: 503)),
      .backendServerError)
  }

  func testClassifiesCredentialFailuresWithoutRawProviderText() {
    let failure = RealtimeHubToolFailure.classify(
      CredentialHealthError.providerAuth(provider: .openai, mode: .byok, message: "raw provider body"))

    XCTAssertEqual(failure.kind, .providerCredential)
    XCTAssertEqual(
      failure.userFacingOutput(base: "Could not read your memories right now."),
      "Could not read your memories right now. The provider credential needs attention.")
    XCTAssertFalse(failure.userFacingOutput(base: "Could not read your memories right now.").contains("raw provider body"))
  }

  func testClassifiesTransportAndDecodeFailures() {
    XCTAssertEqual(
      RealtimeHubToolFailureKind.classify(APIError.decodingError(DummyDecodeError())),
      .responseDecode)

    let transport = NSError(domain: NSURLErrorDomain, code: NSURLErrorNotConnectedToInternet)
    XCTAssertEqual(RealtimeHubToolFailureKind.classify(transport), .backendTransport)
  }

  func testRealtimeToolCatchPathUsesTypedFailureOutput() throws {
    let source = try realtimeHubControllerSource()

    XCTAssertTrue(source.contains("RealtimeHubToolFailure.classify(error)"))
    XCTAssertTrue(source.contains("failure_type=\\(failure.kind.rawValue)"))
    XCTAssertTrue(source.contains("out = failure.userFacingOutput(base: errorText)"))
    XCTAssertFalse(source.contains("out = errorText }"))
  }

  func testBeginTurnDoesNotUploadSpeculativeScreenshotPixels() throws {
    let source = try realtimeHubControllerSource()
    let beginRange = try XCTUnwrap(source.range(of: "func beginTurn()"))
    let nextRange = try XCTUnwrap(source.range(of: "private func captureInterruptedTurnPayloadIfNeeded()", range: beginRange.upperBound..<source.endIndex))
    let beginTurnSource = String(source[beginRange.lowerBound..<nextRange.lowerBound])

    XCTAssertTrue(beginTurnSource.contains("speculativeScreenshot = jpeg"))
    XCTAssertFalse(beginTurnSource.contains("sendVideoFrame"))
  }

  private struct DummyDecodeError: Error {}

  private func realtimeHubControllerSource() throws -> String {
    let sourceURL = URL(fileURLWithPath: #filePath)
      .deletingLastPathComponent()
      .deletingLastPathComponent()
      .appendingPathComponent("Sources/FloatingControlBar/RealtimeHubController.swift")
    return try String(contentsOf: sourceURL, encoding: .utf8)
  }
}
