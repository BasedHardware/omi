import XCTest

@testable import Omi_Computer

final class BYOKTranscriptionClarityTests: XCTestCase {
  func testLLMOnlyBYOKStillShowsOmiTranscriptionAllowance() throws {
    let response = try subscription(
      allowance: #"{"mode":"managed","remaining_seconds":120,"reason":"plan_within_allowance"}"#)

    XCTAssertTrue(response.subscription.features.contains("byok"))
    XCTAssertEqual(
      TranscriptionAllowancePresentation.statusText(response.transcriptionAllowance),
      "Transcription: Omi-managed allowance")
  }

  func testLLMAndDeepgramBYOKShowsProviderScopedTranscription() throws {
    let response = try subscription(
      allowance: #"{"mode":"managed","remaining_seconds":null,"reason":"byok"}"#)

    XCTAssertEqual(response.transcriptionAllowance?.reason, "byok")
    XCTAssertNil(response.transcriptionAllowance?.remainingSeconds)
    XCTAssertEqual(
      TranscriptionAllowancePresentation.statusText(response.transcriptionAllowance),
      "Transcription: using your Deepgram key")
  }

  func testExhaustedAllowanceAndMissingServerAnswerDoNotClaimBYOK() throws {
    let exhausted = try subscription(
      allowance: #"{"mode":"on_device","remaining_seconds":0,"reason":"plan_allowance_exhausted"}"#)
    XCTAssertEqual(
      TranscriptionAllowancePresentation.statusText(exhausted.transcriptionAllowance),
      "Transcription: Omi-managed allowance exhausted")

    let olderBackend = try subscription(allowance: nil)
    XCTAssertNil(olderBackend.transcriptionAllowance)
    XCTAssertEqual(
      TranscriptionAllowancePresentation.statusText(olderBackend.transcriptionAllowance),
      "Transcription allowance unavailable — refresh to check")

    let malformedAllowance = try subscription(allowance: #"{"mode":"managed"}"#)
    XCTAssertNil(malformedAllowance.transcriptionAllowance)
  }

  func testFailedAllowanceLookupDoesNotClaimOmiOrDeepgramAccess() throws {
    for reason in ["allowance_unavailable", "usage_invalid"] {
      let response = try subscription(
        allowance: #"{"mode":"on_device","remaining_seconds":0,"reason":"\#(reason)"}"#)
      XCTAssertEqual(
        TranscriptionAllowancePresentation.statusText(response.transcriptionAllowance),
        "Transcription allowance unavailable — refresh to check")
    }
  }

  private func subscription(allowance: String?) throws -> UserSubscriptionResponse {
    let allowanceField = allowance.map { ",\"transcription_allowance\":\($0)" } ?? ""
    let json = """
      {"subscription":{"plan":"unlimited","status":"active","features":["byok"],"cancel_at_period_end":false,"limits":{}}\(allowanceField)}
      """
    return try JSONDecoder().decode(UserSubscriptionResponse.self, from: Data(json.utf8))
  }
}
