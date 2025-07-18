import SwiftUI
import Combine
import AVFoundation

// Voice popup state for managing different UI states
enum VoicePopupState: Equatable {
    case idle
    case recording
    case transcribing
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

    var body: some View {
        ZStack {
            Color(.windowBackgroundColor)
                .ignoresSafeArea()

            if isChatVisible {
                ChatView()
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
            popupState = .idle
        }
        .onDisappear {
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
                // For now, we'll create a placeholder transcription since the OmiAPIClient 
                // doesn't have a transcribeAudio method yet
                let transcript = await simulateTranscription(audioURL)
                
                await MainActor.run {
                    if transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        popupState = .error("No speech detected. Please try again.")
                    } else {
                        transcribedText = transcript
                        popupState = .success(transcript)
                        
                        // Navigate to chat after showing success for 1.5 seconds
                        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) {
                            navigateToChatWithText(transcript)
                        }
                    }
                }
                
                // Clean up the temporary audio file
                try? FileManager.default.removeItem(at: audioURL)
                
            } catch {
                await MainActor.run {
                    popupState = .error("Transcription failed. Please try again.")
                }
            }
        }
    }
    
    // Placeholder transcription method - replace with actual API call when available
    private func simulateTranscription(_ audioURL: URL) async -> String {
        // Simulate processing time
        try? await Task.sleep(nanoseconds: 1_500_000_000) // 1.5 seconds
        
        // For now, return a placeholder text. In the future, this should call
        // the actual transcription API or use a local transcription library
        return "This is a placeholder transcription. Voice recording was successful!"
    }
    
    private func navigateToChatWithText(_ text: String) {
        withAnimation(.easeInOut(duration: 0.3)) {
            isChatVisible = true
        }
        
        // TODO: Pass the transcribed text to the chat view
        // This will need to be implemented when we integrate with ChatView
    }
    
    private func formatDuration(_ duration: TimeInterval) -> String {
        let minutes = Int(duration) / 60
        let seconds = Int(duration) % 60
        return String(format: "%02d:%02d", minutes, seconds)
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
