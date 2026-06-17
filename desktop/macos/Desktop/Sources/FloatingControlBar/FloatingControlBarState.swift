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

/// The high-level voice activity the floating bar is reflecting right now. Derived
/// from the lower-level PTT/hub flags so the status indicator has a single, ordered
/// source of truth (each state has exactly one visual treatment).
enum VoiceActivity: Equatable {
    /// Nothing happening — the bar rests as a calm, barely-breathing sliver.
    case idle
    /// User is holding push-to-talk; we're capturing their voice (red, "you").
    case listening
    /// Turn committed, waiting on the model's reply — the model may answer late,
    /// so this MUST read as "working, wait" rather than "done" (cool autonomous swirl).
    case thinking
    /// The model is speaking its reply (warm, audio-reactive waveform — "it").
    case speaking
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
    /// True after a voice turn is committed and we're waiting on the model's reply
    /// (vs. still recording) — drives the "Thinking…/Responding…" indicator so the user
    /// knows to wait rather than re-pressing (which would interrupt a slow reply).
    @Published var isVoiceThinking: Bool = false
    /// True while the model is actually speaking its reply (native audio playing or the
    /// AVSpeech fallback talking). Distinct from `isVoiceThinking` so the indicator can
    /// show a clearly different "it's talking" treatment vs. "it's working".
    @Published var isVoiceSpeaking: Bool = false
    /// Smoothed 0…1 output amplitude of the model's spoken reply, sampled from the
    /// playback engine. Drives the speaking waveform so it reacts to the actual voice
    /// (premium feel) rather than animating blindly. 0 when not speaking.
    @Published var voiceLevel: CGFloat = 0

    /// Single ordered source of truth for the status indicator. Listening wins (the user
    /// is actively talking), then speaking, then thinking, else idle — by construction the
    /// hub sets these mutually exclusively, the ordering just makes barge-in race-safe.
    var voiceActivity: VoiceActivity {
        if isVoiceListening { return .listening }
        if isVoiceSpeaking { return .speaking }
        if isVoiceThinking { return .thinking }
        return .idle
    }

    /// Whether any voice turn is in flight — keeps the bar expanded across the whole
    /// listening → thinking → speaking arc so the indicator stays visible (one expand,
    /// one collapse per turn — no resize churn mid-turn).
    var isVoiceActive: Bool {
        isVoiceListening || isVoiceThinking || isVoiceSpeaking
    }

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
        isVoiceSpeaking = false
        voiceLevel = 0
        lastConversationActivityAt = nil
    }
}
