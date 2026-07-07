import XCTest
@testable import Omi_Computer

final class LiveNotesAccumulatorTests: XCTestCase {
    func testBuildsGenerationRequestWhenWordThresholdIsReached() {
        var accumulator = LiveNotesAccumulator(wordThreshold: 5, maxWordBufferSize: 20, maxExistingNotesContext: 3)

        XCTAssertNil(accumulator.handleSegmentsUpdate([
            segment(text: "one two", start: 0, end: 1),
        ], isGenerating: false))
        XCTAssertEqual(accumulator.wordBuffer, ["one", "two"])

        let request = accumulator.handleSegmentsUpdate([
            segment(text: "one two", start: 0, end: 1),
            segment(text: "three four five", start: 1, end: 2),
        ], isGenerating: false)

        XCTAssertEqual(request?.recentText, "one two three four five")
        XCTAssertEqual(request?.existingNotesText, "No existing notes yet.")
        XCTAssertEqual(request?.segmentStartOrder, 0)
        XCTAssertEqual(request?.segmentEndOrder, 2)
    }

    func testIgnoresAlreadyProcessedSegments() {
        var accumulator = LiveNotesAccumulator(wordThreshold: 3, maxWordBufferSize: 20, maxExistingNotesContext: 3)
        let segments = [
            segment(text: "one two three", start: 0, end: 1),
        ]

        XCTAssertNotNil(accumulator.handleSegmentsUpdate(segments, isGenerating: false))
        XCTAssertNil(accumulator.handleSegmentsUpdate(segments, isGenerating: false))
        XCTAssertEqual(accumulator.wordBuffer, ["one", "two", "three"])
    }

    func testSuccessfulGenerationResetsThresholdAndTrimsExistingNotesContext() {
        var accumulator = LiveNotesAccumulator(wordThreshold: 3, maxWordBufferSize: 20, maxExistingNotesContext: 2)
        accumulator.seedExistingNotes(["old one", "old two", "old three"])

        let firstRequest = accumulator.handleSegmentsUpdate([
            segment(text: "alpha beta gamma", start: 0, end: 1),
        ], isGenerating: false)

        XCTAssertEqual(firstRequest?.existingNotesText, "Existing notes:\n- old two\n- old three")

        accumulator.markGenerationSucceeded(noteText: "new note")
        XCTAssertEqual(accumulator.existingNotesContext, ["old three", "new note"])

        XCTAssertNil(accumulator.handleSegmentsUpdate([
            segment(text: "alpha beta gamma", start: 0, end: 1),
            segment(text: "delta epsilon", start: 1, end: 2),
        ], isGenerating: false))

        let secondRequest = accumulator.handleSegmentsUpdate([
            segment(text: "alpha beta gamma", start: 0, end: 1),
            segment(text: "delta epsilon", start: 1, end: 2),
            segment(text: "zeta", start: 2, end: 3),
        ], isGenerating: false)

        XCTAssertEqual(secondRequest?.recentText, "delta epsilon zeta")
        XCTAssertEqual(secondRequest?.existingNotesText, "Existing notes:\n- old three\n- new note")
    }

    func testWordBufferTrimsWithoutBlockingFutureGeneration() {
        var accumulator = LiveNotesAccumulator(wordThreshold: 3, maxWordBufferSize: 5, maxExistingNotesContext: 3)

        XCTAssertNotNil(accumulator.handleSegmentsUpdate([
            segment(text: "one two three", start: 0, end: 1),
        ], isGenerating: false))
        accumulator.markGenerationSucceeded(noteText: "first note")

        let request = accumulator.handleSegmentsUpdate([
            segment(text: "one two three", start: 0, end: 1),
            segment(text: "four five six seven eight", start: 1, end: 2),
        ], isGenerating: false)

        XCTAssertEqual(accumulator.wordBuffer, ["four", "five", "six", "seven", "eight"])
        XCTAssertEqual(request?.recentText, "six seven eight")
    }

    func testGenerationInFlightSuppressesRequestButKeepsAccumulatingWords() {
        var accumulator = LiveNotesAccumulator(wordThreshold: 3, maxWordBufferSize: 20, maxExistingNotesContext: 3)

        XCTAssertNil(accumulator.handleSegmentsUpdate([
            segment(text: "one two three", start: 0, end: 1),
        ], isGenerating: true))
        XCTAssertEqual(accumulator.wordBuffer, ["one", "two", "three"])

        let request = accumulator.handleSegmentsUpdate([
            segment(text: "one two three", start: 0, end: 1),
            segment(text: "four", start: 1, end: 2),
        ], isGenerating: false)

        XCTAssertEqual(request?.recentText, "two three four")
    }

    private func segment(text: String, start: Double, end: Double) -> SpeakerSegment {
        SpeakerSegment(
            segmentId: nil,
            speaker: 1,
            text: text,
            start: start,
            end: end
        )
    }
}
