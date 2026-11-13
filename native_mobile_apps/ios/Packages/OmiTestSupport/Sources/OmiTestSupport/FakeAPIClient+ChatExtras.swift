import Foundation
import OmiCore
import OmiNetwork

/// What the chat's extra endpoints received, and how they answer.
public final class FakeChatExtras: @unchecked Sendable {
    public struct Rating: Sendable {
        public let id: String
        public let value: Int
        public let reason: String?
    }

    public var sentFileIDs: [[String]] = []
    /// The `device_tools` each send declared.
    public var sentDeviceTools: [[String]] = []
    /// The questions sent, in order.
    public var sentTexts: [String] = []
    /// When set, every send streams exactly these frames (device tool calls, steps, a `done:`).
    /// After a device tool frame it waits for that call's result, as the backend does.
    public var script: [ChatStreamEvent]?
    /// The task list once a scripted turn ends (what the agent's task tools did server-side).
    public var tasksAfterTurn: [ActionItem]?
    /// Frames queued by a transcribed voice question: the next send streams them.
    var queuedVoiceReply: [ChatStreamEvent]?
    public var ratings: [Rating] = []
    public var clearedSessions: [String] = []
    public var uploads: [String] = []
    public var speech: [(text: String, voiceID: String?)] = []
    /// Thrown by the matching endpoint.
    public var ratingError: APIError?
    public var uploadError: APIError?
    public var speechError: APIError?
    /// Uploads take this long (to test sending while one is still on its way).
    public var uploadDelay: Duration?
    /// The stream fails with this instead of answering.
    public var streamError: (any Error & Sendable)?
    /// The stream sends a typed `error:` frame with this code, then a `done:` with `doneText`.
    public var streamErrorCode: String?
    /// The stream never answers (a backend that hangs), until the caller cancels.
    public var hangs = false
    public var doneText: String?
    public var followUp: String?
    public var chart: ChatChart?
    public var clearGreeting = ChatMessage(
        id: "greeting-2", text: "Fresh start. What's on your mind?", sender: .omi, createdAt: Fixtures.now
    )

    init() {}
}

public extension FakeAPIClient {
    func sendChatMessage(
        _ text: String, fileIDs: [String], context: ChatContext?, sessionID: String?, deviceTools: [String]
    ) -> AsyncThrowingStream<ChatStreamEvent, any Error> {
        let extras = chatExtras
        if let scripted = recordSend(text, fileIDs: fileIDs, sessionID: sessionID, deviceTools: deviceTools) {
            return scriptedStream(scripted)
        }
        if let error = extras.streamError {
            return AsyncThrowingStream { $0.finish(throwing: error) }
        }
        if extras.hangs {
            return AsyncThrowingStream { continuation in
                let task = Task {
                    try? await Task.sleep(for: .seconds(3600))
                    continuation.finish()
                }
                continuation.onTermination = { _ in task.cancel() }
            }
        }
        if let code = extras.streamErrorCode {
            let done = ChatMessage(id: "reply-err", text: extras.doneText ?? "", sender: .omi, createdAt: Fixtures.now)
            return AsyncThrowingStream { continuation in
                continuation.yield(.failed(code))
                continuation.yield(.done(done))
                continuation.finish()
            }
        }
        let followUp = extras.followUp
        let chart = extras.chart
        let doneText = extras.doneText
        let base = sendMessage(text, context: context, sessionID: sessionID)
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    for try await event in base {
                        guard case var .done(message) = event else {
                            continuation.yield(event)
                            continue
                        }
                        if let doneText { message.text = doneText }
                        message.followUp = followUp
                        message.chart = chart
                        continuation.yield(.done(message))
                    }
                    continuation.finish()
                } catch {
                    continuation.finish(throwing: error)
                }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// Notes what a send carried; returns the frames it should stream instead of the default reply.
    private func recordSend(_ text: String, fileIDs: [String], sessionID: String?, deviceTools: [String]) -> [ChatStreamEvent]? {
        let extras = chatExtras
        devApps.lock.withLock { devApps.sentSessions.append(sessionID) }
        return lock.withLock {
            extras.sentFileIDs.append(fileIDs)
            extras.sentDeviceTools.append(deviceTools)
            extras.sentTexts.append(text)
            defer { extras.queuedVoiceReply = nil }
            return extras.queuedVoiceReply ?? extras.script
        }
    }

    /// The script's frames; after a device tool frame it waits for that call's result (as the
    /// backend does), and a `done:` first applies `tasksAfterTurn`.
    private func scriptedStream(_ events: [ChatStreamEvent]) -> AsyncThrowingStream<ChatStreamEvent, any Error> {
        let (extras, wait) = (chatExtras, deviceToolWait)
        return AsyncThrowingStream { continuation in
            let task = Task {
                for event in events {
                    if case .done = event, let after = lock.withLock({ extras.tasksAfterTurn }) {
                        lock.withLock { _tasks = after }
                    }
                    continuation.yield(event)
                    guard case let .deviceTool(request) = event else { continue }
                    let deadline = ContinuousClock.now + wait
                    while deviceToolResults[request.id] == nil, ContinuousClock.now < deadline, !Task.isCancelled {
                        try? await Task.sleep(for: .milliseconds(5))
                    }
                }
                continuation.finish()
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }

    /// The words come from the voice reply set with `replyToVoice` (its `.question`), and its chat
    /// frames answer the send that follows, so tests of spoken questions read the same either way.
    func transcribeVoiceMessage(filename: String, audio: Data) async throws -> String {
        let events = deviceActions.voice(filename, audio)
        let question = events.compactMap { event -> String? in
            if case let .question(message) = event { return message.text }
            return nil
        }.first ?? ""
        let reply = events.compactMap { event -> ChatStreamEvent? in
            if case let .chat(chat) = event { return chat }
            return nil
        }
        lock.withLock { chatExtras.queuedVoiceReply = question.isEmpty ? nil : reply }
        return question
    }

    func rateChatMessage(id: String, value: Int, reason: String?) async throws {
        try lock.withLock {
            if let error = chatExtras.ratingError { throw error }
            chatExtras.ratings.append(.init(id: id, value: value, reason: reason))
        }
    }

    func clearChat(sessionID: String) async throws -> ChatMessage? {
        try lock.withLock {
            if let _error { throw _error }
            chatExtras.clearedSessions.append(sessionID)
            return chatExtras.clearGreeting
        }
    }

    func uploadChatFile(filename: String, mimeType: String, data _: Data) async throws -> ChatFile {
        if let delay = chatExtras.uploadDelay { try await Task.sleep(for: delay) }
        return try lock.withLock {
            if let error = chatExtras.uploadError { throw error }
            chatExtras.uploads.append(filename)
            return ChatFile(id: "file-\(chatExtras.uploads.count)", name: filename, mimeType: mimeType)
        }
    }

    /// The "audio" is the text itself, so tests can read what would have been spoken.
    func synthesizeSpeech(text: String, voiceID: String?) async throws -> Data {
        try lock.withLock {
            chatExtras.speech.append((text, voiceID))
            if let error = chatExtras.speechError { throw error }
            return Data(text.utf8)
        }
    }
}
