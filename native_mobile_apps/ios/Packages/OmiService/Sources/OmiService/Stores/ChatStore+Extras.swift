import Foundation
import OmiCore
import OmiNetwork

/// A photo or file picked for the next message. It uploads right away (as in Flutter), so sending is
/// instant; the message carries the uploaded ids.
public struct PendingAttachment: Identifiable, Hashable, Sendable {
    public enum State: Hashable, Sendable { case uploading, uploaded(ChatFile), failed }

    public let id: String
    public let filename: String
    public let mimeType: String
    /// A small JPEG for the thumbnail (photos only).
    public let preview: Data?
    public internal(set) var state: State

    public var file: ChatFile? {
        if case let .uploaded(file) = state { return file }
        return nil
    }
}

public extension ChatStore {
    /// Flutter's limit per message.
    static let maxAttachments = 4

    var isUploading: Bool {
        attachments.contains { $0.state == .uploading }
    }

    var canAttach: Bool {
        attachments.count < Self.maxAttachments && !isStreaming
    }

    /// Uploads at once; a failed upload stays in the row (marked) until removed.
    func attach(data: Data, filename: String, mimeType: String, preview: Data?) {
        guard canAttach else { return }
        let id = UUID().uuidString
        attachments.append(PendingAttachment(id: id, filename: filename, mimeType: mimeType, preview: preview, state: .uploading))
        let api = api
        Task { [weak self] in
            let state: PendingAttachment.State
            do {
                var file = try await api.uploadChatFile(filename: filename, mimeType: mimeType, data: data)
                file.localPreview = preview
                state = .uploaded(file)
            } catch {
                state = .failed
            }
            guard let self, let index = attachments.firstIndex(where: { $0.id == id }) else { return }
            attachments[index].state = state
        }
    }

    func removeAttachment(_ id: String) {
        attachments.removeAll { $0.id == id }
    }

    /// Thumbs up (1), down (-1, with a reason key) or cleared (0). The rating shows at once and is
    /// taken back if the backend refuses it; returns whether it was saved.
    @discardableResult
    func rate(_ messageID: String, value: Int, reason: String? = nil) async -> Bool {
        guard let index = messages.firstIndex(where: { $0.id == messageID }), let serverID = messages[index].serverID else { return false }
        let previous = messages[index].rating
        messages[index].rating = value == 0 ? nil : value
        do {
            try await api.rateChatMessage(id: serverID, value: value, reason: reason)
            return true
        } catch {
            if let index = messages.firstIndex(where: { $0.id == messageID }) { messages[index].rating = previous }
            return false
        }
    }

    /// Empties the main chat on the backend (its session only, never an agent run's) and starts
    /// over with Omi's new greeting.
    @discardableResult
    func clearChat() async -> Bool {
        if !hasLoaded { await loadHistory() }
        guard let sessionID else { return false }
        streamTask?.cancel()
        do {
            let greeting = try await api.clearChat(sessionID: sessionID)
            messages = greeting.map { [$0] } ?? []
            fetchedCount = messages.count
            hasEarlier = false
            attachments = []
            return true
        } catch {
            return false
        }
    }

    /// A send that threw: no connection, the request timed out, the plan's limit (HTTP 402).
    nonisolated static func failure(for error: any Error, offline: Bool) -> ChatMessage.Failure {
        if let error = error as? URLError {
            switch error.code {
            case .timedOut: return .timeout
            case .notConnectedToInternet, .networkConnectionLost, .cannotFindHost, .cannotConnectToHost,
                 .dataNotAllowed, .internationalRoamingOff: return .offline
            default: break
            }
        }
        switch error as? APIError {
        case .http(status: 402, body: _): return .quotaExceeded
        case .transport: return .offline
        default: return offline ? .offline : .couldNotAnswer
        }
    }

    /// A typed `error:` frame (backend `X-Omi-Chat-Failure-Protocol`).
    nonisolated static func failure(forStreamCode code: String, offline: Bool) -> ChatMessage.Failure {
        switch code {
        case "quota_exceeded": .quotaExceeded
        case "timeout": .timeout
        case "offline": .offline
        default: offline ? .offline : .couldNotAnswer
        }
    }

    /// The backend streams some failures as answer text; the one about waiting too long is a timeout.
    nonisolated static func failure(forCanned text: String) -> ChatMessage.Failure {
        text.trimmingCharacters(in: .whitespacesAndNewlines) == ChatStreamEvent.serviceFailureTexts[2] ? .timeout : .couldNotAnswer
    }
}
