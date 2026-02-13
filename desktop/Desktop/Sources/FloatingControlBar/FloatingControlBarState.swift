import Combine
import SwiftUI

/// Observable object holding the state for the floating control bar.
@MainActor
class FloatingControlBarState: ObservableObject {
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
}
