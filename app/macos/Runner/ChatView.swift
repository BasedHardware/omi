import SwiftUI

struct ChatView: View {
    @State private var inputText = ""
    @State private var isRecording = false
    @State private var messages: [ChatMessage] = []
    @State private var isLoading = false
    
    var body: some View {
        VStack(spacing: 0) {
            // Chat messages area (initially hidden, will expand when there are messages)
            if !messages.isEmpty {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(messages) { message in
                            ChatMessageView(message: message)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                }
                .frame(maxHeight: 200) // Limit height to keep it manageable
                .background(Color.black.opacity(0.9))
            }
            
            // Main input area
            HStack(spacing: 12) {
                TextField("Ask Omi anything...", text: $inputText)
                    .textFieldStyle(PlainTextFieldStyle())
                    .foregroundColor(.white)
                    .padding(.leading, 16)
                    .frame(height: 44)
                    .disabled(isLoading)
                    .onSubmit {
                        handleSendMessage()
                    }

                if isLoading {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                        .scaleEffect(0.8)
                        .padding(.trailing, 8)
                } else {
                    Button(action: {
                        toggleVoiceRecording()
                    }) {
                        Image(systemName: isRecording ? "stop.circle.fill" : "mic.circle.fill")
                            .resizable()
                            .frame(width: 28, height: 28)
                            .foregroundColor(isRecording ? .red : .white)
                            .padding(.trailing, 16)
                    }
                    .buttonStyle(PlainButtonStyle())
                }
            }
            .frame(height: 60)
            .background(Color.black.opacity(0.95))
            .cornerRadius(14)
            .padding()
        }
        .frame(maxWidth: .infinity)
        .background(Color.clear)
        .onAppear {
            checkOmiConnection()
        }
    }
    
    private func checkOmiConnection() {
        if !OmiConfig.isConfigured() {
            print("Omi not configured. User needs to authenticate through main app.")
            // Could show a message or redirect to main app
        } else {
            print("Omi is configured and ready")
            OmiConfig.printConfiguration()
        }
    }
    
    private func handleSendMessage() {
        guard !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        
        let userMessage = ChatMessage(content: inputText, isUser: true)
        messages.append(userMessage)
        
        let messageToSend = inputText
        inputText = ""
        isLoading = true
        
        // Send to Omi
        sendToOmiChat(message: messageToSend)
    }
    
    private func toggleVoiceRecording() {
        isRecording.toggle()
        
        if isRecording {
            print("Starting voice recording...")
            startVoiceRecording()
        } else {
            print("Stopping voice recording...")
            stopVoiceRecording()
        }
    }
    
    private func sendToOmiChat(message: String) {
        print("Sending to Omi: \(message)")
        
        // TODO: Implement actual API call to Omi chat endpoint
        // For now, simulate a response
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            let response = ChatMessage(
                content: "This is a simulated response from Omi. Integration with actual API endpoints will be implemented next.",
                isUser: false
            )
            self.messages.append(response)
            self.isLoading = false
        }
    }
    
    private func startVoiceRecording() {
        // TODO: Implement voice recording functionality
        // This should integrate with Omi's audio processing pipeline
        print("Voice recording started - will integrate with Omi audio pipeline")
    }
    
    private func stopVoiceRecording() {
        // TODO: Stop recording and send audio to Omi for processing
        print("Voice recording stopped - will process with Omi")
        isRecording = false
    }
}

// Chat message model
struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    let content: String
    let isUser: Bool
    let timestamp = Date()
}

// Chat message view component
struct ChatMessageView: View {
    let message: ChatMessage
    
    var body: some View {
        HStack {
            if message.isUser {
                Spacer()
                Text(message.content)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.blue.opacity(0.8))
                    .foregroundColor(.white)
                    .cornerRadius(12)
                    .frame(maxWidth: 250, alignment: .trailing)
            } else {
                Text(message.content)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 8)
                    .background(Color.gray.opacity(0.3))
                    .foregroundColor(.white)
                    .cornerRadius(12)
                    .frame(maxWidth: 250, alignment: .leading)
                Spacer()
            }
        }
    }
}

// Preview for SwiftUI development
#if DEBUG
struct ChatView_Previews: PreviewProvider {
    static var previews: some View {
        ChatView()
            .frame(width: 420, height: 300)
            .background(Color.black.opacity(0.1))
    }
}
#endif
