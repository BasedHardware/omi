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
      LocalSpeakerDiarizer.VoiceSummary(personId: "anna", speechSeconds: 90, updatedAt: now, isEnrolled: true),
      LocalSpeakerDiarizer.VoiceSummary(personId: nil, speechSeconds: 30, updatedAt: now, isEnrolled: false),
    ]

    let rows = PersonOverview.ordered(people: people, activity: activity, voices: voices)

    XCTAssertEqual(rows.map(\.id), ["zed", "bob", "anna", "cara"])
    XCTAssertTrue(rows[2].hasVoice)
    XCTAssertFalse(rows[0].hasVoice, "the user's own voice is not a person's")
    XCTAssertEqual(rows[1].conversationCount, 2)
  }

  func testCaptionsSayWhatOmiKnows() {
    let now = Date()
    XCTAssertEqual(
      PersonOverview.voiceCaption(nil), "No voice yet — name them in a live transcript")
    XCTAssertEqual(
      PersonOverview.voiceCaption(
        LocalSpeakerDiarizer.VoiceSummary(personId: "a", speechSeconds: 125, updatedAt: now, isEnrolled: true)),
      "Voice known · 2 min heard")
    XCTAssertEqual(
      PersonOverview.conversationCaption(count: 0, last: nil), "Not heard in a conversation yet")
    XCTAssertTrue(
      PersonOverview.conversationCaption(count: 1, last: now.addingTimeInterval(-7200), now: now)
        .hasPrefix("1 conversation · last"))
  }
}
