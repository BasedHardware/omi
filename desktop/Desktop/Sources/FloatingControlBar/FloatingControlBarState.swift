import Combine
import SwiftUI

/// A single question/answer exchange in the floating bar chat history.
struct FloatingChatExchange: Identifiable {
    let id = UUID()
    let question: String
    let aiMessage: ChatMessage
}

/// Observable object holding the state for the floating control bar.
@MainActor
class FloatingControlBarState: NSObject, ObservableObject {
    @Published var isRecording: Bool = false
    @Published var duration: Int = 0
    @Published var isInitialising: Bool = false
    @Published var isDragging: Bool = false

    // AI conversation state
    @Published var showingAIConversation: Bool = false
    @Published var showingAIResponse: Bool = false
    @Published var isAILoading: Bool = true
    @Published var aiInputText: String = ""
    @Published var currentAIMessage: ChatMessage? = nil
    @Published var displayedQuery: String = ""
    @Published var inputViewHeight: CGFloat = 120
    @Published var screenshotURL: URL? = nil
    @Published var chatHistory: [FloatingChatExchange] = []

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

    // Model selection
    @Published var selectedModel: String = "claude-sonnet-4-6"

    /// Available models for the floating bar picker
    static let availableModels: [(id: String, label: String)] = [
        ("claude-sonnet-4-6", "Sonnet"),
        ("claude-opus-4-6", "Opus"),
    ]
}
