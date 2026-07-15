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

  func testRealtimeToolDispatchHasNoPhysicalSideEffectBeforeKernelAuthorization() throws {
    let source = try realtimeHubControllerSource()
    let requestStart = try XCTUnwrap(source.range(of: "func hubDidRequestTool("))
    let requestEnd = try XCTUnwrap(
      source.range(
        of: "func hubDidFinishTurn(",
        range: requestStart.upperBound..<source.endIndex))
    let requestSource = String(source[requestStart.lowerBound..<requestEnd.lowerBound])

    XCTAssertTrue(requestSource.contains(".toolStartedScoped("))
    XCTAssertTrue(requestSource.contains("invokeExternallyAuthorizedTool("))
    XCTAssertFalse(requestSource.contains("ChatToolExecutor.execute"))
    XCTAssertFalse(requestSource.contains("APIClient.shared.tool"))
    XCTAssertFalse(requestSource.contains("ScreenCaptureManager.captureScreen"))
    XCTAssertFalse(requestSource.contains("Self.click(at:"))
    XCTAssertTrue(source.contains("func executeAuthorizedRealtimeTool("))
  }

  func testRealtimeScreenshotUsesOnlyPreCapturedTurnEvidence() throws {
    let source = try realtimeHubControllerSource()
    let beginRange = try XCTUnwrap(source.range(of: "func beginTurn(turnID requestedTurnID:"))
    let nextRange = try XCTUnwrap(
      source.range(
        of: "func captureInterruptedTurnPayloadIfNeeded()",
        range: beginRange.upperBound..<source.endIndex))
    let beginTurnSource = String(source[beginRange.lowerBound..<nextRange.lowerBound])

    XCTAssertFalse(beginTurnSource.contains("ScreenCaptureManager.captureScreen"))
    XCTAssertFalse(beginTurnSource.contains("sendVideoFrame"))
    XCTAssertFalse(source.contains("voiceTurnScreenContextEnvelopeJSON"))
    XCTAssertFalse(source.contains("sendVoiceTurnScreenContextIfNeeded"))
    XCTAssertFalse(source.contains("ScreenCaptureManager.captureScreenJPEG"))
    XCTAssertTrue(source.contains("effect: { [currentEvidence] in [currentEvidence] }"))
    XCTAssertTrue(source.contains("RealtimeScreenEvidenceAttachment"))
  }

  private struct DummyDecodeError: Error {}

  private func realtimeHubControllerSource() throws -> String {
    try RealtimeHubControllerSourceTestSupport.moduleSource(testFilePath: #filePath)
  }
}
