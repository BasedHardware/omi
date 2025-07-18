import SwiftUI
import Combine
import AVFoundation
import Speech

// Voice popup state for managing different UI states
enum VoicePopupState: Equatable {
    case idle
    case recording
    case transcribing
    case transcribed(String)
    case success(String)
    case error(String)
}

// Simple voice recorder for the popup
class SimpleVoiceRecorder: NSObject, ObservableObject {
    @Published var isRecording = false
    @Published var audioLevel: Float = 0.0
    @Published var recordingDuration: TimeInterval = 0.0
    
    private var audioRecorder: AVAudioRecorder?
    private var audioLevelTimer: Timer?
    private var recordingTimer: Timer?
    private var recordingStartTime: Date?
    
    func startRecording() async -> Bool {
        print("🎙️ Starting voice recording...")
        
        // Check permissions first
        guard await checkMicrophonePermission() else {
            print("❌ Microphone permission denied")
            return false
        }
        
        // Setup audio session
        do {
            try setupAudioSession()
        } catch {
            print("❌ Failed to setup audio session: \(error)")
            return false
        }
        
        // Create temporary file for recording
        let tempURL = createTempAudioFileURL()
        
        // Configure audio recorder
        let settings: [String: Any] = [
            AVFormatIDKey: Int(kAudioFormatLinearPCM),
            AVSampleRateKey: 16000.0,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsFloatKey: false,
            AVEncoderAudioQualityKey: AVAudioQuality.high.rawValue
        ]
        
        do {
            audioRecorder = try AVAudioRecorder(url: tempURL, settings: settings)
            audioRecorder?.delegate = self
            audioRecorder?.isMeteringEnabled = true
            
            guard let recorder = audioRecorder else {
                print("❌ Failed to create audio recorder")
                return false
            }
            
            if recorder.record() {
                await MainActor.run {
                    isRecording = true
                    recordingStartTime = Date()
                    startAudioLevelMonitoring()
                    startRecordingTimer()
                }
                print("✅ Recording started successfully")
                return true
            } else {
                print("❌ Failed to start recording")
                return false
            }
        } catch {
            print("❌ Failed to setup recorder: \(error)")
            return false
        }
    }
    
    func stopRecording() -> URL? {
        print("🎙️ Stopping voice recording...")
        
        guard let recorder = audioRecorder else {
            print("❌ No active recording")
            return nil
        }
        
        stopAudioLevelMonitoring()
        stopRecordingTimer()
        
        let recordingURL = recorder.url
        recorder.stop()
        
        isRecording = false
        
        // Check if file exists and has content
        if FileManager.default.fileExists(atPath: recordingURL.path) {
            do {
                let attributes = try FileManager.default.attributesOfItem(atPath: recordingURL.path)
                let fileSize = attributes[.size] as? NSNumber ?? 0
                
                if fileSize.intValue > 0 {
                    print("✅ Recording saved successfully. File size: \(fileSize) bytes")
                    return recordingURL
                } else {
                    print("❌ Recording file is empty")
                    return nil
                }
            } catch {
                print("❌ Failed to check recording file: \(error)")
                return nil
            }
        } else {
            print("❌ Recording file does not exist")
            return nil
        }
    }
    
    func cancelRecording() {
        guard let recorder = audioRecorder else { return }
        
        stopAudioLevelMonitoring()
        stopRecordingTimer()
        recorder.stop()
        recorder.deleteRecording()
        
        isRecording = false
        audioRecorder = nil
        recordingStartTime = nil
        recordingDuration = 0.0
    }
    
    // MARK: - Private Methods
    
    private func checkMicrophonePermission() async -> Bool {
        return await PermissionManager.shared.requestMicrophonePermission()
    }
    
    private func setupAudioSession() throws {
        // On macOS, we don't need to configure audio session like iOS
        // AVAudioRecorder handles the audio setup automatically
        print("✅ Audio session ready for recording on macOS")
    }
    
    private func createTempAudioFileURL() -> URL {
        let tempDir = FileManager.default.temporaryDirectory
        let fileName = "voice_recording_\(Date().timeIntervalSince1970).wav"
        return tempDir.appendingPathComponent(fileName)
    }
    
    private func startAudioLevelMonitoring() {
        audioLevelTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let recorder = self.audioRecorder else { return }
            
            recorder.updateMeters()
            let averagePower = recorder.averagePower(forChannel: 0)
            
            // Convert decibel level to 0-1 range for UI
            let normalizedLevel = pow(10.0, averagePower / 20.0)
            
            DispatchQueue.main.async {
                self.audioLevel = Float(normalizedLevel)
            }
        }
    }
    
    private func stopAudioLevelMonitoring() {
        audioLevelTimer?.invalidate()
        audioLevelTimer = nil
        
        DispatchQueue.main.async {
            self.audioLevel = 0.0
        }
    }
    
    private func startRecordingTimer() {
        recordingTimer = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            guard let self = self, let startTime = self.recordingStartTime else { return }
            
            let duration = Date().timeIntervalSince(startTime)
            
            DispatchQueue.main.async {
                self.recordingDuration = duration
            }
        }
    }
    
    private func stopRecordingTimer() {
        recordingTimer?.invalidate()
        recordingTimer = nil
    }
}

// MARK: - AVAudioRecorderDelegate
extension SimpleVoiceRecorder: AVAudioRecorderDelegate {
    func audioRecorderDidFinishRecording(_ recorder: AVAudioRecorder, successfully flag: Bool) {
        print("🎙️ Recording finished. Success: \(flag)")
    }
    
    func audioRecorderEncodeErrorDidOccur(_ recorder: AVAudioRecorder, error: Error?) {
        print("❌ Recording encode error: \(error?.localizedDescription ?? "Unknown error")")
    }
}

struct VoiceAssistantPopup: View {
    @State private var isChatVisible = false
    @StateObject private var voiceRecorder = SimpleVoiceRecorder()
    @State private var popupState: VoicePopupState = .idle
    @State private var transcribedText = ""
    @State private var editableText = ""
    @State private var isLoading = false
    @State private var apiResponse = ""
    @State private var isViewActive = true

    var body: some View {
        ZStack {
            Color(.windowBackgroundColor)
                .ignoresSafeArea()

            if isChatVisible {
                SafeChatView()
                    .transition(.move(edge: .bottom).combined(with: .opacity))
                    .animation(.easeInOut(duration: 0.3), value: isChatVisible)
            } else {
                VStack(spacing: 20) {
                    Text(titleText)
                        .font(.title2)
                        .bold()
                        .foregroundColor(.white)
                        .multilineTextAlignment(.center)
                        .transition(.opacity)

                    // Main content based on state
                    Group {
                        switch popupState {
                        case .idle:
                            idleView
                        case .recording:
                            recordingView
                        case .transcribing:
                            transcribingView
                        case .transcribed(let text):
                            transcribedView(text: text)
                        case .success(let text):
                            successView(text: text)
                        case .error(let message):
                            errorView(message: message)
                        }
                    }
                    .transition(.opacity.combined(with: .scale))
                    .animation(.easeInOut(duration: 0.3), value: popupState)

                    // "Type Instead" Button
                    Button(action: {
                        withAnimation(.easeInOut(duration: 0.3)) {
                            isChatVisible = true
                        }
                    }) {
                        Text("Type Instead")
                            .fontWeight(.medium)
                            .foregroundColor(.white)
                            .padding(.horizontal, 20)
                            .padding(.vertical, 10)
                    }
                    .buttonStyle(PlainButtonStyle())
                    .background(
                        RoundedRectangle(cornerRadius: 20)
                            .stroke(.white.opacity(0.3), lineWidth: 1)
                            .background(RoundedRectangle(cornerRadius: 20).fill(.ultraThinMaterial))
                    )
                    .padding(.horizontal)
                }
                .padding(24)
                .background(
                    RoundedRectangle(cornerRadius: 30)
                        .fill(.ultraThinMaterial)
                        .overlay(
                            RoundedRectangle(cornerRadius: 30)
                                .stroke(
                                    LinearGradient(colors: [.white.opacity(0.2), .purple.opacity(0.2)], startPoint: .topLeading, endPoint: .bottomTrailing),
                                    lineWidth: 1
                                )
                        )
                )
                .shadow(color: .black.opacity(0.3), radius: 20, x: 0, y: 10)
                .transition(.move(edge: .top).combined(with: .opacity))
                .animation(.easeInOut(duration: 0.3), value: isChatVisible)
            }
        }
        .onAppear {
            isViewActive = true
            popupState = .idle
        }
        .onDisappear {
            isViewActive = false
            voiceRecorder.cancelRecording()
        }
    }

    // MARK: - State Views
    
    private var idleView: some View {
        VStack(spacing: 16) {
            Text("Hold to speak or click to start recording")
                .font(.caption)
                .foregroundColor(.white.opacity(0.7))
                .multilineTextAlignment(.center)
            
            Button(action: {
                startRecording()
            }) {
                ZStack {
                    Circle()
                        .fill(Color.purple.opacity(0.2))
                        .frame(width: 80, height: 80)
                    
                    Circle()
                        .stroke(Color.purple, lineWidth: 2)
                        .frame(width: 80, height: 80)
                    
                    Image(systemName: "mic.fill")
                        .resizable()
                        .scaledToFit()
                        .frame(height: 30)
                        .foregroundColor(.purple)
                }
            }
            .buttonStyle(PlainButtonStyle())
            .simultaneousGesture(
                DragGesture(minimumDistance: 0)
                    .onChanged { _ in
                        if popupState == .idle {
                            startRecording()
                        }
                    }
                    .onEnded { _ in
                        if popupState == .recording {
                            stopRecordingAndTranscribe()
                        }
                    }
            )
        }
    }
    
    private var recordingView: some View {
        VStack(spacing: 16) {
            Button(action: {
                stopRecordingAndTranscribe()
            }) {
                ZStack {
                    // Animated rings based on audio level
                    ForEach(0..<3, id: \.self) { index in
                        Circle()
                            .stroke(Color.red.opacity(0.3), lineWidth: 2)
                            .scaleEffect(1.0 + (CGFloat(voiceRecorder.audioLevel) * CGFloat(index + 1) * 0.5))
                            .opacity(Double(voiceRecorder.audioLevel))
                            .animation(.easeInOut(duration: 0.5).repeatForever(autoreverses: true), value: voiceRecorder.audioLevel)
                    }
                    
                    Circle()
                        .fill(Color.red.opacity(0.2))
                        .frame(width: 80, height: 80)
                    
                    Circle()
                        .stroke(Color.red, lineWidth: 2)
                        .frame(width: 80, height: 80)
                    
                    // Stop icon instead of microphone
                    RoundedRectangle(cornerRadius: 4)
                        .fill(Color.red)
                        .frame(width: 24, height: 24)
                }
            }
            .buttonStyle(PlainButtonStyle())
            .frame(height: 80)
            
            VStack(spacing: 4) {
                Text("Recording...")
                    .font(.headline)
                    .foregroundColor(.white)
                
                Text(formatDuration(voiceRecorder.recordingDuration))
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.7))
                    .monospacedDigit()
                
                Text("Release to stop")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.5))
            }
        }
    }
    
    private var transcribingView: some View {
        VStack(spacing: 16) {
            ProgressView()
                .progressViewStyle(CircularProgressViewStyle(tint: .purple))
                .scaleEffect(1.5)
            
            Text("Transcribing audio...")
                .font(.headline)
                .foregroundColor(.white)
        }
    }
    
    private func transcribedView(text: String) -> some View {
        VStack(spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Review and edit your message:")
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.7))
                
                HStack {
                    TextField("Your message", text: $editableText, axis: .vertical)
                        .textFieldStyle(PlainTextFieldStyle())
                        .padding(12)
                        .background(
                            RoundedRectangle(cornerRadius: 12)
                                .fill(Color.black.opacity(0.2))
                                .overlay(
                                    RoundedRectangle(cornerRadius: 12)
                                        .stroke(Color.white.opacity(0.3), lineWidth: 1)
                                )
                        )
                        .foregroundColor(.white)
                        .font(.body)
                        .lineLimit(3...6)
                    
                    Button(action: {
                        sendToAPI()
                    }) {
                        if isLoading {
                            ProgressView()
                                .progressViewStyle(CircularProgressViewStyle(tint: .white))
                                .scaleEffect(0.8)
                        } else {
                            Image(systemName: "arrow.up")
                                .font(.system(size: 16, weight: .bold))
                                .foregroundColor(.white)
                        }
                    }
                    .frame(width: 36, height: 36)
                    .background(
                        Circle()
                            .fill(Color.purple)
                    )
                    .disabled(editableText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isLoading)
                    .opacity(editableText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? 0.5 : 1.0)
                }
            }
            .padding(.horizontal, 4)
        }
    }
    
    private func successView(text: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "checkmark.circle.fill")
                .resizable()
                .scaledToFit()
                .frame(height: 40)
                .foregroundColor(.green)
            
            Text("Transcription complete!")
                .font(.headline)
                .foregroundColor(.white)
            
            if !text.isEmpty {
                Text("\"\(text)\"")
                    .font(.body)
                    .foregroundColor(.white.opacity(0.8))
                    .multilineTextAlignment(.center)
                    .lineLimit(3)
                    .padding(.horizontal, 8)
            }
        }
    }
    
    private func errorView(message: String) -> some View {
        VStack(spacing: 16) {
            Image(systemName: "exclamationmark.triangle.fill")
                .resizable()
                .scaledToFit()
                .frame(height: 40)
                .foregroundColor(.orange)
            
            Text("Error")
                .font(.headline)
                .foregroundColor(.white)
            
            Text(message)
                .font(.caption)
                .foregroundColor(.white.opacity(0.7))
                .multilineTextAlignment(.center)
                
            Button("Retry") {
                popupState = .idle
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 6)
            .background(Color.green.opacity(0.6))
            .foregroundColor(.white)
            .font(.system(size: 12, weight: .medium))
            .cornerRadius(8)
        }
    }

    // MARK: - Computed Properties
    
    private var titleText: String {
        switch popupState {
        case .idle:
            return "How can I help you?"
        case .recording:
            return "Listening..."
        case .transcribing:
            return "Processing..."
        case .transcribed:
            return "Review & Send"
        case .success:
            return "Got it!"
        case .error:
            return "Oops!"
        }
    }

    // MARK: - Methods
    
    private func startRecording() {
        Task {
            let success = await voiceRecorder.startRecording()
            
            await MainActor.run {
                if success {
                    popupState = .recording
                } else {
                    popupState = .error("Failed to start recording. Please check microphone permissions.")
                }
            }
        }
    }
    
    private func stopRecordingAndTranscribe() {
        guard let audioURL = voiceRecorder.stopRecording() else {
            popupState = .error("Failed to save recording")
            return
        }
        
        transcribeAudio(audioURL)
    }
    
    private func transcribeAudio(_ audioURL: URL) {
        popupState = .transcribing
        
        Task {
            do {
                let transcript = try await performSpeechRecognition(audioURL: audioURL)
                
                await MainActor.run {
                    if transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        popupState = .error("No speech detected. Please try again.")
                    } else {
                        transcribedText = transcript
                        editableText = transcript
                        popupState = .transcribed(transcript)
                    }
                }
                
                // Clean up the temporary audio file
                try? FileManager.default.removeItem(at: audioURL)
                
            } catch {
                await MainActor.run {
                    popupState = .error("Transcription failed: \(error.localizedDescription)")
                }
                
                // Clean up the temporary audio file even on error
                try? FileManager.default.removeItem(at: audioURL)
            }
        }
    }
    
    private func performSpeechRecognition(audioURL: URL) async throws -> String {
        return try await withCheckedThrowingContinuation { continuation in
            // Ensure we're on main thread for authorization
            DispatchQueue.main.async {
                // Request speech recognition authorization
                SFSpeechRecognizer.requestAuthorization { authStatus in
                    guard authStatus == .authorized else {
                        continuation.resume(throwing: NSError(domain: "SpeechRecognitionError", code: 1, userInfo: [NSLocalizedDescriptionKey: "Speech recognition not authorized"]))
                        return
                    }
                    
                    // Create speech recognizer
                    guard let recognizer = SFSpeechRecognizer() else {
                        continuation.resume(throwing: NSError(domain: "SpeechRecognitionError", code: 2, userInfo: [NSLocalizedDescriptionKey: "Speech recognizer not available"]))
                        return
                    }
                    
                    guard recognizer.isAvailable else {
                        continuation.resume(throwing: NSError(domain: "SpeechRecognitionError", code: 3, userInfo: [NSLocalizedDescriptionKey: "Speech recognizer not available"]))
                        return
                    }
                    
                    // Create recognition request
                    let request = SFSpeechURLRecognitionRequest(url: audioURL)
                    request.shouldReportPartialResults = false
                    request.requiresOnDeviceRecognition = false // Allow network if needed
                    
                    // Add timeout for recognition
                    var hasCompleted = false
                    let timeout = DispatchTime.now() + .seconds(10)
                    
                    // Perform recognition
                    let task = recognizer.recognitionTask(with: request) { result, error in
                        guard !hasCompleted else { return }
                        
                        if let error = error {
                            hasCompleted = true
                            continuation.resume(throwing: error)
                            return
                        }
                        
                        if let result = result, result.isFinal {
                            hasCompleted = true
                            let transcript = result.bestTranscription.formattedString
                            continuation.resume(returning: transcript)
                        }
                    }
                    
                    // Set up timeout
                    DispatchQueue.main.asyncAfter(deadline: timeout) {
                        if !hasCompleted {
                            hasCompleted = true
                            task.cancel()
                            continuation.resume(throwing: NSError(domain: "SpeechRecognitionError", code: 4, userInfo: [NSLocalizedDescriptionKey: "Speech recognition timed out"]))
                        }
                    }
                }
            }
        }
    }
    
    private func sendToAPI() {
        guard !editableText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        
        isLoading = true
        
        Task {
            do {
                let response = try await sendMessageToAPI(text: editableText)
                
                await MainActor.run {
                    // Check if view is still active before updating UI
                    guard isViewActive else {
                        print("⚠️ API response ignored - view is no longer active")
                        return
                    }
                    
                    isLoading = false
                    apiResponse = response
                    popupState = .success(response)
                    
                    // Show success for 2 seconds then navigate to chat
                    DispatchQueue.main.asyncAfter(deadline: .now() + 2.0) {
                        // Ensure we're still in a valid state before navigating
                        if popupState == .success(response) && isViewActive {
                            navigateToChatWithResponse(originalMessage: editableText, response: response)
                        }
                    }
                }
            } catch {
                await MainActor.run {
                    isLoading = false
                    popupState = .error("Failed to send message: \(error.localizedDescription)")
                }
            }
        }
    }
    
    private func sendMessageToAPI(text: String) async throws -> String {
        // Use the existing OmiAPIClient to send the message
        var fullResponse = ""
        
        do {
            // Ensure authentication is synced before API call
            await MainActor.run {
                AuthBridge.shared.syncFromFlutterApp()
            }
            
            // Check if configuration is valid
            guard OmiConfig.isConfigured() else {
                throw NSError(domain: "VoiceAssistantError", code: 1, userInfo: [NSLocalizedDescriptionKey: "Authentication required. Please sign in to Omi."])
            }
            
            // Create async stream to collect the response
            let stream = OmiAPIClient.shared.sendMessage(text: text, appId: nil, fileIds: [])
            
            // Collect response chunks with timeout
            let timeoutDuration: TimeInterval = 30.0 // 30 second timeout
            let startTime = Date()
            
            for try await chunk in stream {
                // Check for timeout
                if Date().timeIntervalSince(startTime) > timeoutDuration {
                    throw NSError(domain: "VoiceAssistantError", code: 2, userInfo: [NSLocalizedDescriptionKey: "Request timed out"])
                }
                
                fullResponse += chunk.text
                
                // Yield to prevent blocking
                if Task.isCancelled {
                    throw CancellationError()
                }
            }
            
            return fullResponse.isEmpty ? "I received your message but couldn't generate a response." : fullResponse
            
        } catch {
            // Log the error for debugging
            print("❌ API Error: \(error.localizedDescription)")
            throw error
        }
    }
    
    private func navigateToChatWithResponse(originalMessage: String, response: String) {
        // Ensure we're on the main thread
        guard Thread.isMainThread else {
            DispatchQueue.main.async {
                self.navigateToChatWithResponse(originalMessage: originalMessage, response: response)
            }
            return
        }
        
        // Check if view is still active
        guard isViewActive else {
            print("⚠️ Navigation cancelled - view is no longer active")
            return
        }
        
        // Double-check that we're still in a valid state
        guard case .success = popupState else {
            print("⚠️ Navigation cancelled - popup state changed")
            return
        }
        
        print("🔄 Preparing to navigate to chat with message: \(originalMessage)")
        
        // Instead of immediate navigation, let's delay and be more cautious
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) {
            // Final safety check before navigation
            guard self.isViewActive else {
                print("⚠️ Late navigation cancelled - view not active")
                return
            }
            
            if case .success = self.popupState {
                print("🔄 Actually navigating to chat now")
                
                // Use the most gentle animation possible
                withAnimation(.easeInOut(duration: 0.8)) {
                    self.isChatVisible = true
                }
            } else {
                print("⚠️ Late navigation cancelled - state changed")
            }
        }
        
        // TODO: Pass both the original message and response to ChatView
        // This will need proper implementation when we integrate message passing
    }
    
    private func formatDuration(_ duration: TimeInterval) -> String {
        let minutes = Int(duration) / 60
        let seconds = Int(duration) % 60
        return String(format: "%02d:%02d", minutes, seconds)
    }
}

// Safe wrapper for ChatView to prevent crashes during initialization
struct SafeChatView: View {
    @State private var isReady = false
    @State private var hasError = false
    @State private var errorMessage = ""
    
    var body: some View {
        ZStack {
            Color(.windowBackgroundColor)
                .ignoresSafeArea()
            
            if hasError {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .resizable()
                        .scaledToFit()
                        .frame(height: 40)
                        .foregroundColor(.orange)
                    
                    Text("Chat Loading Error")
                        .font(.headline)
                        .foregroundColor(.white)
                    
                    Text(errorMessage)
                        .font(.caption)
                        .foregroundColor(.white.opacity(0.7))
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 20)
                    
                    Button("Retry") {
                        attemptChatLoad()
                    }
                    .padding(.horizontal, 16)
                    .padding(.vertical, 8)
                    .background(Color.purple)
                    .foregroundColor(.white)
                    .cornerRadius(8)
                }
                .padding(24)
            } else if isReady {
                ChatView()
                    .transition(.opacity)
                    .animation(.easeInOut(duration: 0.3), value: isReady)
            } else {
                VStack(spacing: 16) {
                    ProgressView()
                        .progressViewStyle(CircularProgressViewStyle(tint: .purple))
                        .scaleEffect(1.5)
                    
                    Text("Loading chat...")
                        .font(.headline)
                        .foregroundColor(.white)
                }
                .padding(24)
            }
        }
        .onAppear {
            attemptChatLoad()
        }
    }
    
    private func attemptChatLoad() {
        hasError = false
        isReady = false
        
        // Add a small delay to ensure the popup animation completes
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) {
            do {
                // Try to safely initialize required components
                let _ = OmiConfig.isConfigured()
                let _ = AuthBridge.shared.getAuthStatus()
                
                // If we get here without crashing, we can safely show ChatView
                withAnimation(.easeInOut(duration: 0.3)) {
                    isReady = true
                }
                
                print("✅ SafeChatView: Successfully loaded ChatView")
                
            } catch {
                print("❌ SafeChatView: Failed to load ChatView - \(error.localizedDescription)")
                hasError = true
                errorMessage = "Failed to initialize chat: \(error.localizedDescription)"
            }
        }
    }
}

#if DEBUG
struct VoiceAssistantPopup_Previews: PreviewProvider {
    static var previews: some View {
        VoiceAssistantPopup()
            .frame(width: 420, height: 300)
            .preferredColorScheme(.dark)
    }
}
#endif
