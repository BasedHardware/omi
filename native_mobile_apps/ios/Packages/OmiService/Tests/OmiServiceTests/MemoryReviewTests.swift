import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Memory review: only real doubts become questions, each asked the right way, and every answer
/// goes to the right endpoint.
@MainActor
struct MemoryReviewTests {
    private func memory(
        _ id: String, _ content: String, reasons: [String] = [], subject: String? = nil, reviewed: Bool = false,
        category: String = "interesting", minutesAgo: Double = 0
    ) -> Memory {
        Memory(
            id: id, content: content, headline: nil, category: category, createdAt: Fixtures.now.addingTimeInterval(-minutesAgo * 60),
            conversationID: nil, reviewed: reviewed, uncertaintyReasons: reasons, subjectName: subject
        )
    }

    private func store(_ memories: [Memory], conflicts: [MemoryConflict] = []) async -> (MemoriesStore, FakeAPIClient) {
        let api = FakeAPIClient(memories: memories)
        api.memoryExtras.conflicts = conflicts
        let store = MemoriesStore(api: api)
        await store.load()
        await store.loadReviewQueue()
        return (store, api)
    }

    @Test func onlyRealDoubtsAreQuestions() {
        #expect(!MemoryReviewRule.needsReview(memory("a", "Likes tea.")))
        // One conversation is the normal case, not a doubt.
        #expect(!MemoryReviewRule.needsReview(memory("b", "Likes tea.", reasons: ["single_source"])))
        #expect(MemoryReviewRule.needsReview(memory("c", "Likes tea.", reasons: ["single_source", "low_capture_signal"])))
        #expect(MemoryReviewRule.needsReview(memory("d", "Moves to Lisbon.", reasons: ["third_party_subject"])))
        #expect(MemoryReviewRule.needsReview(memory("e", "Lives in Berlin.", reasons: ["stale"])))
        #expect(MemoryReviewRule.needsReview(memory("f", "Lives in Munich.", reasons: ["contradicted_by:m-berlin"])))
        // Answered, typed in or pinned memories are never asked about.
        #expect(!MemoryReviewRule.needsReview(memory("g", "x", reasons: ["stale"], reviewed: true)))
        #expect(!MemoryReviewRule.needsReview(memory("h", "x", reasons: ["stale"], category: "manual")))
    }

    @Test func eachDoubtIsAskedItsOwnWay() {
        let berlin = memory("m-berlin", "Lives in Berlin.")
        let all = [berlin]
        #expect(MemoryReviewRule.question(for: memory("a", "Likes tea.", reasons: ["single_source", "low_capture_signal"]), among: all)?.0
            == .heardOnce)
        #expect(MemoryReviewRule.question(for: memory("b", "Likes tea.", reasons: ["low_capture_signal"]), among: all)?.0 == .unclear)
        #expect(MemoryReviewRule.question(
            for: memory("c", "Moves to Lisbon.", reasons: ["third_party_subject"], subject: "Lena"),
            among: all
        )?
            .0 == .aboutSomeoneElse(name: "Lena"))
        #expect(MemoryReviewRule.question(for: memory("d", "Works at Acme.", reasons: ["stale"]), among: all)?.0 == .stillTrue)
        let moved = MemoryReviewRule.question(for: memory("e", "Lives in Munich.", reasons: ["contradicted_by:m-berlin"]), among: all)
        #expect(moved?.0 == .whichIsRight(earlier: "Lives in Berlin.", now: "Lives in Munich."))
        #expect(moved?.earlier?.id == "m-berlin")
        // A contradiction wins over the other doubts.
        let both = memory("f", "Lives in Munich.", reasons: ["third_party_subject", "contradicted_by"])
        #expect(MemoryReviewRule.question(for: both, among: all)?.0 == .whichIsRight(earlier: nil, now: "Lives in Munich."))
    }

    @Test func conflictsComeFirstThenContradictionsThenTheRest() async {
        let conflict = MemoryConflict(
            id: "review:m9:m-berlin",
            factID: "m9",
            candidate: "Lives in Hamburg.",
            conflictsWith: ["m-berlin"],
            createdAt: nil
        )
        let (store, _) = await store([
            memory("m-berlin", "Lives in Berlin."),
            memory("a", "Likes tea.", reasons: ["single_source", "low_capture_signal"], minutesAgo: 1),
            memory("b", "Moves to Lisbon.", reasons: ["third_party_subject"], minutesAgo: 5),
            memory("c", "Lives in Munich.", reasons: ["contradicted_by:m-berlin"], minutesAgo: 9),
            memory("d", "Plays chess."),
        ], conflicts: [conflict])
        #expect(store.reviewQueue.map(\.id) == ["conflict.review:m9:m-berlin", "memory.c", "memory.b", "memory.a"])
        #expect(store.reviewQueue.first?.question == .whichIsRight(earlier: "Lives in Berlin.", now: "Lives in Hamburg."))
        #expect(store.reviewCount == 4)
    }

    @Test func noDoubtsMeansNoReviewAtAll() async {
        let (store, _) = await store([memory("a", "It's done."), memory("b", "Likes tea.", reasons: ["single_source"])])
        #expect(store.reviewQueue.isEmpty)
        #expect(store.reviewCount == 0)
    }

    @Test func memoryAnswersGoToTheReviewEndpoint() async throws {
        let (store, api) = await store([
            memory("a", "Likes tea.", reasons: ["low_capture_signal"]),
            memory("b", "Moves to Lisbon.", reasons: ["third_party_subject"]),
            memory("c", "Works at Acme.", reasons: ["stale"]),
        ])
        let items = store.reviewQueue
        let item = { (id: String) in try #require(items.first { $0.id == "memory.\(id)" }) }
        try await store.answer(item("a"), .yes)
        try await store.answer(item("b"), .no)
        try await store.answer(item("c"), .edit("Works at Northwind."))
        #expect(api.memoryExtras.log.filter { $0.hasPrefix("review") } == ["review:a=true", "review:b=false", "review:c=true"])
        #expect(api.editLog.contains { $0.contains("Works at Northwind.") })
        #expect(store.reviewQueue.isEmpty)
    }

    @Test func aContradictionCanKeepEitherOrNeither() async throws {
        let berlin = memory("m-berlin", "Lives in Berlin.")
        let munich = memory("m-munich", "Lives in Munich.", reasons: ["contradicted_by:m-berlin"])
        let (store, api) = await store([berlin, munich])
        try await store.answer(#require(store.reviewQueue.first), .keepNew)
        #expect(api.memoryExtras.log.filter { $0.hasPrefix("review") } == ["review:m-munich=true", "review:m-berlin=false"])

        let (other, otherAPI) = await self.store([berlin, munich])
        try await other.answer(#require(other.reviewQueue.first), .neither)
        #expect(otherAPI.memoryExtras.log.filter { $0.hasPrefix("review") } == ["review:m-munich=false", "review:m-berlin=false"])
    }

    @Test func queueConflictsResolveOnTheQueue() async {
        let conflicts = [
            MemoryConflict(id: "r1", factID: "m9", candidate: "Lives in Hamburg.", conflictsWith: ["m-berlin"], createdAt: nil),
            MemoryConflict(id: "r2", factID: "m8", candidate: "Has a dog.", conflictsWith: ["m-cat"], createdAt: nil),
            MemoryConflict(id: "r3", factID: "m7", candidate: "Drinks coffee.", conflictsWith: ["m-tea"], createdAt: nil),
        ]
        let (store, api) = await store(
            [memory("m-berlin", "Lives in Berlin."), memory("m-cat", "Has a cat."), memory("m-tea", "Drinks tea.")],
            conflicts: conflicts
        )
        let items = store.reviewQueue
        await store.answer(items[0], .keepNew)
        await store.answer(items[1], .keepEarlier)
        await store.answer(items[2], .neither)
        #expect(api.memoryExtras.log.filter { $0.hasPrefix("resolve") || $0.hasPrefix("review") } == [
            "resolve:r1=accept", "resolve:r2=reject", "resolve:r3=reject", "review:m-tea=false",
        ])
        #expect(store.reviewConflicts.isEmpty)
        await store.loadReviewQueue()
        #expect(store.reviewCount == 0)
    }

    @Test func aFailedResolveKeepsTheQuestion() async {
        let conflict = MemoryConflict(id: "r1", factID: "m9", candidate: "Lives in Hamburg.", conflictsWith: [], createdAt: nil)
        let (store, api) = await store([], conflicts: [conflict])
        api.memoryExtras.failing = ["resolve"]
        await store.answer(store.reviewQueue[0], .keepNew)
        #expect(store.reviewConflicts.map(\.id) == ["r1"])
        #expect(store.lastError != nil)
    }
}
