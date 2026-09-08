import XCTest

@testable import Omi_Computer

final class PeopleRebuildPlannerTests: XCTestCase {
  private func segment(_ text: String, start: Double, end: Double, isUser: Bool = false, personId: String? = nil)
    -> TranscriptSegment
  {
    TranscriptSegment(
      id: UUID().uuidString, backendId: nil, text: text, speaker: "SPEAKER_01", isUser: isUser, personId: personId,
      start: start, end: end, translations: [])
  }

  /// Two captured spans with a 100 s gap between them in wall time.
  private var artifact: CapturePlaybackArtifact {
    CapturePlaybackArtifact(
      signedURL: URL(fileURLWithPath: "/tmp/a.wav"), duration: 60,
      spans: [
        CaptureAudioURLSpan(fileID: "f1", wallOffset: 0, artifactOffset: 0, length: 30),
        CaptureAudioURLSpan(fileID: "f2", wallOffset: 130, artifactOffset: 30, length: 30),
      ])
  }

  func testOnlyNamedOrUserSegmentsInsideCapturedAudioBecomeCuts() {
    let cuts = PeopleRebuildPlanner.cuts(
      segments: [
        segment("me", start: 2, end: 6, isUser: true),
        segment("anna", start: 10, end: 14, personId: "anna"),
        segment("unknown", start: 15, end: 20),
        segment("too short", start: 20, end: 20.5, personId: "anna"),
        segment("in the gap", start: 60, end: 70, personId: "anna"),
        segment("second span", start: 135, end: 160, personId: "bob"),
      ],
      artifact: artifact)

    XCTAssertEqual(cuts.map(\.personId), [nil, "anna", "bob"])
    XCTAssertEqual(cuts[0].artifactStart, 2, accuracy: 1e-6)
    XCTAssertEqual(cuts[0].artifactEnd, 6, accuracy: 0.01)
    XCTAssertEqual(cuts[2].artifactStart, 35, accuracy: 1e-6, "second span maps through its artifact offset")
    XCTAssertEqual(cuts[2].length, PeopleRebuildPlanner.maxCutSeconds, accuracy: 0.01, "long segments are capped")
  }

  func testActivityCountsConversationsPerPersonAndMergesWithLocal() {
    let day: TimeInterval = 86_400
    let now = Date()
    let remote = PeopleRebuildPlanner.activity(in: [
      (
        segments: [
          segment("a", start: 0, end: 2, personId: "anna"), segment("a2", start: 2, end: 4, personId: "anna"),
        ], date: now.addingTimeInterval(-day)
      ),
      (
        segments: [segment("b", start: 0, end: 2, personId: "bob"), segment("me", start: 2, end: 4, isUser: true)],
        date: now
      ),
      (segments: [segment("a", start: 0, end: 2, personId: "anna")], date: now.addingTimeInterval(-3 * day)),
    ])
    XCTAssertEqual(remote["anna"]?.conversationCount, 2, "two conversations, not three segments")
    XCTAssertEqual(remote["anna"]?.lastTalkedAt, now.addingTimeInterval(-day))
    XCTAssertEqual(remote["bob"]?.conversationCount, 1)
    XCTAssertEqual(remote.count, 2, "the user is not a person")

    let merged = PeopleRebuildPlanner.merge(
      ["anna": PersonActivity(conversationCount: 5, lastTalkedAt: now.addingTimeInterval(-10 * day))], remote)
    XCTAssertEqual(merged["anna"]?.conversationCount, 5)
    XCTAssertEqual(merged["anna"]?.lastTalkedAt, now.addingTimeInterval(-day))
    XCTAssertEqual(merged["bob"]?.conversationCount, 1)
  }

  func testSummaryMessageReadsNaturally() {
    var summary = PeopleRebuildSummary(conversations: 12, withAudio: 3, voicesRebuilt: 2, clipsSaved: 5)
    XCTAssertEqual(summary.message, "12 conversations checked · 3 with audio · 2 voices rebuilt · 5 clips saved")
    summary = PeopleRebuildSummary(conversations: 1)
    XCTAssertEqual(summary.message, "1 conversation checked · no voices rebuilt")
    XCTAssertEqual(PeopleRebuildSummary(failure: "Couldn't load conversations").message, "Couldn't load conversations")
  }
}

extension PeopleRebuildPlannerTests {
  /// The dev backend never builds the aggregate artifact; the one cached part begins at its
  /// first chunk, 30–60 s after the conversation started. The synthesized span carries that.
  func testASinglePartIsPlacedAtItsFirstChunkNotAtTheConversationStart() throws {
    let startedAt = Date(timeIntervalSince1970: 1_800_000_000)
    let file = CapturePlaybackFile(id: "part", signedURL: URL(fileURLWithPath: "/tmp/part.wav"), duration: 120)
    let artifact = try XCTUnwrap(
      PeopleRebuildPlanner.singlePartArtifact(
        file: file, firstChunkTimestamp: 1_800_000_033, conversationStartedAt: startedAt))
    XCTAssertEqual(try XCTUnwrap(artifact.artifactOffset(forWallOffset: 40)), 7, accuracy: 1e-6)
    XCTAssertNil(artifact.artifactOffset(forWallOffset: 10), "speech before the first chunk was never captured")
    XCTAssertNil(
      PeopleRebuildPlanner.singlePartArtifact(file: file, firstChunkTimestamp: nil, conversationStartedAt: startedAt),
      "without a chunk timestamp the part cannot be placed and must not be guessed")
  }
}
