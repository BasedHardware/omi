import Foundation
import OmiCore
import OmiNetwork

/// Runs from earlier sessions, rebuilt from the backend: the workstream, its full event log
/// (the steps) and the run's own chat thread; quiet ones count as stopped after `staleAfter`.
public extension AgentStore {
    /// Fetches the workstreams behind tasks Omi worked on before (they carry a workstream id),
    /// and for unfinished ones what they did so far (steps and thread), so a restart does not
    /// show an empty "working" forever.
    func loadWorkstreams(for tasks: [ActionItem]) async {
        for id in Set(tasks.compactMap(\.workstreamID)) where workstreams[id] == nil {
            if let workstream = try? await api.workstream(id) { workstreams[id] = workstream }
        }
        for task in tasks where !task.isCompleted && runs[task.id] == nil && histories[task.id] == nil {
            guard let id = task.workstreamID, let workstream = workstreams[id], workstream.status != .completed else { continue }
            await loadHistory(for: task)
        }
    }

    /// An earlier run's steps (its workstream events) and its thread's latest answer text.
    func loadHistory(for task: ActionItem) async {
        guard let workstreamID = task.workstreamID else { return }
        let events = await (try? api.workstreamEvents(workstreamID, afterSequence: 0)) ?? workstreams[workstreamID]?.events ?? []
        var sessionID = events.reversed().flatMap(\.evidence)
            .first { $0.kind == "external" && $0.id.hasPrefix("chat_session:") }
            .map { String($0.id.dropFirst("chat_session:".count)) }
        if sessionID == nil {
            let title = Self.sessionTitlePrefix + task.description
            let runSessions = await (try? api.chatSessions(appID: Self.runSessionAppID)) ?? []
            // Runs before the run app id were sessions without an app.
            let legacy = runSessions.contains { $0.title == title } ? [] : await (try? api.chatSessions()) ?? []
            sessionID = (runSessions + legacy).first { $0.title == title }?.id
        }
        var partialText = ""
        if let sessionID, let messages = try? await api.chatHistory(limit: 20, sessionID: sessionID) {
            partialText = messages.last { $0.sender == .omi && RunFailure.from(answer: $0.text) == nil }?.text ?? ""
        }
        histories[task.id] = RunHistory(
            events: events, steps: Self.steps(in: events), partialText: partialText, sessionID: sessionID
        )
    }

    internal func recoveredRun(_ task: ActionItem, workstream: Workstream, history: RunHistory?) -> Run {
        let events = (history?.events.isEmpty == false ? history?.events : nil) ?? workstream.events
        let lastEvent = events.last
        let lastAgentEvent = events.last { $0.kind == "agent_update" }
        let result = workstream.summary ?? lastEvent?.summary ?? ""
        let lastActivity = [workstream.lastActivityAt, lastEvent?.createdAt].compactMap(\.self).max()
        let state: RunState = if workstream.status == .completed {
            if let failure = RunFailure.from(answer: result) { .failed(failure.rawValue) } else { .done(result: result) }
        } else if let failure = lastAgentEvent.flatMap({ RunFailure.from(event: $0.summary) }) {
            .failed(failure.rawValue)
        } else if Self.isStale(lastActivity, now: now()) {
            .failed(RunFailure.stopped.rawValue)
        } else {
            .working(step: lastAgentEvent.map(\.summary).flatMap { Self.isStepEvent($0) ? $0 : nil } ?? "")
        }
        return Run(
            id: task.id, taskTitle: task.description, workstreamID: workstream.id, state: state,
            steps: history?.steps ?? Self.steps(in: events),
            partialText: history.flatMap { $0.partialText.isEmpty ? nil : $0.partialText }
                ?? (workstream.status == .completed ? Self.writtenBeforeFailure(result) : ""),
            startedAt: lastEvent?.createdAt ?? .distantPast, sessionID: history?.sessionID, lastProgressAt: lastActivity
        )
    }

    /// The agent's own steps among a workstream's events (not the system, artifact or marker events).
    static func steps(in events: [Workstream.Event]) -> [String] {
        events.filter { $0.kind == "agent_update" }.map(\.summary).filter(isStepEvent)
    }

    /// What the agent wrote before a canned failure was appended ("I'll gather context … I'm
    /// having trouble …"); empty for a real answer or a bare failure.
    static func writtenBeforeFailure(_ answer: String) -> String {
        guard RunFailure.from(answer: answer) != nil else { return "" }
        let canned = ChatStreamEvent.serviceFailureTexts + [RunFailure.refusalText, RunFailure.emptyAnswerText]
        var text = answer.trimmingCharacters(in: .whitespacesAndNewlines)
        for suffix in canned where text.hasSuffix(suffix) {
            text = String(text.dropLast(suffix.count))
        }
        return text.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// No sign of life for `staleAfter` (no known time at all counts as stale).
    internal static func isStale(_ lastActivity: Date?, now: Date) -> Bool {
        guard let lastActivity else { return true }
        return now.timeIntervalSince(lastActivity) > staleAfter
    }

    /// A workstream event or stream frame that is one of the agent's steps (not the start, a
    /// heartbeat, the result or a failure).
    nonisolated static func isStepEvent(_ summary: String) -> Bool {
        let summary = summary.trimmingCharacters(in: .whitespacesAndNewlines)
        return !summary.isEmpty && summary != startedSummary && summary != "Work initiated by the user" && !isHeartbeat(summary)
            && !summary.hasPrefix("Done: ") && RunFailure.from(event: summary) == nil
    }
}
