import Combine
import Foundation
import os.log

// MARK: - Audio Source Types

/// Available audio input sources for transcription
enum AudioSource: String, CaseIterable {
    case microphone = "microphone"      // Mac microphone (+ optional system audio)
    case bleDevice = "ble_device"       // BLE wearable device

    var displayName: String {
        switch self {
        case .microphone: return "Microphone"
        case .bleDevice: return "Wearable Device"
        }
    }

    var iconName: String {
        switch self {
        case .microphone: return "mic.fill"
        case .bleDevice: return "wave.3.right.circle.fill"
        }
    }
}

// MARK: - ConversationSource Extension

extension ConversationSource {
    /// Create from device type
    static func from(deviceType: DeviceType) -> ConversationSource {
        switch deviceType {
        case .omi: return .omi
        case .openglass: return .openglass
        case .bee: return .bee
        case .frame: return .frame
        case .friendPendant: return .friendCom
        case .fieldy: return .fieldy
        case .limitless: return .limitless
        case .plaud: return .plaud
        case .appleWatch: return .desktop  // Apple Watch not BLE, use desktop
        }
    }
}

// MARK: - Audio Source Manager

/// Manages audio source selection and routing for transcription
/// Coordinates between microphone capture, system audio, and BLE device audio
@MainActor
final class AudioSourceManager: ObservableObject {

    // MARK: - Singleton

    static let shared = AudioSourceManager()

    // MARK: - Published Properties

    /// Currently selected audio source
    @Published var selectedSource: AudioSource = .microphone

    /// Whether audio is currently streaming
    @Published private(set) var isStreaming = false

    /// Current audio level (0.0 - 1.0)
    @Published private(set) var audioLevel: Float = 0.0

    /// Current conversation source (for API tagging)
    @Published private(set) var conversationSource: ConversationSource = .desktop

    /// Error message if something goes wrong
    @Published var errorMessage: String?

    // MARK: - Properties

    private let logger = Logger(subsystem: "me.omi.desktop", category: "AudioSourceManager")
    private let deviceProvider = DeviceProvider.shared
    private let bleAudioService = BleAudioService.shared
    private let walService = WALService.shared

    // Audio services
    private var audioCaptureService: AudioCaptureService?
    private var systemAudioCaptureService: Any?  // SystemAudioCaptureService (macOS 14.4+)
    private var audioMixer: AudioMixer?

    // Callbacks
    private var onStereoAudio: ((Data) -> Void)?
    private var cancellables = Set<AnyCancellable>()

    // Button event handlers
    var onButtonSingleTap: (() -> Void)?
    var onButtonDoubleTap: (() -> Void)?
    var onButtonLongPress: (() -> Void)?

    private var buttonStreamTask: Task<Void, Never>?

    // MARK: - Initialization

    private init() {
        setupBindings()
    }

    private func setupBindings() {
        // Monitor BLE audio level
        bleAudioService.$audioLevel
            .receive(on: DispatchQueue.main)
            .sink { [weak self] level in
                guard let self = self, self.selectedSource == .bleDevice else { return }
                self.audioLevel = level
            }
            .store(in: &cancellables)

        // Monitor device connection state
        deviceProvider.$isConnected
            .receive(on: DispatchQueue.main)
            .sink { [weak self] isConnected in
                self?.handleDeviceConnectionChanged(isConnected: isConnected)
            }
            .store(in: &cancellables)
    }

    // MARK: - Public Methods

    /// Start streaming audio from the selected source
    /// - Parameter onAudio: Callback receiving stereo PCM audio data (16kHz, 16-bit, 2 channels)
    func startStreaming(onAudio: @escaping (Data) -> Void) async throws {
        guard !isStreaming else {
            logger.warning("Already streaming audio")
            return
        }

        self.onStereoAudio = onAudio
        errorMessage = nil

        switch selectedSource {
        case .microphone:
            try await startMicrophoneStreaming()

        case .bleDevice:
            try await startBleDeviceStreaming()
        }

        isStreaming = true
        logger.info("Started streaming from source: \(self.selectedSource.rawValue)")
    }

    /// Stop streaming audio
    func stopStreaming() {
        guard isStreaming else { return }

        switch selectedSource {
        case .microphone:
            stopMicrophoneStreaming()

        case .bleDevice:
            stopBleDeviceStreaming()
        }

        isStreaming = false
        audioLevel = 0
        onStereoAudio = nil

        logger.info("Stopped streaming")
    }

    /// Switch to a different audio source
    /// - Parameter source: The new audio source
    func switchSource(to source: AudioSource) async throws {
        guard source != selectedSource else { return }

        let wasStreaming = isStreaming

        // Stop current streaming
        if wasStreaming {
            stopStreaming()
        }

        // Update source
        selectedSource = source

        // Update conversation source
        updateConversationSource()

        // Restart streaming if it was active
        if wasStreaming, let onAudio = onStereoAudio {
            try await startStreaming(onAudio: onAudio)
        }

        logger.info("Switched to source: \(source.rawValue)")
    }

    /// Check if BLE device source is available
    var isBleDeviceAvailable: Bool {
        deviceProvider.isConnected
    }

    /// Get the name of the current audio source
    var currentSourceName: String {
        switch selectedSource {
        case .microphone:
            return AudioCaptureService.getCurrentMicrophoneName() ?? "Microphone"
        case .bleDevice:
            return deviceProvider.connectedDevice?.displayName ?? "Wearable Device"
        }
    }

    // MARK: - Microphone Streaming

    private func startMicrophoneStreaming() async throws {
        // Check permission
        guard AudioCaptureService.checkPermission() else {
            throw AudioSourceError.microphonePermissionDenied
        }

        // Initialize services
        audioCaptureService = AudioCaptureService()
        audioMixer = AudioMixer()

        // Initialize system audio if supported (macOS 14.4+)
        if #available(macOS 14.4, *) {
            systemAudioCaptureService = SystemAudioCaptureService()
        }

        // Start the audio mixer
        audioMixer?.start { [weak self] stereoData in
            self?.onStereoAudio?(stereoData)
        }

        // Start microphone capture
        try await audioCaptureService?.startCapture(
            onAudioChunk: { [weak self] audioData in
                self?.audioMixer?.setMicAudio(audioData)
            },
            onAudioLevel: { [weak self] level in
                Task { @MainActor in
                    self?.audioLevel = level
                    AudioLevelMonitor.shared.microphoneLevel = level
                }
            }
        )

        // Start system audio capture if available
        if #available(macOS 14.4, *), let systemCapture = systemAudioCaptureService as? SystemAudioCaptureService {
            try await systemCapture.startCapture(
                onAudioChunk: { [weak self] audioData in
                    self?.audioMixer?.setSystemAudio(audioData)
                },
                onAudioLevel: { level in
                    Task { @MainActor in
                        AudioLevelMonitor.shared.systemLevel = level
                    }
                }
            )
        }

        conversationSource = .desktop
    }

    private func stopMicrophoneStreaming() {
        audioCaptureService?.stopCapture()
        audioCaptureService = nil

        if #available(macOS 14.4, *) {
            (systemAudioCaptureService as? SystemAudioCaptureService)?.stopCapture()
            systemAudioCaptureService = nil
        }

        audioMixer?.stop()
        audioMixer = nil

        AudioLevelMonitor.shared.reset()
    }

    // MARK: - BLE Device Streaming

    private func startBleDeviceStreaming() async throws {
        guard deviceProvider.isConnected else {
            throw AudioSourceError.deviceNotConnected
        }

        guard let connection = deviceProvider.activeConnection else {
            throw AudioSourceError.deviceNotConnected
        }

        // Get codec for WAL recording
        let codec = await connection.getAudioCodec()

        // Start WAL recording for offline storage
        if let device = deviceProvider.connectedDevice {
            walService.startRecording(device: device.id, codec: codec.name)
        }

        // Start BLE audio processing with direct audio callback and WAL recording
        await bleAudioService.startProcessing(
            from: connection,
            transcriptionService: nil,  // We'll handle routing ourselves
            audioDataHandler: { [weak self] pcmData in
                // Convert decoded PCM mono to stereo and forward
                self?.handleBleAudio(pcmData)
            },
            rawFrameHandler: { [weak self] rawFrame in
                // Record raw encoded frame to WAL for offline storage
                self?.walService.addFrame(rawFrame, synced: true)
            }
        )

        // Update conversation source based on device type
        if let device = deviceProvider.connectedDevice {
            conversationSource = ConversationSource.from(deviceType: device.type)
        }

        // Start listening for button events
        startButtonEventListener()
    }

    private func stopBleDeviceStreaming() {
        bleAudioService.stopProcessing()
        buttonStreamTask?.cancel()
        buttonStreamTask = nil

        // Stop WAL recording
        walService.stopRecording()
    }

    /// Handle decoded mono PCM from BLE device
    private func handleBleAudio(_ monoData: Data) {
        // Convert mono to stereo (BLE device audio goes to both channels as "user")
        let stereoData = convertMonoToStereo(monoData)
        onStereoAudio?(stereoData)
    }

    /// Convert mono PCM to stereo (duplicate to both channels)
    private func convertMonoToStereo(_ monoData: Data) -> Data {
        var stereoData = Data(capacity: monoData.count * 2)

        monoData.withUnsafeBytes { bytes in
            let samples = bytes.bindMemory(to: Int16.self)
            for i in 0..<samples.count {
                var sample = samples[i]
                // Write same sample to both channels (interleaved)
                stereoData.append(Data(bytes: &sample, count: 2))
                stereoData.append(Data(bytes: &sample, count: 2))
            }
        }

        return stereoData
    }

    // MARK: - Button Events

    private func startButtonEventListener() {
        guard let buttonStream = deviceProvider.getButtonStream() else { return }

        buttonStreamTask = Task { [weak self] in
            do {
                for try await buttonState in buttonStream {
                    self?.handleButtonEvent(buttonState)
                }
            } catch {
                self?.logger.debug("Button stream ended: \(error.localizedDescription)")
            }
        }
    }

    private func handleButtonEvent(_ buttonState: [UInt8]) {
        guard !buttonState.isEmpty else { return }

        let state = buttonState[0]
        logger.debug("Button event: \(state)")

        switch state {
        case 1:
            // Single tap
            onButtonSingleTap?()

        case 2:
            // Double tap
            onButtonDoubleTap?()

        case 3:
            // Long press
            onButtonLongPress?()

        default:
            logger.debug("Unknown button state: \(state)")
        }
    }

    // MARK: - Connection Handling

    private func handleDeviceConnectionChanged(isConnected: Bool) {
        if !isConnected && selectedSource == .bleDevice && isStreaming {
            // Device disconnected while streaming - fall back to microphone
            logger.warning("BLE device disconnected during streaming, falling back to microphone")
            errorMessage = "Device disconnected. Switched to microphone."

            Task {
                try? await switchSource(to: .microphone)
            }
        }
    }

    private func updateConversationSource() {
        switch selectedSource {
        case .microphone:
            conversationSource = .desktop

        case .bleDevice:
            if let device = deviceProvider.connectedDevice {
                conversationSource = ConversationSource.from(deviceType: device.type)
            } else {
                conversationSource = .desktop
            }
        }
    }
}

// MARK: - Errors

enum AudioSourceError: LocalizedError {
    case microphonePermissionDenied
    case deviceNotConnected
    case codecNotSupported(String)
    case streamingFailed(String)

    var errorDescription: String? {
        switch self {
        case .microphonePermissionDenied:
            return "Microphone permission is required"
        case .deviceNotConnected:
            return "No wearable device connected"
        case .codecNotSupported(let codec):
            return "Audio codec not supported: \(codec)"
        case .streamingFailed(let reason):
            return "Audio streaming failed: \(reason)"
        }
    }
}

