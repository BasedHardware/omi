import Foundation
import OmiCore
@testable import OmiService
import OmiTestSupport
import Testing

/// Every task says where it came from: its conversation and the words it was extracted from.
@MainActor
struct TaskSourceTests {
    @Test func loadsEachConversationOnceAndQuotesTheCitedWords() async {
        let api = FakeAPIClient()
        var detail = ConversationDetail(conversation: Fixtures.conversations[0], summaryActionItems: [], transcript: [
            .init(id: 0, speaker: "Anna", isUser: false, text: "Please send the roadmap deck.", start: 0, segmentID: "s1"),
        ])
        detail.actionItemSources = ["send roadmap deck": .init(context: "", segmentIDs: ["s1"])]
        api.conversationExtras.details["c1"] = detail
        let store = ConversationsStore(api: api)
        let deck = Fixtures.task("t2", "Send roadmap deck")
        let other = Fixtures.task("t9", "Something else")

        #expect(store.quote(of: deck) == nil)
        await store.loadSources(for: [deck, other])
        #expect(store.sourceDetails.keys.sorted() == ["c1"])
        #expect(store.source(of: deck)?.title == "Q4 roadmap with Anna")
        #expect(store.quote(of: deck) == "Please send the roadmap deck.")
        #expect(store.quote(of: other) == nil)
        #expect(store.source(of: Fixtures.task("t0", "Loose", conversation: nil)) == nil)
    }
}
