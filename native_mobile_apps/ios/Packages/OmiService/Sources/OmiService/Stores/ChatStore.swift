import Foundation
import Observation
import OmiCore
import OmiNetwork
import OmiPersistence

/// The conversation with Omi (the Omi bar). Mirrors `message_provider.dart`.
@MainActor
@Observable
public final class ChatStore {
    public internal(set) var messages: [ChatMessage] = []
    public private(set) var isStreaming = false
    public private(set) var currentStep: String?
    public private(set) var hasLoaded = false
    /// History could not be loaded; the screen offers a retry.
    public private(set) var historyFailed = false
    /// Older messages exist on the backend (the last page came back full).
    public internal(set) var hasEarlier = false
    public private(set) var isLoadingEarlier = false
    public var context: ChatContext?
    /// The message the next question replies to (long press or swipe "Reply"); sent as a quote.
    public var replyingTo: ChatMessage?
    /// Photos and files picked for the next message (`ChatStore+Extras.swift`).
    public internal(set) var attachments: [PendingAttachment] = []
    /// The phone reports no connection (the screen keeps this current): failures read as offline.
    public var networkUnavailable = false
    /// A reply finished as a real answer (the screen reads it aloud).
    public var onAnswer: (@MainActor (ChatMessage) -> Void)?
    /// The chat app this chat talks to (`ChatStore+Apps.swift`); nil is Omi itself.
    public internal(set) var chatApp: OmiApp?
    /// The user's enabled apps that can chat (the header's "Talk to…" menu).
    public internal(set) var chatApps: [OmiApp] = []
    /// A device tool call the agent is waiting on ("Omi asks"); the chat UI renders it and calls
    /// `answerDeviceTool` (`ChatStore+DeviceTools.swift`). Only arrives once the chat declares tools.
    public internal(set) var pendingDeviceTool: PendingDeviceTool?
    /// The phone's contacts and composer (set by the app shell). With it, every main-chat send
    /// declares the device tools, so Omi can ask (a message to send, a contact) inline.
    public var deviceTools: (any DeviceToolPerforming)?
    /// The answer the pending "Omi asks" belongs to (its card shows under it).
    public internal(set) var pendingDeviceToolMessageID: String?
    /// Answers during which Omi asked something (the thread's "Approvals" filter).
    public internal(set) var askedMessageIDs: Set<String> = []
    /// The task list, to show what the agent added or ticked off (`ChatStore+Cards.swift`).
    public var tasks: TasksStore?
    /// Cards drawn under answers, by message id (`ChatStore+Cards.swift`).
    public internal(set) var cardsByMessage: [String: [ChatCard]] = [:]
    /// Cards the user took back, never shown again this session.
    var undoneCards: Set<String> = []

    let api: any APIClientProtocol
    let preferences: Preferences
    var streamTask: Task<Void, Never>?
    private var loadTask: Task<Void, Never>?
    /// Bumped on every switch of chat app: a load for the previous one is discarded.
    private var scopeGeneration = 0
    var sessionID: String?
    private var stopped = false
    private let pageSize = 50
    /// Messages fetched from the backend so far: the next older page starts here.
    var fetchedCount = 0

    public init(api: any APIClientProtocol, preferences: Preferences) {
        self.api = api
        self.preferences = preferences
    }

    /// Loads once; concurrent callers (the screen, a send) share the same load.
    public func loadHistory() async {
        guard !hasLoaded else { return }
        if let loadTask { return await loadTask.value }
        let generation = scopeGeneration
        let task = Task { [weak self] in
            guard let self else { return }
            let resolved = await resolveSession()
            guard generation == scopeGeneration else { return }
            sessionID = resolved
            do {
                let history = try await api.chatHistory(limit: pageSize, offset: 0, sessionID: sessionID)
                guard generation == scopeGeneration else { return }
                // Prepend: a send may already have added local messages while this loaded.
                prepend(history)
                historyFailed = false
                hasLoaded = true
            } catch {
                historyFailed = true
            }
            loadTask = nil
        }
        loadTask = task
        await task.value
    }

    /// The page before the oldest loaded message (call when the top of the chat appears).
    /// Offsets count from the newest message, so messages sent since shift the page: the overlap
    /// is dropped by id, and nothing in between is skipped.
    public func loadEarlier() async {
        guard hasLoaded, hasEarlier, !isLoadingEarlier else { return }
        isLoadingEarlier = true
        defer { isLoadingEarlier = false }
        guard let page = try? await api.chatHistory(limit: pageSize, offset: fetchedCount, sessionID: sessionID) else { return }
        prepend(page)
    }

    private func prepend(_ page: [ChatMessage]) {
        fetchedCount += page.count
        hasEarlier = page.count == pageSize
        let known = Set(messages.map(\.id))
        let hidden = Set(preferences.strings(.hiddenChatMessages))
        let older = page.filter { !known.contains($0.id) && !hidden.contains($0.id) }.map(Self.marked)
        messages = older + messages
        collectConnectCards(in: older)
    }

    public func retryHistory() async {
        historyFailed = false
        await loadHistory()
    }

    /// A stored answer that is one of the backend's canned failures reads as a failure.
    static func marked(_ message: ChatMessage) -> ChatMessage {
        var message = message
        if message.sender == .omi, ChatStreamEvent.isServiceFailure(message.text) { message.failure = failure(forCanned: message.text) }
        return message
    }

    /// Starts over for another chat app: its own history, session and earlier pages.
    func resetForScope() {
        scopeGeneration += 1
        streamTask?.cancel()
        loadTask?.cancel()
        loadTask = nil
        messages = []
        attachments = []
        cardsByMessage = [:]
        replyingTo = nil
        askedMessageIDs = []
        pendingDeviceTool = nil
        pendingDeviceToolMessageID = nil
        hasLoaded = false
        historyFailed = false
        hasEarlier = false
        fetchedCount = 0
        sessionID = nil
        isStreaming = false
        currentStep = nil
        stopped = false
    }

    /// The backend treats the newest session without an app as "current" (voice questions,
    /// integration messages and greetings land there). Agent runs open theirs under
    /// `AgentStore.runSessionAppID`, so they are never listed here; older runs were sessions without
    /// an app. The main chat pins one session: the newest that is not a run (known locally, or
    /// marked in its title by any device), and every send names it.
    func resolveMainSession() async -> String? {
        let agentSessions = Set(preferences.strings(.agentChatSessionIDs))
        let pinned = preferences.string(.mainChatSessionID)
        guard let sessions = try? await api.chatSessions() else {
            // Offline: trust the pin unless it is known to be a run.
            return pinned.flatMap { agentSessions.contains($0) ? nil : $0 }
        }
        let chats = sessions.filter { !agentSessions.contains($0.id) && !$0.title.hasPrefix(AgentStore.sessionTitlePrefix) }
        if let pinned, chats.contains(where: { $0.id == pinned }) { return pinned }
        if let main = chats.first {
            preferences.set(main.id, for: .mainChatSessionID)
            return main.id
        }
        // No chat yet: open one, so sends never land in an agent run's session.
        guard let created = try? await api.createChatSession(title: "Omi") else { return nil }
        preferences.set(created, for: .mainChatSessionID)
        return created
    }

    /// Sends `text` with the uploaded attachments (none while one is still uploading).
    public func send(_ text: String) {
        guard !isUploading else { return }
        let files = attachments.compactMap(\.file)
        // A reply carries its quote in front (`ChatQuote`); the thread draws it above the question.
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        let quoted = replyingTo.map { ChatQuote(replyingTo: $0).prefixing(trimmed) } ?? trimmed
        guard send(trimmed.isEmpty ? trimmed : quoted, files: files) else { return }
        attachments = []
        replyingTo = nil
    }

    @discardableResult
    func send(_ text: String, files: [ChatFile]) -> Bool {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isStreaming else { return false }
        let generation = scopeGeneration
        let placeholderID = "pending-\(UUID().uuidString)"
        messages.append(ChatMessage(id: "local-\(UUID().uuidString)", text: trimmed, sender: .user, createdAt: .now, files: files))
        messages.append(ChatMessage(id: placeholderID, text: "", sender: .omi, createdAt: .now))
        isStreaming = true
        currentStep = nil
        stopped = false
        streamTask = Task { [weak self] in
            guard let self else { return }
            await stream(trimmed, files: files, into: placeholderID, generation: generation)
        }
        return true
    }

    /// One turn into the pinned session, declaring the device tools (an app's chat declares
    /// none), then the cards for what the turn did.
    private func stream(
        _ text: String, files: [ChatFile], into placeholderID: String, generation: Int, onFirstAnswer: (() -> Void)? = nil
    ) async {
        if !hasLoaded { await loadHistory() }
        let tasksBefore = tasks?.tasks
        let tools = chatApp == nil ? DeviceToolResolver.declaredTools(deviceTools) : []
        var answering = false
        do {
            let events = api.sendChatMessage(
                text, fileIDs: files.map(\.id), context: context, sessionID: sessionID, deviceTools: tools
            )
            for try await event in events {
                if Task.isCancelled {
                    stopped = true
                    break
                }
                if generation != scopeGeneration { break }
                if !answering, case .delta = event {
                    answering = true
                    onFirstAnswer?()
                }
                apply(event, to: placeholderID)
            }
        } catch {
            markFailed(placeholderID, as: Self.failure(for: error, offline: networkUnavailable))
        }
        guard generation == scopeGeneration else { return }
        if Task.isCancelled { stopped = true }
        finish(placeholderID)
        await collectCards(for: placeholderID, tasksBefore: tasksBefore)
    }

    /// Stop generating: what arrived stays, marked as stopped (not as an error).
    public func cancel() {
        stopped = true
        streamTask?.cancel()
    }

    /// Asks the question behind a failed answer again, with the same photos and files.
    public func retry(_ messageID: String) {
        guard !isStreaming, let index = messages.firstIndex(where: { $0.id == messageID }),
              let question = messages[..<index].last(where: { $0.sender == .user }),
              let questionIndex = messages.firstIndex(of: question) else { return }
        messages.removeSubrange(questionIndex ... index)
        send(question.text, files: question.files)
    }

    private func apply(_ event: ChatStreamEvent, to placeholderID: String) {
        guard let index = messages.firstIndex(where: { $0.id == placeholderID }) else { return }
        switch event {
        case let .step(step):
            currentStep = step
            messages[index].steps.append(step)
        case let .delta(text):
            currentStep = nil
            messages[index].text += text
        case let .failed(code):
            markFailed(placeholderID, as: Self.failure(forStreamCode: code, offline: networkUnavailable))
        case let .done(message):
            // Keep the local id: a new identity would rebuild the bubble as it finishes.
            messages[index].text = message.text.isEmpty ? messages[index].text : message.text
            messages[index].references = message.references
            messages[index].evidence = message.evidence
            messages[index].serverID = message.serverID ?? message.id
            messages[index].followUp = message.followUp
            messages[index].chart = message.chart
            messages[index].blocks = message.blocks
            messages[index].kind = message.kind
            if ChatStreamEvent.isServiceFailure(messages[index].text), messages[index].failure == nil {
                messages[index].failure = Self.failure(forCanned: messages[index].text)
            }
        case .memorySaved:
            break
        case let .deviceTool(request):
            askedMessageIDs.insert(placeholderID)
            receive(request, for: placeholderID)
        }
    }

    public enum VoiceAnswer: Equatable, Sendable {
        case answered(String)
        case noSpeech
        case failed
    }

    /// A question spoken into the Omi that the iPhone could not transcribe: the backend writes it
    /// down (`v2/voice-message/transcribe`, nothing stored) and it is asked like a typed one in the
    /// pinned main chat. (`v2/voice-messages` would answer it in the backend's newest session
    /// without an app, which need not be the one this chat shows.) `onFirstAnswer` fires when the
    /// answer starts (the Omi buzzes).
    public func ask(voiceFile filename: String, audio: Data, onFirstAnswer: @escaping () -> Void = {}) async -> VoiceAnswer {
        guard !isStreaming else { return .failed }
        if chatApp != nil { await talk(to: nil) }
        let question: String
        do {
            question = try await api.transcribeVoiceMessage(filename: filename, audio: audio)
        } catch {
            return .failed
        }
        guard !question.isEmpty else { return .noSpeech }
        return await ask(question: question, onFirstAnswer: onFirstAnswer)
    }

    /// A spoken question the iPhone already transcribed (Ask Omi from the Omi): asked like a typed
    /// one in the main chat and awaited, so the caller can show or read the answer. A cancelled
    /// caller (a timeout) leaves what arrived, marked as stopped.
    public func ask(question: String, onFirstAnswer: @escaping () -> Void = {}) async -> VoiceAnswer {
        let trimmed = question.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return .noSpeech }
        guard !isStreaming else { return .failed }
        if chatApp != nil { await talk(to: nil) }
        let placeholderID = "pending-\(UUID().uuidString)"
        messages.append(ChatMessage(id: "voice-\(UUID().uuidString)", text: trimmed, sender: .user, createdAt: .now))
        messages.append(ChatMessage(id: placeholderID, text: "", sender: .omi, createdAt: .now))
        isStreaming = true
        currentStep = nil
        stopped = false
        await stream(trimmed, files: [], into: placeholderID, generation: scopeGeneration, onFirstAnswer: onFirstAnswer)
        guard let answer = messages.first(where: { $0.id == placeholderID }), answer.failure == nil else { return .failed }
        return .answered(answer.text)
    }

    /// Quota, offline and timeout keep their own wording; anything else is "could not answer", or
    /// "interrupted" once part of the answer arrived.
    private func markFailed(_ placeholderID: String, as failure: ChatMessage.Failure) {
        guard let index = messages.firstIndex(where: { $0.id == placeholderID }) else { return }
        if failure == .couldNotAnswer, !messages[index].text.isEmpty {
            messages[index].failure = .interrupted
        } else {
            messages[index].failure = failure
        }
    }

    private func finish(_ placeholderID: String) {
        if let index = messages.firstIndex(where: { $0.id == placeholderID }) {
            if stopped {
                messages[index].failure = .stopped
            } else if messages[index].text.isEmpty, messages[index].failure == nil {
                messages[index].failure = .couldNotAnswer
            }
            if messages[index].failure == nil { onAnswer?(messages[index]) }
        }
        // The turn is over: the agent no longer waits for an answer.
        if pendingDeviceToolMessageID == placeholderID {
            pendingDeviceTool = nil
            pendingDeviceToolMessageID = nil
        }
        isStreaming = false
        currentStep = nil
        stopped = false
    }
}

public extension ChatMessage {
    /// One of the backend's canned failure answers (streamed as ordinary text), not a reply.
    var isServiceFailure: Bool {
        ChatStreamEvent.isServiceFailure(text)
    }
}
