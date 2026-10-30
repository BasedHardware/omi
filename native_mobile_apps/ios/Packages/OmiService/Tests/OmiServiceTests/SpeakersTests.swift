import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct TranscriptSpeakersTests {
    private static let lines: [ConversationDetail.Line] = [
        .init(id: 0, speaker: "You", isUser: true, text: "Hi", start: 0, segmentID: "s0", speakerID: 0),
        .init(id: 1, speaker: "Speaker 2", isUser: false, text: "Hello", start: 3, segmentID: "s1", speakerID: 1),
        .init(id: 2, speaker: "Speaker 2", isUser: false, text: "Again", start: 6, segmentID: "s2", speakerID: 1),
    ]

    private func make(_ api: FakeAPIClient) -> (ConversationDetailStore, TranscriptSpeakersStore) {
        api.speakers.transcripts["c1"] = Self.lines
        let detail = ConversationDetailStore(preview: Fixtures.conversations[0], api: api)
        detail.detail = ConversationDetail(conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: Self.lines)
        return (detail, TranscriptSpeakersStore(detail: detail))
    }

    @Test func namesTheWholeVoice() async {
        let api = FakeAPIClient()
        let anna = Person(id: "p1", name: "Anna", sampleCount: 0)
        api.fakePeople = [anna]
        let (detail, speakers) = make(api)
        await speakers.assign(Self.lines[1], to: .person(anna), scope: .voice)
        #expect(detail.detail?.transcript.map(\.personID) == [nil, "p1", "p1"])
        #expect(api.speakers.log == ["assign:c1:voice=1:person:p1"])
        #expect(speakers.offersSummaryRefresh)
    }

    @Test func onlyThisLineUsesBulkAssign() async {
        let api = FakeAPIClient()
        let (detail, speakers) = make(api)
        await speakers.assign(Self.lines[2], to: .me, scope: .line)
        #expect(detail.detail?.transcript.map(\.isUser) == [true, false, true])
        #expect(api.speakers.log == ["assign:c1:s2:user"])
    }

    @Test func rollsBackWhenTheBackendRefuses() async {
        let api = FakeAPIClient()
        api.speakers.failing = ["assign"]
        let (detail, speakers) = make(api)
        await speakers.assign(Self.lines[1], to: .person(Person(id: "p1", name: "Anna", sampleCount: 0)), scope: .voice)
        #expect(detail.detail?.transcript == Self.lines)
        #expect(speakers.lastError != nil)
        #expect(!speakers.offersSummaryRefresh)
    }

    @Test func aNewNameCreatesThePersonFirst() async {
        let api = FakeAPIClient()
        let (detail, speakers) = make(api)
        let created = await speakers.assign(Self.lines[1], to: .newPerson(" Lena "), scope: .voice)
        #expect(created?.name == "Lena")
        #expect(api.fakePeople.map(\.name) == ["Lena"])
        #expect(detail.detail?.transcript[1].personID == created?.id)
    }

    @Test func notAPersonClearsTheVoice() async {
        let api = FakeAPIClient()
        let (detail, speakers) = make(api)
        await speakers.assign(Self.lines[1], to: .notAPerson, scope: .voice)
        #expect(api.speakers.log == ["reject:c1:1:not_a_person"])
        #expect(api.speakers.ignored.count == 1)
        #expect(detail.detail?.transcript[1].personID == nil)
    }

    @Test func offersEarlierMatchesAndAnswersThem() async {
        let api = FakeAPIClient()
        let anna = Person(id: "p1", name: "Anna", sampleCount: 0)
        let earlier = VoiceMatch(
            conversationID: "c9", title: "Lunch", startedAt: nil, speakerID: 2, talkSeconds: 30,
            segmentIDs: ["x"], clipStart: 0, clipEnd: 4, isStrong: true
        )
        let same = VoiceMatch(
            conversationID: "c1", title: "This one", startedAt: nil, speakerID: 1, talkSeconds: 5,
            segmentIDs: ["s1"], clipStart: 0, clipEnd: 2, isStrong: true
        )
        api.speakers.matches["p1"] = [earlier, same]
        let (_, speakers) = make(api)
        await speakers.assign(Self.lines[1], to: .person(anna), scope: .voice)
        #expect(speakers.matches?.items.map(\.conversationID) == ["c9"])
        await speakers.answer(earlier, same: false)
        #expect(speakers.matches?.items.isEmpty == true)
        #expect(api.speakers.log.last == "reject:c9:2:not_person")
    }

    @Test func refreshesTheSummary() async {
        let api = FakeAPIClient()
        let (_, speakers) = make(api)
        await speakers.assign(Self.lines[1], to: .me, scope: .voice)
        await speakers.refreshSummary()
        #expect(api.speakers.log.last == "reprocess:c1")
        #expect(!speakers.offersSummaryRefresh)
    }
}

@MainActor
struct PeopleManagementTests {
    private func settings(_ api: FakeAPIClient) -> SettingsStore {
        SettingsStore(api: api, preferences: freshPreferences())
    }

    @Test func searchesPinsAndCleansUp() async {
        let api = FakeAPIClient()
        api.fakePeople = [
            Person(id: "a", name: "Zoë", sampleCount: 0, confidence: .unverified),
            Person(id: "b", name: "Anna", sampleCount: 0, isPinned: true, confidence: .unverified),
            Person(id: "c", name: "Ben", sampleCount: 0, confidence: .confirmed),
        ]
        let store = settings(api)
        await store.loadPeopleWithStats()
        #expect(store.people(matching: "zoe").map(\.id) == ["a"])
        #expect(store.cleanUpCandidates.map(\.id) == ["a"])
        await store.setPinned("a", true)
        #expect(store.cleanUpCandidates.isEmpty)
        await store.deletePeople(["a", "c"])
        #expect(store.people.map(\.id) == ["b"])
        #expect(api.fakePeople.map(\.id) == ["b"])
    }

    @Test func pinRollsBack() async {
        let api = FakeAPIClient()
        api.fakePeople = [Person(id: "a", name: "Anna", sampleCount: 0)]
        api.speakers.failing = ["pin"]
        let store = settings(api)
        await store.loadPeople()
        await store.setPinned("a", true)
        #expect(store.person("a")?.isPinned == false)
        #expect(store.lastError != nil)
    }

    @Test func deletesASampleAndRollsBack() async throws {
        let api = FakeAPIClient()
        let urls = try [#require(URL(string: "https://x/1.wav")), #require(URL(string: "https://x/2.wav"))]
        api.fakePeople = [Person(id: "a", name: "Anna", sampleCount: 2, sampleURLs: urls)]
        let store = settings(api)
        await store.loadPeople()
        await store.deleteSample(of: "a", at: 0)
        #expect(store.person("a")?.sampleURLs == [urls[1]])
        #expect(api.speakers.log == ["deleteSample:a:0"])
        api.speakers.failing = ["deleteSample"]
        await store.deleteSample(of: "a", at: 0)
        #expect(store.person("a")?.sampleURLs == [urls[1]])
        #expect(store.person("a")?.sampleCount == 1)
    }
}

@MainActor
struct VoicesStoreTests {
    private let prompt = SpeakerPrompt(id: "q1", kind: .identify, conversationID: "c1", speakerID: 1, segmentIDs: ["s1"])

    @Test func answersAndDismissesPrompts() async {
        let api = FakeAPIClient()
        api.speakers.prompts = [prompt, SpeakerPrompt(id: "q2", kind: .ownerCheck, conversationID: "c2", speakerID: 0, segmentIDs: ["s"])]
        let voices = VoicesStore(api: api)
        await voices.loadPrompts()
        await voices.promptsShown()
        await voices.promptsShown()
        #expect(api.speakers.log == ["shown:q1,q2"])
        await voices.answer(prompt, .newPerson("Lena"))
        #expect(voices.currentPrompt?.id == "q2")
        await voices.dismissPrompts()
        #expect(voices.prompts.isEmpty)
    }

    @Test func answerRollsBack() async {
        let api = FakeAPIClient()
        api.speakers.prompts = [prompt]
        api.speakers.failing = ["answer"]
        let voices = VoicesStore(api: api)
        await voices.loadPrompts()
        await voices.answer(prompt, .me)
        #expect(voices.currentPrompt?.id == "q1")
        #expect(voices.lastError != nil)
    }

    @Test func settingsAndIgnoredVoices() async {
        let api = FakeAPIClient()
        api.speakers.ignored = [IgnoredVoice(conversationID: "c1", speakerID: 3, conversationTitle: "TV", ignoredAt: nil)]
        let voices = VoicesStore(api: api)
        await voices.loadSettings()
        await voices.setAsksToTag(false)
        #expect(voices.settings?.asksToTag == false)
        api.speakers.failing = ["settings", "restore"]
        await voices.setSavesOtherVoices(false)
        #expect(voices.settings?.savesOtherVoices == true)
        await voices.loadIgnored()
        await voices.restore(voices.ignored[0])
        #expect(voices.ignored.count == 1)
        api.speakers.failing = []
        await voices.restore(voices.ignored[0])
        #expect(voices.ignored.isEmpty)
        #expect(api.speakers.ignored.isEmpty)
    }
}
