import Combine
import SwiftUI

/// A single question/answer exchange in the floating bar chat history.
struct FloatingChatExchange: Identifiable {
    let id = UUID()
    let question: String?
    let questionMessageId: String?
    let aiMessage: ChatMessage
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
    @Published var chatHistory: [FloatingChatExchange] = []
    @Published var lastConversationActivityAt: Date? = nil

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

    // Voice follow-up state (PTT while AI conversation is active)
    @Published var isVoiceFollowUp: Bool = false
    @Published var voiceFollowUpTranscript: String = ""

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

    var hasVisibleConversation: Bool {
        !chatHistory.isEmpty || currentAIMessage != nil || !displayedQuery.isEmpty
    }

    var canRestoreVisibleConversation: Bool {
        guard hasVisibleConversation, let lastConversationActivityAt else { return false }
        return Date().timeIntervalSince(lastConversationActivityAt) <= Self.visibleConversationReuseInterval
    }

    func markConversationActivity(at date: Date = Date()) {
        lastConversationActivityAt = date
    }

    func clearVisibleConversation() {
        aiInputText = ""
        displayedQuery = ""
        currentAIMessage = nil
        currentQuestionMessageId = nil
        chatHistory = []
        showingAIResponse = false
        isAILoading = false
        isVoiceFollowUp = false
        voiceFollowUpTranscript = ""
        currentQueryFromVoice = false
        lastConversationActivityAt = nil
    }
}
