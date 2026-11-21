import Foundation
import OmiCore
import OmiNetwork
@testable import OmiService
import OmiTestSupport
import Testing

/// Agent runs: the real reason a run stopped, the backend's heartbeats kept out of the steps,
/// "Omi asks" round trips that never act without a tap, stale runs, and runs rebuilt after a restart.
@MainActor
struct AgentRunTests {
    private let task = Fixtures.task("t9", "Send Anna the Thursday follow-up")

    private func done(_ text: String) -> ChatStreamEvent {
        .done(ChatMessage(id: "reply-9", text: text, sender: .omi, createdAt: Fixtures.now))
    }

    /// Starts the run, waits for Omi's question, returns the pending call and the running task.
    private func startAndWaitForQuestion(_ agent: AgentStore) async throws -> (PendingDeviceTool, Task<Void, Never>) {
        let task = task
        let running = Task { await agent.takeOver(task, conversationTitle: nil) }
        for _ in 0 ..< 200 where agent.deviceToolRequests.isEmpty {
            try await Task.sleep(for: .milliseconds(5))
        }
        let pending = try #require(agent.deviceToolRequests[task.id])
        return (pending, running)
    }

    // MARK: Failure reasons

    @Test func failureCodesFromFramesAnswersAndErrors() {
        #expect(RunFailure.from(streamError: "quota_exceeded") == .quotaExceeded)
        #expect(RunFailure.from(streamError: "server_error") == .serverError)
        #expect(RunFailure.from(streamError: "idle_timeout") == .timeout)
        #expect(RunFailure.from(streamError: "The response took too long. Please try again.") == .timeout)
        #expect(RunFailure.from(streamError: "Unable to complete the response. Please try again.") == .serverError)
        #expect(RunFailure.from(streamError: "Google Calendar isn't connected.") == .notConnected)
        #expect(RunFailure.from(streamError: "something odd") == .couldNotFinish)
        // The safety guard appends its sentence to what the agent wrote so far.
        let stuck = "I looked at your calendar.\n\n" + ChatStreamEvent.serviceFailureTexts[4]
        #expect(RunFailure.from(answer: stuck) == .toolLoop)
        #expect(RunFailure.from(answer: ChatStreamEvent.serviceFailureTexts[3]) == .toolLoop)
        #expect(RunFailure.from(answer: "I can't help with that one. Try asking me something else.") == .refused)
        #expect(RunFailure.from(answer: "Drafted the follow-up for Anna.") == nil)
        #expect(RunFailure.from(error: APIError.http(status: 402, body: "")) == .quotaExceeded)
        #expect(RunFailure.from(error: APIError.http(status: 503, body: "")) == .serverError)
        #expect(RunFailure.from(error: URLError(.notConnectedToInternet)) == .offline)
        #expect(RunFailure.from(error: URLError(.timedOut)) == .timeout)
        // Recorded on the workstream and read back on another device; older markers stay readable.
        #expect(RunFailure.from(event: RunFailure.toolLoop.eventSummary) == .toolLoop)
        #expect(RunFailure.from(event: AgentStore.failedSummary) == .couldNotFinish)
        #expect(RunFailure.from(event: "Searching your conversations") == nil)
        #expect(!RunFailure.quotaExceeded.canRetry && RunFailure.toolLoop.canRetry)
    }

    @Test func theTypedReasonSurvivesTheCannedAnswerAfterIt() async {
        let api = FakeAPIClient()
        api.agentScript = [.step("Searching your conversations"), .failed("quota_exceeded"), done(ChatStreamEvent.serviceFailureTexts[0])]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(task, conversationTitle: nil)
        #expect(agent.runs[task.id]?.failure == .quotaExceeded)
        #expect(api.workstreamLog.contains("event:\(RunFailure.quotaExceeded.eventSummary)"))
        #expect(!api.workstreamLog.contains("status:completed"))
    }

    @Test func safetyGuardStopReadsAsStuck() async {
        let api = FakeAPIClient()
        api.agentScript = [
            .step("Preparing response…"), .step("Searching your conversations"),
            done("Let me check.\n\n" + ChatStreamEvent.serviceFailureTexts[4]),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(task, conversationTitle: nil)
        #expect(agent.runs[task.id]?.failure == .toolLoop)
    }

    @Test func heartbeatsAreNeverSteps() async {
        let api = FakeAPIClient()
        api.agentScript = [
            .step("Preparing response…"),
            .step("Still working…"),
            .step("⚠️ I'm processing a lot of information."),
            done("Drafted it."),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(task, conversationTitle: nil)
        #expect(agent.runs[task.id]?.steps == [])
        #expect(agent.runs[task.id]?.state == .done(result: "Drafted it."))
        #expect(!api.workstreamLog.contains { $0.contains("Preparing") || $0.contains("Still working") })
        #expect(AgentStore.isHeartbeat("Preparing response…") && !AgentStore.isStepEvent("Still working…"))
    }

    @Test func aThrownErrorKeepsItsReason() async {
        let api = FakeAPIClient(error: .transport("offline"))
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(task, conversationTitle: nil)
        #expect(agent.runs[task.id]?.failure == .offline)
    }

    @Test func thinkStepsReachTheWorkstreamThrottled() async {
        let api = FakeAPIClient()
        api.agentScript = [
            .step("Searching your conversations"),
            .step("Searching your conversations"),
            .step("Checking your calendar"),
            done("Done."),
        ]
        let clock = RunClock(Fixtures.now)
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { clock.now })
        await agent.takeOver(task, conversationTitle: nil)
        #expect(api.workstreamLog.count(where: { $0 == "event:Searching your conversations" }) == 1)
        #expect(!api.workstreamLog.contains("event:Checking your calendar"))
        #expect(api.eventKeys.contains { $0.hasSuffix(":step:1") })
    }

    // MARK: Omi asks

    @Test func declaresOnlyWhatThePhoneCanRun() async {
        let api = FakeAPIClient()
        let agent = AgentStore(api: api, preferences: freshPreferences())
        await agent.takeOver(task, conversationTitle: nil)
        #expect(api.agentRequests.last?.deviceTools == [])
        agent.deviceTools = FakeDeviceTools(canSendMessages: false)
        await agent.takeOver(Fixtures.task("t8", "Other"), conversationTitle: nil)
        #expect(api.agentRequests.last?.deviceTools == ["search_contacts", "request_permission"])
        agent.deviceTools = FakeDeviceTools()
        await agent.takeOver(Fixtures.task("t7", "Third"), conversationTitle: nil)
        #expect(api.agentRequests.last?.deviceTools == ["propose_message", "search_contacts", "request_permission"])
    }

    @Test func aProposedMessageOnlyOpensTheComposerAfterTheTap() async throws {
        let api = FakeAPIClient()
        let tools = FakeDeviceTools()
        let request = DeviceToolRequest(
            id: "call-1",
            toolName: "propose_message",
            recipients: ["+49 170 1234567"],
            text: "Hi Anna, Thursday 7 pm?"
        )
        api.agentScript = [.step("Drafting the message"), .deviceTool(request), done("Anna has the follow-up.")]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = tools
        let (pending, running) = try await startAndWaitForQuestion(agent)
        #expect(pending.request.text == "Hi Anna, Thursday 7 pm?")
        #expect(tools.log.isEmpty)
        #expect(api.deviceToolResults.isEmpty)
        await agent.answer(pending, .send(text: "Hi Anna, Thursday 7 pm works?"))
        await running.value
        #expect(tools.log == ["compose:+49 170 1234567:Hi Anna, Thursday 7 pm works?"])
        #expect(api.deviceToolResults["call-1"] == DeviceToolResult(ok: true, status: "sent"))
        #expect(agent.deviceToolRequests.isEmpty)
        #expect(agent.runs[task.id]?.state == .done(result: "Anna has the follow-up."))
    }

    @Test func notNowTellsTheAgentAndSendsNothing() async throws {
        let api = FakeAPIClient()
        let tools = FakeDeviceTools()
        api.agentScript = [
            .deviceTool(DeviceToolRequest(id: "call-2", toolName: "propose_message", recipients: ["anna@example.com"], text: "Hi")),
            done("Okay."),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = tools
        let (pending, running) = try await startAndWaitForQuestion(agent)
        await agent.answer(pending, .decline)
        await running.value
        #expect(tools.log.isEmpty)
        let result = try #require(api.deviceToolResults["call-2"])
        #expect(!result.ok && result.status == "cancelled" && result.reason == "declined")
    }

    @Test func aCancelledComposerIsNotASentMessage() async throws {
        let api = FakeAPIClient()
        let tools = FakeDeviceTools()
        tools.composeOutcome = .cancelled
        api.agentScript = [
            .deviceTool(DeviceToolRequest(id: "call-3", toolName: "propose_message", recipients: ["x"], text: "Hi")),
            done("Okay."),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = tools
        let (pending, running) = try await startAndWaitForQuestion(agent)
        await agent.answer(pending, .send(text: "Hi"))
        await running.value
        #expect(api.deviceToolResults["call-3"]?.ok == false)
        #expect(api.deviceToolResults["call-3"]?.status == "cancelled")
    }

    @Test func onlyThePickedContactLeavesThePhone() async throws {
        let api = FakeAPIClient()
        let tools = FakeDeviceTools()
        api.agentScript = [.deviceTool(DeviceToolRequest(id: "call-4", toolName: "search_contacts", query: "Ann")), done("Found Anna.")]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = tools
        let (pending, running) = try await startAndWaitForQuestion(agent)
        #expect(pending.matches.map(\.name) == ["Anna Schmidt", "Annabel Lee"])
        #expect(!pending.needsContactsAccess)
        await agent.answer(pending, .pick(pending.matches[0]))
        await running.value
        let result = try #require(api.deviceToolResults["call-4"])
        #expect(result.ok && result.contacts?.map(\.id) == ["c-anna"] && result.query == "Ann")
    }

    @Test func contactsAskForAccessFirstAndOnlyOnTap() async throws {
        let api = FakeAPIClient()
        let tools = FakeDeviceTools(contactsAccess: .notDetermined)
        api.agentScript = [.deviceTool(DeviceToolRequest(id: "call-5", toolName: "search_contacts", query: "Anna")), done("Found Anna.")]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = tools
        let (pending, running) = try await startAndWaitForQuestion(agent)
        #expect(pending.needsContactsAccess && pending.matches.isEmpty)
        #expect(tools.log.isEmpty)
        await agent.answer(pending, .allow)
        let allowed = try #require(agent.deviceToolRequests[task.id])
        #expect(tools.log == ["prompt", "search:Anna"])
        #expect(allowed.matches.first?.id == "c-anna")
        #expect(api.deviceToolResults.isEmpty)
        await agent.answer(allowed, .pick(allowed.matches[0]))
        await running.value
        #expect(api.deviceToolResults["call-5"]?.contacts?.count == 1)
    }

    @Test func deniedAccessIsReportedNotRetried() async throws {
        let api = FakeAPIClient()
        let tools = FakeDeviceTools(contactsAccess: .notDetermined)
        tools.accessAfterPrompt = .denied
        api.agentScript = [
            .deviceTool(DeviceToolRequest(id: "call-6", toolName: "request_permission", permission: "contacts")),
            done("Okay."),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = tools
        let (pending, running) = try await startAndWaitForQuestion(agent)
        await agent.answer(pending, .allow)
        await running.value
        #expect(api.deviceToolResults["call-6"]?.reason == "authorization_denied")
    }

    @Test func malformedAndUnknownCallsAreAnsweredWithoutAsking() async {
        let api = FakeAPIClient()
        api.agentScript = [
            .deviceTool(DeviceToolRequest(id: "bad-1", toolName: "")),
            .deviceTool(DeviceToolRequest(id: "bad-2", toolName: "run_applescript")),
            .deviceTool(DeviceToolRequest(id: "bad-3", toolName: "propose_message", recipients: [], text: "Hi")),
            done("Done."),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = FakeDeviceTools()
        await agent.takeOver(task, conversationTitle: nil)
        #expect(api.deviceToolResults["bad-1"]?.reason == "malformed_request")
        #expect(api.deviceToolResults["bad-2"]?.reason == "unsupported_tool")
        #expect(api.deviceToolResults["bad-3"]?.reason == "empty_recipient")
        #expect(agent.deviceToolRequests.isEmpty)
    }

    @Test func anUnansweredQuestionLeavesWithTheRun() async {
        let api = FakeAPIClient()
        api.deviceToolWait = .milliseconds(20)
        api.agentScript = [
            .deviceTool(DeviceToolRequest(id: "call-7", toolName: "search_contacts", query: "Anna")),
            done("I could not ask you in time."),
        ]
        let agent = AgentStore(api: api, preferences: freshPreferences())
        agent.deviceTools = FakeDeviceTools()
        await agent.takeOver(task, conversationTitle: nil)
        #expect(agent.deviceToolRequests.isEmpty)
        #expect(api.deviceToolResults.isEmpty)
    }
}

/// Stale runs and runs rebuilt from the backend after a restart.
@MainActor
struct RecoveredRunTests {
    private let task = Fixtures.task("t9", "Send Anna the Thursday follow-up")

    @Test func aRunWithoutProgressForTenMinutesHasStopped() async {
        let api = FakeAPIClient()
        let started = { (minutesAgo: Double) in
            [Workstream.Event(
                id: "e1", kind: "agent_update", summary: AgentStore.startedSummary,
                createdAt: Fixtures.now.addingTimeInterval(-minutesAgo * 60), sequence: 1
            )]
        }
        api.workstreamsByID = [
            "w-old": Workstream(id: "w-old", title: "a", status: .open, summary: nil, events: started(11)),
            "w-new": Workstream(id: "w-new", title: "b", status: .open, summary: nil, events: started(4)),
        ]
        let tasks = [Fixtures.task("t1", "Old", workstream: "w-old"), Fixtures.task("t2", "New", workstream: "w-new")]
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadWorkstreams(for: tasks)
        let items = Dictionary(uniqueKeysWithValues: agent.workItems(tasks: tasks).map { ($0.id, $0) })
        #expect(items["t1"]?.isStopped == true)
        #expect(items["t2"]?.isActive == true)
    }

    @Test func aRestartRebuildsStepsAndTextFromTheBackend() async {
        let api = FakeAPIClient()
        let at = { (minutes: Double) in Fixtures.now.addingTimeInterval(-minutes * 60) }
        api.workstreamsByID = ["w9": Workstream(id: "w9", title: "Follow-up", status: .open, summary: nil, events: [], updatedAt: at(30))]
        api.eventLogs["w9"] = [
            Workstream.Event(
                id: "e1", kind: "agent_update", summary: AgentStore.startedSummary, createdAt: at(30), sequence: 1,
                evidence: [.init(kind: "external", id: "chat_session:s-9")]
            ),
            Workstream.Event(id: "e2", kind: "agent_update", summary: "Searching your conversations", createdAt: at(29), sequence: 2),
            Workstream.Event(id: "e3", kind: "agent_update", summary: "Checking your calendar", createdAt: at(28), sequence: 3),
        ]
        api.sessionHistories["s-9"] = [
            ChatMessage(id: "u", text: "Please take care of this task", sender: .user, createdAt: at(30)),
            ChatMessage(id: "o", text: "I found Thursday 7 pm free.", sender: .omi, createdAt: at(28)),
        ]
        let task = Fixtures.task("t9", "Send Anna the Thursday follow-up", workstream: "w9")
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadWorkstreams(for: [task])
        let run = agent.workItems(tasks: [task]).first
        #expect(run?.steps == ["Searching your conversations", "Checking your calendar"])
        #expect(run?.partialText == "I found Thursday 7 pm free.")
        #expect(run?.sessionID == "s-9")
        #expect(run?.isStopped == true)

        // Resume continues in the same thread; no new session.
        let sessionsBefore = api.chatSessions.count
        await agent.resume(task, conversationTitle: nil)
        #expect(api.agentRequests.last?.sessionID == "s-9")
        #expect(api.chatSessions.count == sessionsBefore)
        #expect(agent.runs[task.id]?.state == .done(result: api.chatReply))
    }

    @Test func aFailureRecordedByAnotherDeviceReadsTheSame() async {
        let api = FakeAPIClient()
        api.workstreamsByID = ["w1": Workstream(id: "w1", title: "a", status: .open, summary: nil, events: [
            Workstream.Event(
                id: "e1",
                kind: "agent_update",
                summary: RunFailure.timeout.eventSummary,
                createdAt: Fixtures.now,
                sequence: 4
            ),
        ])]
        let task = Fixtures.task("t1", "A", workstream: "w1")
        let agent = AgentStore(api: api, preferences: freshPreferences(), now: { Fixtures.now })
        await agent.loadWorkstreams(for: [task])
        #expect(agent.workItems(tasks: [task]).first?.failure == .timeout)
    }

    @Test func theRunsThreadIsRecordedAtTheStart() async {
        let api = FakeAPIClient()
        await AgentStore(api: api, preferences: freshPreferences()).takeOver(task, conversationTitle: nil)
        #expect(api.eventEvidence.first == [["kind": "external", "id": "chat_session:app-session-omi-agent-run-1", "scope": "canonical"]])
    }
}

/// A settable clock for throttling tests.
final class RunClock: @unchecked Sendable {
    var now: Date

    init(_ now: Date) {
        self.now = now
    }
}
