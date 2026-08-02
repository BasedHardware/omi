import ContextCore
import Foundation
import XCTest

/// The pure decisions: where a conversation ends, which lines are worth storing, and what a sample
/// is. No database, no clock — every input is a literal.
final class PolicyTests: XCTestCase {

    // MARK: - Session boundaries

    func testSessionOpensOnlyPastTheGap() {
        let policy = SessionPolicy()
        let last = Fixture.base

        XCTAssertTrue(
            policy.shouldOpenNewSession(lastSegmentEndedAt: nil, nextSegmentStartedAt: last),
            "with nothing stored there is no session to continue")

        XCTAssertFalse(policy.shouldOpenNewSession(
            lastSegmentEndedAt: last, nextSegmentStartedAt: last + 1))
        XCTAssertFalse(policy.shouldOpenNewSession(
            lastSegmentEndedAt: last, nextSegmentStartedAt: last + SessionPolicy.gapSeconds))
        XCTAssertTrue(policy.shouldOpenNewSession(
            lastSegmentEndedAt: last, nextSegmentStartedAt: last + SessionPolicy.gapSeconds + 1))
        XCTAssertTrue(policy.shouldOpenNewSession(
            lastSegmentEndedAt: last, nextSegmentStartedAt: last + 3_600))
    }

    func testBackwardsClockContinuesTheSessionInsteadOfSplittingIt() {
        let policy = SessionPolicy()
        let last = Fixture.base

        // An NTP correction, a sleep/wake, or two transcribers finishing out of order. Splitting
        // here would cut a live conversation in half for a reason the user can never see.
        XCTAssertFalse(policy.shouldOpenNewSession(
            lastSegmentEndedAt: last, nextSegmentStartedAt: last - 10))
        XCTAssertFalse(policy.shouldOpenNewSession(
            lastSegmentEndedAt: last, nextSegmentStartedAt: last - 86_400))
        XCTAssertFalse(policy.shouldOpenNewSession(
            lastSegmentEndedAt: last, nextSegmentStartedAt: last))
    }

    func testGapIsInjectable() {
        let policy = SessionPolicy(gapSeconds: 30)

        XCTAssertFalse(policy.shouldOpenNewSession(
            lastSegmentEndedAt: Fixture.base, nextSegmentStartedAt: Fixture.base + 30))
        XCTAssertTrue(policy.shouldOpenNewSession(
            lastSegmentEndedAt: Fixture.base, nextSegmentStartedAt: Fixture.base + 31))
        XCTAssertEqual(SessionPolicy.gapSeconds, 300)
    }

    // MARK: - Transcript hygiene

    func testCleanDropsWhatASilentWindowProduces() {
        for noise in ["", "   ", "\n\t ", ".", "…", "-", "!?", "a", "I", "…  …"] {
            XCTAssertNil(
                TranscriptFilter.clean(noise),
                "\(noise.debugDescription) is not a transcript line")
        }
    }

    func testCleanKeepsRealSpeechAndNormalisesWhitespace() {
        XCTAssertEqual(TranscriptFilter.clean("  we should ship it  "), "we should ship it")
        XCTAssertEqual(TranscriptFilter.clean("we\tshould\n\nship   it"), "we should ship it")
        XCTAssertEqual(TranscriptFilter.clean("ok"), "ok")
        // Digits count as content: "42" is a real answer to a real question.
        XCTAssertEqual(TranscriptFilter.clean("42"), "42")
    }

    func testCleanHandlesDecoderLoops() {
        // The documented rule: a run of four or more identical words is always an artifact. Whether
        // the *line* survives depends on how much of it the loop is.
        XCTAssertNil(TranscriptFilter.clean("AND AND AND AND"))
        XCTAssertNil(TranscriptFilter.clean("and and, and. AND and"))

        // Three is a real speech pattern, not a loop.
        XCTAssertEqual(TranscriptFilter.clean("no no no"), "no no no")

        // A loop inside otherwise good speech collapses to one occurrence rather than costing the
        // whole sentence.
        XCTAssertEqual(
            TranscriptFilter.clean("we should ship it and and and and then review it"),
            "we should ship it and then review it")
    }

    func testSilenceGateSitsBetweenRoomToneAndQuietSpeech() {
        XCTAssertTrue(TranscriptFilter.isSilent(rms: 0))
        XCTAssertTrue(TranscriptFilter.isSilent(rms: 0.002), "room tone must never reach the model")
        XCTAssertFalse(TranscriptFilter.isSilent(rms: 0.004), "the floor itself is not silence")
        XCTAssertFalse(TranscriptFilter.isSilent(rms: 0.02), "quiet speech across a room is speech")
        XCTAssertTrue(TranscriptFilter.isSilent(rms: 0.02, floor: 0.05))
    }

    // MARK: - PCM

    func testInt16EncodingIsLittleEndianAndClamped() {
        // 0.5 * 32767 rounds to 16384 == 0x4000, low byte first.
        XCTAssertEqual(Array(PCM.int16LE(from: [0.5])), [0x00, 0x40])
        XCTAssertEqual(Array(PCM.int16LE(from: [Float(16382.5 / 32767)])), [0xFF, 0x3F])
        XCTAssertEqual(Array(PCM.int16LE(from: [0])), [0x00, 0x00])

        // Out of range clamps rather than wrapping: a wrapped sample is a full-scale sign flip, an
        // audible click that also drags its window over the silence floor.
        XCTAssertEqual(Array(PCM.int16LE(from: [2.0])), [0xFF, 0x7F])
        XCTAssertEqual(Array(PCM.int16LE(from: [-3.0])), [0x01, 0x80])
        XCTAssertEqual(Array(PCM.int16LE(from: [.nan])), [0x00, 0x00])
        XCTAssertEqual(PCM.int16LE(from: []).count, 0)
    }

    func testFloatRoundTripStaysWithinOneLSB() {
        let samples: [Float] = [0, 0.5, -0.5, 0.123, -0.987, 1, -1]

        let decoded = PCM.floatSamples(int16LE: PCM.int16LE(from: samples))

        XCTAssertEqual(decoded.count, samples.count)
        for (original, round) in zip(samples, decoded) {
            XCTAssertEqual(round, original, accuracy: 1e-4)
        }
    }

    func testRMSOfAKnownSignal() {
        // Four samples of 16384 (0x4000): half of full scale, exactly.
        let data = Data([0x00, 0x40, 0x00, 0x40, 0x00, 0x40, 0x00, 0x40])

        XCTAssertEqual(PCM.rms(int16LE: data), 0.5, accuracy: 1e-5)
        XCTAssertEqual(PCM.rms(int16LE: Data([0x00, 0x00, 0x00, 0x00])), 0, accuracy: 1e-6)
    }

    func testRMSToleratesEmptyAndRaggedBuffers() {
        // A callback firing with nothing in it is normal during a device change, not an error.
        XCTAssertEqual(PCM.rms(int16LE: Data()), 0)
        XCTAssertEqual(PCM.rms(int16LE: Data([0x01])), 0)
        XCTAssertEqual(PCM.floatSamples(int16LE: Data()), [])
        XCTAssertEqual(PCM.floatSamples(int16LE: Data([0x01])), [])

        // Odd byte count: a chunk split mid-sample upstream. Drop the trailing byte, keep capturing.
        let ragged = Data([0x00, 0x40, 0x00, 0x40, 0x7F])
        XCTAssertEqual(PCM.floatSamples(int16LE: ragged).count, 2)
        XCTAssertEqual(PCM.rms(int16LE: ragged), 0.5, accuracy: 1e-5)
    }

    func testPCMIsCorrectForASlicedDataWithANonZeroStartIndex() {
        // Audio arrives as slices constantly, and a slice keeps its parent's indices: `data[0]` on
        // one reads the wrong byte or traps. The one-byte prefix also leaves the samples on an odd
        // address, which is where an aligned 16-bit load would crash.
        let samples = PCM.int16LE(from: [0.5, -0.5, 0.25, -0.25, 0.75])
        var prefixed = Data([0x7F])
        prefixed.append(samples)
        let slice = prefixed.dropFirst()

        XCTAssertEqual(slice.count, samples.count)
        XCTAssertNotEqual(slice.startIndex, 0, "the point of this test is a non-zero start index")
        XCTAssertEqual(PCM.floatSamples(int16LE: slice), PCM.floatSamples(int16LE: samples))
        XCTAssertEqual(PCM.rms(int16LE: slice), PCM.rms(int16LE: samples), accuracy: 1e-6)
        XCTAssertGreaterThan(PCM.rms(int16LE: slice), 0)
    }

    func testDownmixAveragesChannelsRatherThanPickingOne() {
        // Headsets routinely put the mic on one channel and silence on the other; picking a channel
        // would lose the input entirely on half of them.
        let stereo: [Float] = [1, 0, 0.5, -0.5, 0.2, 0.2]

        let mono = PCM.downmixToMono(interleaved: stereo, channels: 2)

        XCTAssertEqual(mono.count, 3)
        for (value, expected) in zip(mono, [0.5, 0, 0.2] as [Float]) {
            XCTAssertEqual(value, expected, accuracy: 1e-6)
        }

        XCTAssertEqual(PCM.downmixToMono(interleaved: stereo, channels: 1), stereo)
        XCTAssertEqual(PCM.downmixToMono(interleaved: [], channels: 2), [])
        // A ragged buffer from a format change truncates the partial frame instead of trapping.
        XCTAssertEqual(PCM.downmixToMono(interleaved: [1, 0, 1], channels: 2), [0.5])
    }
}
