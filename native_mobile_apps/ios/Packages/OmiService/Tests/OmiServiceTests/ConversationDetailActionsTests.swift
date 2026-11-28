import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

/// The detail store: transcript edits, reprocess, audio, search, copy text.
@MainActor
struct ConversationDetailActionsTests {
    private func detailStore(_ api: FakeAPIClient) async -> ConversationDetailStore {
        let store = ConversationDetailStore(preview: Fixtures.conversations[0], api: api)
        await store.load()
        return store
    }

    @Test func editsALineAndRollsBack() async {
        let api = FakeAPIClient()
        let store = await detailStore(api)
        #expect(await store.editLine(0, text: " Fixed words "))
        #expect(store.detail?.transcript[0].text == "Fixed words")
        #expect(api.conversationActions.log == ["segment:c1/seg-0=Fixed words"])
        // Nothing changed, nothing sent.
        #expect(await !(store.editLine(0, text: "Fixed words")))

        api.conversationActions.failing = ["segment"]
        #expect(await !(store.editLine(0, text: "Other")))
        #expect(store.detail?.transcript[0].text == "Fixed words")
    }

    @Test func reprocessReplacesTheDetail() async {
        let api = FakeAPIClient()
        let list = ConversationsStore(api: api)
        await list.load()
        let store = await detailStore(api)
        #expect(await store.reprocess(in: list))
        #expect(store.detail?.summary == "Reprocessed overview.")
        #expect(!store.isReprocessing)

        api.conversationActions.failing = ["reprocess"]
        #expect(await !(store.reprocess(in: list)))
        #expect(store.detail?.summary == "Reprocessed overview.")
    }

    @Test func waitsForTheAudioFile() async throws {
        let api = FakeAPIClient()
        let url = try #require(URL(string: "https://storage.example/a.mp3"))
        api.conversationActions.audio = [.pending(retryAfter: 0), .pending(retryAfter: 0), .ready(url, duration: 60)]
        let store = await detailStore(api)
        await store.loadAudio()
        #expect(store.audio == .ready(url, duration: 60))
        #expect(api.conversationActions.log.count(where: { $0.hasPrefix("audio") }) == 3)
    }

    @Test func givesUpOnAudioThatNeverComes() async {
        let api = FakeAPIClient()
        api.conversationActions.audio = [.pending(retryAfter: 0)]
        let store = await detailStore(api)
        await store.loadAudio(attempts: 2)
        #expect(store.audio == .unavailable)
    }

    @Test func searchesTheTranscript() {
        let lines = ["We meet on Monday", "Bring the slides", "Monday works, café at noon"].enumerated().map {
            ConversationDetail.Line(id: $0.offset, speaker: "You", isUser: true, text: $0.element, start: 0)
        }
        let detail = ConversationDetail(conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: lines)
        #expect(detail.lines(matching: "monday") == [0, 2])
        #expect(detail.lines(matching: "cafe") == [2])
        #expect(detail.lines(matching: "  ").isEmpty)
        #expect(detail.transcriptText.hasPrefix("You: We meet on Monday\nYou: Bring the slides"))
    }

    @Test func summaryTextJoinsEverySummary() async {
        let api = FakeAPIClient()
        let store = await detailStore(api)
        #expect(store.summaryText == Fixtures.conversations[0].overview)
    }
}
