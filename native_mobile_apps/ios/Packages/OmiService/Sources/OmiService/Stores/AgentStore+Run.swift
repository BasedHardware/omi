import Foundation
import OmiCore

public extension AgentStore {
    struct Run: Identifiable, Equatable, Sendable {
        public let id: String // task id
        public let taskTitle: String
        public var workstreamID: String?
        public var state: RunState
        public var steps: [String]
        public var partialText: String
        public let startedAt: Date
        /// The run's own chat thread (resume continues in it).
        public var sessionID: String?
        /// When the work last moved (a step, text, an event on the workstream).
        public var lastProgressAt: Date?
        /// When this session's run ended (nil while running, and for runs recovered from the backend).
        public var finishedAt: Date?

        public init(
            id: String, taskTitle: String, workstreamID: String? = nil, state: RunState, steps: [String], partialText: String,
            startedAt: Date, sessionID: String? = nil, lastProgressAt: Date? = nil
        ) {
            self.id = id
            self.taskTitle = taskTitle
            self.workstreamID = workstreamID
            self.state = state
            self.steps = steps
            self.partialText = partialText
            self.startedAt = startedAt
            self.sessionID = sessionID
            self.lastProgressAt = lastProgressAt
        }

        public var isActive: Bool {
            switch state {
            case .starting, .working: true
            case .done, .failed: false
            }
        }

        /// Why the run stopped, when it did.
        public var failure: RunFailure? {
            guard case let .failed(code) = state else { return nil }
            return RunFailure(rawValue: code) ?? RunFailure.from(event: code) ?? .couldNotFinish
        }

        /// Died without a word (no progress for `staleAfter`, no live stream): "Tap to resume".
        public var isStopped: Bool {
            failure == .stopped
        }
    }

    /// What an earlier run left on the backend: its steps (workstream events) and its thread.
    struct RunHistory: Equatable, Sendable {
        public let events: [Workstream.Event]
        public let steps: [String]
        public let partialText: String
        public let sessionID: String?
    }
}
