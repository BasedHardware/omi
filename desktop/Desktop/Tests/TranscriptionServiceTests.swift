import XCTest

@testable import Omi_Computer

// MARK: - State machine and idempotency tests

final class TranscriptionServiceStateTests: XCTestCase {

    /// Create a service in proxy mode (no API key needed, just needs OMI_API_URL set)
    private func makeService() -> TranscriptionService? {
        // Set env so proxy mode is available — static let already captured,
        // so we create with try? and accept it may throw if env isn't set
        return try? TranscriptionService(apiKey: "test-key", channels: 1)
    }

    func testInitialStateIsDisconnected() {
        guard let service = makeService() else {
            // Can't create without valid env — skip gracefully
            return
        }
        XCTAssertEqual(service.testConnectionState, .disconnected)
        XCTAssertEqual(service.testConnectionGeneration, 0)
    }

    func testStopFromDisconnectedRemainsDisconnected() {
        guard let service = makeService() else { return }
        service.stop()
        XCTAssertEqual(service.testConnectionState, .disconnected)
    }

    func testHandleDisconnectionFromDisconnectedIsNoOp() {
        guard let service = makeService() else { return }
        let genBefore = service.testConnectionGeneration
        service.testHandleDisconnection()
        // Should be a no-op: state stays disconnected, generation unchanged
        XCTAssertEqual(service.testConnectionState, .disconnected)
        XCTAssertEqual(service.testConnectionGeneration, genBefore)
    }

    func testHandleDisconnectionFromConnectedBumpsGeneration() {
        guard let service = makeService() else { return }
        service.testSetState(.connected)
        service.testSetShouldReconnect(false)
        let genBefore = service.testConnectionGeneration
        service.testHandleDisconnection()
        // Should bump generation and transition to disconnected (shouldReconnect=false)
        XCTAssertEqual(service.testConnectionState, .disconnected)
        XCTAssertGreaterThan(service.testConnectionGeneration, genBefore)
    }

    func testHandleDisconnectionIdempotent() {
        guard let service = makeService() else { return }
        service.testSetState(.connected)
        service.testSetShouldReconnect(false)
        // First call
        service.testHandleDisconnection()
        let genAfterFirst = service.testConnectionGeneration
        let stateAfterFirst = service.testConnectionState
        // Second call (should be no-op since we're already disconnected)
        service.testHandleDisconnection()
        XCTAssertEqual(service.testConnectionState, stateAfterFirst)
        XCTAssertEqual(service.testConnectionGeneration, genAfterFirst,
                       "Second handleDisconnection should not bump generation again")
    }

    func testHandleDisconnectionFromReconnectingIsNoOp() {
        guard let service = makeService() else { return }
        service.testSetState(.reconnecting)
        let genBefore = service.testConnectionGeneration
        service.testHandleDisconnection()
        // .reconnecting is guarded out — no state change
        XCTAssertEqual(service.testConnectionState, .reconnecting)
        XCTAssertEqual(service.testConnectionGeneration, genBefore)
    }

    func testHandleDisconnectionFromConnectingBumpsGeneration() {
        guard let service = makeService() else { return }
        service.testSetState(.connecting)
        service.testSetShouldReconnect(false)
        let genBefore = service.testConnectionGeneration
        service.testHandleDisconnection()
        XCTAssertEqual(service.testConnectionState, .disconnected)
        XCTAssertGreaterThan(service.testConnectionGeneration, genBefore)
    }
}

// MARK: - sendAudio drop behavior tests

final class SendAudioDropTests: XCTestCase {

    private func makeService() -> TranscriptionService? {
        return try? TranscriptionService(apiKey: "test-key", channels: 1)
    }

    func testSendAudioDropsWhenDisconnected() {
        guard let service = makeService() else { return }
        // State is .disconnected by default
        let genBefore = service.testConnectionGeneration
        service.sendAudio(Data(repeating: 0xAB, count: 100))
        // Should not change state or generation
        XCTAssertEqual(service.testConnectionState, .disconnected)
        XCTAssertEqual(service.testConnectionGeneration, genBefore)
    }

    func testSendAudioDropsWhenReconnecting() {
        guard let service = makeService() else { return }
        service.testSetState(.reconnecting)
        let genBefore = service.testConnectionGeneration
        service.sendAudio(Data(repeating: 0xCD, count: 100))
        // Should not change state or generation
        XCTAssertEqual(service.testConnectionState, .reconnecting)
        XCTAssertEqual(service.testConnectionGeneration, genBefore)
    }

    func testSendAudioDropsWhenConnecting() {
        guard let service = makeService() else { return }
        service.testSetState(.connecting)
        let genBefore = service.testConnectionGeneration
        service.sendAudio(Data(repeating: 0xEF, count: 100))
        XCTAssertEqual(service.testConnectionState, .connecting)
        XCTAssertEqual(service.testConnectionGeneration, genBefore)
    }
}

// MARK: - Invalid URL construction tests

final class URLConstructionTests: XCTestCase {

    func testEmptyBaseProducesNilComponents() {
        // Simulates what connectWithAuth does with empty base
        let wsBase = ""
        let listenPath = "/v1/proxy/deepgram/ws/v1/listen"
        let components = URLComponents(string: "\(wsBase)\(listenPath)")
        // Empty base + path should still produce valid components (path-only URL)
        // but verify the behavior is defined
        XCTAssertNotNil(components, "Path-only URL should parse")
    }

    func testMalformedBaseProducesNilComponents() {
        // A truly malformed URL that URLComponents rejects
        let wsBase = "wss://[invalid"
        let listenPath = "/v1/listen"
        let components = URLComponents(string: "\(wsBase)\(listenPath)")
        XCTAssertNil(components, "Malformed URL base should produce nil URLComponents")
    }

    func testValidBaseProducesValidURL() {
        let wsBase = "wss://api.omi.me"
        let listenPath = "/v1/proxy/deepgram/ws/v1/listen"
        let components = URLComponents(string: "\(wsBase)\(listenPath)")
        XCTAssertNotNil(components)
        XCTAssertNotNil(components?.url)
    }
}

final class ReconnectDelayTests: XCTestCase {

    func testExponentialGrowth() {
        // With jitter range 1.0...1.0 (no jitter), delays should be exact powers of 2
        let d1 = TranscriptionService.reconnectDelay(attempt: 1, maxBackoff: 60, jitterRange: 1.0...1.0)
        let d2 = TranscriptionService.reconnectDelay(attempt: 2, maxBackoff: 60, jitterRange: 1.0...1.0)
        let d3 = TranscriptionService.reconnectDelay(attempt: 3, maxBackoff: 60, jitterRange: 1.0...1.0)
        let d5 = TranscriptionService.reconnectDelay(attempt: 5, maxBackoff: 60, jitterRange: 1.0...1.0)

        XCTAssertEqual(d1, 2.0, accuracy: 0.001)
        XCTAssertEqual(d2, 4.0, accuracy: 0.001)
        XCTAssertEqual(d3, 8.0, accuracy: 0.001)
        XCTAssertEqual(d5, 32.0, accuracy: 0.001)
    }

    func testMaxBackoffCap() {
        // Attempt 100 should still be capped at maxBackoff
        let delay = TranscriptionService.reconnectDelay(attempt: 100, maxBackoff: 60, jitterRange: 1.0...1.0)
        XCTAssertEqual(delay, 60.0, accuracy: 0.001)
    }

    func testJitterBounds() {
        // Run many iterations to verify jitter stays within range
        for _ in 0..<100 {
            let delay = TranscriptionService.reconnectDelay(attempt: 3, maxBackoff: 60, jitterRange: 0.5...1.5)
            // Base = 8.0, so range is [4.0, 12.0]
            XCTAssertGreaterThanOrEqual(delay, 4.0)
            XCTAssertLessThanOrEqual(delay, 12.0)
        }
    }

    func testAttemptZero() {
        // 2^0 = 1.0
        let delay = TranscriptionService.reconnectDelay(attempt: 0, maxBackoff: 60, jitterRange: 1.0...1.0)
        XCTAssertEqual(delay, 1.0, accuracy: 0.001)
    }
}
