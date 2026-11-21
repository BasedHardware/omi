import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Recorded runs from before this build (the canned failure behind a "Done:" and an artifact event).
@MainActor
struct LegacyRunTests {
    @Test func aCannedFailureRecordedAsDoneReadsAsFailedWithWhatWasWritten() async {
        let api = FakeAPIClient()
        let answer = "I'll gather context: the conversation and your calendar.\n\n" + ChatStreamEvent.serviceFailureTexts[3]
        api.workstreamsByID = ["w1": Workstream(id: "w1", title: "Physio", status: .completed, summary: answer, events: [
            Workstream.Event(id: "e1", kind: "system", summary: "Work initiated by the user", createdAt: Fixtures.now, sequence: 1),
            Workstream.Event(id: "e2", kind: "agent_update", summary: AgentStore.startedSummary, createdAt: Fixtures.now, sequence: 2),
            Workstream.Event(id: "e3", kind: "agent_update", summary: "Done: " + answer, createdAt: Fixtures.now, sequence: 3),
            Workstream.Event(
                id: "e4",
                kind: "artifact_version",
                summary: "Artifact omi-result-1 version 1 created",
                createdAt: Fixtures.now,
                sequence: 4
            ),
        ])]
        let task = Fixtures.task("t1", "Book physio session in two weeks", workstream: "w1")
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadWorkstreams(for: [task])
        let run = agent.workItems(tasks: [task]).first
        #expect(run?.failure == .toolLoop)
        #expect(run?.steps == [])
        #expect(run?.partialText == "I'll gather context: the conversation and your calendar.")
    }

    @Test func omiAsksComesFirstAndReplacesItsWorkingRow() {
        let run = AgentStore.Run(
            id: "t1",
            taskTitle: "Follow-up",
            state: .working(step: "x"),
            steps: [],
            partialText: "",
            startedAt: Fixtures.now
        )
        let ask = PendingDeviceTool(taskID: "t1", taskTitle: "Follow-up", request: DeviceToolRequest(id: "c1", toolName: "search_contacts"))
        let inbox = HomeAttention.inbox(.init(runs: [run], asks: [ask], showsSiriTip: true))
        #expect(inbox.needsYou.map(\.id) == ["asks.c1"])
        #expect(inbox.later.map(\.id) == ["siri"])
    }
}
