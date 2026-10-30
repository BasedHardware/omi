import Foundation
@testable import OmiCore
import Testing

/// Recordings of one moment, the suggested calendar event, participants, the list's display
/// rules and the template form (Flutter `capture_groups`, `calendar_event_sheets`,
/// `conversation_detail_meta`, `conversation_display_settings`, `create_template_bottom_sheet`).
struct ConversationExtrasTests {
    static let base = Date(timeIntervalSince1970: 1_791_280_800)

    static func conversation(
        _ id: String, minutes: Double = 10, discarded: Bool = false, group: String? = nil, primary: String? = nil
    ) -> Conversation {
        Conversation(
            id: id, title: id, overview: "", emoji: nil, category: nil, createdAt: base, startedAt: base,
            finishedAt: base.addingTimeInterval(minutes * 60), status: .completed, isStarred: false, actionItemCount: 0,
            isDiscarded: discarded, captureGroupID: group, captureGroupPrimaryID: primary
        )
    }

    @Test func recordingsNeedTwoAndSortByStart() {
        let later = CaptureRecording(id: "phone", source: "phone", start: Self.base.addingTimeInterval(60), end: nil, isCurrent: false)
        let unknown = CaptureRecording(id: "desk", source: "desktop", start: nil, end: nil, isCurrent: false)
        let list = CaptureRecording.list(members: [later, unknown, later], current: "omi", source: "omi", start: Self.base, end: nil)
        #expect(list.map(\.id) == ["omi", "phone", "desk"])
        #expect(list.map(\.isCurrent) == [true, false, false])
        // Alone in its group: nothing to show.
        #expect(CaptureRecording.list(members: [], current: "omi", source: "omi", start: Self.base, end: nil).isEmpty)
    }

    @Test func suggestsTheBiggestOverlap() {
        let start = Self.base, end = Self.base.addingTimeInterval(3600)
        let lunch = CalendarEventCandidate(
            id: "lunch",
            title: "Lunch",
            start: end.addingTimeInterval(-240),
            end: end.addingTimeInterval(3600),
            attendees: []
        )
        let sync = CalendarEventCandidate(
            id: "sync",
            title: "Sync",
            start: start.addingTimeInterval(600),
            end: start.addingTimeInterval(2400),
            attendees: []
        )
        let short = CalendarEventCandidate(
            id: "short",
            title: "Call",
            start: start.addingTimeInterval(-60),
            end: start.addingTimeInterval(240),
            attendees: []
        )
        #expect(CalendarEventCandidate.suggested([lunch, sync, short], start: start, end: end)?.id == "sync")
        // Four of five minutes overlap: half the event counts.
        #expect(CalendarEventCandidate.suggested([short], start: start, end: end)?.id == "short")
        // Four minutes of a long event: not suggested.
        #expect(CalendarEventCandidate.suggested([lunch], start: start, end: end) == nil)
    }

    @Test func sharesWithAttendeesByMail() {
        let event = CalendarEventLink(
            eventID: "e", title: "Q4", attendees: ["Anna"], attendeeEmails: ["anna@example.com", "leo@example.com"],
            start: Self.base, end: Self.base, htmlLink: nil
        )
        #expect(event.shareURL(subject: "Notes: Q4")?.absoluteString == "mailto:anna@example.com,leo@example.com?subject=Notes:%20Q4")
        let nobody = CalendarEventLink(
            eventID: "e",
            title: "Q4",
            attendees: [],
            attendeeEmails: [],
            start: Self.base,
            end: Self.base,
            htmlLink: nil
        )
        #expect(nobody.shareURL(subject: "x") == nil)
    }

    private func detail(_ lines: [ConversationDetail.Line], speakers: [Int]?, event: CalendarEventLink? = nil) -> ConversationDetail {
        ConversationDetail(
            conversation: Self.conversation("c"), summaryActionItems: [], transcript: lines, calendarEvent: event,
            participantSpeakerIDs: speakers
        )
    }

    @Test func participantsCountNamedAndCountableVoices() {
        let lines: [ConversationDetail.Line] = [
            .init(id: 0, speaker: "You", isUser: true, text: "Hi", start: 0, speakerID: 0),
            .init(id: 1, speaker: "Speaker 2", isUser: false, text: "Hey", start: 1, speakerID: 1, personID: "p-anna"),
            .init(id: 2, speaker: "Speaker 3", isUser: false, text: "Yo", start: 2, speakerID: 2),
        ]
        let names = ["p-anna": "Anna"]
        let counted = detail(lines, speakers: [0, 1, 2]).participants(you: "You") { names[$0] }
        #expect(counted == Participants(names: ["You", "Anna"], unnamed: 1, uncounted: false))
        #expect(counted.others == 2)
        // Ids are not people (`unavailable`): "+ others".
        let uncounted = detail(lines, speakers: nil).participants(you: "You") { names[$0] }
        #expect(uncounted.uncounted)
    }

    @Test func participantsFallBackToAttendees() {
        let event = CalendarEventLink(
            eventID: "e", title: "Q4", attendees: ["Anna Keller", "leo@example.com"], attendeeEmails: [],
            start: Self.base, end: Self.base, htmlLink: nil
        )
        let lines: [ConversationDetail.Line] = [.init(id: 0, speaker: "You", isUser: true, text: "Hi", start: 0, speakerID: 0)]
        let people = detail(lines, speakers: [0], event: event).participants(you: "You") { _ in nil }
        #expect(people.names == ["You", "Anna", "Leo"])
    }

    @Test func displayHidesDiscardedAndShort() {
        let short = Self.conversation("short", minutes: 0.5)
        let discarded = Self.conversation("gone", discarded: true)
        let normal = Self.conversation("ok")
        let defaults = ConversationDisplay()
        // Flutter's threshold starts at 0: nothing is too short.
        #expect([short, discarded, normal].filter(defaults.keeps).map(\.id) == ["short", "ok"])
        let strict = ConversationDisplay(showsDiscarded: true, showsShort: false, shortThreshold: 60)
        #expect([short, discarded, normal].filter(strict.keeps).map(\.id) == ["gone", "ok"])
        #expect(strict.hidesShorterThan == 60)
        #expect(ConversationDisplay(showsShort: true, shortThreshold: 60).hidesShorterThan == nil)
    }

    @Test func oneRowPerCaptureGroup() {
        let list = [
            Self.conversation("phone", group: "g", primary: "omi"),
            Self.conversation("solo"),
            Self.conversation("omi", group: "g", primary: "omi"),
            Self.conversation("desk", group: "h", primary: "missing"),
            Self.conversation("watch", group: "h", primary: "missing"),
        ]
        #expect(ConversationDisplay.oneRowPerCaptureGroup(list).map(\.id) == ["solo", "omi", "desk"])
    }

    @Test func templateFormRules() {
        #expect(SummaryTemplateDraft(name: " ", prompt: "").problem == .nameMissing)
        #expect(SummaryTemplateDraft(name: "Ab", prompt: "").problem == .nameTooShort)
        #expect(SummaryTemplateDraft(name: "Notes", prompt: "").problem == .promptMissing)
        #expect(SummaryTemplateDraft(name: "Notes", prompt: "short").problem == .promptTooShort)
        #expect(SummaryTemplateDraft(name: "Notes", prompt: "List every decision.").problem == nil)
    }
}
