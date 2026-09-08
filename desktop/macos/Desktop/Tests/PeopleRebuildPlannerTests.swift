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

  func testEverySegmentInsideCapturedAudioBecomesACutLongestFirst() throws {
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

    XCTAssertEqual(cuts.count, 4, "unnamed voices count too; the gap and the blip do not")
    XCTAssertEqual(cuts.map(\.personId).prefix(2), ["bob", nil], "longest first")
    XCTAssertEqual(Set(cuts.map(\.personId)), Set(["bob", nil, "anna"]))
    XCTAssertEqual(cuts[0].artifactStart, 35, accuracy: 1e-6, "second span maps through its artifact offset")
    XCTAssertEqual(cuts[0].length, PeopleRebuildPlanner.maxCutSeconds, accuracy: 0.01, "long segments are capped")
    let me = try XCTUnwrap(cuts.first { $0.labeledAsUser })
    XCTAssertEqual(me.artifactStart, 2, accuracy: 1e-6)
    XCTAssertEqual(me.artifactEnd, 6, accuracy: 0.01)
  }

  /// "You" is whoever is heard in the most conversations, not whoever the backend flagged.
  func testTheVoiceInTheMostConversationsIsTheUser() {
    func voice(_ axis: Int) -> [Float] {
      var v = [Float](repeating: 0, count: 8)
      v[axis] = 1
      return v
    }
    var clusterer = VoiceClusterer()
    // Voice 0: three conversations, little speech. Voice 1: one conversation, lots of speech,
    // flagged is_user by the backend. Voice 2: two conversations.
    for (conversation, seconds) in [("c1", 3.0), ("c2", 3.0), ("c3", 3.0)] {
      clusterer.add(
        embedding: voice(0), seconds: seconds, conversationId: conversation, date: nil, clip: nil, labeledAsUser: false)
    }
    clusterer.add(embedding: voice(1), seconds: 300, conversationId: "c1", date: nil, clip: nil, labeledAsUser: true)
    for conversation in ["c1", "c2"] {
      clusterer.add(
        embedding: voice(2), seconds: 50, conversationId: conversation, date: nil, clip: nil, labeledAsUser: false)
    }

    XCTAssertEqual(clusterer.clusters.count, 3)
    let user = clusterer.userCluster
    XCTAssertEqual(user?.conversationIds.count, 3)
    XCTAssertEqual(user?.speechSeconds ?? 0, 9, accuracy: 1e-6)
    XCTAssertEqual(user?.labeledAsUserSeconds, 0, "the backend's flag did not decide it")
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

extension PeopleRebuildPlannerTests {
  /// A long history holds dozens of one-off voices; only the leading few may keep audio, or the
  /// rebuild would carry hundreds of megabytes of samples it can never use.
  func testOnlyTheLeadingVoicesKeepAudio() {
    func voice(_ axis: Int) -> [Float] {
      var v = [Float](repeating: 0, count: 16)
      v[axis] = 1
      return v
    }
    var clusterer = VoiceClusterer()
    clusterer.clipHoldingClusters = 2
    let clip = [Float](repeating: 0.1, count: 1600)
    // Voice 0 in three conversations, voice 1 in two, voices 2 and 3 in one each.
    for conversation in ["c1", "c2", "c3"] {
      clusterer.add(
        embedding: voice(0), seconds: 4, conversationId: conversation, date: nil, clip: clip, labeledAsUser: false)
    }
    for conversation in ["c1", "c2"] {
      clusterer.add(
        embedding: voice(1), seconds: 4, conversationId: conversation, date: nil, clip: clip, labeledAsUser: false)
    }
    clusterer.add(embedding: voice(2), seconds: 4, conversationId: "c1", date: nil, clip: clip, labeledAsUser: false)
    clusterer.add(embedding: voice(3), seconds: 4, conversationId: "c2", date: nil, clip: clip, labeledAsUser: false)

    XCTAssertEqual(clusterer.clusters.count, 4)
    let withAudio = clusterer.clusters.filter { !$0.clips.isEmpty }
    XCTAssertEqual(withAudio.count, 2, "only the two most-present voices keep clips")
    XCTAssertEqual(clusterer.userCluster?.clips.isEmpty, false, "the user's own audio survives")
  }
}
