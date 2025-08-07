import SwiftUI
import AVFoundation
import Speech

struct ChatView: View {
    var initialMessage: String = ""
    var onFirstMessageSent: (() -> Void)? = nil
    
    @State private var inputText = ""
    @State private var isRecording = false
    @State private var messages: [ChatMessage] = []
    @State private var isLoading = false
    @State private var showWelcomeMessage = true
    @State private var errorMessage: String?
    @State private var isInitialized = false
    @FocusState private var isTextFieldFocused: Bool
    
    // Voice recording properties
    @State private var audioEngine: AVAudioEngine?
    @State private var recognitionTask: SFSpeechRecognitionTask?
    @State private var recognitionRequest: SFSpeechAudioBufferRecognitionRequest?
    @State private var transcriptionText: String = ""
    
    // Use lazy initialization to avoid crashes during view creation
    private var apiClient: OmiAPIClient {
        OmiAPIClient.shared
    }
    
    private var messageSyncManager: MessageSyncManager {
        MessageSyncManager.shared
    }

    var body: some View {
        VStack(spacing: 0) {
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
                ScrollViewReader { proxy in
                    ScrollView {
                        LazyVStack(alignment: .leading, spacing: 10) {
                            ForEach(messages) { message in
                                ChatMessageView(message: message)
                                    .id(message.id) // assign unique ID
                            }
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 12)
                    }
                    .onChange(of: messages.count) { _ in
                        // Scroll to last message when new one appears
                        if let last = messages.last {
                            withAnimation {
                                proxy.scrollTo(last.id, anchor: .bottom)
                            }
                        }
                    }
                    .onAppear {
                        // Auto-scroll when view first appears and there's message history
                        if let last = messages.last {
                            DispatchQueue.main.asyncAfter(deadline: .now() + 0.1) {
                                withAnimation {
                                    proxy.scrollTo(last.id, anchor: .bottom)
                                }
                            }
                        }
                    }
                }
                .frame(minHeight: 300)
                .transition(.move(edge: .top))
                .animation(.easeInOut(duration: 0.3), value: messages.count)
            } else if showWelcomeMessage {
                VStack(spacing: 16) {
                    Text("Ready to chat! 😊")
                        .font(.system(size: 16, weight: .medium))
                        .foregroundColor(.white)
                        .multilineTextAlignment(.center)
                        .padding(.vertical, 20)
                }
            }

            // Input field with enhanced styling
            HStack(spacing: 12) {

                
                // Expand button
                Button(action: {
                    // Flush current messages to Flutter
                    messageSyncManager.flushMessagesToFlutter(messages)
                    
                    // Set flag for Flutter to open full chat
                    UserDefaults.standard.set(true, forKey: "swift_overlay_open_full_chat")
                    
                    // Activate Flutter app
                    NSRunningApplication.current.activate(options: [.activateAllWindows, .activateIgnoringOtherApps])
                    
                    // Hide current ChatView safely
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                        NSApp.keyWindow?.orderOut(nil)
                    }
                }) {
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
                    .focused($isTextFieldFocused)
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
        .padding(.vertical, 16)
        .background(
            RoundedRectangle(cornerRadius: 24)
                .fill(.ultraThinMaterial)
                .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
        )
        .clipShape(RoundedRectangle(cornerRadius: 24))
        .onAppear {
            // Prevent repeated initialization and initial message sending on re-open
            guard !isInitialized else { return }
            
            // Safely sync auth data first, then initialize with error handling
            DispatchQueue.main.async {
                do {
                    AuthBridge.shared.syncFromFlutterApp()
                    isInitialized = true
                    checkOmiConnection()
                    
                    // Focus the text field for better user experience
                    isTextFieldFocused = true
                    
                    // Auto-send initial message if provided
                    if !initialMessage.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        inputText = initialMessage
                        handleSendMessage()
                        
                        // Tell the popup to close
                        onFirstMessageSent?()
                    }
                } catch {
                    print("❌ Failed to initialize authentication")
                    errorMessage = "Authentication initialization failed"
                    isInitialized = false
                }
            }
        }
        .onReceive(NotificationCenter.default.publisher(for: NSApplication.didBecomeActiveNotification)) { _ in
            // Sync auth when app becomes active with error handling
            DispatchQueue.main.async {
                do {
                    AuthBridge.shared.forceSync()
                    checkOmiConnection()
                } catch {
                    print("❌ Failed to sync authentication on app activation")
                    errorMessage = "Authentication sync failed"
                }
            }
        }
    }

    private func checkOmiConnection() {
        // Sync authentication data from Flutter app with error handling
        do {
            AuthBridge.shared.forceSync()
        } catch {
            print("❌ Failed to sync authentication data")
            errorMessage = "Authentication sync failed. Please restart the app."
            return
        }
        
        if !OmiConfig.isConfigured() {
            let status = AuthBridge.shared.getAuthStatus()
            // Log minimal info for debugging without exposing sensitive data
            print("⚠️ Omi configuration incomplete")
            errorMessage = "Please sign in to Omi to use chat functionality"
            
            #if DEBUG
            // Only print debug info in debug builds, never in production
            print("Debug: Missing configuration fields count: \(status.missingData.count)")
            #endif
        } else {
            print("✅ Omi configuration successful")
            #if DEBUG
            // Only print configuration details in debug builds
            OmiConfig.printConfiguration()
            #endif
            errorMessage = nil
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
                            content: "Failed to send message. Please try again.", 
                            isUser: false
                        )
                    }
                    isLoading = false
                    errorMessage = "Failed to send message. Please check your connection."
                }
            }
        }
    }

    private func toggleVoiceRecording() {
        if isRecording {
            stopVoiceRecordingAndTranscribe()
        } else {
            startVoiceRecording()
        }
    }

    private func startVoiceRecording() {
        do {
            let engine = AVAudioEngine()
            let request = SFSpeechAudioBufferRecognitionRequest()
            recognitionRequest = request

            guard let recognizer = SFSpeechRecognizer(), recognizer.isAvailable else {
                errorMessage = "Speech recognizer not available"
                return
            }

            let inputNode = engine.inputNode
            request.shouldReportPartialResults = true

            recognitionTask = recognizer.recognitionTask(with: request) { result, error in
                if let result = result {
                    transcriptionText = result.bestTranscription.formattedString
                    
                    if result.isFinal {
                        stopVoiceRecordingAndTranscribe()
                    }
                }
                
                if let error = error {
                    print("❌ Transcription error: \(error.localizedDescription)")
                    stopVoiceRecordingAndTranscribe()
                }
            }

            let format = inputNode.outputFormat(forBus: 0)
            inputNode.installTap(onBus: 0, bufferSize: 1024, format: format) { buffer, _ in
                request.append(buffer)
            }

            engine.prepare()
            try engine.start()

            audioEngine = engine
            isRecording = true
            transcriptionText = ""

        } catch {
            print("❌ Failed to start recording: \(error)")
            errorMessage = "Failed to start voice recording"
            isRecording = false
        }
    }

    private func stopVoiceRecordingAndTranscribe() {
        guard isRecording else { return }  // Prevent duplicate calls
        isRecording = false

        audioEngine?.stop()
        audioEngine?.inputNode.removeTap(onBus: 0)
        recognitionRequest?.endAudio()

        recognitionTask?.cancel()
        recognitionTask = nil
        audioEngine = nil
        recognitionRequest = nil

        if !transcriptionText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            inputText = transcriptionText
            transcriptionText = "" // reset to prevent double-send
            handleSendMessage()
        } else {
            errorMessage = "Could not recognize any speech"
        }
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

// MARK: - Preview
#if DEBUG
struct ChatView_Previews: PreviewProvider {
    static var previews: some View {
        Group {
            ChatView()
                .preferredColorScheme(.dark)
                .previewDisplayName("Empty Chat")
            
            ChatView(initialMessage: "Hello, how are you today?")
                .preferredColorScheme(.dark)
                .previewDisplayName("With Initial Message")
        }
    }
}
#endif
