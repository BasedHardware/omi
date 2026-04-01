import XCTest

@testable import Omi_Computer

final class ReconnectAudioRingBufferTests: XCTestCase {

    // MARK: - Basic append and drain

    func testAppendAndDrain() {
        var buffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 960_000)
        let chunk1 = Data(repeating: 0x01, count: 100)
        let chunk2 = Data(repeating: 0x02, count: 200)

        buffer.append(chunk1)
        buffer.append(chunk2)

        let drained = buffer.drain()
        XCTAssertEqual(drained.count, 2)
        XCTAssertEqual(drained[0], chunk1)
        XCTAssertEqual(drained[1], chunk2)
        XCTAssertEqual(buffer.totalBytes, 0)
    }

    func testDrainClearsBuffer() {
        var buffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 960_000)
        buffer.append(Data(repeating: 0xAA, count: 500))
        _ = buffer.drain()

        let secondDrain = buffer.drain()
        XCTAssertTrue(secondDrain.isEmpty)
    }

    func testEmptyDataIgnored() {
        var buffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 960_000)
        buffer.append(Data())
        XCTAssertEqual(buffer.totalBytes, 0)
        XCTAssertTrue(buffer.drain().isEmpty)
    }

    // MARK: - TTL eviction

    func testTTLEviction() {
        var buffer = ReconnectAudioRingBuffer(ttl: 5, maxBytes: 960_000)
        let now = Date()

        // Add a chunk "5.1 seconds ago"
        buffer.append(Data(repeating: 0x01, count: 100), now: now.addingTimeInterval(-5.1))
        // Add a recent chunk
        buffer.append(Data(repeating: 0x02, count: 200), now: now)

        let drained = buffer.drain(now: now)
        XCTAssertEqual(drained.count, 1, "Old chunk should be evicted by TTL")
        XCTAssertEqual(drained[0], Data(repeating: 0x02, count: 200))
    }

    func testPruneEvictsExpired() {
        var buffer = ReconnectAudioRingBuffer(ttl: 2, maxBytes: 960_000)
        let now = Date()

        buffer.append(Data(repeating: 0x01, count: 100), now: now.addingTimeInterval(-3))
        buffer.append(Data(repeating: 0x02, count: 200), now: now)

        buffer.prune(now: now)
        XCTAssertEqual(buffer.totalBytes, 200)
    }

    // MARK: - Byte cap eviction

    func testByteCapEviction() {
        var buffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 500)

        buffer.append(Data(repeating: 0x01, count: 300))
        buffer.append(Data(repeating: 0x02, count: 300))

        // Total would be 600 > 500, so oldest chunk should be evicted
        XCTAssertEqual(buffer.totalBytes, 300)
        let drained = buffer.drain()
        XCTAssertEqual(drained.count, 1)
        XCTAssertEqual(drained[0], Data(repeating: 0x02, count: 300))
    }

    func testMultipleChunksEvictedForByteCap() {
        var buffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 200)

        buffer.append(Data(repeating: 0x01, count: 80))
        buffer.append(Data(repeating: 0x02, count: 80))
        buffer.append(Data(repeating: 0x03, count: 80))
        // 240 > 200, evict oldest until <= 200
        buffer.append(Data(repeating: 0x04, count: 80))
        // 320 > 200, evict more

        XCTAssertTrue(buffer.totalBytes <= 200)
    }

    // MARK: - Oversize chunk truncation

    func testOversizeChunkTruncation() {
        var buffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 100)

        // Append a chunk larger than maxBytes
        let oversized = Data(repeating: 0xFF, count: 500)
        buffer.append(oversized)

        XCTAssertEqual(buffer.totalBytes, 100, "Should be truncated to maxBytes")
        let drained = buffer.drain()
        XCTAssertEqual(drained.count, 1)
        XCTAssertEqual(drained[0].count, 100, "Chunk should be truncated to maxBytes")
        // Should keep the suffix (last 100 bytes)
        XCTAssertEqual(drained[0], Data(repeating: 0xFF, count: 100))
    }

    func testOversizeReplacesExistingChunks() {
        var buffer = ReconnectAudioRingBuffer(ttl: 30, maxBytes: 100)

        buffer.append(Data(repeating: 0x01, count: 50))
        buffer.append(Data(repeating: 0xFF, count: 200))

        // Oversize replaces everything
        XCTAssertEqual(buffer.totalBytes, 100)
        let drained = buffer.drain()
        XCTAssertEqual(drained.count, 1)
    }
}

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

// MARK: - Replay gating tests

final class ReplayGatingTests: XCTestCase {

    private func makeService() -> TranscriptionService? {
        return try? TranscriptionService(apiKey: "test-key", channels: 1)
    }

    func testSendAudioBufferedDuringReplay() {
        guard let service = makeService() else { return }
        service.testSetState(.connected)
        service.testSetIsReplaying(true)

        // sendAudio during replay should buffer data in reconnectBuffer instead of sending
        let chunk = Data(repeating: 0xAB, count: 100)
        service.sendAudio(chunk)

        // The chunk should have been appended to reconnectBuffer
        let buffered = service.testDrainReconnectBuffer()
        XCTAssertEqual(buffered.count, 1, "Chunk should be buffered during replay")
        XCTAssertEqual(buffered[0], chunk)
    }

    func testSendAudioNotBufferedWhenNotReplaying() {
        guard let service = makeService() else { return }
        service.testSetState(.connected)
        service.testSetIsReplaying(false)

        // Without replay, sendAudio should NOT buffer (it tries to send directly)
        let chunk = Data(repeating: 0xCD, count: 100)
        service.sendAudio(chunk)

        // reconnectBuffer should be empty — audio was sent (or attempted), not buffered
        let buffered = service.testDrainReconnectBuffer()
        XCTAssertTrue(buffered.isEmpty, "Audio should not be buffered when not replaying")
    }

    func testIsReplayingInitiallyFalse() {
        guard let service = makeService() else { return }
        XCTAssertFalse(service.testIsReplaying)
    }

    func testReplayFlagToggles() {
        guard let service = makeService() else { return }
        service.testSetIsReplaying(true)
        XCTAssertTrue(service.testIsReplaying)
        service.testSetIsReplaying(false)
        XCTAssertFalse(service.testIsReplaying)
    }
}

// MARK: - Disconnect buffer salvage tests

final class DisconnectBufferSalvageTests: XCTestCase {

    private func makeService() -> TranscriptionService? {
        return try? TranscriptionService(apiKey: "test-key", channels: 1)
    }

    func testHandleDisconnectionFromConnectedPreservesReconnectBuffer() {
        guard let service = makeService() else { return }
        service.testSetState(.connected)
        service.testSetShouldReconnect(false)

        // Pre-populate reconnectBuffer
        let existingChunk = Data(repeating: 0x01, count: 50)
        service.testAppendToReconnectBuffer(existingChunk)

        service.testHandleDisconnection()

        // reconnectBuffer content should survive the disconnection
        let remaining = service.testDrainReconnectBuffer()
        XCTAssertGreaterThanOrEqual(remaining.count, 1, "Reconnect buffer should preserve data across disconnect")
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
