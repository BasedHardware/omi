import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// "Omi takes over": runs a task through the chat agent and records it on a backend workstream
/// (PLAN.md §4.4). The backend stores workstreams but executes nothing; the chat agent does the
/// work with its server-side tools, and this store keeps the workstream in step.
@MainActor
@Observable
public final class AgentStore {
    public enum RunState: Equatable, Sendable {
        case starting
        case working(step: String)
        case done(result: String)
        /// Why it stopped: a `RunFailure` code (older runs: a free-text marker).
        case failed(String)
    }

    public internal(set) var runs: [String: Run] = [:]
    public internal(set) var recommendations: [Recommendation] = []
    /// Dedupe keys of recommendations the user answered this session.
    public internal(set) var decidedRecommendations: Set<String> = []
    /// Tasks whose finished run the user has opened; Home only points at the others.
    public private(set) var openedRunIDs: Set<String>
    /// Workstreams Omi started in earlier sessions, keyed by workstream id.
    public internal(set) var workstreams: [String: Workstream] = [:]
    /// Earlier runs rebuilt from the backend after a restart, keyed by task id.
    public internal(set) var histories: [String: RunHistory] = [:]
    /// Device tool calls waiting for the user ("Omi asks"), keyed by task id (a run waits on one
    /// at a time). Home, the run's detail and chat UIs render these.
    public internal(set) var deviceToolRequests: [String: PendingDeviceTool] = [:]
    /// Called when a run ends (task, whether it finished): the shell tells the user when the app
    /// is not in front, since a hand-over can take minutes.
    @ObservationIgnored public var onRunEnded: ((ActionItem, Bool) -> Void)?
    /// Called when Omi asks something mid-run (the shell can notify while the app is away).
    @ObservationIgnored public var onDeviceToolRequest: ((PendingDeviceTool) -> Void)?
    /// The phone's contacts and message composer; without it no device tools are declared.
    @ObservationIgnored public var deviceTools: (any DeviceToolPerforming)?
    /// Raw failure reasons and tool round trips go here (Settings › Developer).
    @ObservationIgnored public var log: DebugLog?

    let api: any APIClientProtocol
    private let preferences: Preferences
    let now: @Sendable () -> Date
    /// Per running task: the run id, its workstream and when a step was last written there.
    @ObservationIgnored private var contexts: [String: RunContext] = [:]
    /// Per running task: the stream's task ("Stop" cancels it) and the runs the user stopped.
    @ObservationIgnored private var streams: [String: Task<(ChatMessage?, RunFailure?), Never>] = [:]
    @ObservationIgnored private var stopRequests: Set<String> = []

    private struct RunContext {
        let runID: String
        var ref: WorkstreamRef?
        var lastStepEventAt: Date?
        var lastStepEvent: String?
        var stepEvents = 0
    }

    /// Marks an agent run's chat session in its backend title, so every device can tell runs from
    /// the main chat (the local list of run sessions does not survive a sign-out or a new phone).
    public static let sessionTitlePrefix = "✦ "
    /// The app id a run's chat session is created with. The backend's "current" main chat is its
    /// newest session without an app (`database/chat.py` `get_chat_session`): voice questions,
    /// integration messages and greetings land there, so a run must never be one. No app has this
    /// id, so the backend answers the run as plain Omi (with every tool), and history stays
    /// scoped to the session (`utils/chat_session_target.py`).
    public nonisolated static let runSessionAppID = "omi-agent-run"

    /// Event summary that marks a failed run (`RunFailure.eventSummary` appends the reason).
    public nonisolated static let failedSummary = "Omi could not finish this task."
    /// Event summary of a run's start; carries the chat session as evidence.
    public nonisolated static let startedSummary = "Omi started working on this task."
    /// A run with no progress for this long and no live stream has stopped.
    public static let staleAfter: TimeInterval = 10 * 60
    /// Think steps are written to the workstream at most this often (other devices see progress).
    static let stepEventInterval: TimeInterval = 15
    /// The backend's keep-alive `think:` frames (`agentic.py` `AGENT_STREAM_SETUP_PROGRESS`,
    /// `AGENT_STREAM_PROGRESS_HEARTBEAT`) and its safety-guard warning: never a step.
    public nonisolated static let heartbeats: Set<String> = [
        "Preparing response…", "Preparing response...", "Still working…", "Still working...",
    ]

    public init(api: any APIClientProtocol, preferences: Preferences, now: @escaping @Sendable () -> Date = { .now }) {
        self.api = api
        self.preferences = preferences
        self.now = now
        openedRunIDs = Set(preferences.strings(.openedAgentRuns))
    }

    /// A keep-alive or warning frame, not something Omi did.
    public nonisolated static func isHeartbeat(_ step: String) -> Bool {
        let step = step.trimmingCharacters(in: .whitespacesAndNewlines)
        return heartbeats.contains(step) || step.hasPrefix("⚠️")
    }

    public var activeRuns: [Run] {
        runs.values.filter(\.isActive).sorted { $0.startedAt > $1.startedAt }
    }

    /// Omi's open questions.
    public var pendingDeviceTools: [PendingDeviceTool] {
        deviceToolRequests.values.sorted { $0.taskTitle < $1.taskTitle }
    }

    /// Finished hand-overs stay on Home this long; the task keeps the result after that.
    static let finishedRunVisibility: TimeInterval = 48 * 3600

    /// What Omi is doing or did: this session's runs plus earlier ones recovered from the
    /// backend (tasks carry the workstream id), so the list survives an app restart. Finished
    /// runs drop off after two days; running and failed ones stay until dealt with. A recovered
    /// run that has not moved for `staleAfter` is stopped, not "working" forever.
    public func workItems(tasks: [ActionItem]) -> [Run] {
        var items = runs
        for task in tasks where items[task.id] == nil && !task.isCompleted {
            guard let id = task.workstreamID, let workstream = workstreams[id] else { continue }
            items[task.id] = recoveredRun(task, workstream: workstream, history: histories[task.id])
        }
        let cutoff = now().addingTimeInterval(-Self.finishedRunVisibility)
        return items.values
            .filter { run in
                guard case .done = run.state else { return true }
                return run.startedAt > cutoff
            }
            .sorted { $0.startedAt > $1.startedAt }
    }

    public var recentRuns: [Run] {
        runs.values.sorted { $0.startedAt > $1.startedAt }
    }

    /// The trust ladder for v1: the agent prepares anything that would reach other people and
    /// leaves the sending to the user.
    static func prompt(for task: ActionItem, conversationTitle: String?) -> String {
        var lines = ["Please take care of this task for me: \"\(task.description)\"."]
        if let conversationTitle, !conversationTitle.isEmpty {
            lines.append("It came up in my conversation \"\(conversationTitle)\".")
        }
        if let due = task.dueAt {
            lines.append("It is due \(due.formatted(date: .complete, time: .shortened)).")
        }
        lines.append(
            "Use your tools to do as much of it as you can: look things up, check my calendar and past conversations, "
                + "and prepare drafts. Do not send messages or invite other people; prepare those as drafts for me to send. "
                + "If a tool is unavailable or fails twice, stop using it and work with what you have. "
                + "Never run the same search twice; after three searches that add nothing new, stop searching. "
                + "Link every fact you took from the web to its source as a Markdown link. "
                + "Finish with a short summary of what you did and what is left for me."
        )
        return lines.joined(separator: " ")
    }

    /// Asked when a stopped run continues in its own thread.
    static func resumePrompt(for task: ActionItem, conversationTitle: String?) -> String {
        prompt(for: task, conversationTitle: conversationTitle)
            + " You started on this earlier in this conversation and stopped before finishing: "
            + "pick up where you left off instead of starting over."
    }

    /// The user saw this task's finished run (the hand-over sheet showed its result).
    public func markOpened(_ taskID: String) {
        guard openedRunIDs.insert(taskID).inserted else { return }
        preferences.append(taskID, to: .openedAgentRuns)
    }

    public func takeOver(_ task: ActionItem, conversationTitle: String?) async {
        await run(task, conversationTitle: conversationTitle, resumeSessionID: nil)
    }

    /// "Tap to resume": a stopped or failed run continues in the same workstream and, when the
    /// run's thread is known, in that thread (else it starts fresh).
    public func resume(_ task: ActionItem, conversationTitle: String?) async {
        if runs[task.id]?.isActive == true { return }
        let sessionID = runs[task.id]?.sessionID ?? histories[task.id]?.sessionID
        runs[task.id] = nil
        await run(task, conversationTitle: conversationTitle, resumeSessionID: sessionID)
    }

    private func run(_ task: ActionItem, conversationTitle: String?, resumeSessionID: String?) async {
        if runs[task.id]?.isActive == true { return }
        // A new run of the same task is news again.
        if openedRunIDs.remove(task.id) != nil {
            preferences.set(preferences.strings(.openedAgentRuns).filter { $0 != task.id }, for: .openedAgentRuns)
        }
        let runID = UUID().uuidString.lowercased()
        runs[task.id] = Run(
            id: task.id, taskTitle: task.description, state: .starting, steps: [], partialText: "", startedAt: now(),
            sessionID: resumeSessionID, lastProgressAt: now()
        )
        contexts[task.id] = RunContext(runID: runID)

        // A thread of its own per run, under the run app id, so the main chat stays the user's.
        var sessionID = resumeSessionID
        if sessionID == nil {
            sessionID = try? await api.createChatSession(title: Self.sessionTitlePrefix + task.description, appID: Self.runSessionAppID)
            if let sessionID { preferences.append(sessionID, to: .agentChatSessionIDs) }
        }
        runs[task.id]?.sessionID = sessionID

        let workstream = await openWorkstream(for: task, runID: runID, sessionID: sessionID)
        runs[task.id]?.workstreamID = workstream?.id
        contexts[task.id]?.ref = workstream
        let prompt = resumeSessionID == nil
            ? Self.prompt(for: task, conversationTitle: conversationTitle)
            : Self.resumePrompt(for: task, conversationTitle: conversationTitle)
        let outcome = await work(on: task, prompt: prompt, sessionID: sessionID)
        deviceToolRequests[task.id] = nil
        await record(outcome, in: workstream, runID: runID)
        contexts[task.id] = nil
        if case .success = outcome { onRunEnded?(task, true) } else { onRunEnded?(task, false) }
    }

    /// Opens (or reuses) the task's workstream and notes the start, with the run's thread as
    /// evidence (a restart finds it there). Nil if bookkeeping fails; the work itself still runs.
    private func openWorkstream(for task: ActionItem, runID: String, sessionID: String?) async -> WorkstreamRef? {
        do {
            let generation = try await api.accountGeneration()
            let id = try await api.startWork(onTask: task.id, title: task.description, generation: generation)
            let ref = WorkstreamRef(id: id, generation: generation)
            let evidence = sessionID.map { [["kind": "external", "id": "chat_session:\($0)", "scope": "canonical"]] } ?? []
            try await api.recordWorkstreamEvent(
                ref, kind: "agent_update", summary: Self.startedSummary, evidence: evidence, idempotencyKey: "run:\(runID):start"
            )
            return ref
        } catch {
            return nil
        }
    }

    /// Streams the task through the chat agent. The typed reason of a failure survives: an
    /// `error:` frame, a canned answer, a thrown error and an empty stream each keep their own.
    private func work(on task: ActionItem, prompt: String, sessionID: String?) async -> Result<ChatMessage, RunFailureBox> {
        // Its own task, so "Stop" can end it (`stop(_:)`) while it waits for the next frame.
        let consumer = Task { await consume(task, prompt: prompt, sessionID: sessionID) }
        streams[task.id] = consumer
        var (finalMessage, failure) = await consumer.value
        streams[task.id] = nil
        if stopRequests.remove(task.id) != nil {
            finalMessage = nil
            failure = .stopped
        }
        if failure == nil {
            if let finalMessage, let canned = RunFailure.from(answer: finalMessage.text) {
                failure = canned
                log?.add(.warning, "agent", "run \(task.id) canned answer: \(finalMessage.text)")
            } else if finalMessage?.text.isEmpty != false {
                failure = .noAnswer
            }
        }
        runs[task.id]?.finishedAt = now()
        if let failure {
            runs[task.id]?.state = .failed(failure.rawValue)
            return .failure(RunFailureBox(failure))
        }
        guard let finalMessage else { return .failure(RunFailureBox(.noAnswer)) }
        runs[task.id]?.state = .done(result: finalMessage.text)
        return .success(finalMessage)
    }

    private func consume(_ task: ActionItem, prompt: String, sessionID: String?) async -> (ChatMessage?, RunFailure?) {
        var finalMessage: ChatMessage?
        var failure: RunFailure?
        do {
            let context = ChatContext(kind: .task, id: task.id, title: task.description)
            let tools = DeviceToolResolver.declaredTools(deviceTools)
            for try await event in api.streamAgent(prompt, context: context, sessionID: sessionID, deviceTools: tools) {
                if Task.isCancelled { break }
                switch event {
                case let .done(message):
                    finalMessage = message
                case let .failed(reason):
                    // The first reason wins; the canned answer that may follow says less.
                    if failure == nil { failure = RunFailure.from(streamError: reason) }
                    log?.add(.error, "agent", "run \(task.id) error frame: \(reason)")
                case let .deviceTool(request):
                    await ask(request, for: task)
                case .step, .delta, .memorySaved:
                    await apply(event, to: task.id)
                }
            }
        } catch {
            if failure == nil { failure = RunFailure.from(error: error) }
            log?.add(.error, "agent", "run \(task.id) stream: \(error)")
        }
        return (finalMessage, failure)
    }

    /// "Stop" on a running hand-over: the stream ends, the run reads as stopped (it can resume
    /// in its thread), and a waiting "Omi asks" goes away.
    public func stop(_ taskID: String) {
        guard runs[taskID]?.isActive == true, let stream = streams[taskID] else { return }
        log?.add(.info, "agent", "run \(taskID) stopped by the user")
        stopRequests.insert(taskID)
        deviceToolRequests[taskID] = nil
        stream.cancel()
    }

    private func apply(_ event: ChatStreamEvent, to taskID: String) async {
        switch event {
        case let .step(step):
            runs[taskID]?.lastProgressAt = now()
            // Keep-alive frames say nothing about the work.
            guard !Self.isHeartbeat(step) else {
                if case .starting = runs[taskID]?.state { runs[taskID]?.state = .working(step: "") }
                return
            }
            runs[taskID]?.steps.append(step)
            runs[taskID]?.state = .working(step: step)
            await recordStep(step, for: taskID)
        case let .delta(text):
            runs[taskID]?.partialText += text
            runs[taskID]?.lastProgressAt = now()
            if case .starting = runs[taskID]?.state { runs[taskID]?.state = .working(step: "") }
        case .done, .memorySaved, .failed, .deviceTool:
            break
        }
    }

    /// Writes a think step to the workstream (throttled, no repeats), so other devices see
    /// what Omi is doing and a restart can show the steps.
    private func recordStep(_ step: String, for taskID: String) async {
        guard var context = contexts[taskID], let ref = context.ref else { return }
        let text = step.trimmingCharacters(in: .whitespacesAndNewlines)
        guard Self.isStepEvent(text), text != context.lastStepEvent else { return }
        if let last = context.lastStepEventAt, now().timeIntervalSince(last) < Self.stepEventInterval { return }
        context.lastStepEventAt = now()
        context.lastStepEvent = text
        context.stepEvents += 1
        contexts[taskID] = context
        _ = try? await api.recordWorkstreamEvent(
            ref, kind: "agent_update", summary: text, evidence: [], idempotencyKey: "run:\(context.runID):step:\(context.stepEvents)"
        )
    }

    /// Writes the outcome to the workstream: the answer as an artifact and the workstream
    /// completed, or a failure event (with its reason) that leaves it open.
    private func record(_ outcome: Result<ChatMessage, RunFailureBox>, in ref: WorkstreamRef?, runID: String) async {
        guard let ref else { return }
        let message: ChatMessage
        switch outcome {
        case let .failure(box):
            _ = try? await api.recordWorkstreamEvent(
                ref, kind: "agent_update", summary: box.failure.eventSummary, evidence: [], idempotencyKey: "run:\(runID):failed"
            )
            return
        case let .success(answer):
            message = answer
        }
        do {
            let eventID = try await api.recordWorkstreamEvent(
                ref, kind: "agent_update", summary: "Done: \(message.text)",
                evidence: [["kind": "chat_message", "id": message.id, "scope": "canonical"]],
                idempotencyKey: "run:\(runID):done"
            )
            try await api.recordResultArtifact(
                ref, messageID: message.id, resultText: message.text, evidenceEventID: eventID, runID: runID
            )
            try await api.updateWorkstream(ref, status: .completed, summary: message.text)
        } catch {
            // The answer is shown either way; the record catches up on the next run.
        }
    }

    public func dismiss(_ taskID: String) {
        runs[taskID] = nil
    }
}

/// Carries a `RunFailure` through `Result`.
struct RunFailureBox: Error {
    let failure: RunFailure

    init(_ failure: RunFailure) {
        self.failure = failure
    }
}
