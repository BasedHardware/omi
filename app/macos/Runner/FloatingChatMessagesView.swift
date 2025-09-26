import SwiftUI

struct ChatMessage: Identifiable {
    let id = UUID()
    let text: String
    let attachmentURL: URL?
    let type: FloatingChatMessageBubble.BubbleType
}

struct FloatingChatMessagesView: View {
    @State private var messages: [ChatMessage] = []
    
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(spacing: 10) {
                    ForEach(messages) { message in
                        FloatingChatMessageBubble(
                            message: message.text,
                            attachmentURL: message.attachmentURL,
                            type: message.type
                        )
                        .id(message.id)
                    }
                }
                .padding(10)
            }
            .accessibilityLabel("Chat messages")
            .onChange(of: messages.count) { _ in
                if let lastMessage = messages.last {
                    withAnimation(.easeOut(duration: 0.3)) {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
    }
    
    func addMessage(text: String, attachmentURL: URL?, type: FloatingChatMessageBubble.BubbleType, animated: Bool = true) {
        let newMessage = ChatMessage(text: text, attachmentURL: attachmentURL, type: type)
        
        if animated {
            withAnimation(.easeOut(duration: 0.3)) {
                messages.append(newMessage)
            }
        } else {
            messages.append(newMessage)
        }
    }
    
    func updateLastAIMessage(text: String) {
        if let lastIndex = messages.lastIndex(where: { $0.type == .ai }) {
            messages[lastIndex] = ChatMessage(text: text, attachmentURL: messages[lastIndex].attachmentURL, type: .ai)
        }
    }
    
    func clearMessages() {
        messages.removeAll()
    }
    
    func displayHistory(messagesData: [[String: Any]]) {
        var newMessages: [ChatMessage] = []
        
        for messageData in messagesData {
            guard let text = messageData["text"] as? String,
                  let typeString = messageData["type"] as? String else {
                continue
            }
            
            let type: FloatingChatMessageBubble.BubbleType = (typeString == "user") ? .user : .ai
            let attachmentPath = messageData["attachmentPath"] as? String
            let attachmentURL = attachmentPath != nil ? URL(fileURLWithPath: attachmentPath!) : nil
            
            newMessages.append(ChatMessage(text: text, attachmentURL: attachmentURL, type: type))
        }
        
        messages = newMessages
    }
}
