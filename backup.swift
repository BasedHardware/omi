import SwiftUI
import Combine
import AVFoundation
import Speech
import Accelerate

// MARK: - Shared Chat Models
struct ChatMessage: Identifiable, Equatable {
    let id = UUID()
    let content: String
    let isUser: Bool
    let timestamp = Date()
}

// Enhanced voice popup state for managing different UI states including chat mode
enum VoicePopupState: Equatable {
    case idle
    case recording
    case transcribing
    case transcribed(String)
    case chatMode  // New state for chat interface
    case error(String)
}

// MARK: - Working Audio Waveform Monitor
class AudioWaveformMonitor: ObservableObject {
    @Published var magnitudes: [Float] = []
    @Published var volumeHistory: [Float] = Array(repeating: 0.0, count: 200)  // Increased to store more raw samples
    @Published var averagedVolumeHistory: [Float] = Array(repeating: 0.0, count: 40)  // Averaged data for display
    @Published var hasPermission = false
    @Published var isRunning = false
    @Published var errorMessage: String?

    private let engine = AVAudioEngine()
    private var fftSetup: vDSP_DFT_Setup?
    private var previousMagnitudes: [Float] = []

    private var isTestMode = false
    private var testTimer: Timer?

    struct Constants {
        static let sampleAmount = 30  // Reduced for compact display
        static let bufferSize = 1024
        static let sampleRate: Double = 44100
    }

    init() {
        checkPermission()
        magnitudes = [Float](repeating: 0, count: Constants.sampleAmount)
        previousMagnitudes = [Float](repeating: 0, count: Constants.sampleAmount)
    }

    func checkPermission() {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized:
            hasPermission = true
        case .notDetermined:
            AVCaptureDevice.requestAccess(for: .audio) { [weak self] granted in
                DispatchQueue.main.async {
                    self?.hasPermission = granted
                }
            }
        case .denied, .restricted:
            hasPermission = false
            errorMessage = "Microphone access denied. Please enable it in System Preferences."
        @unknown default:
            hasPermission = false
            errorMessage = "Unknown microphone permission status."
        }
    }

    func start() {
        guard !isRunning else { return }
        guard hasPermission else {
            errorMessage = "Cannot start audio monitoring without microphone permission."
            return
        }

        if isTestMode {
            testTimer?.invalidate()
            testTimer = nil
            isTestMode = false
        }

        do {
            let inputNode = engine.inputNode
            let format = inputNode.inputFormat(forBus: 0)

            guard format.sampleRate > 0 else {
                throw NSError(domain: "AudioError", code: -1, userInfo: [NSLocalizedDescriptionKey: "Invalid audio format"])
            }

            fftSetup = vDSP_DFT_zop_CreateSetup(nil, UInt(Constants.bufferSize), .FORWARD)

            inputNode.removeTap(onBus: 0)

            inputNode.installTap(onBus: 0, bufferSize: AVAudioFrameCount(Constants.bufferSize), format: format) { [weak self] buffer, _ in
                guard let self = self else { return }
                self.processAudioBuffer(buffer)
            }

            engine.prepare()
            try engine.start()
            isRunning = true
            errorMessage = nil
            print("✅ Waveform engine started")

        } catch {
            errorMessage = "Failed to start audio engine: \(error.localizedDescription)"
            print("❌ Waveform audio engine error: \(error)")
        }
    }

    private func processAudioBuffer(_ buffer: AVAudioPCMBuffer) {
        guard let channelData = buffer.floatChannelData?[0] else { return }
        let frameLength = Int(buffer.frameLength)
        guard frameLength > 0 else { return }

        let channelDataArray = Array(UnsafeBufferPointer(start: channelData, count: frameLength))

        // Enhanced RMS calculation with peak detection
        let rms = sqrt(channelDataArray.reduce(0) { $0 + $1 * $1 } / Float(frameLength))
        
        // Peak detection for more dynamic response
        let peak = channelDataArray.max(by: { abs($0) < abs($1) }) ?? 0.0
        let enhancedVolume = max(rms, abs(peak) * 0.3)  // Combine RMS with peak for better dynamics
        
        DispatchQueue.main.async {
            self.volumeHistory.append(enhancedVolume)
            if self.volumeHistory.count > 200 {  // Keep 200 raw samples
                self.volumeHistory.removeFirst()
            }
            
            // Calculate enhanced averaged volumes with smooth animation
            withAnimation(.easeOut(duration: 0.1)) {
                self.updateAveragedVolumeHistory()
            }
        }

        // Enhanced sensitivity threshold for better responsiveness
        guard enhancedVolume > 0.0003 else { return }  // Further reduced threshold for maximum sensitivity

        let newMagnitudes = performFFT(samples: channelDataArray)
        DispatchQueue.main.async {
            self.magnitudes = self.smoothMagnitudes(newMagnitudes)
        }
    }

    private func performFFT(samples: [Float]) -> [Float] {
        guard let fftSetup = fftSetup else { return [] }

        let bufferSize = Constants.bufferSize
        let sampleAmount = Constants.sampleAmount

        var paddedSamples = samples
        if paddedSamples.count < bufferSize {
            paddedSamples += [Float](repeating: 0, count: bufferSize - paddedSamples.count)
        } else if paddedSamples.count > bufferSize {
            paddedSamples = Array(paddedSamples.prefix(bufferSize))
        }

        for i in 0..<paddedSamples.count {
            let window = 0.5 * (1.0 - cos(2.0 * .pi * Float(i) / Float(paddedSamples.count - 1)))
            paddedSamples[i] *= Float(window)
        }

        var realIn = paddedSamples
        var imagIn = [Float](repeating: 0, count: bufferSize)
        var realOut = [Float](repeating: 0, count: bufferSize)
        var imagOut = [Float](repeating: 0, count: bufferSize)

        vDSP_DFT_Execute(fftSetup, &realIn, &imagIn, &realOut, &imagOut)

        var magnitudes = [Float](repeating: 0, count: sampleAmount)
        let binSize = bufferSize / (2 * sampleAmount)

        for i in 0..<sampleAmount {
            var sum: Float = 0
            let start = i * binSize
            let end = min(start + binSize, bufferSize / 2)
            for j in start..<end {
                sum += sqrt(realOut[j] * realOut[j] + imagOut[j] * imagOut[j])
            }
            if binSize > 0 {
                magnitudes[i] = sum / Float(binSize)
            }
        }

        // Increased sensitivity: higher multiplier and lower max clamp for more dynamic range
        for i in 0..<magnitudes.count {
            magnitudes[i] = log10(magnitudes[i] + 1) * 60  // Increased from 40 to 60
            magnitudes[i] = max(0, min(120, magnitudes[i]))  // Reduced max from 150 to 120
        }

        return magnitudes
    }

    private func smoothMagnitudes(_ newMagnitudes: [Float]) -> [Float] {
        let factor: Float = 0.6  // Increased responsiveness for more dynamic waveform
        var smoothed = [Float](repeating: 0, count: Constants.sampleAmount)

        for i in 0..<min(newMagnitudes.count, Constants.sampleAmount) {
            let prev = i < previousMagnitudes.count ? previousMagnitudes[i] : 0
            // Enhanced smoothing with slight overshoot for more natural motion
            let baseSmooth = prev * (1 - factor) + newMagnitudes[i] * factor
            let overshoot = (newMagnitudes[i] - prev) * 0.1  // Small overshoot for natural feel
            smoothed[i] = max(0, baseSmooth + overshoot)
        }

        previousMagnitudes = smoothed
        return smoothed
    }
    
    // MARK: - Fixed-Size Scrolling Waveform Logic
    private func updateAveragedVolumeHistory() {
        let latestVolume = volumeHistory.last ?? 0.0
        
        // Apply some smoothing to the latest volume for better visual flow
        let smoothingFactor: Float = 0.7
        let smoothedVolume = latestVolume * smoothingFactor + (averagedVolumeHistory.last ?? 0.0) * (1.0 - smoothingFactor)
        
        // Shift array left, add new sample at end
        if averagedVolumeHistory.count >= 40 {
            averagedVolumeHistory.removeFirst()
        }
        averagedVolumeHistory.append(smoothedVolume)
    }

    func stop() {
        guard isRunning else { return }

        if isTestMode {
            testTimer?.invalidate()
            testTimer = nil
            isTestMode = false
        } else {
            engine.inputNode.removeTap(onBus: 0)
            engine.stop()
        }

        isRunning = false
        fftSetup.map { vDSP_DFT_DestroySetup($0) }
        fftSetup = nil

        magnitudes = [Float](repeating: 0, count: Constants.sampleAmount)
        previousMagnitudes = magnitudes
    }
}

// MARK: - Centered Bar Waveform View for Voice Recording
struct CenteredBarWaveformView: View {
    @ObservedObject var audioMonitor: AudioWaveformMonitor

    var body: some View {
        HStack(spacing: 2) {
            ForEach(Array(audioMonitor.averagedVolumeHistory.enumerated()), id: \.offset) { index, value in
                let height = max(4, min(200, CGFloat(value) * 200))
                RoundedRectangle(cornerRadius: 1)
                    .fill(LinearGradient(
                        gradient: Gradient(colors: [Color.purple.opacity(0.8), Color.blue.opacity(0.9)]),
                        startPoint: .bottom,
                        endPoint: .top
                    ))
                    .frame(width: 3, height: height)
                    .animation(.easeOut(duration: 0.1), value: value)
            }
        }
        .frame(height: 120)
        .background(Color.clear)
    }
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

// MARK: - Chat Message View
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
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(Color.white.opacity(0.2), lineWidth: 1)
                    )
            } else {
                Text(message.content)
                    .font(.system(size: 14))
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 16)
                            .fill(Color.gray.opacity(0.2))
                    )
                    .foregroundColor(.white)
                    .overlay(
                        RoundedRectangle(cornerRadius: 16)
                            .stroke(Color.white.opacity(0.1), lineWidth: 1)
                    )
                Spacer()
            }
        }
        .padding(.horizontal, 8)
    }
}

struct VoiceAssistantPopup: View {
    @StateObject private var voiceRecorder = SimpleVoiceRecorder()
    @StateObject private var waveformMonitor = AudioWaveformMonitor()
    @State private var popupState: VoicePopupState = .idle
    @State private var transcribedText = ""
    @State private var editableText = ""
    @State private var isLoading = false
    @State private var isViewActive = true
    
    // Chat functionality
    @State private var messages: [ChatMessage] = []
    @State private var inputText = ""
    @State private var isRecording = false
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
                    case .chatMode:
                        chatView
                    case .error(let message):
                        errorView(message: message)
                    }
                }
                .transition(.opacity.combined(with: .scale))
                .animation(.easeInOut(duration: 0.3), value: popupState)

                // "Type Instead" Button - only show in non-chat modes
                if popupState != .chatMode {
                    Button(action: {
                        withAnimation(.easeInOut(duration: 0.3)) {
                            popupState = .chatMode
                            initializeChatMode()
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
            }
            .padding(24)
            .frame(width: 420)
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
        .onAppear {
            isViewActive = true
            popupState = .idle
            initializeAuthentication()
            
            // Auto-start recording when popup appears for seamless voice interaction
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.05) {
                if popupState == .idle {
                    startRecording()
                }
            }
        }
        .onDisappear {
            isViewActive = false
            voiceRecorder.cancelRecording()
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

    // MARK: - State Views
    
    private var idleView: some View {
        VStack(spacing: 16) {
            Text("Starting recording... Click to start manually")
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
            // Live waveform visualization
            CenteredBarWaveformView(audioMonitor: waveformMonitor)
                .onTapGesture {
                    stopRecordingAndTranscribe()
                }
            
            VStack(spacing: 4) {
                Text("Recording...")
                    .font(.headline)
                    .foregroundColor(.white)
                
                Text(formatDuration(voiceRecorder.recordingDuration))
                    .font(.caption)
                    .foregroundColor(.white.opacity(0.7))
                    .monospacedDigit()
                
                Text("Tap waveform to stop")
                    .font(.caption2)
                    .foregroundColor(.white.opacity(0.8))
                    .padding(.horizontal, 12)
                    .padding(.vertical, 4)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color.white.opacity(0.1))
                    )
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
                        sendToAPIAndEnterChatMode()
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
                    .buttonStyle(PlainButtonStyle())
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
    
    // MARK: - New Chat View
    
    private var chatView: some View {
        VStack(spacing: 0) {
            // Chat messages
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
                .frame(maxHeight: 200)
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

            // Input field - simplified without unnecessary buttons
            HStack(spacing: 12) {
                TextField("Ask anything", text: $inputText)
                    .textFieldStyle(PlainTextFieldStyle())
                    .foregroundColor(.white)
                    .font(.system(size: 14))
                    .onSubmit {
                        handleSendMessage()
                    }

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
                    
                    // Send button
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
        case .chatMode:
            return "Chat with Omi"
        case .error:
            return "Oops!"
        }
    }

    // MARK: - Methods
    
    private func initializeAuthentication() {
        DispatchQueue.main.async {
            do {
                AuthBridge.shared.syncFromFlutterApp()
                self.isInitialized = true
                self.checkOmiConnection()
            } catch {
                print("❌ Failed to initialize authentication")
                self.errorMessage = "Authentication initialization failed"
                self.isInitialized = false
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
    
    private func initializeChatMode() {
        showWelcomeMessage = true
        // Load initial messages if any exist
        loadInitialMessages()
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
                    print("⚠️ Authentication required for loading messages")
                    errorMessage = "Please sign in to Omi to view messages"
                    showWelcomeMessage = true
                }
            } catch {
                await MainActor.run {
                    print("❌ Failed to load messages: \(type(of: error))")
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
                    print("❌ Failed to get initial message: \(type(of: error))")
                    // Keep welcome message
                }
            }
        }
    }
    
    // MARK: - Voice Recording Methods
    
    private func startRecording() {
        Task {
            let success = await voiceRecorder.startRecording()
            
            await MainActor.run {
                if success {
                    popupState = .recording
                    // Start waveform monitoring
                    waveformMonitor.start()
                } else {
                    popupState = .error("Failed to start recording. Please check microphone permissions.")
                }
            }
        }
    }
    
    private func stopRecordingAndTranscribe() {
        // Stop waveform monitoring
        waveformMonitor.stop()
        
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
    
    // Modified to transition to chat mode after first message
    private func sendToAPIAndEnterChatMode() {
        guard !editableText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        
        isLoading = true
        
        // Add user message to chat
        let userMessage = ChatMessage(content: editableText, isUser: true)
        messages.append(userMessage)
        messageSyncManager.syncMessageToFlutter(userMessage)
        
        let messageToSend = editableText
        editableText = ""
        
        Task {
            do {
                let response = try await sendMessageToAPI(text: messageToSend)
                
                await MainActor.run {
                    guard isViewActive else { return }
                    
                    isLoading = false
                    
                    // Add AI response to chat
                    let aiMessage = ChatMessage(content: response, isUser: false)
                    messages.append(aiMessage)
                    messageSyncManager.syncMessageToFlutter(aiMessage)
                    
                    // Transition to chat mode
                    showWelcomeMessage = false
                    popupState = .chatMode
                }
            } catch {
                await MainActor.run {
                    isLoading = false
                    popupState = .error("Failed to send message: \(error.localizedDescription)")
                }
            }
        }
    }
    
    // Chat mode message handling
    private func handleSendMessage() {
        guard !inputText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        guard OmiConfig.isConfigured() else {
            popupState = .error("Please sign in to Omi to send messages")
            return
        }

        if showWelcomeMessage {
            showWelcomeMessage = false
        }

        let userMessage = ChatMessage(content: inputText, isUser: true)
        messages.append(userMessage)
        messageSyncManager.syncMessageToFlutter(userMessage)

        let messageToSend = inputText
        inputText = ""
        isLoading = true

        sendToOmiChat(message: messageToSend)
    }
    
    private func sendToOmiChat(message: String) {
        print("Sending to Omi: \(message)")
        
        Task {
            do {
                var responseText = ""
                
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
                            responseText += chunk.text ?? ""
                            if let lastIndex = messages.indices.last {
                                messages[lastIndex] = ChatMessage(content: responseText, isUser: false)
                            }
                        case "done":
                            // Final message received
                            break
                        case "error":
                            // Handle error
                            if let lastIndex = messages.indices.last {
                                messages[lastIndex] = ChatMessage(content: "Error processing message", isUser: false)
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
            startVoiceRecordingInChatMode()
        } else {
            stopVoiceRecordingInChatMode()
        }
    }

    private func startVoiceRecordingInChatMode() {
        print("Voice recording started in chat mode")
        // TODO: Implement voice recording for chat mode using the same voiceRecorder
        // This would use the same voice recording logic but directly add to chat
        Task {
            let success = await voiceRecorder.startRecording()
            
            await MainActor.run {
                if success {
                    // Start waveform monitoring for chat mode too
                    waveformMonitor.start()
                } else {
                    isRecording = false
                    // Could show a temporary error state
                }
            }
        }
    }

    private func stopVoiceRecordingInChatMode() {
        print("Voice recording stopped in chat mode")
        isRecording = false
        
        // Stop waveform monitoring
        waveformMonitor.stop()
        
        guard let audioURL = voiceRecorder.stopRecording() else {
            print("Failed to get audio recording")
            return
        }
        
        // Transcribe and add to input text
        Task {
            do {
                let transcript = try await performSpeechRecognition(audioURL: audioURL)
                
                await MainActor.run {
                    if !transcript.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                        inputText = transcript
                    }
                }
                
                try? FileManager.default.removeItem(at: audioURL)
                
            } catch {
                print("Failed to transcribe audio in chat mode: \(error)")
                try? FileManager.default.removeItem(at: audioURL)
            }
        }
    }
    
    // MARK: - API Communication
    
    private func sendMessageToAPI(text: String) async throws -> String {
        // Use the existing OmiAPIClient to send the message
        var fullResponse = ""
        
        do {
            // Ensure authentication is synced before API call with proper error handling
            await MainActor.run {
                do {
                    AuthBridge.shared.syncFromFlutterApp()
                } catch {
                    print("❌ Failed to sync authentication before API call")
                }
            }
            
            // Check if configuration is valid
            guard OmiConfig.isConfigured() else {
                throw NSError(domain: "VoiceAssistantError", code: 1, userInfo: [NSLocalizedDescriptionKey: "Authentication required. Please sign in to Omi."])
            }
            
            // Create async stream to collect the response
            let stream = OmiAPIClient.shared.sendMessage(text: text, appId: OmiConfig.selectedAppId, fileIds: [])
            
            // Collect response chunks with timeout
            let timeoutDuration: TimeInterval = 30.0 // 30 second timeout
            let startTime = Date()
            
            for try await chunk in stream {
                // Check for timeout
                if Date().timeIntervalSince(startTime) > timeoutDuration {
                    throw NSError(domain: "VoiceAssistantError", code: 2, userInfo: [NSLocalizedDescriptionKey: "Request timed out"])
                }
                
                fullResponse += chunk.text ?? ""
                
                // Yield to prevent blocking
                if Task.isCancelled {
                    throw CancellationError()
                }
            }
            
            return fullResponse.isEmpty ? "I received your message but couldn't generate a response." : fullResponse
            
        } catch {
            // Log the error for debugging without exposing sensitive information
            print("❌ API Error: \(type(of: error))")
            throw error
        }
    }
    
    // MARK: - Helper Methods
    
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
            .frame(width: 420, height: 400)
            .preferredColorScheme(.dark)
    }
}
#endif


