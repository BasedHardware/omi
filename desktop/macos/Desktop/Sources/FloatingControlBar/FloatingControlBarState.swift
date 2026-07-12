import Combine
import SwiftUI

/// Message-id pair for one archived floating-bar exchange.
/// Content always resolves from `ChatProvider.messages` — these are viewport anchors only.
struct FloatingChatExchangePair: Equatable {
    var questionMessageId: String?
    var answerMessageId: String?
}

/// Session cursor over the shared chat timeline. Chrome + anchors live here;
/// transcript text lives in `ChatProvider.messages`.
struct FloatingChatViewport: Equatable {
    var activeClientTurnId: String?
    var questionMessageId: String?
    var answerMessageId: String?
    var archivedExchanges: [FloatingChatExchangePair] = []

    var hasAnchors: Bool {
        activeClientTurnId != nil
            || questionMessageId != nil
            || answerMessageId != nil
            || !archivedExchanges.isEmpty
    }

    mutating func archiveCurrentExchange() {
        guard answerMessageId != nil || questionMessageId != nil else { return }
        archivedExchanges.append(
            FloatingChatExchangePair(
                questionMessageId: questionMessageId,
                answerMessageId: answerMessageId
            )
        )
        questionMessageId = nil
        answerMessageId = nil
        activeClientTurnId = nil
    }

    mutating func clear() {
        activeClientTurnId = nil
        questionMessageId = nil
        answerMessageId = nil
        archivedExchanges = []
    }
}

/// Thin view-model derived from provider messages for `AIResponseView`.
/// Not stored as source of truth on floating-bar state.
struct FloatingChatExchange: Identifiable {
    let id: String
    let question: String?
    let questionMessageId: String?
    let aiMessage: ChatMessage

    init(
        id: String? = nil,
        question: String?,
        questionMessageId: String?,
        aiMessage: ChatMessage
    ) {
        self.id = id ?? aiMessage.id
        self.question = question
        self.questionMessageId = questionMessageId
        self.aiMessage = aiMessage
    }
}

enum FloatingConversationSurface: Equatable {
    case closed
    case mainInput
    case mainResponse
    case agent(UUID)

    var isOpen: Bool {
        switch self {
        case .closed: return false
        case .mainInput, .mainResponse, .agent: return true
        }
    }

    var isResponseLike: Bool {
        switch self {
        case .mainResponse, .agent: return true
        case .closed, .mainInput: return false
        }
    }

    var agentID: UUID? {
        guard case .agent(let id) = self else { return nil }
        return id
    }

    var measurementKey: String {
        switch self {
        case .closed: return "closed"
        case .mainInput: return "mainInput"
        case .mainResponse: return "mainResponse"
        case .agent(let id): return "agent:\(id.uuidString)"
        }
    }
}

/// Hidden provenance carried with a floating-bar notification so follow-up
/// questions can explain where the notification came from without guessing.
struct FloatingBarNotificationContext: Equatable {
    let sourceTitle: String
    let assistantId: String
    let sourceApp: String?
    let windowTitle: String?
    let contextSummary: String?
    let currentActivity: String?
    let reasoning: String?
    let detail: String?
}

enum FloatingBarNotificationAction: Equatable {
    case openWhatMattersNow(recommendationID: String)
}

/// A custom in-app notification rendered directly below the floating bar.
struct FloatingBarNotification: Identifiable, Equatable {
    let id = UUID()
    let title: String
    let message: String
    let assistantId: String
    let context: FloatingBarNotificationContext?
    let action: FloatingBarNotificationAction?
    /// Screenshot JPEG data from the moment the notification was generated (not shown in UI)
    let screenshotData: Data?

    init(
        title: String,
        message: String,
        assistantId: String,
        context: FloatingBarNotificationContext? = nil,
        action: FloatingBarNotificationAction? = nil,
        screenshotData: Data? = nil
    ) {
        self.title = title
        self.message = message
        self.assistantId = assistantId
        self.context = context
        self.action = action
        self.screenshotData = screenshotData
    }

    static func == (lhs: FloatingBarNotification, rhs: FloatingBarNotification) -> Bool {
        lhs.id == rhs.id
    }
}

/// Observable object holding the state for the floating control bar.
@MainActor
class FloatingControlBarState: NSObject, ObservableObject {
    static let visibleConversationReuseInterval: TimeInterval = 10 * 60

    @Published var isRecording: Bool = false
    @Published var duration: Int = 0
    @Published var isInitialising: Bool = false
    @Published var isDragging: Bool = false
    @Published var isHoveringBar: Bool = false
    @Published var requiresHoverReset: Bool = false
    @Published var currentNotification: FloatingBarNotification? = nil

    // AI conversation chrome (not transcript content)
    @Published var showingAIConversation: Bool = false
    @Published var showingAIResponse: Bool = false
    @Published var isAILoading: Bool = true
    @Published var aiInputText: String = "" {
        didSet {
            guard !isRestoringAIDraft else { return }
            aiDraftRevision &+= 1
            ChatDraftStore.shared.setText(aiInputText, for: activeAIDraftKey)
        }
    }
    /// Optimistic pending user text shown before/while the provider turn resolves.
    @Published var displayedQuery: String = ""
    @Published var inputViewHeight: CGFloat = 120
    @Published var responseContentHeight: CGFloat = 0
    @Published private(set) var responseContentHeights: [String: CGFloat] = [:]
    /// Viewport cursor over `ChatProvider.messages` — ids only, never a durable transcript copy.
    @Published var chatViewport = FloatingChatViewport()
    /// Bumped when provider message content streams in-place so SwiftUI re-reads derived accessors.
    @Published private(set) var answerStreamToken: String = ""
    /// Local-only answer for ephemeral presentation (usage limit, busy, legacy updateAIResponse)
    /// that is not (yet) on the shared provider timeline.
    @Published private(set) var localAnswerOverride: ChatMessage? = nil
    @Published var lastConversationActivityAt: Date? = nil
    @Published var activeAgentChatPillID: UUID? = nil
    @Published var conversationSurface: FloatingConversationSurface = .closed
    private var activeAIDraftKey = ChatDraftKey.floatingMain
    private var isRestoringAIDraft = false
    private var aiDraftRevision: UInt64 = 0
    private var submittedAIDraft: (key: ChatDraftKey, text: String, revision: UInt64)?

    override init() {
        super.init()
        isRestoringAIDraft = true
        aiInputText = ChatDraftStore.shared.text(for: activeAIDraftKey)
        isRestoringAIDraft = false
    }

    /// The sole bridge from reducer state into floating-bar voice presentation.
    /// Keeping the presenter nested lets `applyVoiceProjection` remain private,
    /// so no capture, window, onboarding, or automation caller can mutate the
    /// rendered voice state independently.
    @MainActor
    final class PTTBarPresenter {
        private weak var barState: FloatingControlBarState?

        init(barState: FloatingControlBarState) {
            self.barState = barState
        }

        func apply(_ projection: VoiceTurnUIProjection) {
            guard let barState else { return }
            let wasExpandedForVoice = barState.isVoiceListening
            barState.applyVoiceProjection(projection)
            let shouldExpandForVoice = barState.isVoiceListening

            if shouldExpandForVoice != wasExpandedForVoice,
               !barState.isVoiceFollowUp,
               !barState.showingAIConversation,
               UserDefaults.standard.bool(forKey: .hasCompletedOnboarding)
            {
                FloatingControlBarManager.shared.resizeForPTT(expanded: shouldExpandForVoice)
            }
        }
    }

    /// Onboarding demos reuse the real floating window but must not overwrite the
    /// user's normal notch draft. Switching scopes restores each independently.
    func switchAIDraft(to key: ChatDraftKey) {
        guard key != activeAIDraftKey else { return }
        activeAIDraftKey = key
        aiDraftRevision &+= 1
        isRestoringAIDraft = true
        aiInputText = ChatDraftStore.shared.text(for: key)
        isRestoringAIDraft = false
    }

    func markAIDraftSubmitted(_ text: String) {
        submittedAIDraft = (activeAIDraftKey, text, aiDraftRevision)
    }

    func clearSubmittedAIDraftIfUnchanged(_ text: String) {
        guard let submittedAIDraft,
              submittedAIDraft.key == activeAIDraftKey,
              submittedAIDraft.text == text,
              submittedAIDraft.revision == aiDraftRevision,
              aiInputText == text else { return }
        self.submittedAIDraft = nil
        aiInputText = ""
    }

    /// Subagent switcher visibility state, shared by both display modes.
    /// On notched displays the menu opens on hover over the notch; on
    /// non-notched displays it opens pinned via an explicit click on the
    /// pill's agents affordance. Mirrored from the SwiftUI view so the
    /// window can account for an expanded switcher when resizing.
    @Published var agentSwitcherPinned: Bool = false
    @Published var agentSwitcherHovering: Bool = false
    var isAgentSwitcherExpanded: Bool { agentSwitcherPinned || agentSwitcherHovering }
    @Published private(set) var notchHoverMenuOpen: Bool = false
    var canShowNotchHoverMenu: Bool {
        !showingAIConversation
            && !isVoiceListening
            && !isShowingNotification
            && currentNotification == nil
    }
    var isNotchHoverMenuVisible: Bool {
        canShowNotchHoverMenu && notchHoverMenuOpen
    }

    func setNotchHoverMenuOpen(_ open: Bool) {
        notchHoverMenuOpen = open
        isHoveringBar = open
        agentSwitcherHovering = open
        if !open {
            agentSwitcherPinned = false
        }
    }

    /// Convenience for call sites that previously used a stored question id.
    var currentQuestionMessageId: String? {
        get { chatViewport.questionMessageId }
        set {
            var viewport = chatViewport
            viewport.questionMessageId = newValue
            chatViewport = viewport
        }
    }

    // Push-to-talk presentation is one atomic reducer projection. Individual
    // fields are read-only derivations so observers cannot see or create a
    // partially applied voice state.
    @Published private(set) var voiceProjection = VoiceTurnUIProjection.idle
    var isVoiceListening: Bool {
        voiceProjection.isListening || !voiceProjection.hint.isEmpty
    }
    var isVoiceLocked: Bool { voiceProjection.isLocked }
    var voiceTranscript: String { voiceProjection.transcript }
    /// Transient inline hint shown in the bar (e.g. "Hold longer to record") after a
    /// too-short PTT tap. Non-empty keeps the bar in its voice-UI size for ~2s.
    var pttHintText: String { voiceProjection.hint }
    var isVoiceResponseActive: Bool { voiceProjection.isResponseActive }
    var isVoiceResponseWaiting: Bool { voiceProjection.isResponseWaiting }
    /// True while a committed Push-to-Talk query is being processed and no
    /// response output (voice glow or conversation surface) has surfaced yet.
    /// Drives the notch/pill "thinking" animation.
    var isThinking: Bool { voiceProjection.isThinking }
    var isVoiceResponseGlowActive: Bool {
        isVoiceResponseActive || isVoiceResponseWaiting
    }
    /// True only when the notch-mode setting is enabled and the current display
    /// exposes a real camera housing safe area. External displays keep old pill UI.
    @Published var usesNotchIsland: Bool = false
    @Published var notchRevealProgress: CGFloat = 1

    // Voice follow-up state (PTT while AI conversation is active)
    var isVoiceFollowUp: Bool { voiceProjection.isFollowUp && isVoiceListening }
    var voiceFollowUpTranscript: String {
        isVoiceFollowUp ? voiceProjection.transcript : ""
    }

    private func applyVoiceProjection(_ projection: VoiceTurnUIProjection) {
        voiceProjection = projection
    }

    /// Whether the current query originated from voice (PTT). Used to decide
    /// whether voice responses should play for this particular query.
    @Published var currentQueryFromVoice: Bool = false

    // Model selection
    @Published var selectedModel: String = ModelQoS.Claude.defaultSelection

    /// Available models for the floating bar picker (driven by QoS tier)
    static var availableModels: [(id: String, label: String)] { ModelQoS.Claude.availableModels }

    var isShowingNotification: Bool {
        currentNotification != nil
    }

    var hasMainConversation: Bool {
        chatViewport.hasAnchors || localAnswerOverride != nil || !displayedQuery.isEmpty
    }

    var hasVisibleConversation: Bool {
        conversationSurface.isOpen || activeAgentChatPillID != nil || hasMainConversation
    }

    var canRestoreVisibleConversation: Bool {
        guard hasVisibleConversation, let lastConversationActivityAt else { return false }
        return Date().timeIntervalSince(lastConversationActivityAt) <= Self.visibleConversationReuseInterval
    }

    /// True when a restored viewport should re-subscribe to provider streaming
    /// for the active turn (mid-stream close → reopen within the reuse window).
    static func shouldReobserveStreamingTurn(
        activeClientTurnId: String?,
        answerMessage: ChatMessage?
    ) -> Bool {
        guard let turnId = activeClientTurnId?.trimmingCharacters(in: .whitespacesAndNewlines),
              !turnId.isEmpty,
              let answerMessage,
              answerMessage.isStreaming,
              answerMessage.clientTurnId == turnId
        else { return false }
        return true
    }

    /// Resolve the current answer from the shared provider timeline (or local override).
    /// Provider-bound answers always win over `localAnswerOverride` so the shared
    /// timeline remains source of truth once an answer id is anchored.
    func currentAIMessage(from provider: ChatProvider?) -> ChatMessage? {
        if let answerId = chatViewport.answerMessageId,
           let message = provider?.messages.first(where: { $0.id == answerId })
        {
            return message
        }
        if let localAnswerOverride { return localAnswerOverride }
        guard let provider else { return nil }
        if let turnId = chatViewport.activeClientTurnId,
           let message = provider.messages.last(where: {
               $0.clientTurnId == turnId && $0.sender == .ai
           })
        {
            return message
        }
        return nil
    }

    func aiResponseText(from provider: ChatProvider?) -> String {
        currentAIMessage(from: provider)?.text ?? ""
    }

    /// True when a message has user-visible answer payload (plain text, structured
    /// blocks, or resources). Block-only / resource-only answers are not empty.
    static func messageHasAnswerContent(_ message: ChatMessage) -> Bool {
        !message.text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            || !message.contentBlocks.isEmpty
            || !message.resources.isEmpty
    }

    /// Provider-bound answer with visible content (text, contentBlocks, or resources).
    func hasProviderBackedAnswerContent(from provider: ChatProvider?) -> Bool {
        guard let answerId = chatViewport.answerMessageId,
              let message = provider?.messages.first(where: { $0.id == answerId })
        else { return false }
        return Self.messageHasAnswerContent(message)
    }

    /// Post-send empty-response path: only fail when there is no provider-backed
    /// answer and no visible content. Never treat a bound provider answer as a
    /// failure (calling `setLocalAnswerOverride` would clear the answer id).
    func shouldPresentEmptyResponseFailure(from provider: ChatProvider?) -> Bool {
        if let answerId = chatViewport.answerMessageId,
           provider?.messages.contains(where: { $0.id == answerId }) == true
        {
            return false
        }
        guard let message = currentAIMessage(from: provider) else { return true }
        return !Self.messageHasAnswerContent(message)
    }

    /// Resources visible in the floating/notch viewport — only those owned by
    /// viewport-anchored message ids (INV-6: no orphan historical artifacts).
    func viewportDisplayResources(from provider: ChatProvider?) -> [ChatResource] {
        guard let provider else { return [] }
        var ids = Set<String>()
        if let answerId = chatViewport.answerMessageId { ids.insert(answerId) }
        if let questionId = chatViewport.questionMessageId { ids.insert(questionId) }
        for pair in chatViewport.archivedExchanges {
            if let questionId = pair.questionMessageId { ids.insert(questionId) }
            if let answerId = pair.answerMessageId { ids.insert(answerId) }
        }
        return ChatContinuityInvariants.resourcesBelongingToMessages(
            messages: provider.messages,
            messageIds: ids
        )
    }

    /// Build archived exchanges as a thin view-model from ids + provider messages.
    func derivedChatHistory(from provider: ChatProvider?) -> [FloatingChatExchange] {
        guard let provider else { return [] }
        return chatViewport.archivedExchanges.compactMap { pair in
            guard let answerId = pair.answerMessageId,
                  let aiMessage = provider.messages.first(where: { $0.id == answerId })
            else { return nil }
            let question: String?
            if let questionId = pair.questionMessageId,
               let questionMessage = provider.messages.first(where: { $0.id == questionId })
            {
                question = questionMessage.text
            } else {
                question = nil
            }
            return FloatingChatExchange(
                id: answerId,
                question: question,
                questionMessageId: pair.questionMessageId,
                aiMessage: aiMessage
            )
        }
    }

    /// Synced message ids for share/rate, in chat order.
    func syncedShareMessageIds(from provider: ChatProvider?) -> [String] {
        guard let provider else { return [] }
        var messageIds: [String] = []
        for pair in chatViewport.archivedExchanges {
            if let questionId = pair.questionMessageId,
               provider.messages.contains(where: { $0.id == questionId && $0.isSynced })
            {
                messageIds.append(questionId)
            }
            if let answerId = pair.answerMessageId,
               provider.messages.contains(where: { $0.id == answerId && $0.isSynced })
            {
                messageIds.append(answerId)
            }
        }
        if let questionId = chatViewport.questionMessageId,
           provider.messages.contains(where: { $0.id == questionId && $0.isSynced })
        {
            messageIds.append(questionId)
        }
        if let answerId = chatViewport.answerMessageId,
           provider.messages.contains(where: { $0.id == answerId && $0.isSynced })
        {
            messageIds.append(answerId)
        }
        return messageIds.reduce(into: [String]()) { ids, messageId in
            if !ids.contains(messageId) {
                ids.append(messageId)
            }
        }
    }

    func beginTurn(clientTurnId: String) {
        localAnswerOverride = nil
        var viewport = chatViewport
        viewport.activeClientTurnId = clientTurnId
        viewport.questionMessageId = nil
        viewport.answerMessageId = nil
        chatViewport = viewport
        answerStreamToken = ""
    }

    /// Clear the current answer/question cursor without archiving or wiping prior exchanges.
    func clearCurrentAnswerAnchors() {
        localAnswerOverride = nil
        var viewport = chatViewport
        viewport.activeClientTurnId = nil
        viewport.questionMessageId = nil
        viewport.answerMessageId = nil
        chatViewport = viewport
        answerStreamToken = ""
    }

    func bindAnswerMessage(_ message: ChatMessage) {
        localAnswerOverride = nil
        var viewport = chatViewport
        viewport.answerMessageId = message.id
        if let turnId = message.clientTurnId {
            viewport.activeClientTurnId = turnId
        }
        chatViewport = viewport
        answerStreamToken = [
            message.id,
            message.text,
            String(message.isStreaming),
            String(message.contentBlocks.count),
            message.contentBlocks.map(\.blockIdentity).joined(separator: ","),
        ].joined(separator: "\u{1F}")
    }

    func bindQuestionMessageId(_ messageId: String?) {
        var viewport = chatViewport
        viewport.questionMessageId = messageId
        chatViewport = viewport
    }

    /// Ephemeral UI-only answer (usage limit, busy, synthetic errors with no
    /// provider message). Not for provider-backed answers — those must
    /// `bindAnswerMessage` instead. Setting a non-nil override drops the answer
    /// id so the ephemeral message is visible; if an answer id is later bound
    /// while an override remains, `currentAIMessage` prefers the provider.
    func setLocalAnswerOverride(_ message: ChatMessage?) {
        if message != nil, chatViewport.answerMessageId != nil {
            var viewport = chatViewport
            viewport.answerMessageId = nil
            chatViewport = viewport
        }
        localAnswerOverride = message
        if let message {
            answerStreamToken = "local:\(message.id):\(message.text)"
        }
    }

    func appendLocalAnswerText(_ text: String) {
        var message = localAnswerOverride ?? ChatMessage(text: "", sender: .ai)
        message.text += text
        setLocalAnswerOverride(message)
    }

    func replaceLocalAnswerText(_ text: String) {
        var message = localAnswerOverride ?? ChatMessage(text: "", sender: .ai)
        message.text = text
        setLocalAnswerOverride(message)
    }

    /// Archive the current exchange as message-id anchors (not ChatMessage copies).
    func archiveCurrentExchange(using provider: ChatProvider?) {
        if chatViewport.answerMessageId == nil,
           let message = currentAIMessage(from: provider),
           Self.messageHasAnswerContent(message)
        {
            bindAnswerMessage(message)
        }
        guard chatViewport.answerMessageId != nil || chatViewport.questionMessageId != nil else {
            return
        }
        if let answerId = chatViewport.answerMessageId,
           let provider,
           let message = provider.messages.first(where: { $0.id == answerId }),
           !Self.messageHasAnswerContent(message)
        {
            return
        }
        if localAnswerOverride != nil, chatViewport.answerMessageId == nil {
            // Ephemeral local answers with no provider id are not durable.
            localAnswerOverride = nil
            return
        }
        var viewport = chatViewport
        viewport.archiveCurrentExchange()
        chatViewport = viewport
        localAnswerOverride = nil
        answerStreamToken = ""
    }

    func clearViewport() {
        chatViewport = FloatingChatViewport()
        localAnswerOverride = nil
        answerStreamToken = ""
        displayedQuery = ""
    }

    func markConversationActivity(at date: Date = Date()) {
        lastConversationActivityAt = date
    }

    func present(_ surface: FloatingConversationSurface) {
        conversationSurface = surface
        activeAgentChatPillID = surface.agentID
        showingAIConversation = surface.isOpen
        showingAIResponse = surface.isResponseLike
        markConversationActivity()
    }

    func leaveAgentSurface() {
        activeAgentChatPillID = nil
        let nextSurface: FloatingConversationSurface = hasMainConversation ? .mainResponse : .mainInput
        present(nextSurface)
    }

    func hideConversationSurface() {
        // Cancel in-flight work before resetting process flags so UI state and
        // active response/follow-up workflows stay in sync. Without this, a
        // streaming response or PTT follow-up keeps running after its UI flags
        // are cleared, and late-arriving chunks update a surface nobody sees.
        // (Cubic P2 — presentation/process desync.)
        FloatingControlBarManager.shared.cancelChat()
        // Call cancelListening() directly instead of gating on isVoiceFollowUp:
        // the derived UI flag is not the authoritative source of microphone
        // state, and cancelListening() is already guarded by state != .idle.
        // (Cubic P2 — stale PTT capture after surface hide.)
        PushToTalkManager.shared.cancelListening()
        activeAgentChatPillID = nil
        conversationSurface = .closed
        showingAIConversation = false
        showingAIResponse = false
        isAILoading = false
        markConversationActivity()
    }

    func reportContentHeight(_ height: CGFloat, for surface: FloatingConversationSurface) {
        guard height > 0, conversationSurface == surface else { return }
        let measuredHeight = (height * 2).rounded(.up) / 2
        let key = surface.measurementKey
        if let previousHeight = responseContentHeights[key],
           abs(previousHeight - measuredHeight) < 0.5
        {
            return
        }
        responseContentHeights[key] = measuredHeight
        if surface == .mainResponse {
            responseContentHeight = measuredHeight
        }
    }

    func measuredContentHeight(for surface: FloatingConversationSurface) -> CGFloat? {
        responseContentHeights[surface.measurementKey]
    }

    func resetMeasuredContentHeight(for surface: FloatingConversationSurface) {
        responseContentHeights.removeValue(forKey: surface.measurementKey)
        if surface == .mainResponse {
            responseContentHeight = 0
        }
    }

    func clearVisibleConversation(cancelInFlightWork: Bool = true) {
        // When cancelInFlightWork is true (default), cancel in-flight chat
        // streaming and PTT capture before resetting UI flags. This is needed
        // from close/restore/notification paths where stale streams and mic
        // capture should be stopped. (Cubic P2.)
        //
        // Callers that only need a UI reset (e.g. openAIInputWithQuery, which
        // already cancelled its own subscriptions and is about to route a new
        // typed query) pass cancelInFlightWork: false to avoid killing a
        // provider session that the new query depends on. (Cubic P2 — semantic
        // mismatch between method name and hard-cancellation side effects.)
        if cancelInFlightWork {
            FloatingControlBarManager.shared.cancelChat()
            PushToTalkManager.shared.cancelListening()
        }
        activeAgentChatPillID = nil
        conversationSurface = .closed
        responseContentHeights = [:]
        responseContentHeight = 0
        aiInputText = ""
        clearViewport()
        showingAIConversation = false
        showingAIResponse = false
        isAILoading = false
        currentQueryFromVoice = false
        lastConversationActivityAt = nil
    }

}

private extension ChatContentBlock {
    var blockIdentity: String {
        switch self {
        case .text(let id, _): return "t:\(id)"
        case .toolCall(let id, let name, let status, _, _, _): return "c:\(id):\(name):\(status)"
        case .thinking(let id, _): return "h:\(id)"
        case .discoveryCard(let id, _, _, _): return "d:\(id)"
        case .agentSpawn(let id, let pillId, _, _, _, _): return "s:\(id):\(pillId?.uuidString ?? "")"
        case .agentCompletion(let id, let pillId, _, _, _, _, _, _): return "a:\(id):\(pillId?.uuidString ?? "")"
        }
    }
}
