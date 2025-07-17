import SwiftUI

struct ChatView: View {
    @State private var inputText = ""
    @State private var isRecording = false
    @State private var messages: [ChatMessage] = []
    @State private var isLoading = false
    @State private var showWelcomeMessage = true

    var body: some View {
        VStack(spacing: 0) {
            // Welcome message when no conversation has started
            if messages.isEmpty && showWelcomeMessage {
                VStack(spacing: 16) {
                    Text("Hey there! How can I help you today? 😊")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 24)
                        .padding(.top, 20)
                    
                    // Action buttons row
                    HStack(spacing: 12) {
                        ActionButton(icon: "square.and.arrow.up", action: {})
                        ActionButton(icon: "speaker.wave.2", action: {})
                        ActionButton(icon: "hand.thumbsup", action: {})
                        ActionButton(icon: "hand.thumbsdown", action: {})
                        ActionButton(icon: "arrow.clockwise", action: {})
                    }
                    .padding(.bottom, 20)
                }
                .transition(.opacity.combined(with: .scale))
                .animation(.easeInOut(duration: 0.3), value: showWelcomeMessage)
            }
            
            // Chat messages when conversation has started
            if !messages.isEmpty {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        ForEach(messages) { message in
                            ChatMessageView(message: message)
                        }
                    }
                    .padding(.horizontal, 16)
                    .padding(.top, 12)
                }
                .frame(maxHeight: 240)
                .transition(.move(edge: .top))
                .animation(.easeInOut(duration: 0.3), value: messages.count)
            }

            // Input field with enhanced styling
            HStack(spacing: 12) {
                // Plus button
                Button(action: {}) {
                    Image(systemName: "plus")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
                .buttonStyle(.plain)
                
                // Web button
                Button(action: {}) {
                    Image(systemName: "globe")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
                .buttonStyle(.plain)
                
                // Share button
                Button(action: {}) {
                    Image(systemName: "square.and.arrow.up")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
                .buttonStyle(.plain)
                
                // Expand button
                Button(action: {}) {
                    Image(systemName: "arrow.up.left.and.arrow.down.right")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white.opacity(0.7))
                }
                .buttonStyle(.plain)
                
                Spacer()
                
                TextField("Ask anything", text: $inputText)
                    .textFieldStyle(PlainTextFieldStyle())
                    .foregroundColor(.white)
                    .font(.system(size: 14))
                    .onSubmit {
                        handleSendMessage()
                    }
                
                Spacer()

                if isLoading {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .white))
                        .scaleEffect(0.8)
                } else {
                    // Voice recording button
                    Button(action: toggleVoiceRecording) {
                        Image(systemName: isRecording ? "waveform" : "mic")
                            .font(.system(size: 16, weight: .medium))
                            .foregroundColor(isRecording ? .red : .white)
                    }
                    .buttonStyle(.plain)
                    
                    // Send/Up arrow button
                    Button(action: {
                        if !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                            handleSendMessage()
                        }
                    }) {
                        Image(systemName: "arrow.up")
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.black)
                            .frame(width: 24, height: 24)
                            .background(Circle().fill(.white))
                    }
                    .buttonStyle(.plain)
                    .opacity(inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.5 : 1.0)
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(
                RoundedRectangle(cornerRadius: 24)
                    .fill(.ultraThinMaterial)
                    .overlay(
                        RoundedRectangle(cornerRadius: 24)
                            .stroke(
                                LinearGradient(colors: [.white.opacity(0.2), .purple.opacity(0.2)], startPoint: .topLeading, endPoint: .bottomTrailing),
                                lineWidth: 1
                            )
                    )
            )
            .padding(.horizontal, 16)
            .padding(.bottom, 16)
        }
        .frame(width: 420)
        .padding(.vertical, 16)
        .background(
            RoundedRectangle(cornerRadius: 24)
                .fill(.ultraThinMaterial)
                .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
        )
        .clipShape(RoundedRectangle(cornerRadius: 24))
        .onAppear {
            checkOmiConnection()
        }
    }

    private func checkOmiConnection() {
        if !OmiConfig.isConfigured() {
            print("Omi not configured. Please authenticate.")
        } else {
            OmiConfig.printConfiguration()
        }
    }

    private func handleSendMessage() {
        guard !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }

        // Hide welcome message when first message is sent
        if showWelcomeMessage {
            showWelcomeMessage = false
        }

        let userMessage = ChatMessage(content: inputText, isUser: true)
        messages.append(userMessage)

        let messageToSend = inputText
        inputText = ""
        isLoading = true

        sendToOmiChat(message: messageToSend)
    }

    private func toggleVoiceRecording() {
        isRecording.toggle()
        if isRecording {
            startVoiceRecording()
        } else {
            stopVoiceRecording()
        }
    }

    private func sendToOmiChat(message: String) {
        print("Sending to Omi: \(message)")

        // Simulated response
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.0) {
            let response = ChatMessage(
                content: "Simulated Omi response. Replace this with real API call.",
                isUser: false
            )
            self.messages.append(response)
            self.isLoading = false
        }
    }

    private func startVoiceRecording() {
        print("Voice recording started (simulate integration here)")
    }

    private func stopVoiceRecording() {
        print("Voice recording stopped")
        isRecording = false
    }
}

// MARK: - Action Button Component
struct ActionButton: View {
    let icon: String
    let action: () -> Void
    
    var body: some View {
        Button(action: action) {
            Image(systemName: icon)
                .font(.system(size: 14, weight: .medium))
                .foregroundColor(.white.opacity(0.8))
                .frame(width: 32, height: 32)
                .background(
                    Circle()
                        .fill(.ultraThinMaterial)
                        .overlay(
                            Circle()
                                .stroke(.white.opacity(0.2), lineWidth: 1)
                        )
                )
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Message Model
struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    let content: String
    let isUser: Bool
    let timestamp = Date()
}

// MARK: - Chat Bubble
struct ChatMessageView: View {
    let message: ChatMessage

    var body: some View {
        HStack {
            if message.isUser {
                Spacer()
                Text(message.content)
                    .font(.system(size: 14))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(
                                LinearGradient(
                                    colors: [Color.blue.opacity(0.8), Color.purple.opacity(0.6)], 
                                    startPoint: .topLeading, 
                                    endPoint: .bottomTrailing
                                )
                            )
                    )
                    .foregroundColor(.white)
                    .frame(maxWidth: 280, alignment: .trailing)
            } else {
                HStack(alignment: .top, spacing: 8) {
                    // Omi avatar/icon
                    Circle()
                        .fill(.ultraThinMaterial)
                        .frame(width: 24, height: 24)
                        .overlay(
                            Text("O")
                                .font(.system(size: 12, weight: .bold))
                                .foregroundColor(.white)
                        )
                    
                    Text(message.content)
                        .font(.system(size: 14))
                        .padding(.horizontal, 16)
                        .padding(.vertical, 10)
                        .background(
                            RoundedRectangle(cornerRadius: 16)
                                .fill(.ultraThinMaterial)
                                .overlay(
                                    RoundedRectangle(cornerRadius: 16)
                                        .stroke(.white.opacity(0.1), lineWidth: 1)
                                )
                        )
                        .foregroundColor(.white)
                        .frame(maxWidth: 280, alignment: .leading)
                }
                Spacer()
            }
        }
        .padding(.horizontal, 8)
    }
}

// MARK: - Preview
#if DEBUG
struct ChatView_Previews: PreviewProvider {
    static var previews: some View {
        ChatView()
            .preferredColorScheme(.dark)
    }
}
#endif
