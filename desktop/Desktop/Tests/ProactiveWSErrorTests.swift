import XCTest
@testable import Omi_Computer

final class ProactiveWSErrorTests: XCTestCase {
    func testRetryableErrorIsRetryable() {
        let error = ProactiveWSError.retryableError(code: "GEMINI_ERROR", message: "rate limit")
        XCTAssertTrue(error.isRetryable)
    }

    func testServerErrorIsNotRetryable() {
        let error = ProactiveWSError.serverError(code: "INTERNAL", message: "crash")
        XCTAssertFalse(error.isRetryable)
    }

    func testNotConnectedIsNotRetryable() {
        XCTAssertFalse(ProactiveWSError.notConnected.isRetryable)
    }

    func testConnectionFailedIsNotRetryable() {
        XCTAssertFalse(ProactiveWSError.connectionFailed("refused").isRetryable)
    }

    func testStreamEndedIsNotRetryable() {
        XCTAssertFalse(ProactiveWSError.streamEnded.isRetryable)
    }

    func testTimeoutIsNotRetryable() {
        XCTAssertFalse(ProactiveWSError.timeout.isRetryable)
    }

    func testErrorDescriptions() {
        XCTAssertNotNil(ProactiveWSError.notConnected.errorDescription)
        XCTAssertNotNil(ProactiveWSError.connectionFailed("test").errorDescription)
        XCTAssertNotNil(ProactiveWSError.serverError(code: "X", message: "Y").errorDescription)
        XCTAssertNotNil(ProactiveWSError.retryableError(code: "X", message: "Y").errorDescription)
        XCTAssertNotNil(ProactiveWSError.streamEnded.errorDescription)
        XCTAssertNotNil(ProactiveWSError.timeout.errorDescription)
    }

    func testRetryableErrorDescription() {
        let error = ProactiveWSError.retryableError(code: "RATE_LIMIT", message: "too many")
        XCTAssertTrue(error.errorDescription?.contains("RATE_LIMIT") ?? false)
        XCTAssertTrue(error.errorDescription?.contains("too many") ?? false)
    }
}
