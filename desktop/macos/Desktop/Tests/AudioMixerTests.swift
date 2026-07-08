import XCTest
@testable import Omi_Computer

final class AudioMixerTests: XCTestCase {

    // Fake clock: tests control time by mutating `now`.
    private var now: CFAbsoluteTime = 1000.0
    private func fakeClock() -> CFAbsoluteTime { now }

    /// 3200 bytes of non-silent Int16 PCM (minBufferBytes threshold).
    private func audioChunk(value: Int16 = 1000, byteCount: Int = 3200) -> Data {
        let sampleCount = byteCount / 2
        var samples = [Int16](repeating: value, count: sampleCount)
        return samples.withUnsafeMutableBufferPointer { Data(buffer: $0) }
    }

    /// Empty Data (0 bytes).
    private func emptyChunk() -> Data { Data() }

    // MARK: - Normal dual-source mixing

    func testDualSourceMonoMixing() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Both sources deliver enough data
        mixer.setMicAudio(audioChunk(value: 100))
        XCTAssertEqual(output.count, 0, "Should wait for both buffers")

        mixer.setSystemAudio(audioChunk(value: 200))
        XCTAssertEqual(output.count, 1, "Should emit once both have data")

        // Verify summing: 100 + 200 = 300
        let samples = output[0].withUnsafeBytes { $0.bindMemory(to: Int16.self) }
        XCTAssertEqual(samples[0], 300)
    }

    func testDualSourceStereoInterleaving() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .stereo, clock: fakeClock)
        mixer.start { output.append($0) }

        mixer.setMicAudio(audioChunk(value: 100))
        mixer.setSystemAudio(audioChunk(value: 200))
        XCTAssertEqual(output.count, 1)

        // Stereo: [mic0, sys0, mic1, sys1, ...]
        let samples = output[0].withUnsafeBytes { $0.bindMemory(to: Int16.self) }
        XCTAssertEqual(samples[0], 100, "Left channel = mic")
        XCTAssertEqual(samples[1], 200, "Right channel = system")
    }

    // MARK: - System source stall (mic-only mode)

    func testSystemNeverStartsMicBlockedBeforeTimeout() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Advance 1.9s (below timeout)
        now += 1.9
        mixer.setMicAudio(audioChunk(value: 500))
        XCTAssertEqual(output.count, 0, "Should still wait for system before timeout")
    }

    func testSystemNeverStartsMicEmitsAfterTimeout() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Advance past timeout
        now += 2.1
        mixer.setMicAudio(audioChunk(value: 500))
        XCTAssertEqual(output.count, 1, "Should emit mic-only after system stall timeout")

        // Output should be mic audio (summed with silence = unchanged)
        let samples = output[0].withUnsafeBytes { $0.bindMemory(to: Int16.self) }
        XCTAssertEqual(samples[0], 500)
    }

    // MARK: - Mic source stall (system-only mode)

    func testMicNeverStartsSystemEmitsAfterTimeout() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        now += 2.1
        mixer.setSystemAudio(audioChunk(value: 300))
        XCTAssertEqual(output.count, 1, "Should emit system-only after mic stall timeout")

        let samples = output[0].withUnsafeBytes { $0.bindMemory(to: Int16.self) }
        XCTAssertEqual(samples[0], 300)
    }

    // MARK: - Active source stops mid-session

    func testSystemStopsAfterBeingActive() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Both sources active
        mixer.setMicAudio(audioChunk(value: 100))
        mixer.setSystemAudio(audioChunk(value: 200))
        XCTAssertEqual(output.count, 1)

        // System stops, mic continues. Advance past timeout.
        now += 2.1
        mixer.setMicAudio(audioChunk(value: 100))
        XCTAssertEqual(output.count, 2, "Should emit mic-only after system stall")

        let samples = output[1].withUnsafeBytes { $0.bindMemory(to: Int16.self) }
        XCTAssertEqual(samples[0], 100, "Should be mic-only (system padded with silence)")
    }

    // MARK: - Empty data does not refresh liveness

    func testEmptyDataDoesNotRefreshLiveness() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // System sends empty data — should not count as alive
        now += 2.1
        mixer.setSystemAudio(emptyChunk())
        mixer.setMicAudio(audioChunk(value: 400))
        XCTAssertEqual(output.count, 1, "System should be stalled despite empty chunk; mic emits solo")

        let samples = output[0].withUnsafeBytes { $0.bindMemory(to: Int16.self) }
        XCTAssertEqual(samples[0], 400)
    }

    // MARK: - Recovery

    func testStalledSourceRecovery() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // System stalls, mic emits solo
        now += 2.1
        mixer.setMicAudio(audioChunk(value: 100))
        XCTAssertEqual(output.count, 1)

        // System recovers with real data
        now += 0.1
        mixer.setSystemAudio(audioChunk(value: 200))

        // Now send mic again — should wait for system (dual-source mode resumed)
        output.removeAll()
        now += 0.1
        mixer.setMicAudio(audioChunk(value: 100))
        // Both have data, should emit mixed
        XCTAssertEqual(output.count, 1, "Should resume dual-source mixing after recovery")

        let samples = output[0].withUnsafeBytes { $0.bindMemory(to: Int16.self) }
        XCTAssertEqual(samples[0], 300, "Should be sum of mic(100) + system(200)")
    }

    // MARK: - start() resets state

    func testStartResetsLivenessState() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Make system stall
        now += 2.1
        mixer.setMicAudio(audioChunk(value: 100))
        XCTAssertEqual(output.count, 1)

        // Stop and restart — stale state should be cleared
        mixer.stop()
        output.removeAll()

        now += 0.1
        mixer.start { output.append($0) }

        // Both sources deliver data — should work as dual-source (no stale stall)
        mixer.setMicAudio(audioChunk(value: 100))
        XCTAssertEqual(output.count, 0, "Should wait for both after restart")
        mixer.setSystemAudio(audioChunk(value: 200))
        XCTAssertEqual(output.count, 1, "Should emit dual-source mixed")
    }

    // MARK: - Timeout boundary

    func testExactlyAtTimeoutStillWaits() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Advance exactly 2.0s (timeout uses strict >)
        now += 2.0
        mixer.setMicAudio(audioChunk(value: 100))
        XCTAssertEqual(output.count, 0, "Exactly at timeout boundary should still wait (strict >)")
    }

    func testJustOverTimeoutSwitchesToSingleSource() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Advance 2.001s (just over)
        now += 2.001
        mixer.setMicAudio(audioChunk(value: 100))
        XCTAssertEqual(output.count, 1, "Just over timeout should switch to single-source")
    }

    // MARK: - Flush behavior

    func testStopFlushesBothBuffers() {
        var output = [Data]()
        let mixer = AudioMixer(outputMode: .mono, clock: fakeClock)
        mixer.start { output.append($0) }

        // Add sub-threshold data to both
        let smallChunk = audioChunk(value: 100, byteCount: 1000)
        mixer.setMicAudio(smallChunk)
        mixer.setSystemAudio(smallChunk)
        XCTAssertEqual(output.count, 0, "Below threshold, no output yet")

        mixer.stop()
        XCTAssertEqual(output.count, 1, "Stop should flush remaining data")
    }
}
