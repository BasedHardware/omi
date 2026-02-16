import Combine
import SwiftUI

/// A single question/answer exchange in the chat history.
struct ChatExchange: Identifiable {
    let id = UUID()
    let question: String
    let response: String
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
    @Published var aiResponseText: String = ""
    @Published var displayedQuery: String = ""
    @Published var inputViewHeight: CGFloat = 120
    @Published var screenshotURL: URL? = nil
    @Published var chatHistory: [ChatExchange] = []

    // Push-to-talk state
    @Published var isVoiceListening: Bool = false
    @Published var isVoiceLocked: Bool = false
    @Published var voiceTranscript: String = ""

    // Voice follow-up state (PTT while AI conversation is active)
    @Published var isVoiceFollowUp: Bool = false
    @Published var voiceFollowUpTranscript: String = ""
}
