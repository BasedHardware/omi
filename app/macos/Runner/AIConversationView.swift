import SwiftUI

struct AIConversationView: View {
    @ObservedObject var manager: FloatingChatWindowManager
    @State private var displayedQuery: String = ""

    var body: some View {
        Group {
            if manager.isShowingAIResponse {
                AIResponseView(
                    isLoading: $manager.isAIResponseLoading,
                    responseText: $manager.aiResponseText,
                    userInput: displayedQuery,
                    screenshotURL: manager.currentScreenshotURL,
                    width: manager.aiConversationWindowWidth,
                    onClose: {
                        manager.clearAndHideAIConversationWindow()
                    },
                    onAskFollowUp: {
                        manager.isShowingAIResponse = false
                        manager.aiResponseText = ""
                        manager.askAIInputText = ""
                        manager.isAIResponseLoading = false
                        manager.removeScreenshotFromAIConversation()
                    }
                )
            } else {
                AskAIInputView(
                    userInput: Binding(
                        get: { manager.askAIInputText },
                        set: { manager.askAIInputText = $0 }
                    ),
                    screenshotURL: manager.currentScreenshotURL,
                    width: manager.aiConversationWindowWidth,
                    onSend: { message, url in
                        displayedQuery = message
                        manager.isShowingAIResponse = true
                        manager.isAIResponseLoading = true
                        manager.aiResponseText = ""
                        manager.sendAIQuery(message: message, url: url)
                    },
                    onCancel: {
                        manager.clearAndHideAIConversationWindow()
                    },
                    onRemoveScreenshot: {
                        manager.removeScreenshotFromAIConversation()
                    }
                )
                .transition(.opacity.animation(.easeInOut(duration: 0.2)))
            }
        }
    }
}
