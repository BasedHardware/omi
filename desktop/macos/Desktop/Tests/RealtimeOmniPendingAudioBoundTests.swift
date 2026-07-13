import Foundation
import XCTest

@testable import Omi_Computer

/// Regression coverage for the bounded pre-connect audio buffer in RealtimeOmniService.
///
/// While the relay session is still connecting, mic chunks are queued in `pendingAudio`.
/// Without a cap, a relay that stalls open during a multi-minute locked-mode hold would
/// grow the buffer unboundedly. `appendBoundedAudio` drops the oldest chunks to keep the
/// buffered total under the cap. These tests pin that policy.
final class RealtimeOmniPendingAudioBoundTests: XCTestCase {
    private func chunk(_ n: Int) -> Data { Data(repeating: 0, count: n) }

    func testDropsOldestWhenExceedingCap() {
        var buffer: [Data] = []
        var bytes = 0
        let maxBytes = 100
        // Append 10 chunks of 30 bytes each = 300 bytes; cap is 100.
        for _ in 0..<10 {
            RealtimeOmniService.appendBoundedAudio(chunk(30), to: &buffer, bytes: &bytes, maxBytes: maxBytes)
        }
        XCTAssertLessThanOrEqual(bytes, maxBytes)
        XCTAssertEqual(bytes, buffer.reduce(0) { $0 + $1.count }, "tracked bytes must match buffer contents")
        // 100 / 30 → keeps the newest 3 chunks (90 bytes).
        XCTAssertEqual(buffer.count, 3)
    }

    func testKeepsAtLeastNewestChunkEvenIfItAloneExceedsCap() {
        var buffer: [Data] = []
        var bytes = 0
        RealtimeOmniService.appendBoundedAudio(chunk(500), to: &buffer, bytes: &bytes, maxBytes: 100)
        XCTAssertEqual(buffer.count, 1)
        XCTAssertEqual(bytes, 500)
    }

    func testNoDropUnderCap() {
        var buffer: [Data] = []
        var bytes = 0
        RealtimeOmniService.appendBoundedAudio(chunk(10), to: &buffer, bytes: &bytes, maxBytes: 100)
        RealtimeOmniService.appendBoundedAudio(chunk(20), to: &buffer, bytes: &bytes, maxBytes: 100)
        XCTAssertEqual(buffer.count, 2)
        XCTAssertEqual(bytes, 30)
    }
}
