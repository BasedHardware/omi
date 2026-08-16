import XCTest

@testable import Omi_Computer

@MainActor
final class LiveTranscriptionFailureStateTests: XCTestCase {
  func testTerminalFailureRemainsVisibleUntilTheBackendReportsReady() {
    let state = AppState()

    state.handleListenEvent(
      TranscriptionService.ListenEvent(
        type: "service_status",
        raw: [
          "status": "stt_failed",
          "outcome": "upstream_error",
          "retryable": true,
        ]
      )
    )

    XCTAssertEqual(state.transcriptionServiceError, "Transcription unavailable")

    state.handleListenEvent(
      TranscriptionService.ListenEvent(type: "service_status", raw: ["status": "ready"])
    )

    XCTAssertNil(state.transcriptionServiceError)
  }

  func testStoppingAfterTerminalFailureClearsTheEndedSessionError() {
    let state = AppState()
    state.handleListenEvent(
      TranscriptionService.ListenEvent(type: "service_status", raw: ["status": "stt_failed"])
    )

    state.stopTranscription()

    XCTAssertNil(state.transcriptionServiceError)
  }
}
