import SwiftUI

struct ChatView: View {
    @State private var inputText = ""
    @State private var isRecording = false
    @State private var messages: [ChatMessage] = []
    @State private var isLoading = false
    @State private var showWelcomeMessage = true
    @State private var errorMessage: String?
    @State private var isInitialized = false
    
    // Use lazy initialization to avoid crashes during view creation
    private var apiClient: OmiAPIClient {
        OmiAPIClient.shared
    }
    
    private var messageSyncManager: MessageSyncManager {
        MessageSyncManager.shared
    }

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
            
            // Error message display
            if let error = errorMessage {
                VStack(spacing: 8) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.system(size: 20))
                        .foregroundColor(.orange)
                    
                    Text(error)
                        .font(.system(size: 14))
                        .foregroundColor(.white.opacity(0.8))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 16)
                    
                    Button("Retry Connection") {
                        checkOmiConnection()
                        if OmiConfig.isConfigured() {
                            loadInitialMessages()
                        }
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(Color.blue.opacity(0.6))
                    .foregroundColor(.white)
                    .font(.system(size: 12, weight: .medium))
                    .cornerRadius(8)
                }
                .padding(.vertical, 16)
                .transition(.opacity.combined(with: .move(edge: .top)))
                .animation(.easeInOut(duration: 0.3), value: errorMessage)
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
            // Safely sync auth data first, then initialize
            DispatchQueue.main.async {
                AuthBridge.shared.syncFromFlutterApp()
                isInitialized = true
                checkOmiConnection()
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            // Sync auth when app becomes active
            DispatchQueue.main.async {
                AuthBridge.shared.forceSync()
                checkOmiConnection()
            }
        }
    }

    private func checkOmiConnection() {
        // Force sync authentication data from Flutter app
        AuthBridge.shared.forceSync()
        
        if !OmiConfig.isConfigured() {
            let status = AuthBridge.shared.getAuthStatus()
            print("Omi not configured. Missing: \(status.missingData.joined(separator: ", "))")
            errorMessage = "Please sign in to Omi to use chat functionality"
            
            // Debug: Print available keys to help with integration
            AuthBridge.shared.printAvailableKeys()
        } else {
            print("✅ Omi configuration successful")
            OmiConfig.printConfiguration()
            errorMessage = nil
        }
    }
    
    private func loadInitialMessages() {
        guard OmiConfig.isConfigured() else { 
            errorMessage = "Authentication required. Please sign in to Omi."
            return 
        }
        
        Task {
            do {
                let serverMessages = try await apiClient.getMessages(appId: OmiConfig.selectedAppId)
                await MainActor.run {
                    // Convert server messages to local chat messages
                    messages = serverMessages.reversed().map { serverMessage in
                        ChatMessage(
                            content: serverMessage.text,
                            isUser: serverMessage.sender == "human"
                        )
                    }
                    
                    // If no messages, get initial message
                    if messages.isEmpty {
                        loadInitialMessage()
                    } else {
                        showWelcomeMessage = false
                    }
                    
                    // Clear any previous error messages on success
                    errorMessage = nil
                }
            } catch APIError.authenticationRequired {
                await MainActor.run {
                    print("Authentication required for loading messages")
                    errorMessage = "Please sign in to Omi to view messages"
                    showWelcomeMessage = true
                }
            } catch {
                await MainActor.run {
                    print("Failed to load messages: \(error)")
                    errorMessage = "Failed to load messages. Please check your connection."
                    // Show welcome message as fallback
                    showWelcomeMessage = true
                }
            }
        }
    }
    
    private func loadInitialMessage() {
        guard OmiConfig.isConfigured() else { return }
        
        Task {
            do {
                let initialMessage = try await apiClient.getInitialMessage(appId: OmiConfig.selectedAppId)
                await MainActor.run {
                    let chatMessage = ChatMessage(content: initialMessage.text, isUser: false)
                    messages.append(chatMessage)
                    showWelcomeMessage = false
                }
            } catch {
                await MainActor.run {
                    print("Failed to get initial message: \(error)")
                    // Keep welcome message
                }
            }
        }
    }

    private func handleSendMessage() {
        guard !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard OmiConfig.isConfigured() else {
            errorMessage = "Please sign in to Omi to send messages"
            return
        }

        // Hide welcome message when first message is sent
        if showWelcomeMessage {
            showWelcomeMessage = false
        }

        let userMessage = ChatMessage(content: inputText, isUser: true)
        messages.append(userMessage)
        
        // Sync user message to Flutter app
        messageSyncManager.syncMessageToFlutter(userMessage)

        let messageToSend = inputText
        inputText = ""
        isLoading = true
        errorMessage = nil

        sendToOmiChat(message: messageToSend)
    }
    
    private func sendToOmiChat(message: String) {
        print("Sending to Omi: \(message)")
        
        Task {
            do {
                var responseText = ""
                // var finalMessage: ServerMessage? // Unused for now
                
                // Create a placeholder AI message
                let aiMessage = ChatMessage(content: "", isUser: false)
                await MainActor.run {
                    messages.append(aiMessage)
                }
                
                // Stream the response
                for try await chunk in apiClient.sendMessage(
                    text: message, 
                    appId: OmiConfig.selectedAppId
                ) {
                    await MainActor.run {
                        switch chunk.type {
                        case "think":
                            // Handle thinking chunks (optional: show typing indicator)
                            break
                        case "data":
                            // Update the AI message with streaming text
                            responseText += chunk.text
                            if let lastIndex = messages.indices.last {
                                messages[lastIndex] = ChatMessage(content: responseText, isUser: false)
                            }
                        case "done":
                            // Final message received
                            if let serverMessage = chunk.message {
                                // finalMessage = serverMessage // Unused for now
                                if let lastIndex = messages.indices.last {
                                    let aiMessage = ChatMessage(content: serverMessage.text, isUser: false)
                                    messages[lastIndex] = aiMessage
                                    // Sync AI response to Flutter app
                                    messageSyncManager.syncMessageToFlutter(aiMessage)
                                }
                            }
                        case "error":
                            // Handle error
                            if let lastIndex = messages.indices.last {
                                messages[lastIndex] = ChatMessage(content: "Error: \(chunk.text)", isUser: false)
                            }
                        default:
                            break
                        }
                    }
                }
                
                await MainActor.run {
                    isLoading = false
                }
                
            } catch APIError.authenticationRequired {
                await MainActor.run {
                    // Update the last message with auth error
                    if let lastIndex = messages.indices.last {
                        messages[lastIndex] = ChatMessage(
                            content: "Authentication required. Please sign in to Omi to send messages.", 
                            isUser: false
                        )
                    }
                    isLoading = false
                    errorMessage = "Please sign in to Omi to send messages"
                }
            } catch {
                await MainActor.run {
                    // Update the last message with error
                    if let lastIndex = messages.indices.last {
                        messages[lastIndex] = ChatMessage(
                            content: "Failed to send message: \(error.localizedDescription)", 
                            isUser: false
                        )
                    }
                    isLoading = false
                    errorMessage = error.localizedDescription
                }
            }
        }
    }

    private func toggleVoiceRecording() {
        isRecording.toggle()
        if isRecording {
            startVoiceRecording()
        } else {
            stopVoiceRecording()
        }
    }

    private func startVoiceRecording() {
        print("Voice recording started (implementation needed)")
        // TODO: Implement voice recording using AVAudioRecorder
        // TODO: Send audio to Omi voice message endpoint
    }

    private func stopVoiceRecording() {
        print("Voice recording stopped")
        isRecording = false
        // TODO: Stop recording and process audio
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
