import Foundation
import OmiCore
import OmiNetwork

/// Why an agent run stopped, as a short code the app words in plain language (`AgentWording`).
/// The raw backend reason goes to the debug log; the code is what the run state and the
/// workstream carry (`failedSummary [code]`), so another device words it the same way.
public enum RunFailure: String, CaseIterable, Sendable {
    /// The plan's chat allowance is used up.
    case quotaExceeded = "quota_exceeded"
    /// The answer took longer than the backend allows.
    case timeout
    /// The agent went round in circles (the safety guard's tool-call, loop or context limits).
    case toolLoop = "tool_loop"
    /// The backend failed.
    case serverError = "server_error"
    /// The phone had no connection.
    case offline
    /// No progress for a long time and no live stream: the run died with the app.
    case stopped
    /// The stream ended without an answer.
    case noAnswer = "no_answer"
    /// The model declined the request (retrying the same thing would be declined again).
    case refused
    /// The task needs an app that is not connected (calendar, mail …).
    case notConnected = "not_connected"
    /// Anything else (also what older runs recorded).
    case couldNotFinish = "could_not_finish"

    /// The agent's other fixed answers (`agentic.py` `AGENT_REFUSAL_MESSAGE`, `AGENT_EMPTY_ANSWER_MESSAGE`).
    static let refusalText = "I can't help with that one. Try asking me something else."
    static let emptyAnswerText = "I wasn't able to put a response together for that. Please try again."

    /// A typed `error:` code (`X-Omi-Chat-Failure-Protocol`) or a plain-text `error:` frame.
    public static func from(streamError text: String) -> RunFailure {
        switch text.trimmingCharacters(in: .whitespacesAndNewlines) {
        case "quota_exceeded": .quotaExceeded
        case "timeout", "idle_timeout", "setup_timeout": .timeout
        case "server_error": .serverError
        case "offline": .offline
        default: from(answer: text) ?? (mentionsMissingConnection(text) ? .notConnected : .couldNotFinish)
        }
    }

    /// The canned texts the agent streams as an answer (`ChatStreamEvent.serviceFailureTexts`),
    /// alone or appended to what it wrote so far (the safety guard adds "I seem to be stuck …"
    /// after the partial answer); nil for a real answer.
    public static func from(answer text: String) -> RunFailure? {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.hasSuffix(refusalText) { return .refused }
        if trimmed.hasSuffix(emptyAnswerText) { return .noAnswer }
        guard let index = ChatStreamEvent.serviceFailureTexts.firstIndex(where: { trimmed.hasSuffix($0) }) else { return nil }
        switch index {
        case 0, 1: return .serverError
        case 2: return .timeout
        default: return .toolLoop
        }
    }

    /// A thrown stream or request error.
    public static func from(error: any Error) -> RunFailure {
        if let urlError = error as? URLError {
            switch urlError.code {
            case .timedOut: return .timeout
            case .notConnectedToInternet, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost, .dataNotAllowed: return .offline
            default: return .couldNotFinish
            }
        }
        switch error as? APIError {
        case .http(status: 402, body: _): return .quotaExceeded
        case let .http(status, _) where status >= 500: return .serverError
        case .transport: return .offline
        default: return .couldNotFinish
        }
    }

    /// Reads the code back from a workstream event (`"<failedSummary> [timeout]"`); the bare
    /// marker older runs wrote reads as `couldNotFinish`. Nil for other events.
    public static func from(event summary: String) -> RunFailure? {
        let summary = summary.trimmingCharacters(in: .whitespacesAndNewlines)
        guard summary.hasPrefix(AgentStore.failedSummary) else { return nil }
        let rest = summary.dropFirst(AgentStore.failedSummary.count).trimmingCharacters(in: CharacterSet(charactersIn: " []"))
        return RunFailure(rawValue: rest) ?? .couldNotFinish
    }

    /// The event summary that records this failure.
    public var eventSummary: String {
        "\(AgentStore.failedSummary) [\(rawValue)]"
    }

    /// Worth trying again as it is (not a used-up plan, not a refusal).
    public var canRetry: Bool {
        self != .quotaExceeded && self != .refused
    }

    private static func mentionsMissingConnection(_ text: String) -> Bool {
        let lowered = text.lowercased()
        return ["not connected", "isn't connected", "aren't connected", "no integration", "connect your"].contains { lowered.contains($0) }
    }
}
