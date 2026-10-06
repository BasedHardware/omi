import XCTest

@testable import Omi_Computer

final class MeetingMemoryBriefComposerTests: XCTestCase {
  private let now = Date(timeIntervalSince1970: 1_780_000_000)

  private func event(
    id: String = "new-event", title: String = "Atlas planning", email: String? = "sara@example.com",
    offset: TimeInterval = 30 * 60
  ) -> SystemCalendarEventSnapshot {
    SystemCalendarEventSnapshot(
      calendarEventID: id,
      title: title,
      startTime: now.addingTimeInterval(offset),
      endTime: now.addingTimeInterval(offset + 30 * 60),
      isAllDay: false,
      isCanceled: false,
      participants: [DesktopMeetingParticipant(name: "Sara", email: email)],
      urlCandidates: [])
  }

  private func conversation(
    id: String = "prior-1", identity: ConversationMeetingIdentity? = nil,
    sections: [SummarySection] = [], actions: [ActionItem] = [], overview: String = "Reviewed Atlas launch milestones.",
    locked: Bool = false, ageDays: Double = 7
  ) -> ServerConversation {
    let start = now.addingTimeInterval(-ageDays * 24 * 60 * 60)
    return ServerConversation(
      id: id,
      createdAt: start,
      startedAt: start,
      finishedAt: start.addingTimeInterval(30 * 60),
      structured: Structured(
        title: "Atlas review", overview: overview, emoji: "🧠", category: "other", actionItems: actions,
        events: [], sections: sections),
      transcriptSegments: [], transcriptSegmentsIncluded: false,
      geolocation: nil, photos: [], appsResults: [], source: .desktop, language: "en",
      meetingIdentity: identity,
      status: .completed, discarded: false, deleted: false, isLocked: locked,
      starred: false, folderId: nil, inputDeviceName: nil)
  }

  private var matchingIdentity: ConversationMeetingIdentity {
    ConversationMeetingIdentity(
      eventID: "prior-event", source: "system_calendar", title: "Atlas planning",
      attendeeEmails: ["sara@example.com"])
  }

  private var citedDecision: SummarySection {
    SummarySection(heading: "Decisions", bodyMarkdown: "- Ship the smaller pilot first.", sourceSegmentIDs: ["s1"])
  }

  func testStrongTitleAndAttendeeMatchProducesSourceLinkedBrief() {
    let source = conversation(
      identity: matchingIdentity,
      sections: [
        SummarySection(heading: "Decisions", bodyMarkdown: "- Ship the smaller pilot first.", sourceSegmentIDs: ["s1"]),
        SummarySection(heading: "Open questions", bodyMarkdown: "- Who owns the rollout?", sourceSegmentIDs: ["s3"]),
      ],
      actions: [
        ActionItem(
          description: "Send Sara the rollout draft", completed: false, deleted: false, captureOwner: "user",
          sourceSegmentIDs: ["s2"])
      ])

    let brief = MeetingMemoryBriefComposer.compose(events: [event()], conversations: [source], now: now)

    XCTAssertEqual(brief?.sourceConversationID, "prior-1")
    XCTAssertEqual(brief?.facts.map(\.kind), [.decision, .followUp, .openQuestion])
    XCTAssertEqual(brief?.facts.map(\.sourceSegmentIDs), [["s1"], ["s2"], ["s3"]])
    XCTAssertEqual(brief?.facts.map(\.sourceConversationID), ["prior-1", "prior-1", "prior-1"])
  }

  func testTitleOnlyAndEmailOnlyAreNotEnough() {
    let sameTitleWrongPerson = conversation(
      identity: ConversationMeetingIdentity(
        eventID: "old", source: "system_calendar", title: "Atlas planning", attendeeEmails: ["other@example.com"]))
    let samePersonWrongTitle = conversation(
      identity: ConversationMeetingIdentity(
        eventID: "old", source: "system_calendar", title: "Budget review", attendeeEmails: ["sara@example.com"]))

    XCTAssertNil(
      MeetingMemoryBriefComposer.compose(
        events: [event()], conversations: [sameTitleWrongPerson, samePersonWrongTitle], now: now))
  }

  func testExactSystemCalendarEventCanMatchWithoutAttendee() {
    let source = conversation(
      identity: ConversationMeetingIdentity(
        eventID: "repeat-event", source: "system_calendar", title: "Different title", attendeeEmails: []),
      sections: [citedDecision])
    XCTAssertNotNil(
      MeetingMemoryBriefComposer.compose(
        events: [event(id: "repeat-event", title: "1:1", email: nil)], conversations: [source], now: now))
  }

  func testLockedOrUncitedSectionCannotBecomeClaim() {
    let uncited = conversation(
      identity: matchingIdentity,
      sections: [SummarySection(heading: "Decisions", bodyMarkdown: "- Guess", sourceSegmentIDs: [])],
      overview: "")
    XCTAssertNil(MeetingMemoryBriefComposer.compose(events: [event()], conversations: [uncited], now: now))
    XCTAssertNil(
      MeetingMemoryBriefComposer.compose(
        events: [event()], conversations: [conversation(identity: matchingIdentity, locked: true)], now: now))
  }

  func testSkipsUncitedLatestMeetingForEarlierCitedSource() {
    let latest = conversation(id: "latest", identity: matchingIdentity, ageDays: 1)
    let earlier = conversation(
      id: "earlier", identity: matchingIdentity,
      sections: [citedDecision], ageDays: 7)

    let brief = MeetingMemoryBriefComposer.compose(
      events: [event()], conversations: [latest, earlier], now: now)
    XCTAssertEqual(brief?.sourceConversationID, "earlier")
  }

  func testTooFarAwayOrPastMeetingRemainsSilent() {
    let source = conversation(identity: matchingIdentity, sections: [citedDecision])
    XCTAssertNil(
      MeetingMemoryBriefComposer.compose(
        events: [event(offset: 3 * 60 * 60)], conversations: [source], now: now))
    XCTAssertNil(
      MeetingMemoryBriefComposer.compose(
        events: [event(offset: -5 * 60)], conversations: [source], now: now))
  }

  func testFollowUpDraftUsesOnlyCitedUserCommitments() {
    let source = conversation(
      identity: matchingIdentity,
      actions: [
        ActionItem(
          description: "Send the rollout draft", completed: false, deleted: false,
          captureOwner: "user", sourceSegmentIDs: ["s1"]),
        ActionItem(
          description: "Sara will review it", completed: false, deleted: false,
          captureOwner: "other", sourceSegmentIDs: ["s2"]),
        ActionItem(
          description: "Uncited guess", completed: false, deleted: false,
          captureOwner: "user"),
      ])

    let draft = MeetingFollowUpDraftComposer.compose(from: source)
    XCTAssertNotNil(draft)
    XCTAssertTrue(draft?.contains("Send the rollout draft") == true)
    XCTAssertFalse(draft?.contains("Sara will review it") == true)
    XCTAssertFalse(draft?.contains("Uncited guess") == true)
    XCTAssertNil(
      MeetingFollowUpDraftComposer.compose(
        from: conversation(
          identity: matchingIdentity, actions: source.structured.actionItems, locked: true)))
  }

  func testFollowUpDraftDoesNotSilentlyDropLaterCommitments() {
    let actions = (1...7).map { number in
      ActionItem(
        description: "Commitment \(number)", completed: false, deleted: false,
        captureOwner: "user", sourceSegmentIDs: ["s\(number)"])
    }
    let source = conversation(identity: matchingIdentity, actions: actions)

    let draft = MeetingFollowUpDraftComposer.compose(from: source)
    XCTAssertTrue(draft?.contains("Commitment 1") == true)
    XCTAssertTrue(draft?.contains("Commitment 7") == true)
  }
}
