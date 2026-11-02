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

  /// Shaped like a real production summary: sections titled by topic, with the outcome
  /// stated in a cited line rather than under a "Decisions" heading.
  func testOutcomesStatedInTopicSectionsBecomeFacts() {
    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Calendar permission",
          bodyMarkdown: """
            - The beta group had about 40 testers.
            - The speakers decided to show the calendar prompt only in settings.
            """,
          sourceSegmentIDs: ["s1", "s2"]),
        SummarySection(
          heading: "Measuring wrong matches",
          bodyMarkdown: "- The speakers have not decided how to measure wrong matches.",
          sourceSegmentIDs: ["s3"]),
      ]))

    XCTAssertEqual(
      facts.map(\.kind), [.decision, .openQuestion])
    XCTAssertEqual(facts.first?.text, "The speakers decided to show the calendar prompt only in settings.")
    XCTAssertEqual(facts.first?.sourceSegmentIDs, ["s1", "s2"])
    XCTAssertEqual(facts.last?.text, "The speakers have not decided how to measure wrong matches.")
  }

  func testNegatedOrDisputedLinesAreNeverDecisions() {
    XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision("They have not decided on pricing."))
    XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision("Sara disagreed with the rollout date."))
    XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision("No decision was made on hosting."))
    XCTAssertTrue(MeetingMemoryBriefComposer.statesOpenQuestion("No decision was made on hosting."))
    XCTAssertTrue(MeetingMemoryBriefComposer.statesDecision("The team agreed to ship on Thursday."))

    for unsettled in [
      "We have not yet decided on pricing.", "We haven't decided on pricing.", "We haven\u{2019}t agreed on scope.",
      "Nobody has decided who owns hosting.", "They never reached a decision on hosting.",
    ] {
      XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision(unsettled), unsettled)
      XCTAssertTrue(MeetingMemoryBriefComposer.statesOpenQuestion(unsettled), unsettled)
    }
    // A negation anywhere else in the line still vetoes, so it is shown under neither label.
    XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision("They agreed that we will not ship the beta."))
    XCTAssertFalse(MeetingMemoryBriefComposer.statesOpenQuestion("They agreed that we will not ship the beta."))

    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Pricing", bodyMarkdown: "- Sara disagreed with the rollout date.", sourceSegmentIDs: ["s1"])
      ]))
    XCTAssertTrue(facts.isEmpty)
  }

  func testADecisionsHeadingSkipsUnsettledLines() {
    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Decisions",
          bodyMarkdown: """
            - We have not yet decided on pricing.
            - Ship the smaller pilot first.
            """,
          sourceSegmentIDs: ["s1"])
      ]))

    XCTAssertEqual(facts.first { $0.kind == .decision }?.text, "Ship the smaller pilot first.")
    XCTAssertEqual(facts.first { $0.kind == .openQuestion }?.text, "We have not yet decided on pricing.")
  }

  func testAHeadingStillWinsAndUncitedBodiesNeverCount() {
    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Rollout", bodyMarkdown: "- We decided to ship Friday.", sourceSegmentIDs: []),
        SummarySection(
          heading: "Notes", bodyMarkdown: "- The team agreed to cut scope.", sourceSegmentIDs: ["s2"]),
        citedDecision,
      ]))

    XCTAssertEqual(facts.map(\.text), ["Ship the smaller pilot first."])
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

  // MARK: - Settled outcomes only

  func testFutureDiscussionAndProposalsAreNeverDecisions() {
    for line in [
      "The team will discuss the decision next week.", "We should revisit the decision on hosting.",
      "Sara proposed shipping on Friday.", "Do we agree on the scope?", "The decision is pending legal review.",
      "Sara owns the hosting decision.",
    ] {
      XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision(line), line)
    }
    XCTAssertTrue(MeetingMemoryBriefComposer.statesDecision("We decided to ship the pilot on Thursday."))
    XCTAssertTrue(
      MeetingMemoryBriefComposer.statesDecision(
        "The speakers agreed to ship the pilot and considered the fixture tests sufficient."))

    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Planning", bodyMarkdown: "- The team will discuss the decision next week.",
          sourceSegmentIDs: ["s1"])
      ]))
    XCTAssertFalse(facts.contains { $0.kind == .decision })
  }

  private static let unrealizedOutcomes = [
    "The budget will be approved next week.",
    "We will have decided on the launch date by Friday.",
    "We would have approved the budget if the price had changed.",
  ]

  func testFutureAndHypotheticalOutcomesAreNeverDecisionsInTopicSections() {
    for line in Self.unrealizedOutcomes {
      XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision(line), line)
      let facts = MeetingMemoryBriefComposer.facts(
        from: conversation(sections: [
          SummarySection(heading: "Budget", bodyMarkdown: "- " + line, sourceSegmentIDs: ["s1"])
        ]))
      XCTAssertFalse(facts.contains { $0.kind == .decision }, line)
    }
  }

  func testFutureAndHypotheticalOutcomesAreNeverDecisionsUnderADecisionsHeading() {
    for line in Self.unrealizedOutcomes {
      let facts = MeetingMemoryBriefComposer.facts(
        from: conversation(sections: [
          SummarySection(heading: "Decisions", bodyMarkdown: "- " + line, sourceSegmentIDs: ["s1"])
        ]))
      XCTAssertFalse(facts.contains { $0.kind == .decision }, line)
    }

    let mixed = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Decisions",
          bodyMarkdown: (Self.unrealizedOutcomes + ["Ship the smaller pilot first."]).map { "- " + $0 }
            .joined(separator: "\n"),
          sourceSegmentIDs: ["s1"])
      ]))
    XCTAssertEqual(mixed.first { $0.kind == .decision }?.text, "Ship the smaller pilot first.")
    XCTAssertEqual(mixed.first { $0.kind == .decision }?.sourceSegmentIDs, ["s1"])
  }

  func testACompletedAgreementAboutTheFutureIsStillADecision() {
    for line in [
      "We agreed we will ship Thursday.", "The team decided it would launch in May.",
      "Priya approved the budget, which we'll spend in Q3.", "They made a decision to pause hiring.",
    ] {
      XCTAssertTrue(MeetingMemoryBriefComposer.statesDecision(line), line)
    }
    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(heading: "Launch", bodyMarkdown: "- We agreed we will ship Thursday.", sourceSegmentIDs: ["s9"])
      ]))
    XCTAssertEqual(facts.first { $0.kind == .decision }?.text, "We agreed we will ship Thursday.")
    XCTAssertFalse(
      MeetingMemoryBriefComposer.statesDecision("We will have made a decision by Friday."),
      "the phrase form is checked the same way")
  }

  func testADecisionsHeadingDropsDisputedAndNegatedLinesButKeepsImperatives() {
    let disputed = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Decisions",
          bodyMarkdown: """
            - Sara disagreed with the rollout date.
            - We haven\u{2019}t agreed on scope.
            """,
          sourceSegmentIDs: ["s1"])
      ]))
    XCTAssertFalse(disputed.contains { $0.kind == .decision })

    let imperative = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Decisions",
          bodyMarkdown: """
            - Sara disagreed with the rollout date.
            - Ship the smaller pilot first.
            """,
          sourceSegmentIDs: ["s1"])
      ]))
    XCTAssertEqual(imperative.first { $0.kind == .decision }?.text, "Ship the smaller pilot first.")
  }

  func testANegativeDecisionIsStillADecision() {
    // Production summary of a live pilot meeting (PR #20824 evidence 003).
    let live =
      "The team agreed not to ask for calendar access at first launch. The prompt will appear only when "
      + "someone enables meeting briefs in settings, with a brief explanation of why access is needed."
    for decided in [
      live, "They agreed not to ship the beta.", "We decided never to store raw audio.",
      "The team chose to not renew the contract.",
    ] {
      XCTAssertTrue(MeetingMemoryBriefComposer.statesDecision(decided), decided)
      XCTAssertFalse(MeetingMemoryBriefComposer.statesOpenQuestion(decided), decided)
    }
    for unsettled in [
      "We have not agreed not to ship.", "Nobody agreed not to ship.", "They agreed nothing.",
      "They agreed not on the date.", "We will have agreed not to ship by Friday.",
    ] {
      XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision(unsettled), unsettled)
    }

    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(heading: "Calendar permission", bodyMarkdown: "- " + live, sourceSegmentIDs: ["s1"])
      ]))
    XCTAssertEqual(facts.first { $0.kind == .decision }?.sourceSegmentIDs, ["s1"])
    let fromHeading = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(
          heading: "Decisions", bodyMarkdown: "- They agreed not to ship the beta.", sourceSegmentIDs: ["s2"])
      ]))
    XCTAssertEqual(fromHeading.first { $0.kind == .decision }?.text, "They agreed not to ship the beta.")
  }

  func testLongCardLinesEndAtAWordWithAnEllipsis() {
    let line =
      "The team agreed not to ask for calendar access at first launch. The prompt will appear only when "
      + "someone enables meeting briefs in settings, with a brief explanation of why access is needed. The "
      + "concern was that another launch-time permission prompt could feel overwhelming."
    let excerpt = MeetingMemoryBriefComposer.cardExcerpt(line)
    XCTAssertLessThanOrEqual(excerpt.count, 240)
    XCTAssertTrue(excerpt.hasSuffix("launch-time\u{2026}"), excerpt)
    XCTAssertTrue(line.hasPrefix(String(excerpt.dropLast())))
    XCTAssertEqual(MeetingMemoryBriefComposer.cardExcerpt("Ship Thursday."), "Ship Thursday.")
    XCTAssertEqual(
      MeetingMemoryBriefComposer.cardExcerpt(String(repeating: "x", count: 300)),
      String(repeating: "x", count: 239) + "\u{2026}", "one unbroken word is still bounded")
  }

  func testALateNegationInALongLineStillVetoesTheDecision() {
    let line =
      "We agreed to " + String(repeating: "align on the launch checklist and ", count: 8)
      + "not ship until legal approves."
    XCTAssertGreaterThan(line.count, 240)
    XCTAssertFalse(MeetingMemoryBriefComposer.statesDecision(line))
    let facts = MeetingMemoryBriefComposer.facts(
      from: conversation(sections: [
        SummarySection(heading: "Launch", bodyMarkdown: "- " + line, sourceSegmentIDs: ["s1"])
      ]))
    XCTAssertFalse(facts.contains { $0.kind == .decision }, "classified on the whole line, not the card excerpt")
  }

  // MARK: - Short titles

  func testShortTitlesNeedTheExactEventID() {
    let shortIdentity = ConversationMeetingIdentity(
      eventID: "prior-event", source: "system_calendar", title: "Sync", attendeeEmails: ["sara@example.com"])
    XCTAssertFalse(
      MeetingMemoryBriefComposer.matches(event: event(id: "other-event", title: "Sync"), identity: shortIdentity),
      "a short generic title plus one shared attendee is too weak without the event ID")
    XCTAssertTrue(
      MeetingMemoryBriefComposer.matches(event: event(id: "prior-event", title: "Sync"), identity: shortIdentity))
    XCTAssertEqual(MeetingMemoryBriefComposer.minimumTitleOnlyMatchLength, 8)
  }

  // MARK: - Follow-up draft keeps every word

  func testFollowUpDraftKeepsLongCommitmentsWhole() {
    let long =
      "Send the revised Atlas budget to Priya with the vendor quotes from https://example.com/quotes/q3, "
      + String(repeating: "including the line-item notes from finance, ", count: 6)
      + "but do not send until legal approves the indemnity clause on Thursday."
    XCTAssertGreaterThan(long.count, 400)
    let actions = [
      ActionItem(description: long, completed: false, deleted: false, captureOwner: "user", sourceSegmentIDs: ["s1"]),
      ActionItem(
        description: "Book the follow-up review for October 20", completed: false, deleted: false,
        captureOwner: "user", sourceSegmentIDs: ["s2"]),
      ActionItem(
        description: "Already done", completed: true, deleted: false, captureOwner: "user", sourceSegmentIDs: ["s3"]),
      ActionItem(
        description: "Deleted task", completed: false, deleted: true, captureOwner: "user", sourceSegmentIDs: ["s4"]),
      ActionItem(
        description: "Sara owns this", completed: false, deleted: false, captureOwner: "other",
        sourceSegmentIDs: ["s5"]),
      ActionItem(description: "Uncited", completed: false, deleted: false, captureOwner: "user"),
    ]

    let draft = MeetingFollowUpDraftComposer.compose(from: conversation(identity: matchingIdentity, actions: actions))

    XCTAssertTrue(draft?.contains(long) == true, "the whole commitment, qualifier included")
    XCTAssertTrue(draft?.contains("do not send until legal approves the indemnity clause on Thursday.") == true)
    XCTAssertTrue(draft?.contains("Book the follow-up review for October 20") == true)
    for excluded in ["Already done", "Deleted task", "Sara owns this", "Uncited"] {
      XCTAssertFalse(draft?.contains(excluded) == true, excluded)
    }
  }
}
