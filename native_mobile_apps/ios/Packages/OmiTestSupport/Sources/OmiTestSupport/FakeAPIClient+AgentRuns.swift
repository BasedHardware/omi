import Foundation
import OmiCore
import OmiNetwork

/// Backend state for agent runs: recommendation feedback, scripted agent streams with device
/// tools, the results posted for them, full workstream event logs and run threads.
public final class FakeAgentRuns: @unchecked Sendable {
    /// `<intervention id>=<decision>`, one per feedback sent; decided ones leave `whatMattersNow`.
    public internal(set) var recommendationFeedback: [String] = []
    public var failsRecommendationFeedback = false
    /// The session and declared tools of each `streamAgent` call.
    public internal(set) var agentRequests: [(sessionID: String?, deviceTools: [String])] = []
    /// Replaces the default steps-and-reply stream; after a `.deviceTool` event it waits (like
    /// the backend) until that call's result is posted, at most `deviceToolWait`.
    public var agentScript: [ChatStreamEvent]?
    public var deviceToolWait: Duration = .seconds(2)
    public internal(set) var deviceToolResults: [String: DeviceToolResult] = [:]
    public var failsDeviceToolResult = false
    /// Full event logs by workstream id (`workstreamEvents`); falls back to `workstreamsByID`.
    public var eventLogs: [String: [Workstream.Event]] = [:]
    /// The evidence refs and idempotency keys of each recorded event, in order.
    public internal(set) var eventEvidence: [[[String: String]]] = []
    public internal(set) var eventKeys: [String] = []
    /// Stored threads by chat session id (agent runs reload theirs after a restart).
    public var sessionHistories: [String: [ChatMessage]] = [:]

    public init() {}
}

public extension FakeAPIClient {
    var recommendationFeedback: [String] {
        lock.withLock { agentRuns.recommendationFeedback }
    }

    var failsRecommendationFeedback: Bool {
        get { agentRuns.failsRecommendationFeedback }
        set { agentRuns.failsRecommendationFeedback = newValue }
    }

    var agentRequests: [(sessionID: String?, deviceTools: [String])] {
        lock.withLock { agentRuns.agentRequests }
    }

    var agentScript: [ChatStreamEvent]? {
        get { agentRuns.agentScript }
        set { agentRuns.agentScript = newValue }
    }

    var deviceToolWait: Duration {
        get { agentRuns.deviceToolWait }
        set { agentRuns.deviceToolWait = newValue }
    }

    var deviceToolResults: [String: DeviceToolResult] {
        lock.withLock { agentRuns.deviceToolResults }
    }

    var failsDeviceToolResult: Bool {
        get { agentRuns.failsDeviceToolResult }
        set { agentRuns.failsDeviceToolResult = newValue }
    }

    var eventLogs: [String: [Workstream.Event]] {
        get { agentRuns.eventLogs }
        set { agentRuns.eventLogs = newValue }
    }

    var eventEvidence: [[[String: String]]] {
        lock.withLock { agentRuns.eventEvidence }
    }

    var eventKeys: [String] {
        lock.withLock { agentRuns.eventKeys }
    }

    var sessionHistories: [String: [ChatMessage]] {
        get { agentRuns.sessionHistories }
        set { agentRuns.sessionHistories = newValue }
    }

    func sendRecommendationFeedback(_ recommendation: Recommendation, decision: Recommendation.Decision, generation _: Int) async throws {
        if agentRuns.failsRecommendationFeedback { throw APIError.http(status: 409, body: "generation") }
        lock.withLock { agentRuns.recommendationFeedback.append("\(recommendation.id)=\(decision.rawValue)") }
    }

    func workstreamEvents(_ workstreamID: String, afterSequence: Int) async throws -> [Workstream.Event] {
        let events = agentRuns.eventLogs[workstreamID] ?? workstreamsByID[workstreamID]?.events ?? []
        return events.filter { $0.sequence > afterSequence }
    }

    func streamAgent(
        _ text: String, context: ChatContext?, sessionID: String?, deviceTools: [String]
    ) -> AsyncThrowingStream<ChatStreamEvent, any Error> {
        lock.withLock { agentRuns.agentRequests.append((sessionID, deviceTools)) }
        guard let script = agentRuns.agentScript else { return sendMessage(text, context: context, sessionID: sessionID) }
        let wait = agentRuns.deviceToolWait
        return AsyncThrowingStream { continuation in
            let task = Task {
                for event in script {
                    continuation.yield(event)
                    guard case let .deviceTool(request) = event else { continue }
                    let deadline = ContinuousClock.now + wait
                    while lock.withLock({ agentRuns.deviceToolResults[request.id] }) == nil, ContinuousClock.now < deadline {
                        try? await Task.sleep(for: .milliseconds(5))
                    }
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    func sendDeviceToolResult(callID: String, result: DeviceToolResult) async throws {
        if agentRuns.failsDeviceToolResult { throw APIError.http(status: 404, body: "No such in-flight device tool call") }
        lock.withLock { agentRuns.deviceToolResults[callID] = result }
    }
}
