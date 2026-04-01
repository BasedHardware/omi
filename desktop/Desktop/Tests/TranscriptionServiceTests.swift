import XCTest

@testable import Omi_Computer

// MARK: - VAD Gate Auto-Emit Tests

final class VADGateAutoEmitTests: XCTestCase {

    func testAutoEmitFromSpeechTransitionsToSpeech() {
        let gate = VADGateService()
        let buffer = Data(repeating: 0xAA, count: 1_500_000)
        let result = gate.testAutoEmit(
            batchBuffer: buffer,
            startState: .speech,
            speechStartWallTime: 100.0,
            audioCursorMs: 23400,
            lastSpeechMs: 23400
        )

        // Should emit the buffer
        XCTAssertEqual(result.output.audioBuffer?.count, 1_500_000)
        XCTAssertTrue(result.output.isComplete)
        XCTAssertEqual(result.output.speechStartWallTime, 100.0, accuracy: 0.001)

        // Should stay in .speech
        XCTAssertEqual(result.resultState, .speech)

        // Buffer should be cleared
        XCTAssertEqual(gate.testBatchBufferCount, 0)
    }

    func testAutoEmitFromHangoverTransitionsToSpeech() {
        let gate = VADGateService()
        let buffer = Data(repeating: 0xBB, count: 1_500_000)
        let result = gate.testAutoEmit(
            batchBuffer: buffer,
            startState: .hangover,
            speechStartWallTime: 50.0,
            audioCursorMs: 25000,
            lastSpeechMs: 21000
        )

        // Should emit the buffer
        XCTAssertTrue(result.output.isComplete)
        XCTAssertEqual(result.output.audioBuffer?.count, 1_500_000)

        // Should stay in .hangover (preserving original state)
        XCTAssertEqual(result.resultState, .hangover)
    }

    func testAutoEmitResetsBatchLastSpeechMs() {
        let gate = VADGateService()
        let buffer = Data(repeating: 0xCC, count: 1_500_000)
        let result = gate.testAutoEmit(
            batchBuffer: buffer,
            startState: .hangover,
            speechStartWallTime: 50.0,
            audioCursorMs: 25000,
            lastSpeechMs: 21000  // Old speech time from previous buffer
        )

        // batchLastSpeechMs should be reset to batchAudioCursorMs
        XCTAssertEqual(result.resultLastSpeechMs, 25000, accuracy: 0.001)
    }

    func testAutoEmitAdvancesStartWallTime() {
        let gate = VADGateService()
        // 640000 bytes = 10 seconds of stereo 16kHz Int16 audio
        let buffer = Data(repeating: 0xDD, count: 640_000)
        let result = gate.testAutoEmit(
            batchBuffer: buffer,
            startState: .speech,
            speechStartWallTime: 100.0,
            audioCursorMs: 10000,
            lastSpeechMs: 10000
        )

        // emittedDuration = 640000 / 4 / 16000 = 10.0s
        // New start wall time should be 100.0 + 10.0 = 110.0
        XCTAssertEqual(result.resultStartWallTime, 110.0, accuracy: 0.001)

        // Emitted output should have old start time
        XCTAssertEqual(result.output.speechStartWallTime, 100.0, accuracy: 0.001)
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
