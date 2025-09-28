import SwiftUI

struct AIConversationView: View {
    @ObservedObject var manager: FloatingChatWindowManager

    var body: some View {
        Group {
            if manager.isShowingAIResponse {
                AIResponseView(
                    isLoading: $manager.isAIResponseLoading,
                    responseText: $manager.aiResponseText,
                    userInput: manager.askAIInputText,
                    screenshotURL: manager.currentScreenshotURL,
                    width: manager.aiConversationWindowWidth,
                    onClose: {
                        manager.clearAndHideAIConversationWindow()
                    }
                )
                .transition(.opacity.animation(.easeInOut(duration: 0.2)))
            } else {
                AskAIInputView(
                    userInput: Binding(
                        get: { manager.askAIInputText },
                        set: { manager.askAIInputText = $0 }
                    ),
                    screenshotURL: manager.currentScreenshotURL,
                    width: manager.aiConversationWindowWidth,
                    onSend: { message, url in
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
        .animation(.easeInOut(duration: 0.2), value: manager.isShowingAIResponse)
    }
}
