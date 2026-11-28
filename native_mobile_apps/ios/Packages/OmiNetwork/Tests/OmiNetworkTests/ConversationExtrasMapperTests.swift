import Foundation
import OmiCore
@testable import OmiNetwork
import Testing

/// The conversation detail's extras, shaped like the local backend's responses (2026-10-07):
/// calendar link, photos, capture group, audio parts, speaker counting, screenshots, events.
struct ConversationExtrasMapperTests {
    static let json = """
    {
      "id": "demo-1", "created_at": "2026-10-07T13:18:00Z", "started_at": "2026-10-07T13:18:00Z",
      "finished_at": "2026-10-07T13:56:00Z", "status": "completed", "source": "omi", "discarded": true,
      "structured": {
        "title": "Q4", "overview": "Plan.",
        "events": [{"title": "", "start": "2026-10-09T09:00:00Z"},
                   {"title": "Check-in", "description": "Confirm.", "start": "2026-10-09T09:00:00Z", "duration": 30, "created": true}]
      },
      "apps_results": [{"app_id": "demo-coach", "content": "Coach notes."}],
      "calendar_event": {"event_id": "ev1", "title": "Q4 roadmap", "attendees": ["Anna Keller"],
                         "attendee_emails": ["anna@example.com"], "start_time": "2026-10-07T13:18:00Z",
                         "end_time": "2026-10-07T13:56:00Z", "html_link": "https://calendar.google.com/e"},
      "photos": [{"id": "p1", "base64": "iVBORw0KGgo=", "description": "Whiteboard", "discarded": false},
                 {"id": "p2", "base64": "", "storage_id": "s2", "discarded": false}],
      "speaker_resolution": {"status": "resolved", "participant_speaker_ids": [0, 1]},
      "capture_group": {"id": "g1", "primary_id": "demo-1", "members": [
        {"id": "demo-1", "source": "omi", "started_at": "2026-10-07T13:18:00Z"},
        {"id": "demo-8", "source": "phone", "started_at": "2026-10-07T13:19:00Z", "finished_at": "2026-10-07T13:56:00Z"}]},
      "audio_files": [
        {"id": "a2", "uid": "u", "conversation_id": "demo-1", "chunk_timestamps": [], "duration": 4, "started_at": "2026-10-07T13:28:00Z"},
        {"id": "a1", "uid": "u", "conversation_id": "demo-1", "chunk_timestamps": [], "duration": 5, "started_at": "2026-10-07T13:18:00Z"}]
    }
    """

    @Test func mapsTheExtras() throws {
        let detail = try ConversationMapper.detail(JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(Self.json.utf8)))
        #expect(detail.summaryAppID == "demo-coach")
        // An app's result is shown, so Omi's own summary is not.
        #expect(detail.summaryIsOmiOwn == false)
        #expect(detail.calendarEvent?.title == "Q4 roadmap")
        #expect(detail.calendarEvent?.attendeeEmails == ["anna@example.com"])
        #expect(detail.calendarEvent?.htmlLink?.host == "calendar.google.com")
        #expect(detail.photos.map(\.id) == ["p1", "p2"])
        #expect(detail.photos[0].data?.isEmpty == false)
        #expect(detail.photos[0].isDescribing == false)
        #expect(detail.photos[1].data == nil && detail.photos[1].isStored && detail.photos[1].isDescribing)
        #expect(detail.participantSpeakerIDs == [0, 1])
        #expect(detail.recordings.map(\.id) == ["demo-1", "demo-8"])
        #expect(detail.recordings.first?.isCurrent == true)
        #expect(detail.audioParts.map(\.id) == ["a1", "a2"])
        // Positions stay the backend's: the untitled first event is kept (hidden by the view).
        #expect(detail.events.map(\.isCreated) == [false, true])
        #expect(detail.conversation.isDiscarded)
        #expect(detail.conversation.captureGroupID == "g1")
        #expect(detail.conversation.captureGroupPrimaryID == "demo-1")
    }

    @Test func unavailableSpeakersAreNotCounted() throws {
        let json = Self.json.replacingOccurrences(of: "\"resolved\"", with: "\"unavailable\"")
        let detail = try ConversationMapper.detail(JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(json.utf8)))
        #expect(detail.participantSpeakerIDs == nil)
    }

    @Test func omisOwnSummaryIsTheOneWithoutAnAppResult() throws {
        let json = Self.json.replacingOccurrences(
            of: "\"apps_results\": [{\"app_id\": \"demo-coach\", \"content\": \"Coach notes.\"}],", with: ""
        )
        let detail = try ConversationMapper.detail(JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(json.utf8)))
        #expect(detail.summaryAppID == nil)
        // Omi's own summary: the overview, and editable in place.
        #expect(detail.summary == "Plan.")
        #expect(detail.summaryIsOmiOwn)
    }

    /// An app result the mapper drops (no content) leaves no app id, so the summary shown is not
    /// that app's: the PATCH would have nothing to address.
    @Test func anEmptyAppResultIsNotTheSummaryShown() throws {
        let json = Self.json.replacingOccurrences(of: "\"content\": \"Coach notes.\"", with: "\"content\": \"  \"")
        let detail = try ConversationMapper.detail(JSONDecoder().decode(OmiAPI.Conversation.self, from: Data(json.utf8)))
        #expect(detail.summaryAppID == nil)
        #expect(detail.summaryIsOmiOwn)
    }

    @Test func severalCachedPartsPlayInARow() {
        let parts: [String: Any] = [
            "audio_files": [
                ["id": "a1", "status": "cached", "signed_url": "http://127.0.0.1/a1.wav", "duration": 4.4],
                ["id": "a2", "status": "cached", "signed_url": "http://127.0.0.1/a2.wav", "duration": 4.3],
            ],
            "conversation_audio": NSNull(),
        ]
        guard case let .parts(found) = ConversationAudioMapper.map(parts) else { Issue.record("not parts"); return }
        #expect(found.map(\.id) == ["a1", "a2"])
        #expect(found.map(\.duration) == [4.4, 4.3])
        // The dense file still building, every part cached: the parts play (Flutter `playbackReady`).
        var building = parts
        building["conversation_audio"] = ["status": "pending"]
        if case .parts = ConversationAudioMapper.map(building) {} else { Issue.record("dense pending should play parts") }
        // A part still building: wait.
        let waiting: [String: Any] = ["audio_files": [
            ["id": "a1", "status": "cached", "signed_url": "http://x/a"],
            ["id": "a2", "status": "pending"],
        ]]
        #expect(ConversationAudioMapper.map(waiting) == .pending(retryAfter: 2))
    }

    @Test func mapsScreenshotsBannerFirst() {
        let set: [String: Any] = [
            "revision": 3,
            "banner": ["id": "b", "caption": "Slides", "content_url": "https://x/b.png", "thumbnail_url": "https://x/b-t.png", "rank": 0],
            "strip": [["id": "s2", "caption": "", "rank": 2], ["id": "s1", "caption": "Code", "rank": 1]],
        ]
        let shots = ScreenshotMapper.map(set)
        #expect(shots.map(\.id) == ["b", "s1", "s2"])
        #expect(shots.first?.thumbnailURL?.lastPathComponent == "b-t.png")
        #expect(ScreenshotMapper.map(["revision": 0]).isEmpty)
    }

    @Test func mapsCalendarCandidates() {
        let event = CalendarMapper.candidate([
            "event_id": "e1", "title": "Sync", "start_time": "2026-10-07T13:00:00Z", "end_time": "2026-10-07T13:30:00Z",
            "attendees": ["Anna"], "all_day": false,
        ])
        #expect(event?.id == "e1")
        #expect(event.map { $0.end.timeIntervalSince($0.start) } == 1800)
        #expect(CalendarMapper.candidate(["event_id": "e2", "title": "No times"]) == nil)
    }
}
