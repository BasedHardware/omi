import Combine
import SwiftUI

/// A single question/answer exchange in the floating bar chat history.
struct FloatingChatExchange: Identifiable {
    let id = UUID()
    let question: String?
    let questionMessageId: String?
    let aiMessage: ChatMessage
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

/// A custom in-app notification rendered directly below the floating bar.
struct FloatingBarNotification: Identifiable, Equatable {
    let id = UUID()
    let title: String
    let message: String
    let assistantId: String
    let context: FloatingBarNotificationContext?
    /// Screenshot JPEG data from the moment the notification was generated (not shown in UI)
    let screenshotData: Data?

    init(
        title: String,
        message: String,
        assistantId: String,
        context: FloatingBarNotificationContext? = nil,
        screenshotData: Data? = nil
    ) {
        self.title = title
        self.message = message
        self.assistantId = assistantId
        self.context = context
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
    static var voiceResponseWatchdogDelay: TimeInterval = 30
    /// Safety cap: the "thinking" indicator self-clears after this long even if
    /// no explicit response-start/teardown signal arrives, so it can never stick.
    static var thinkingWatchdogDelay: TimeInterval = 25

    @Published var isRecording: Bool = false
    @Published var duration: Int = 0
    @Published var isInitialising: Bool = false
    @Published var isDragging: Bool = false
    @Published var isHoveringBar: Bool = false
    @Published var requiresHoverReset: Bool = false
    @Published var currentNotification: FloatingBarNotification? = nil

    // AI conversation state
    @Published var showingAIConversation: Bool = false
    @Published var showingAIResponse: Bool = false
    @Published var isAILoading: Bool = true
    @Published var aiInputText: String = ""
    @Published var currentAIMessage: ChatMessage? = nil
    @Published var displayedQuery: String = ""
    @Published var currentQuestionMessageId: String? = nil
    @Published var inputViewHeight: CGFloat = 120
    @Published var responseContentHeight: CGFloat = 0
    @Published private(set) var responseContentHeights: [String: CGFloat] = [:]
    @Published var chatHistory: [FloatingChatExchange] = []
    @Published var lastConversationActivityAt: Date? = nil
    @Published var activeAgentChatPillID: UUID? = nil
    @Published var conversationSurface: FloatingConversationSurface = .closed

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

    /// Convenience accessor for plain-text response (used by window geometry and error handling).
    var aiResponseText: String {
        get { currentAIMessage?.text ?? "" }
        set {
            if currentAIMessage != nil {
                currentAIMessage?.text = newValue
            } else {
                currentAIMessage = ChatMessage(text: newValue, sender: .ai)
            }
        }
    }

    // Push-to-talk state
    @Published var isVoiceListening: Bool = false
    @Published var isVoiceLocked: Bool = false
    @Published var voiceTranscript: String = ""
    /// Transient inline hint shown in the bar (e.g. "Hold longer to record") after a
    /// too-short PTT tap. Non-empty keeps the bar in its voice-UI size for ~2s.
    @Published var pttHintText: String = ""
    @Published var isVoiceResponseActive: Bool = false {
        didSet {
            if isVoiceResponseActive {
                isVoiceResponseWaiting = false
            }
            updateVoiceResponseWatchdog()
            // A live voice response supersedes the "thinking" indicator.
            if isVoiceResponseActive { isThinking = false }
        }
    }
    @Published var isVoiceResponseWaiting: Bool = false {
        didSet { updateVoiceResponseWatchdog() }
    }
    /// True while a committed Push-to-Talk query is being processed and no
    /// response output (voice glow or conversation surface) has surfaced yet.
    /// Drives the notch/pill "thinking" animation. Auto-clears via a watchdog.
    @Published var isThinking: Bool = false {
        didSet { updateThinkingWatchdog() }
    }
    var isVoiceResponseGlowActive: Bool {
        isVoiceResponseActive || isVoiceResponseWaiting
    }
    /// True only when the notch-mode setting is enabled and the current display
    /// exposes a real camera housing safe area. External displays keep old pill UI.
    @Published var usesNotchIsland: Bool = false
    @Published var notchRevealProgress: CGFloat = 1

    // Voice follow-up state (PTT while AI conversation is active)
    @Published var isVoiceFollowUp: Bool = false
    @Published var voiceFollowUpTranscript: String = ""

    /// Whether the current query originated from voice (PTT). Used to decide
    /// whether voice responses should play for this particular query.
    @Published var currentQueryFromVoice: Bool = false

    private var voiceResponseWatchdogWorkItem: DispatchWorkItem?
    private var thinkingWatchdogWorkItem: DispatchWorkItem?

    // Model selection
    @Published var selectedModel: String = ModelQoS.Claude.defaultSelection

    /// Available models for the floating bar picker (driven by QoS tier)
    static var availableModels: [(id: String, label: String)] { ModelQoS.Claude.availableModels }

    var isShowingNotification: Bool {
        currentNotification != nil
    }

    var hasMainConversation: Bool {
        !chatHistory.isEmpty || currentAIMessage != nil || !displayedQuery.isEmpty
    }

    var hasVisibleConversation: Bool {
        conversationSurface.isOpen || activeAgentChatPillID != nil || hasMainConversation
    }

    var canRestoreVisibleConversation: Bool {
        guard hasVisibleConversation, let lastConversationActivityAt else { return false }
        return Date().timeIntervalSince(lastConversationActivityAt) <= Self.visibleConversationReuseInterval
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
        // The conversation surface owns its own loading header once it opens, so
        // hand the "thinking" indicator off to it (avoids showing both).
        if surface.isOpen { isThinking = false }
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
        isThinking = false
        isVoiceFollowUp = false
        voiceFollowUpTranscript = ""
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
        displayedQuery = ""
        currentAIMessage = nil
        currentQuestionMessageId = nil
        chatHistory = []
        showingAIConversation = false
        showingAIResponse = false
        isAILoading = false
        isThinking = false
        isVoiceFollowUp = false
        voiceFollowUpTranscript = ""
        currentQueryFromVoice = false
        lastConversationActivityAt = nil
        pttHintText = ""  // stay self-consistent; don't rely on PTTManager's cancel side effect
        clearVoiceResponseState()
    }

    func beginVoiceResponseWaiting() {
        guard !isVoiceResponseActive else { return }
        isVoiceResponseWaiting = true
    }

    func clearVoiceResponseState() {
        isVoiceResponseWaiting = false
        isVoiceResponseActive = false
    }

    private func updateVoiceResponseWatchdog() {
        voiceResponseWatchdogWorkItem?.cancel()
        voiceResponseWatchdogWorkItem = nil
        guard isVoiceResponseGlowActive else { return }

        let workItem = DispatchWorkItem { [weak self] in
            guard let self, self.isVoiceResponseGlowActive else { return }
            self.clearVoiceResponseState()
        }
        voiceResponseWatchdogWorkItem = workItem
        DispatchQueue.main.asyncAfter(
            deadline: .now() + Self.voiceResponseWatchdogDelay,
            execute: workItem
        )
    }

    private func updateThinkingWatchdog() {
        thinkingWatchdogWorkItem?.cancel()
        thinkingWatchdogWorkItem = nil
        guard isThinking else { return }

        let workItem = DispatchWorkItem { [weak self] in
            guard let self, self.isThinking else { return }
            self.isThinking = false
        }
        thinkingWatchdogWorkItem = workItem
        DispatchQueue.main.asyncAfter(
            deadline: .now() + Self.thinkingWatchdogDelay,
            execute: workItem
        )
    }
}
