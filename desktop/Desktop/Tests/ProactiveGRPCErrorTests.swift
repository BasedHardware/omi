import XCTest
@testable import Omi_Computer

final class ProactiveGRPCErrorTests: XCTestCase {
    func testRetryableErrorIsRetryable() {
        let error = ProactiveGRPCError.retryableError(code: "GEMINI_ERROR", message: "rate limit")
        XCTAssertTrue(error.isRetryable)
    }

    func testServerErrorIsNotRetryable() {
        let error = ProactiveGRPCError.serverError(code: "INTERNAL", message: "crash")
        XCTAssertFalse(error.isRetryable)
    }

    func testNotConnectedIsNotRetryable() {
        XCTAssertFalse(ProactiveGRPCError.notConnected.isRetryable)
    }

    func testConnectionFailedIsNotRetryable() {
        XCTAssertFalse(ProactiveGRPCError.connectionFailed("refused").isRetryable)
    }

    func testStreamEndedIsNotRetryable() {
        XCTAssertFalse(ProactiveGRPCError.streamEnded.isRetryable)
    }

    func testTimeoutIsNotRetryable() {
        XCTAssertFalse(ProactiveGRPCError.timeout.isRetryable)
    }

    func testErrorDescriptions() {
        XCTAssertNotNil(ProactiveGRPCError.notConnected.errorDescription)
        XCTAssertNotNil(ProactiveGRPCError.connectionFailed("test").errorDescription)
        XCTAssertNotNil(ProactiveGRPCError.serverError(code: "X", message: "Y").errorDescription)
        XCTAssertNotNil(ProactiveGRPCError.retryableError(code: "X", message: "Y").errorDescription)
        XCTAssertNotNil(ProactiveGRPCError.streamEnded.errorDescription)
        XCTAssertNotNil(ProactiveGRPCError.timeout.errorDescription)
    }

    func testRetryableErrorDescription() {
        let error = ProactiveGRPCError.retryableError(code: "RATE_LIMIT", message: "too many")
        XCTAssertTrue(error.errorDescription?.contains("RATE_LIMIT") ?? false)
        XCTAssertTrue(error.errorDescription?.contains("too many") ?? false)
    }
}
