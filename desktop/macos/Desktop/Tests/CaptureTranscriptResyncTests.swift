import XCTest

@testable import Omi_Computer

/// The on-device transcript-to-audio sync behind the transcript refresh button.
/// Words come from a fake recognizer so the tests are hermetic; the real
/// Parakeet path is exercised on a named bundle.
@MainActor
final class CaptureTranscriptResyncTests: XCTestCase {
  // MARK: - Alignment policy

  func testNormalizationDropsPunctuationAndApostrophesButKeepsDigits() {
    XCTAssertEqual(
      CaptureTranscriptAlignmentPolicy.normalizedTokens("Wait, what's crazy?。 I'm 23!"),
      ["wait", "whats", "crazy", "im", "23"])
  }

  func testConstantShiftIsRecoveredAndShortSegmentsAreSkipped() throws {
    let segments = [
      segment("a", "Yeah.", start: 0, end: 1),
      segment("b", "so she said this is something new", start: 100, end: 104),
      segment("c", "my mom went and apparently it was fine", start: 200, end: 205),
      segment("d", "like there cannot be a cure for that", start: 300, end: 304),
    ]
    // Every sentence is heard 33.3 s later than the transcript claims.
    let words = spoken(segments.dropFirst().map { ($0.text, $0.start + 33.3, $0.end + 33.3) })

    let matches = CaptureTranscriptAlignmentPolicy.matches(segments: segments, words: words)
    XCTAssertEqual(matches.map(\.segmentIndex), [1, 2, 3], "The two-word segment has no 3-gram to match")
    for match in matches {
      XCTAssertEqual(match.offset, 33.3, accuracy: 0.6)
    }
    let curve = try XCTUnwrap(CaptureTranscriptAlignmentPolicy.offsetCurve(from: matches))
    XCTAssertEqual(curve.offset(at: 0), 33.3, accuracy: 0.6, "Before the first anchor the first shift holds")
    XCTAssertEqual(curve.offset(at: 250), 33.3, accuracy: 0.6)
    XCTAssertEqual(curve.offset(at: 900), 33.3, accuracy: 0.6, "After the last anchor the last shift holds")
  }

  func testDriftBetweenAnchorsInterpolatesAndOutliersAreDropped() throws {
    let segments = [
      segment("a", "so she said this is something new", start: 100, end: 104),
      segment("b", "my mom went and apparently it was fine", start: 200, end: 205),
      segment("c", "like there cannot be a cure for that", start: 300, end: 304),
      segment("d", "wait can i call you in a minute", start: 400, end: 404),
      segment("e", "i just turned it off for now", start: 500, end: 504),
    ]
    // Delivery gaps between b and c: the shift grows from 10 s to 40 s.
    var heard: [(String, TimeInterval, TimeInterval)] = [
      (segments[0].text, 110, 114), (segments[1].text, 210, 215),
      (segments[2].text, 340, 344), (segments[3].text, 440, 444), (segments[4].text, 540, 544),
    ]
    // The same phrase as segment b also occurs 180 s away: a coincidence the
    // window admits but the neighbourhood consensus must reject.
    heard.append((segments[1].text, 380, 385))
    let words = spoken(heard)

    let matches = CaptureTranscriptAlignmentPolicy.matches(segments: segments, words: words)
    let curve = try XCTUnwrap(CaptureTranscriptAlignmentPolicy.offsetCurve(from: matches))
    XCTAssertEqual(curve.offset(at: 100), 10, accuracy: 0.6)
    XCTAssertEqual(curve.offset(at: 200), 10, accuracy: 0.6, "The nearer occurrence wins for segment b")
    XCTAssertEqual(curve.offset(at: 250), 25, accuracy: 1.5, "Half-way between anchors the shift is half-way")
    XCTAssertEqual(curve.offset(at: 500), 40, accuracy: 0.6)
  }

  func testTooFewOrContradictoryMatchesProduceNoCurve() {
    let segments = [
      segment("a", "so she said this is something new", start: 100, end: 104),
      segment("b", "my mom went and apparently it was fine", start: 200, end: 205),
    ]
    let words = spoken([(segments[0].text, 133, 137), (segments[1].text, 233, 238)])
    let matches = CaptureTranscriptAlignmentPolicy.matches(segments: segments, words: words)
    XCTAssertEqual(matches.count, 2)
    XCTAssertNil(CaptureTranscriptAlignmentPolicy.offsetCurve(from: matches), "Two anchors are not evidence")

    let scattered = [
      CaptureTranscriptMatch(segmentIndex: 0, transcriptTime: 100, audioTime: 120),
      CaptureTranscriptMatch(segmentIndex: 1, transcriptTime: 200, audioTime: 150),
      CaptureTranscriptMatch(segmentIndex: 2, transcriptTime: 300, audioTime: 420),
    ]
    XCTAssertNil(CaptureTranscriptAlignmentPolicy.offsetCurve(from: scattered), "No two of these agree")
  }

  func testRebaseMovesTimesOnlyAndNeverBeforeZero() {
    let segments = [
      TranscriptSegment(
        id: "s1", backendId: "b1", text: "Hello there", speaker: "SPEAKER_02", isUser: false, personId: "p-9",
        start: 1, end: 3, translations: []),
      TranscriptSegment(
        id: "s2", text: "Mine", speaker: "SPEAKER_00", isUser: true, personId: nil, start: 10, end: 12,
        translations: []),
    ]
    let curve = CaptureTranscriptOffsetCurve(anchors: [.init(transcriptTime: 0, offset: -5)])
    let rebased = CaptureTranscriptAlignmentPolicy.rebase(segments: segments, curve: curve)
    XCTAssertEqual(rebased[0].start, 0, "Clamped at the start of the audio")
    XCTAssertEqual(rebased[0].end, 0, accuracy: 0.001, "An end can never precede its start")
    XCTAssertEqual(rebased[1].start, 5)
    XCTAssertEqual(rebased[1].end, 7)
    XCTAssertEqual(rebased[0].speaker, "SPEAKER_02")
    XCTAssertEqual(rebased[0].personId, "p-9")
    XCTAssertEqual(rebased[0].backendId, "b1")
    XCTAssertTrue(rebased[1].isUser)
  }

  // MARK: - Resync orchestration

  func testResyncPutsTheTranscriptOnTheAudioClockAndRemembersIt() async throws {
    let defaults = try isolatedDefaults()
    let store = CaptureTranscriptSyncStore(defaults: defaults)
    let startedAt = Date(timeIntervalSince1970: 1_000)
    let segments = [
      segment("a", "so she said this is something new", start: 100, end: 104, backendId: "srv-a"),
      segment("b", "my mom went and apparently it was fine", start: 200, end: 205, backendId: "srv-b"),
      segment("c", "like there cannot be a cure for that", start: 300, end: 304, backendId: "srv-c"),
      segment("d", "Okay.", start: 310, end: 311, backendId: "srv-d"),
    ]
    let capture = archiveCapture(
      id: "omi-sync", startedAt: startedAt,
      audioFiles: [CaptureAudioFile(id: "part-1", duration: 900, firstChunkTimestamp: 1_060)],
      segments: segments)
    // The audio part begins 60 s after the transcript's zero; on the media's
    // clock every sentence is heard 33 s later than the transcript claims.
    let artifact = CapturePlaybackArtifact(
      signedURL: URL(fileURLWithPath: "/dev/null"), duration: 900,
      spans: [CaptureAudioURLSpan(fileID: "part-1", wallOffset: 60, artifactOffset: 0, length: 900)])
    let recognizer = RecognizerFake(
      words: spoken(segments.prefix(3).map { ($0.text, $0.start + 33, $0.end + 33) }))
    let resyncer = CaptureTranscriptResyncer(recognizer: recognizer, fetcher: FetcherFake(), store: store)

    let syncedResult = await resyncer.resync(conversation: capture, artifact: artifact)
    let synced = try XCTUnwrap(syncedResult)

    XCTAssertEqual(synced.startedAt, startedAt.addingTimeInterval(60), "Zero is now where the media begins")
    XCTAssertEqual(synced.transcriptSegments[0].start, 133, accuracy: 0.6)
    XCTAssertEqual(synced.transcriptSegments[2].end, 337, accuracy: 0.6)
    XCTAssertEqual(synced.transcriptSegments[3].start, 343, accuracy: 0.6, "Unmatched sentences follow the curve")
    XCTAssertEqual(synced.transcriptSegments.map(\.speaker), segments.map(\.speaker))
    guard case .synced(let report) = resyncer.phase else { return XCTFail("Expected a synced phase") }
    XCTAssertEqual(report.matchedSegments, 3)
    XCTAssertEqual(report.alignableSegments, 3)
    XCTAssertEqual(report.shiftAtStart, 33, accuracy: 0.6)
    let timing = try XCTUnwrap(CaptureSolePartTiming.from(capture: synced))
    XCTAssertEqual(timing.wallOffset, 0, accuracy: 0.001, "The sole part now sits at zero: playback maps identity")

    // Reopening the capture applies the stored sync without listening again.
    let reopened = try XCTUnwrap(store.applied(to: capture))
    XCTAssertEqual(reopened.transcriptSegments[1].start, 233, accuracy: 0.6)
    XCTAssertEqual(reopened.startedAt, synced.startedAt)

    // A different audio part means a different media clock: the sync no longer applies.
    let remerged = archiveCapture(
      id: "omi-sync", startedAt: startedAt,
      audioFiles: [CaptureAudioFile(id: "part-2", duration: 900, firstChunkTimestamp: 1_060)], segments: segments)
    XCTAssertNil(store.applied(to: remerged))
    XCTAssertEqual(recognizer.recognizedURLs.count, 1)
  }

  func testResyncLeavesTheTranscriptAloneWhenTheAudioDoesNotMatch() async throws {
    let defaults = try isolatedDefaults()
    let store = CaptureTranscriptSyncStore(defaults: defaults)
    let segments = [
      segment("a", "so she said this is something new", start: 100, end: 104),
      segment("b", "my mom went and apparently it was fine", start: 200, end: 205),
      segment("c", "like there cannot be a cure for that", start: 300, end: 304),
    ]
    let capture = archiveCapture(
      id: "omi-nomatch", startedAt: Date(timeIntervalSince1970: 1_000),
      audioFiles: [CaptureAudioFile(id: "part-1", duration: 900, firstChunkTimestamp: 1_000)], segments: segments)
    let artifact = CapturePlaybackArtifact(
      signedURL: URL(fileURLWithPath: "/dev/null"), duration: 900,
      spans: [CaptureAudioURLSpan(fileID: "part-1", wallOffset: 0, artifactOffset: 0, length: 900)])
    let recognizer = RecognizerFake(words: spoken([("completely different words were spoken here", 10, 14)]))
    let resyncer = CaptureTranscriptResyncer(recognizer: recognizer, fetcher: FetcherFake(), store: store)

    let synced = await resyncer.resync(conversation: capture, artifact: artifact)

    XCTAssertNil(synced)
    guard case .failed(let message) = resyncer.phase else { return XCTFail("Expected a failed phase") }
    XCTAssertTrue(message.contains("0 of 3"), message)
    XCTAssertNil(store.record(for: "omi-nomatch"))
  }

  func testSyncStoreEvictsTheOldestBeyondCapacity() throws {
    let defaults = try isolatedDefaults()
    let store = CaptureTranscriptSyncStore(defaults: defaults)
    let record = CaptureTranscriptSyncRecord(
      audioFileID: "part", startedAt: 0, timings: [:], matchedSegments: 0, alignableSegments: 0,
      shiftAtStart: 0, shiftAtEnd: 0)
    for index in 0..<(CaptureTranscriptSyncStore.capacity + 1) {
      store.save(record, for: "conv-\(index)")
    }
    XCTAssertNil(store.record(for: "conv-0"))
    XCTAssertNotNil(store.record(for: "conv-1"))
    XCTAssertNotNil(store.record(for: "conv-\(CaptureTranscriptSyncStore.capacity)"))
    store.remove(for: "conv-1")
    XCTAssertNil(store.record(for: "conv-1"))
  }

  // MARK: - Helpers

  private func isolatedDefaults() throws -> UserDefaults {
    let suite = "CaptureTranscriptResyncTests.\(UUID().uuidString)"
    let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
    addTeardownBlock { defaults.removePersistentDomain(forName: suite) }
    return defaults
  }

  private func segment(
    _ id: String, _ text: String, start: TimeInterval, end: TimeInterval, backendId: String? = nil
  ) -> TranscriptSegment {
    TranscriptSegment(
      id: id, backendId: backendId, text: text, speaker: "SPEAKER_0\(id.count)", isUser: false, personId: nil,
      start: start, end: end, translations: [])
  }

  /// Words spread evenly across each spoken span, on the audio's clock.
  private func spoken(_ utterances: [(String, TimeInterval, TimeInterval)]) -> [RecognizedWord] {
    utterances.flatMap { text, start, end -> [RecognizedWord] in
      let tokens = text.split(separator: " ").map(String.init)
      let step = tokens.count > 1 ? (end - start) / Double(tokens.count - 1) : 0
      return tokens.enumerated().map { RecognizedWord(text: $0.element, start: start + Double($0.offset) * step) }
    }
  }

  private func archiveCapture(
    id: String, startedAt: Date, audioFiles: [CaptureAudioFile], segments: [TranscriptSegment]
  ) -> ServerConversation {
    ServerConversation(
      id: id, createdAt: startedAt, updatedAt: startedAt, startedAt: startedAt,
      finishedAt: startedAt.addingTimeInterval(900),
      structured: Structured(title: "Capture", overview: "", emoji: "", category: "other", actionItems: [], events: []),
      transcriptSegments: segments, transcriptSegmentsIncluded: true, geolocation: nil, photos: [], appsResults: [],
      source: .omi, language: "en", audioFiles: audioFiles, status: .completed, discarded: false, deleted: false,
      isLocked: false, starred: false, folderId: nil, inputDeviceName: nil)
  }
}

private final class RecognizerFake: CaptureWordRecognizing, @unchecked Sendable {
  let words: [RecognizedWord]
  private(set) var recognizedURLs: [URL] = []

  init(words: [RecognizedWord]) {
    self.words = words
  }

  func recognizeWords(in audioURL: URL) async throws -> [RecognizedWord] {
    recognizedURLs.append(audioURL)
    return words
  }
}

private struct FetcherFake: CaptureAudioFetching {
  func download(_ remoteURL: URL) async throws -> URL {
    FileManager.default.temporaryDirectory.appendingPathComponent("resync-fake-\(UUID().uuidString).wav")
  }
}
