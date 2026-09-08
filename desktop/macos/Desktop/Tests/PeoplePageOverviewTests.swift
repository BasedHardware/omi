import XCTest

@testable import Omi_Computer

final class PeoplePageOverviewTests: XCTestCase {
  func testPeopleAreOrderedByMostRecentConversationThenName() {
    let now = Date()
    let people = [
      Person(id: "zed", name: "Zed"),
      Person(id: "anna", name: "Anna"),
      Person(id: "bob", name: "Bob"),
      Person(id: "cara", name: "cara"),
    ]
    let activity: [String: PersonActivity] = [
      "bob": PersonActivity(conversationCount: 2, lastTalkedAt: now.addingTimeInterval(-3600)),
      "zed": PersonActivity(conversationCount: 1, lastTalkedAt: now),
    ]
    let voices = [
      summary("anna", seconds: 90, favorite: true),
      summary(nil, seconds: 30),
    ]

    let rows = PersonOverview.ordered(people: people, activity: activity, voices: voices)

    XCTAssertEqual(rows.map(\.id), ["anna", "zed", "bob", "cara"], "favorites first, then recency, then name")
    XCTAssertTrue(rows[0].hasVoice)
    XCTAssertTrue(rows[0].isFavorite)
    XCTAssertFalse(rows[1].hasVoice, "the user's own voice is not a person's")
    XCTAssertEqual(rows[2].conversationCount, 2)
  }

  private func summary(_ personId: String?, seconds: Double, favorite: Bool = false, clips: Int = 0)
    -> LocalSpeakerDiarizer.VoiceSummary
  {
    LocalSpeakerDiarizer.VoiceSummary(
      personId: personId, speechSeconds: seconds, updatedAt: Date(), isEnrolled: true, isFavorite: favorite,
      lastHeardAt: nil, sampleURLs: (0..<clips).map { URL(fileURLWithPath: "/tmp/clip-\($0).wav") })
  }

  func testCaptionsSayWhatOmiKnows() {
    let now = Date()
    XCTAssertEqual(
      PersonOverview.voiceCaption(nil), "No voice yet — name them in a live transcript")
    XCTAssertEqual(PersonOverview.voiceCaption(summary("a", seconds: 125)), "Voice known · 2 min heard")
    XCTAssertEqual(
      PersonOverview.voiceCaption(summary("a", seconds: 125, clips: 2)), "Voice known · 2 min heard · 2 clips")
    XCTAssertEqual(
      PersonOverview.conversationCaption(count: 0, last: nil), "Not heard in a conversation yet")
    XCTAssertTrue(
      PersonOverview.conversationCaption(count: 1, last: now.addingTimeInterval(-7200), now: now)
        .hasPrefix("1 conversation · last"))
  }
}
