import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

@MainActor
struct HomeAttentionTests {
    private var utc: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        return calendar
    }

    private func run(_ id: String, _ state: AgentStore.RunState, minutesAgo: Double = 0) -> AgentStore.Run {
        AgentStore.Run(
            id: id, taskTitle: id, workstreamID: nil, state: state, steps: [], partialText: "",
            startedAt: Fixtures.now.addingTimeInterval(-minutesAgo * 60)
        )
    }

    private func inbox(_ input: HomeAttention.Input) -> (needsYou: [String], later: [String]) {
        let inbox = HomeAttention.inbox(input)
        return (inbox.needsYou.map(\.id), inbox.later.map(\.id))
    }

    /// Needs you: tidy-up, Omi asks, finished runs, What matters now, tasks, one connection;
    /// Omi's running work and tips wait in Later.
    @Test func needsYouOrder() {
        let ask = PendingDeviceTool(taskID: "x", taskTitle: "Follow-up", request: DeviceToolRequest(id: "c1", toolName: "search_contacts"))
        let input = HomeAttention.Input(
            runs: [
                run("failed", .failed("x"), minutesAgo: 1), run("busy", .working(step: "Searching")), run("done", .done(result: "Drafts")),
            ],
            asks: [ask],
            recommendations: [Recommendation(id: "r1", headline: "Proof", whyNow: "Overdue", action: "Send", taskID: nil)],
            tasks: [Fixtures.task("t1", "Send the deck", dueInDays: -1)],
            tidyUp: TaskTidyUp.Proposal(done: [.init(id: "t1", why: "sent")]),
            speakerPrompt: SpeakerPrompt(id: "p1", kind: .identify, conversationID: "c1", speakerID: 2, segmentIDs: []),
            nudges: [ForYouItem(id: "n1", producer: "p", title: "Call Anna", body: "", target: nil)],
            showsSiriTip: true, connect: ["gmail"], now: Fixtures.now, calendar: utc
        )
        let result = inbox(input)
        #expect(result.needsYou == ["tidyup", "asks.c1", "finished.done", "help.failed", "recommendation.r1"])
        #expect(result.later == ["task.t1", "connect.gmail", "working.busy", "speaker.p1", "nudge.n1", "siri"])
    }

    @Test func atMostFiveCardsTheRestWaitsInLater() {
        let texts = [
            "Send the deck", "Book the venue", "Email Anna", "Call the bank", "Renew passport", "Pay rent", "Order cables", "Plan offsite",
        ]
        let tasks = texts.enumerated().map { Fixtures.task("t\($0.offset)", $0.element, dueInDays: -Double($0.offset + 1)) }
        let result = inbox(HomeAttention.Input(tasks: tasks, now: Fixtures.now, calendar: utc))
        #expect(result.needsYou.count == HomeAttention.needsYouLimit)
        #expect(result.later.count == 3)
        #expect(HomeAttention.inbox(HomeAttention.Input()).isEmpty)
    }

    @Test func emptyTidyUpIsNoCard() {
        let result = inbox(HomeAttention.Input(tidyUp: TaskTidyUp.Proposal(important: ["t1"])))
        #expect(result.needsYou.isEmpty)
    }

    @Test func openedFinishedRunsLeave() {
        let input = HomeAttention.Input(
            runs: [run("a", .done(result: "")), run("b", .done(result: ""), minutesAgo: 5)], openedRunIDs: ["a"]
        )
        #expect(inbox(input).needsYou == ["finished.b"])
    }

    @Test func finishedRunsFoldIntoOneCardEachWaitsInLater() {
        let input = HomeAttention.Input(runs: [run("a", .done(result: "")), run("b", .done(result: ""), minutesAgo: 5)])
        let result = HomeAttention.inbox(input)
        let group = result.needsYou.first.flatMap { item -> [AgentStore.Run]? in
            if case let .finishedGroup(runs) = item { runs } else { nil }
        }
        #expect(group?.map(\.id) == ["a", "b"])
        #expect(result.later.map(\.id) == ["finished.a", "finished.b"])
    }

    /// A recommendation with a loaded task is that task's card (first among tasks); tasks Omi has
    /// (a finished run, a workstream) are not repeated.
    @Test func recommendationsBecomeTheirTasksCard() {
        let input = HomeAttention.Input(
            runs: [run("t1", .done(result: ""))],
            openedRunIDs: ["t1"],
            recommendations: [
                Recommendation(id: "r1", headline: "Proof", whyNow: "", action: "", taskID: "t2"),
                Recommendation(id: "r2", headline: "Busy", whyNow: "", action: "", taskID: "t1"),
                Recommendation(id: "r3", headline: "Elsewhere", whyNow: "", action: "", taskID: "unknown"),
            ],
            tasks: [
                Fixtures.task("t1", "Draft the memo", dueInDays: -1), Fixtures.task("t2", "Research venue options"),
                Fixtures.task("t3", "Email the landlord", dueInDays: -1, workstream: "w3"),
                Fixtures.task("t4", "Book the physio", dueInDays: 0),
            ],
            now: Fixtures.now, calendar: utc
        )
        let result = HomeAttention.inbox(input)
        #expect(result.needsYou.map(\.id) == ["task.t2", "recommendation.r3", "task.t4"])
        if case let .task(card) = result.needsYou[0] {
            #expect(card.recommendation?.id == "r1")
        } else {
            Issue.record("expected a task card")
        }
        #expect(result.later.isEmpty)
    }

    /// The magic button: while Omi runs the task its card stays where it was (the held
    /// recommendation keeps the rank, a workstream set mid-run does not hide it) and no
    /// "working" card repeats it; a run without a card still waits in Later.
    @Test func aRunningTaskKeepsItsCard() {
        let input = HomeAttention.Input(
            runs: [run("t1", .working(step: "")), run("t9", .starting)],
            recommendations: [Recommendation(id: "r1", headline: "Memo", whyNow: "", action: "", taskID: "t1")],
            tasks: [
                Fixtures.task("t1", "Draft the memo", workstream: "w1"),
                Fixtures.task("t2", "Book the physio", dueInDays: 0),
            ],
            now: Fixtures.now, calendar: utc
        )
        let result = HomeAttention.inbox(input)
        #expect(result.needsYou.map(\.id) == ["task.t1", "task.t2"])
        #expect(result.later.map(\.id) == ["working.t9"])

        // Finished: the run card replaces the task card.
        var finished = input
        finished.runs = [run("t1", .done(result: "Drafted"))]
        #expect(inbox(finished).needsYou == ["finished.t1", "task.t2"])
    }

    @Test func snoozedTasksWaitInLater() {
        let tomorrow = Fixtures.now.addingTimeInterval(86400)
        let input = HomeAttention.Input(
            tasks: [Fixtures.task("t1", "Send the deck", dueInDays: -1), Fixtures.task("t2", "Book the venue", dueInDays: 0)],
            snoozes: ["t1": tomorrow, "t2": Fixtures.now.addingTimeInterval(-60)], now: Fixtures.now, calendar: utc
        )
        let result = inbox(input)
        #expect(result.needsYou == ["task.t2"])
        #expect(result.later == ["task.t1"])
    }

    /// No dead taps: every kind of card leads somewhere.
    @Test func everyCardHasATapTarget() {
        let card = TaskConsolidation.Card(group: .init(task: Fixtures.task("t1", "Send the deck")), kicker: .overdue)
        let ask = PendingDeviceTool(taskID: "t9", taskTitle: "x", request: DeviceToolRequest(id: "c1", toolName: "search_contacts"))
        let send = "Send Anna the deck"
        let cases: [(HomeAttention.Item, HomeTapTargets.Target)] = [
            (.task(card), .task("t1")),
            (.tidyUp(.init(done: [.init(id: "t1", why: "")])), .tidyUp),
            (.omiAsks(ask), .run("t9")),
            (.finished(run("a", .done(result: ""))), .run("a")),
            (.finishedGroup([run("a", .done(result: ""))]), .later),
            (.needsHelp(run("b", .failed("x"))), .run("b")),
            (.recommendation(Recommendation(id: "r", headline: "H", whyNow: "", action: send, taskID: "t2")), .task("t2")),
            (.recommendation(Recommendation(id: "r", headline: "H", whyNow: "", action: send, taskID: nil)), .ask(send)),
            (.nudge(ForYouItem(id: "n", producer: "", title: "Call Anna", body: "", target: nil)), .ask("Call Anna")),
            (.nudge(ForYouItem(id: "n", producer: "", title: "", body: "", target: .conversation("c1"))), .conversation("c1")),
            (.connect("gmail"), .connect("gmail")),
            (.siriTip, .siriTip),
        ]
        for (item, target) in cases {
            #expect(HomeTapTargets.target(item) == target, "\(item.id)")
        }
    }

    @Test func openingAFinishedRunIsRememberedAndANewRunClearsIt() async {
        let preferences = freshPreferences()
        let agent = AgentStore(api: FakeAPIClient(), preferences: preferences)
        agent.markOpened("t1")
        #expect(AgentStore(api: FakeAPIClient(), preferences: preferences).openedRunIDs == ["t1"])
        await agent.takeOver(Fixtures.tasks[0], conversationTitle: nil)
        #expect(!agent.openedRunIDs.contains(Fixtures.tasks[0].id))
        #expect(AgentStore(api: FakeAPIClient(), preferences: preferences).openedRunIDs.contains(Fixtures.tasks[0].id) == false)
    }
}

@MainActor
struct RecapSlotTests {
    @Test func aDaysRecapLeadsItAndYesterdayOffersToWriteOne() async throws {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = try #require(TimeZone(identifier: "UTC"))
        let api = FakeAPIClient()
        api.summaries = [DailySummary(
            id: "r4", date: "2026-10-04", headline: "Investors", overview: "", emoji: nil,
            conversationCount: 1, highlights: [], decisions: []
        )]
        let store = ConversationsStore(api: api, calendar: calendar)
        await store.load()
        await store.loadRecaps()
        let days = store.sections.map(\.day)
        #expect(store.recapSlot(for: days[0], now: Fixtures.now) == nil)
        #expect(store.recapSlot(for: days[1], now: Fixtures.now) == .write(days[1]))
        #expect(store.recapSlot(for: days[2], now: Fixtures.now) == .recap(api.summaries[0]))
        await store.setFilter(.starred)
        #expect(store.recapSlot(for: days[2], now: Fixtures.now) == nil)
    }
}
