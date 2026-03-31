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
