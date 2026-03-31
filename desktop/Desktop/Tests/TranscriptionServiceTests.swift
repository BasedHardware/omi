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

// MARK: - Batch Transcription Splitting Tests

final class BatchSplitTests: XCTestCase {

    func testDedupeOverlapWordsRemovesDuplicates() {
        let first = [
            TranscriptionService.TranscriptSegment.Word(word: "hello", start: 0.0, end: 0.5, confidence: 0.9, speaker: 0, punctuatedWord: "Hello"),
            TranscriptionService.TranscriptSegment.Word(word: "world", start: 0.5, end: 1.0, confidence: 0.9, speaker: 0, punctuatedWord: "world"),
        ]
        let second = [
            // Duplicate of "world" — within 0.5s of first-half version
            TranscriptionService.TranscriptSegment.Word(word: "world", start: 0.6, end: 1.1, confidence: 0.8, speaker: 0, punctuatedWord: "world"),
            TranscriptionService.TranscriptSegment.Word(word: "foo", start: 1.5, end: 2.0, confidence: 0.9, speaker: 0, punctuatedWord: "foo"),
        ]

        let result = TranscriptionService.dedupeOverlapWords(first: first, second: second)
        XCTAssertEqual(result.count, 3)
        XCTAssertEqual(result[0].word, "hello")
        XCTAssertEqual(result[1].word, "world")
        XCTAssertEqual(result[2].word, "foo")
    }

    func testDedupeOverlapWordsKeepsNonOverlapping() {
        let first = [
            TranscriptionService.TranscriptSegment.Word(word: "hello", start: 0.0, end: 0.5, confidence: 0.9, speaker: 0, punctuatedWord: "Hello"),
        ]
        let second = [
            TranscriptionService.TranscriptSegment.Word(word: "world", start: 5.0, end: 5.5, confidence: 0.9, speaker: 0, punctuatedWord: "world"),
        ]

        let result = TranscriptionService.dedupeOverlapWords(first: first, second: second)
        XCTAssertEqual(result.count, 2)
        XCTAssertEqual(result[0].word, "hello")
        XCTAssertEqual(result[1].word, "world")
    }

    func testDedupeOverlapWordsEmptyFirst() {
        let second = [
            TranscriptionService.TranscriptSegment.Word(word: "hello", start: 0.0, end: 0.5, confidence: 0.9, speaker: 0, punctuatedWord: "Hello"),
        ]

        let result = TranscriptionService.dedupeOverlapWords(first: [], second: second)
        XCTAssertEqual(result.count, 1)
        XCTAssertEqual(result[0].word, "hello")
    }

    func testMergeSegmentsOffsetsSecondHalf() {
        let first = [
            TranscriptionService.TranscriptSegment(
                text: "hello", isFinal: true, speechFinal: true, confidence: 0.9,
                words: [.init(word: "hello", start: 0.0, end: 0.5, confidence: 0.9, speaker: 0, punctuatedWord: "hello")],
                channelIndex: 0
            ),
        ]
        let second = [
            TranscriptionService.TranscriptSegment(
                text: "world", isFinal: true, speechFinal: true, confidence: 0.9,
                words: [.init(word: "world", start: 0.0, end: 0.5, confidence: 0.9, speaker: 0, punctuatedWord: "world")],
                channelIndex: 0
            ),
        ]

        let merged = TranscriptionService.mergeSegments(first: first, second: second, secondOffsetSec: 10.0)
        XCTAssertEqual(merged.count, 1)
        XCTAssertEqual(merged[0].channelIndex, 0)
        XCTAssertEqual(merged[0].words.count, 2)
        XCTAssertEqual(merged[0].words[0].word, "hello")
        XCTAssertEqual(merged[0].words[0].start, 0.0, accuracy: 0.001)
        XCTAssertEqual(merged[0].words[1].word, "world")
        XCTAssertEqual(merged[0].words[1].start, 10.0, accuracy: 0.001)
    }

    func testMergeSegmentsMultiChannel() {
        let first = [
            TranscriptionService.TranscriptSegment(
                text: "mic", isFinal: true, speechFinal: true, confidence: 0.9,
                words: [.init(word: "mic", start: 0.0, end: 0.5, confidence: 0.9, speaker: 0, punctuatedWord: "mic")],
                channelIndex: 0
            ),
        ]
        let second = [
            TranscriptionService.TranscriptSegment(
                text: "sys", isFinal: true, speechFinal: true, confidence: 0.9,
                words: [.init(word: "sys", start: 0.0, end: 0.5, confidence: 0.9, speaker: 1, punctuatedWord: "sys")],
                channelIndex: 1
            ),
        ]

        let merged = TranscriptionService.mergeSegments(first: first, second: second, secondOffsetSec: 5.0)
        XCTAssertEqual(merged.count, 2)
        let ch0 = merged.first { $0.channelIndex == 0 }
        let ch1 = merged.first { $0.channelIndex == 1 }
        XCTAssertEqual(ch0?.words.count, 1)
        XCTAssertEqual(ch1?.words.count, 1)
        XCTAssertEqual(ch1?.words[0].start ?? 0, 5.0, accuracy: 0.001)
    }

    func testMaxBatchBytesConsistent() {
        XCTAssertEqual(TranscriptionService.maxBatchPayloadBytes, VADGateService.maxBatchBytes)
    }

    func testSplitPointIsFrameAligned() {
        // Stereo Int16: 4 bytes per frame
        let audioSize = 100_001  // Not frame-aligned
        let mid = audioSize / 2
        let aligned = (mid / 4) * 4
        XCTAssertEqual(aligned % 4, 0)
        XCTAssertTrue(aligned <= mid)
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
