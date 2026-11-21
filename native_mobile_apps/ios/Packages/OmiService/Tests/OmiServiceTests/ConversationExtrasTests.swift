import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Summary templates, "Was this helpful?", the calendar link, recordings, the test prompt, the
/// list's discarded/short options, the one-day page and joined audio parts.
@MainActor
struct ConversationExtrasTests {
    private func loaded(_ api: FakeAPIClient, id: String = "c1") async -> ConversationDetailStore {
        let preview = Fixtures.conversations.first { $0.id == id } ?? Fixtures.conversations[0]
        let store = ConversationDetailStore(preview: preview, api: api)
        await store.load()
        return store
    }

    // MARK: Summary templates

    @Test func summarizesWithASuggestedAppAfterInstallingIt() async throws {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        let list = ConversationsStore(api: api, preferences: prefs)
        let detail = await loaded(api)
        let templates = list.makeTemplatesStore()
        await templates.load(conversationID: "c1")
        #expect(templates.suggested.map(\.id) == ["app-coach"])
        #expect(templates.apps.map(\.id) == ["app-notes"])

        let coach = try #require(templates.suggested.first)
        #expect(await templates.summarize(detail, with: coach, in: list))
        #expect(api.conversationExtras.log.contains("reprocess:c1@app-coach"))
        #expect(detail.detail?.summaryAppID == "app-coach")
        #expect(templates.suggested.isEmpty)
        // Installed, and now the last used: first among the user's apps.
        #expect(templates.apps.first?.id == "app-coach")
        #expect(templates.lastUsedAppID == "app-coach")
        #expect(prefs.string(.lastUsedSummarizationAppId) == "app-coach")
    }

    @Test func defaultIsSavedOnlyWhenTheBackendAgrees() async throws {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        let templates = ConversationsStore(api: api, preferences: prefs).makeTemplatesStore()
        await templates.load(conversationID: "c1")
        let notes = try #require(templates.apps.first)
        api.conversationExtras.failing = ["preferred"]
        #expect(await !(templates.setDefault(notes)))
        #expect(templates.failure == .saveDefault)
        #expect(templates.defaultAppID == nil)
        api.conversationExtras.failing = []
        #expect(await templates.setDefault(notes))
        #expect(api.conversationExtras.preferredAppID == "app-notes")
        #expect(prefs.string(.preferredSummarizationAppId) == "app-notes")
    }

    @Test func createsAndInstallsATemplate() async {
        let api = FakeAPIClient()
        let templates = ConversationsStore(api: api).makeTemplatesStore()
        await templates.load(conversationID: "c1")
        // The form's rules hold the request back.
        #expect(await templates.create(SummaryTemplateDraft(name: "No", prompt: "x"), icon: { _ in Data([1]) }) == nil)
        let draft = SummaryTemplateDraft(name: "Decision Log", prompt: "List every decision and its owner.", isPublic: true)
        let app = await templates.create(draft) { emoji in Data(emoji.utf8) }
        #expect(app?.id == "app-new")
        #expect(api.conversationExtras.log.contains("describe:Decision Log"))
        #expect(api.conversationExtras.log.contains("create-app:Decision Log|public|4"))
        #expect(templates.apps.contains { $0.id == "app-new" && $0.isEnabled })
        #expect(templates.creationStep == nil)
    }

    @Test func templateWithoutADescriptionStillGetsCreated() async {
        let api = FakeAPIClient()
        api.conversationExtras.failing = ["describe"]
        let templates = ConversationsStore(api: api).makeTemplatesStore()
        let app = await templates.create(SummaryTemplateDraft(name: "Notes", prompt: "Summarize the decisions.")) { _ in Data([1]) }
        #expect(app?.description == "A custom app that Summarize the decisions.")
    }

    // MARK: Was this helpful?

    @Test func asksAQuarterOfConversationsOnceAWeek() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        // demo-5 falls in the sampled quarter, demo-1 does not (first four bytes of SHA-256).
        #expect(SummaryFeedbackStore.sampled("demo-5"))
        #expect(!SummaryFeedbackStore.sampled("demo-1"))
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let first = SummaryFeedbackStore(api: api, preferences: prefs, conversationID: "demo-5", now: { now })
        first.start(hasOwnSummary: false)
        #expect(first.state == .hidden)
        first.start(hasOwnSummary: true)
        #expect(first.state == .asking)
        await first.send(helpful: false, reason: .incomplete)
        #expect(first.state == .thanked)
        #expect(api.conversationExtras.log == ["feedback:demo-5=summary_helpfulness=-1:summary_incomplete"])
        // Answered: never again for this conversation, even after the week.
        let later = SummaryFeedbackStore(api: api, preferences: prefs, conversationID: "demo-5", now: { now + 8 * 86400 })
        later.start(hasOwnSummary: true)
        #expect(later.state == .hidden)
    }

    @Test func aFailedAnswerStaysToRetry() async {
        let api = FakeAPIClient()
        api.conversationExtras.feedbackPersists = false
        let feedback = SummaryFeedbackStore(api: api, preferences: freshPreferences(), conversationID: "demo-5")
        feedback.start(hasOwnSummary: true)
        await feedback.send(helpful: true)
        #expect(feedback.state == .failed)
        api.conversationExtras.feedbackPersists = true
        await feedback.send(helpful: true)
        #expect(feedback.state == .thanked)
        #expect(api.conversationExtras.log == ["feedback:demo-5=summary_helpfulness=1", "feedback:demo-5=summary_helpfulness=1"])
    }

    @Test func closingSendsNothingAndStartsTheCooldown() {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let feedback = SummaryFeedbackStore(api: api, preferences: prefs, conversationID: "demo-5", now: { now })
        feedback.start(hasOwnSummary: true)
        feedback.dismiss()
        #expect(feedback.state == .hidden)
        #expect(api.conversationExtras.log.isEmpty)
        // Another sampled conversation the same week does not ask.
        let other = SummaryFeedbackStore(api: api, preferences: prefs, conversationID: "05f95229-5ae7-40c8-9ee3-8df3844b6ad1", now: { now })
        other.start(hasOwnSummary: true)
        #expect(other.state == .hidden)
    }

    @Test func asksAboutTheOneThingThereIsOrPicksByTheHash() {
        #expect(SummaryFeedbackStore.kind(for: "demo-2", hasSummary: false, hasRecording: false) == nil)
        #expect(SummaryFeedbackStore.kind(for: "demo-1", hasSummary: true, hasRecording: false) == .summary)
        #expect(SummaryFeedbackStore.kind(for: "demo-2", hasSummary: false, hasRecording: true) == .recording)
        // Both: bit 0 of byte 4 of SHA-256(id), as Flutter's feedbackPromptKindForTarget.
        #expect(SummaryFeedbackStore.kind(for: "demo-2", hasSummary: true, hasRecording: true) == .summary)
        #expect(SummaryFeedbackStore.kind(for: "demo-1", hasSummary: true, hasRecording: true) == .recording)
        #expect(SummaryFeedbackStore.kind(for: "", hasSummary: true, hasRecording: true) == nil)
    }

    @Test func aFinishedRecordingAsksAboutTheRecording() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        let feedback = SummaryFeedbackStore(api: api, preferences: prefs, conversationID: "demo-5", now: { now })
        feedback.start(hasOwnSummary: true, hasRecording: true)
        #expect(feedback.state == .asking)
        #expect(feedback.kind == .recording)
        await feedback.send(helpful: false, reason: .missingAudio)
        #expect(api.conversationExtras.log == ["feedback:demo-5=recording_quality=-1:recording_missing_audio"])
        // One budget for both questions: another sampled conversation the same week does not ask.
        let other = SummaryFeedbackStore(api: api, preferences: prefs, conversationID: "05f95229-5ae7-40c8-9ee3-8df3844b6ad1", now: { now })
        other.start(hasOwnSummary: true)
        #expect(other.state == .hidden)
    }

    // MARK: Calendar, events, recordings, test prompt

    @Test func linksAndUnlinksACalendarEvent() async throws {
        let api = FakeAPIClient()
        let detail = await loaded(api)
        let window = detail.window
        api.conversationExtras.calendarEvents = [
            CalendarEventCandidate(id: "ev1", title: "Q4 roadmap", start: window.start, end: window.end, attendees: ["Anna"]),
        ]
        let candidates = try #require(await detail.calendarCandidates())
        #expect(candidates.map(\.id) == ["ev1"])
        #expect(await detail.linkCalendarEvent("ev1")?.title == "Q4 roadmap")
        #expect(detail.detail?.calendarEvent?.attendeeEmails == ["anna@example.com"])
        api.conversationExtras.failing = ["unlink"]
        #expect(await !(detail.unlinkCalendarEvent()))
        #expect(detail.detail?.calendarEvent != nil)
        api.conversationExtras.failing = []
        #expect(await detail.unlinkCalendarEvent())
        #expect(detail.detail?.calendarEvent == nil)
    }

    @Test func marksAnAddedEvent() async {
        let api = FakeAPIClient()
        let event = ConversationDetail.Event(title: "Check-in", description: "", start: Fixtures.now, duration: 30)
        api.conversationExtras.details["c1"] = ConversationDetail(
            conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: [], events: [event]
        )
        let detail = await loaded(api)
        await detail.markEventAdded(0)
        #expect(detail.detail?.events.first?.isCreated == true)
        #expect(api.conversationExtras.log == ["events-created:c1=0=true"])
        // Already added: nothing sent again.
        await detail.markEventAdded(0)
        #expect(api.conversationExtras.log.count == 1)
    }

    @Test func separatesARecordingAndReloads() async {
        let api = FakeAPIClient()
        let list = ConversationsStore(api: api)
        let detail = await loaded(api)
        let phone = CaptureRecording(id: "c2", source: "phone", start: nil, end: nil, isCurrent: false)
        #expect(await detail.separate(phone, in: list))
        #expect(api.conversationExtras.log == ["separate:c2"])
        #expect(list.phase == .loaded)
        api.conversationExtras.failing = ["separate"]
        #expect(await !(detail.separate(phone, in: list)))
    }

    @Test func promptStripsBold() async {
        let api = FakeAPIClient()
        api.conversationExtras.testPromptReply = "**Two** decisions."
        let detail = await loaded(api)
        #expect(await detail.testPrompt("   ") == nil)
        #expect(await detail.testPrompt("Decisions?") == "Two decisions.")
        #expect(api.conversationExtras.log == ["test-prompt:c1=Decisions?"])
    }

    @Test func followsProcessingUntilDone() async {
        let api = FakeAPIClient()
        var processing = Fixtures.conversations[0]
        processing.status = .processing
        api.conversationExtras.details["c1"] = ConversationDetail(conversation: processing, summaryActionItems: [], transcript: [])
        let list = ConversationsStore(api: api)
        let detail = await loaded(api)
        let follow = Task { await detail.followProcessing(in: list, interval: .milliseconds(10), attempts: 50) }
        try? await Task.sleep(for: .milliseconds(30))
        api.conversationExtras.details["c1"] = nil
        await follow.value
        #expect(detail.conversation.status == .completed)
    }

    // MARK: List display, one-day page

    @Test func discardedComeOnlyWhenShown() async {
        let gone = Conversation(
            id: "gone", title: "", overview: "", emoji: nil, category: nil, createdAt: Fixtures.now, startedAt: Fixtures.now,
            finishedAt: Fixtures.now.addingTimeInterval(180), status: .completed, isStarred: false, actionItemCount: 0, isDiscarded: true
        )
        let api = FakeAPIClient(conversations: Fixtures.conversations + [gone])
        let prefs = freshPreferences()
        let list = ConversationsStore(api: api, preferences: prefs)
        await list.load()
        #expect(!list.visible.contains { $0.id == "gone" })
        await list.setShowsDiscarded(true)
        #expect(list.visible.contains { $0.id == "gone" })
        #expect(api.conversationExtras.queries.last?.includeDiscarded == true)
        #expect(prefs.bool(.showDiscardedMemories))
        // A new store reads the choice back.
        #expect(ConversationsStore(api: api, preferences: prefs).display.showsDiscarded)
    }

    @Test func hidesShortConversations() async {
        let api = FakeAPIClient()
        let prefs = freshPreferences()
        let list = ConversationsStore(api: api, preferences: prefs)
        await list.load()
        #expect(list.visible.count == 4)
        // c2 lasts 12 minutes.
        list.hideShorter(than: 15 * 60)
        #expect(!list.visible.contains { $0.id == "c2" })
        #expect(prefs.integer(.shortConversationThreshold, default: 0) == 900)
        list.hideShorter(than: nil)
        #expect(list.visible.count == 4)
        #expect(prefs.bool(.showShortConversations))
    }

    @Test func dayPageLoadsOneDayAndStopsAtToday() async {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .gmt
        let api = FakeAPIClient()
        let list = ConversationsStore(api: api, calendar: calendar)
        let day = list.makeDayStore(day: Fixtures.now)
        await day.load()
        // c1 and c2 are on Fixtures.now's day (10:00 UTC, 60 and 180 minutes before).
        #expect(day.conversations.map(\.id) == ["c1", "c2"])
        let query = api.conversationExtras.queries.last
        #expect(query?.start == calendar.startOfDay(for: Fixtures.now))
        #expect(query?.includeDiscarded == false)
        #expect(!day.canGoForward(now: Fixtures.now))
        await day.go(by: 1, now: Fixtures.now)
        #expect(day.day == calendar.startOfDay(for: Fixtures.now))
        await day.go(by: -1, now: Fixtures.now)
        #expect(day.conversations.map(\.id) == ["c3"])
    }

    // MARK: Audio parts

    @Test func joinsWAVParts() throws {
        func wav(_ samples: [UInt8]) -> Data {
            var data = Data("RIFF".utf8)
            data.append(contentsOf: [0, 0, 0, 0])
            data.append(Data("WAVEfmt ".utf8))
            data.append(contentsOf: [16, 0, 0, 0, 1, 0, 1, 0, 0x80, 0x3E, 0, 0, 0, 0x7D, 0, 0, 2, 0, 16, 0])
            data.append(Data("LIST".utf8))
            data.append(contentsOf: [2, 0, 0, 0, 9, 9])
            data.append(Data("data".utf8))
            data.append(contentsOf: [UInt8(samples.count), 0, 0, 0])
            data.append(contentsOf: samples)
            return data
        }
        let joined = try #require(AudioJoiner.combineWAV([wav([1, 2]), wav([3, 4, 5, 6])]))
        #expect(AudioJoiner.isWAV(joined))
        #expect(joined.suffix(6) == Data([1, 2, 3, 4, 5, 6]))
        #expect(joined.count == 44 + 6)
        #expect(AudioJoiner.combineWAV([Data("nope".utf8)]) == nil)
    }

    @Test func playsSeveralPartsAsOneFile() async {
        let api = FakeAPIClient()
        api.conversationActions.audio = [.parts([])]
        let detail = await loaded(api)
        await detail.loadAudio()
        // Nothing downloadable: unavailable rather than a broken player.
        #expect(detail.audio == .unavailable)
        #expect(api.conversationExtras.log.contains("precache:c1"))
    }
}
