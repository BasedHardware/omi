import Foundation
import OmiCore
import OmiDesign
import OmiService
import SwiftUI

/// User-facing words for agent states whose stored text is a fixed English marker.
public enum AgentWording {
    /// Why a run stopped, in plain words: the state carries a `RunFailure` code (older runs the
    /// bare English marker); free text from elsewhere stays as it is.
    public static func failure(_ message: String) -> String {
        if let failure = RunFailure(rawValue: message) ?? RunFailure.from(event: message) { return words(failure) }
        return message
    }

    public static func words(_ failure: RunFailure) -> String {
        switch failure {
        case .quotaExceeded: L("nativeRunFailedQuota")
        case .timeout: L("nativeRunFailedTimeout")
        case .toolLoop: L("nativeRunFailedStuck")
        case .serverError: L("nativeRunFailedServer")
        case .offline: L("nativeRunFailedOffline")
        case .stopped: L("nativeRunFailedStopped")
        case .noAnswer: L("nativeRunFailedNoAnswer")
        case .refused: L("nativeRunFailedRefused")
        case .notConnected: L("nativeRunFailedNotConnected")
        case .couldNotFinish: L("nativeOmiCouldNotFinish")
        }
    }

    /// The button that deals with it: resume a stopped run, try again otherwise; nil when trying
    /// again cannot help (a used-up plan, a refusal).
    public static func action(_ failure: RunFailure) -> String? {
        guard failure.canRetry else { return nil }
        return failure == .stopped ? L("nativeRunResume") : L("tryAgain")
    }

    /// A run's current step as a person reads it, or nil when it says nothing (a heartbeat, a
    /// marker, machine text). Trailing dots go ("Searching the web…" → "Searching the web").
    public static func step(_ line: String) -> String? {
        guard !isBoilerplate(line) else { return nil }
        var text = line.trimmingCharacters(in: .whitespacesAndNewlines)
        while text.hasSuffix(".") || text.hasSuffix("…") {
            text.removeLast()
        }
        return text.isEmpty ? nil : text
    }

    /// Lines that mean nothing to a person: the app's start and failure markers, the backend's
    /// opening event, and machine text (tool names, ids, "started"): one word, snake_case,
    /// "Calling search_web".
    static func isBoilerplate(_ line: String) -> Bool {
        let line = line.trimmingCharacters(in: .whitespacesAndNewlines)
        if line.isEmpty || boilerplate.contains(line) || AgentStore.isHeartbeat(line) || RunFailure.from(event: line) != nil { return true }
        let words = line.split(whereSeparator: \.isWhitespace)
        if words.count < 2 { return true }
        if words.contains(where: { $0.contains("_") || $0.contains("()") }) { return true }
        let lowered = line.lowercased()
        return machinePrefixes.contains { lowered.hasPrefix($0) }
    }

    private static let boilerplate: Set = [AgentStore.failedSummary, "Omi started working on this task.", "Work initiated by the user"]
    private static let machinePrefixes = ["calling ", "tool:", "tool call", "running tool", "work initiated", "started"]
}

/// Where Omi stands on a task, shown on the task wherever it appears: what it is doing right now
/// (its current step and when that was), what it finished, or why it stopped, in its own words.
public struct AgentTaskStatus: Equatable, Sendable {
    public enum Kind: Equatable, Sendable { case working, finished, failed }

    public let kind: Kind
    /// The current step, or the reason it stopped; `nil` when Omi has not said.
    public let detail: String?
    /// When the work last moved (a running step, the last event).
    public let updatedAt: Date?
    /// Running in this session right now (the glyph may breathe); a recovered run may be stale.
    public let isLive: Bool

    public init(kind: Kind, detail: String? = nil, updatedAt: Date? = nil, isLive: Bool = false) {
        self.kind = kind
        self.detail = detail
        self.updatedAt = updatedAt
        self.isLive = isLive
    }

    public static let working = AgentTaskStatus(kind: .working, isLive: true)
    public static let finished = AgentTaskStatus(kind: .finished)
    public static let failed = AgentTaskStatus(kind: .failed)

    @MainActor
    public init?(task: ActionItem, agent: AgentStore) {
        let workstream = task.workstreamID.flatMap { agent.workstreams[$0] }
        // What the workstream says happened, newest first, without the start and failure markers.
        let events = (workstream?.events ?? []).reversed().filter { !AgentWording.isBoilerplate($0.summary) }
        guard let run = agent.runs[task.id] ?? agent.workItems(tasks: [task]).first else {
            // A workstream not loaded yet still says Omi has it.
            guard task.workstreamID != nil else { return nil }
            self.init(kind: .working)
            return
        }
        let live = agent.runs[task.id] != nil
        let lastStep = run.steps.last { !AgentWording.isBoilerplate($0) } ?? events.first?.summary
        switch run.state {
        case .starting:
            self.init(kind: .working, updatedAt: run.startedAt, isLive: live)
        case let .working(step):
            let step = AgentWording.isBoilerplate(step) ? lastStep : step
            self.init(kind: .working, detail: step, updatedAt: live ? run.startedAt : events.first?.createdAt, isLive: live)
        case .done:
            self.init(kind: .finished, updatedAt: events.first?.createdAt)
        case let .failed(message):
            // The run's reason in plain words ("Omi got stuck and stopped"), else its own words, else
            // where it stopped (a real step, never a heartbeat like "Preparing response").
            if let failure = run.failure, failure != .couldNotFinish {
                self.init(kind: .failed, detail: AgentWording.words(failure))
            } else if !AgentWording.isBoilerplate(message), RunFailure(rawValue: message) == nil {
                self.init(kind: .failed, detail: message)
            } else if let lastStep {
                self.init(kind: .failed, detail: L("nativeOmiStoppedAt", lastStep))
            } else {
                self.init(kind: .failed)
            }
        }
    }

    /// The line on the task: the step or reason when known, else a short default.
    public var title: String {
        if let detail, !detail.isEmpty { return detail }
        switch kind {
        case .working: return L("nativeOmiOnIt")
        case .finished: return L("nativeOmiFinished")
        case .failed: return L("nativeOmiStoppedTapToSee")
        }
    }

    var symbol: String {
        switch kind {
        case .working: "sparkles"
        case .finished: "checkmark.circle"
        case .failed: "exclamationmark.triangle"
        }
    }

    var tint: Color {
        switch kind {
        case .working: DS.Palette.agent
        case .finished: DS.Palette.success
        case .failed: DS.Palette.warning
        }
    }

    /// "2 min ago" while Omi works (a finished or stopped task needs no clock).
    func age(now: Date = .now) -> String? {
        guard kind == .working, let updatedAt, updatedAt > .distantPast, now.timeIntervalSince(updatedAt) > 30 else { return nil }
        return updatedAt.formatted(.relative(presentation: .named, unitsStyle: .abbreviated))
    }
}
